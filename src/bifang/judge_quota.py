"""Fail-closed client for the shared public-demo reservation service."""

from __future__ import annotations

import json
import os
import re
from urllib.parse import urlsplit
from uuid import uuid4

import httpx

MAX_OUTPUT_TOKENS = 8192
MAX_BODY_BYTES = 32768
MAX_RESPONSE_BYTES = 4096
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


def _retry_after(value: str) -> int:
    if not value.isascii() or not value.isdecimal() or len(value) > 4:
        return 60
    return min(3600, max(1, int(value)))


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

    async def reserve(self, *, output_tokens: int, body_bytes: int) -> None:
        if (
            type(output_tokens) is not int
            or not 1 <= output_tokens <= MAX_OUTPUT_TOKENS
            or type(body_bytes) is not int
            or not 1 <= body_bytes <= MAX_BODY_BYTES
        ):
            raise PublicQuotaUnavailable()
        decision = None
        try:
            decision = await self._request(output_tokens, body_bytes)
        except Exception:  # noqa: BLE001 - transport exceptions may contain credentials.
            # Raise outside the except block: upstream exceptions may contain secrets.
            decision = None
        if decision is None:
            raise PublicQuotaUnavailable()
        allowed, retry_after = decision
        if not allowed:
            raise PublicQuotaExceeded(retry_after)

    async def _request(self, output_tokens: int, body_bytes: int) -> tuple[bool, int] | None:
        request = httpx.Request(
            "POST",
            self._url,
            headers={"Authorization": "Bearer " + self._secret, "Accept-Encoding": "identity"},
            json={
                "request_id": str(uuid4()),
                "output_tokens": output_tokens,
                "body_bytes": body_bytes,
            },
            extensions={"timeout": httpx.Timeout(10).as_dict()},
        )
        response = await self._client.send(request, stream=True, auth=None, follow_redirects=False)
        try:
            if response.status_code not in (200, 429):
                return None
            if response.headers.get("content-encoding", "identity").lower() != "identity":
                return None
            body = bytearray()
            async for chunk in response.aiter_bytes(chunk_size=MAX_RESPONSE_BYTES + 1):
                body.extend(chunk)
                if len(body) > MAX_RESPONSE_BYTES:
                    return None
            payload = json.loads(body, object_pairs_hook=_unique_object)
            if type(payload) is not dict or set(payload) != {"allowed"}:
                return None
            if response.status_code == 200 and payload["allowed"] is True:
                return True, 0
            if response.status_code == 429 and payload["allowed"] is False:
                return False, _retry_after(response.headers.get("retry-after", "60"))
            return None
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
