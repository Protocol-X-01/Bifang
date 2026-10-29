from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from .model_ids import TOKEN_FACTORY_ROLES

MAX_METADATA_BYTES = 131072


def relay_origin(value: str) -> str:
    try:
        if len(value) > 2048 or any(character.isspace() for character in value):
            raise ValueError
        parsed = urlsplit(value)
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
                or parsed.port not in (None, 443) or parsed.query or parsed.fragment
                or parsed.path.rstrip("/") not in ("", "/v1")):
            raise ValueError
        return "https://" + parsed.netloc
    except ValueError:
        raise ValueError("Use an HTTPS relay origin or /v1 URL without credentials or extra components") from None


def validate_judge_token(value: str) -> str:
    if not isinstance(value, str) or not 32 <= len(value) <= 1024 or any(
            not 33 <= ord(character) <= 126 for character in value):
        raise ValueError("Expected a strong printable judge-only token without whitespace")
    return value


def load_judge_token(path: Path) -> str:
    try:
        if path.stat().st_size > 4096:
            raise ValueError
        private = json.loads(path.read_text())
        if not isinstance(private, dict):
            raise TypeError
        return validate_judge_token(private.get("judge_token"))
    except (OSError, UnicodeError, ValueError, TypeError):
        raise ValueError("Cannot read a valid private judge-token JSON file; contents withheld") from None


async def check_access(url: str, judge_token: str, *, client: httpx.AsyncClient | None = None) -> dict:
    origin = relay_origin(url)
    token = validate_judge_token(judge_token)
    owns_client = client is None
    connection = client or httpx.AsyncClient(timeout=20, trust_env=False, follow_redirects=False)
    expected_models = frozenset(TOKEN_FACTORY_ROLES.values())
    checks = []
    requests = [
        ("health", "/health", None, 200),
        ("missing_token", "/v1/models", None, 401),
        ("wrong_token", "/v1/models", "synthetic-invalid-judge-token", 401),
        ("catalog", "/v1/models", token, 200),
        ("no_agent_route", "/sessions", token, 404),
        ("source_not_served", "/bifang/judge_relay.py", token, 404),
        ("environment_not_served", "/.env.local", token, 404),
    ]
    try:
        for name, path, credential, expected_status in requests:
            headers = {"Authorization": "Bearer " + credential} if credential else {}
            result = {"name": name, "expected_status": expected_status, "passed": False}
            try:
                async with connection.stream("GET", origin + path, headers=headers,
                                             follow_redirects=False) as response:
                    result["status"] = response.status_code
                    if response.status_code != expected_status:
                        result["failure"] = "unexpected_status"
                    else:
                        body = bytearray()
                        async for chunk in response.aiter_bytes():
                            if len(body) + len(chunk) > MAX_METADATA_BYTES:
                                raise ValueError("Metadata response too large")
                            body.extend(chunk)
                        if name == "health":
                            health = json.loads(body)
                            result["passed"] = isinstance(health, dict) and health.get("status") == "ok" and health.get("scope") == "inference-only"
                        elif name == "catalog":
                            catalog = json.loads(body)
                            rows = catalog.get("data") if isinstance(catalog, dict) else None
                            if not isinstance(rows, list) or any(not isinstance(row, dict) or not isinstance(row.get("id"), str) for row in rows):
                                raise ValueError("Invalid catalog structure")
                            identifiers = {row["id"] for row in rows}
                            result["model_count"] = len(rows)
                            result["enabled_models"] = sorted(identifiers & expected_models)
                            result["passed"] = identifiers == expected_models and len(rows) == len(expected_models)
                        else:
                            result["passed"] = True
                        if not result["passed"]:
                            result["failure"] = "unexpected_metadata"
            except httpx.HTTPError:
                result["failure"] = "transport_error"
            except (ValueError, UnicodeError):
                result["failure"] = "invalid_or_oversize_metadata"
            checks.append(result)
    finally:
        if owns_client:
            await connection.aclose()
    return {"observed_at_utc": datetime.now(UTC).isoformat(), "relay_origin": origin,
            "passed": all(check["passed"] for check in checks), "checks": checks,
            "metadata_get_requests": len(requests), "completion_requests_sent": 0,
            "redirects_followed": False,
            "scope": "Point-in-time metadata/authentication check, not live inference, balance, uptime or judge-capacity proof"}


def save_access_report(path: Path, report: dict) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as destination:
        destination.write(json.dumps(report, indent=2) + "\n")
