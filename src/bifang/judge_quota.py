"""Fail-closed client for the shared public-demo reservation service."""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import os
import re
from urllib.parse import urlsplit
from uuid import uuid4

import httpx

MAX_OUTPUT_TOKENS = 8192
MAX_BODY_BYTES = 32768
MAX_RESPONSE_BYTES = 4096
QUOTA_PROTOCOL_VERSION = 2
_CLIENT_SCOPE = b"bifang-public-quota-client:v1:"
_BUDGET_REASONS = {"global_budget", "client_budget", "client_daily_budget"}
_CONFIG_ERROR = "Public quota configuration is invalid."
_HOST = re.compile(r"[a-z0-9]{32}\.lambda-url\.[a-z]{2}(?:-[a-z]+)+-[0-9]+\.on\.aws")
_TOKEN = re.compile(r"[\x21-\x7e]{1,512}")


class PublicQuotaExceeded(RuntimeError):
    def __init__(self, retry_after: int = 60):
        super().__init__("Public demo usage limit reached.")
        self.retry_after = retry_after


class PublicQuotaUnavailable(RuntimeError):
    def __init__(self):
        super().__init__("Public demo quota is unavailable.")


class PublicQuotaExhausted(RuntimeError):
    def __init__(self, reason: str, reset_at: int | None = None):
        if (
            not isinstance(reason, str)
            or reason not in _BUDGET_REASONS
            or (
                reset_at is not None
                and (
                    reason != "client_daily_budget"
                    or type(reset_at) is not int
                    or reset_at <= 0
                    or reset_at % 86400
                )
            )
        ):
            raise ValueError("Invalid quota exhaustion.")
        super().__init__("Public demo usage budget exhausted.")
        self.reason = reason
        self.reset_at = reset_at


def _configuration_valid(url: str, secret: str) -> bool:
    if not isinstance(url, str) or not isinstance(secret, str) or not _TOKEN.fullmatch(secret):
        return False
    if not url.isascii() or any(ord(char) <= 32 or ord(char) == 127 for char in url):
        return False
    try:
        parts = urlsplit(url)
    except ValueError:
        return False
    return bool(
        parts.scheme == "https"
        and _HOST.fullmatch(parts.netloc)
        and parts.path in ("", "/")
        and "?" not in url
        and "#" not in url
    )


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON field")
        result[key] = value
    return result


def _client_key(client_ip: str, secret: str) -> str:
    if (
        not isinstance(client_ip, str)
        or not client_ip.isascii()
        or any(char.isspace() for char in client_ip)
        or "%" in client_ip
        or "," in client_ip
    ):
        raise ValueError("Invalid quota client.")
    address = ipaddress.ip_address(client_ip)
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        address = address.ipv4_mapped
    network = ipaddress.ip_network((address, 32 if address.version == 4 else 64), strict=False)
    return hmac.new(
        secret.encode(), _CLIENT_SCOPE + str(network).encode(), hashlib.sha256
    ).hexdigest()


def _decision(status: int, payload, headers) -> tuple[int, str | None, int | None] | None:
    if type(payload) is not dict or type(payload.get("allowed")) is not bool:
        return None
    if status != 429 and "retry-after" in headers:
        return None
    if status == 200 and payload == {"allowed": True}:
        return 200, None, None
    if status == 429 and payload == {"allowed": False}:
        value = headers.get("retry-after", "")
        if value.isascii() and value.isdecimal() and 1 <= len(value) <= 2 and 1 <= int(value) <= 60:
            return 429, None, int(value)
    if status == 403 and payload["allowed"] is False:
        reason = payload.get("reason")
        if not isinstance(reason, str) or reason not in _BUDGET_REASONS:
            return None
        if reason == "client_daily_budget":
            reset = payload.get("reset_at")
            if (
                set(payload) == {"allowed", "reason", "reset_at"}
                and type(reset) is int
                and 0 < reset <= 253402300800
                and reset % 86400 == 0
            ):
                return 403, reason, reset
        elif set(payload) == {"allowed", "reason"}:
            return 403, reason, None
    return None


class HttpPublicQuota:
    """One attempt per reservation; an uncertain write remains consumed.

    Injected clients are caller-owned and must use a trusted transport (tests use
    MockTransport). Requests bypass their default headers, cookies, auth and params.
    """

    def __init__(self, url: str, secret: str, client: httpx.AsyncClient | None = None):
        if not _configuration_valid(url, secret):
            raise ValueError(_CONFIG_ERROR)
        self._url = url
        self._secret = secret
        self._owns_client = client is None
        self._client = (
            client
            if client is not None
            else httpx.AsyncClient(
                timeout=10,
                trust_env=False,
                follow_redirects=False,
            )
        )

    async def reserve(self, *, client_ip: str, output_tokens: int, body_bytes: int) -> None:
        if (
            type(output_tokens) is not int
            or not 1 <= output_tokens <= MAX_OUTPUT_TOKENS
            or type(body_bytes) is not int
            or not 1 <= body_bytes <= MAX_BODY_BYTES
        ):
            raise PublicQuotaUnavailable()
        decision = None
        try:
            client_key = _client_key(client_ip, self._secret)
            decision = await self._request(client_key, output_tokens, body_bytes)
        except Exception:  # noqa: BLE001 - transport exceptions may contain credentials.
            # Raise outside the except block: upstream exceptions may contain secrets.
            decision = None
        if decision is None:
            raise PublicQuotaUnavailable()
        status, reason, timing = decision
        if status == 429:
            raise PublicQuotaExceeded(timing)
        if status == 403:
            raise PublicQuotaExhausted(reason, timing)

    async def _request(
        self,
        client_key: str,
        output_tokens: int,
        body_bytes: int,
    ) -> tuple[int, str | None, int | None] | None:
        request = httpx.Request(
            "POST",
            self._url,
            headers={
                "Authorization": "Bearer " + self._secret,
                "Accept-Encoding": "identity",
                "X-Bifang-Quota-Protocol": str(QUOTA_PROTOCOL_VERSION),
            },
            json={
                "request_id": str(uuid4()),
                "client_key": client_key,
                "output_tokens": output_tokens,
                "body_bytes": body_bytes,
            },
            extensions={"timeout": httpx.Timeout(10).as_dict()},
        )
        response = await self._client.send(request, stream=True, auth=None, follow_redirects=False)
        try:
            if response.status_code not in (200, 403, 429):
                return None
            if response.headers.get("content-encoding", "identity").lower() != "identity":
                return None
            body = bytearray()
            async for chunk in response.aiter_bytes(chunk_size=MAX_RESPONSE_BYTES + 1):
                body.extend(chunk)
                if len(body) > MAX_RESPONSE_BYTES:
                    return None
            payload = json.loads(body, object_pairs_hook=_unique_object)
            return _decision(response.status_code, payload, response.headers)
        finally:
            await response.aclose()

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()


def public_quota_from_env() -> HttpPublicQuota:
    """Require both settings; construction performs no HTTP request."""
    return HttpPublicQuota(
        os.environ.get("BIFANG_PUBLIC_QUOTA_URL", ""),
        os.environ.get("BIFANG_PUBLIC_QUOTA_TOKEN", ""),
    )
