"""Protocol 2 Lambda quota guard; only boto3 is required beyond the stdlib.

The existing pk=budget item must explicitly contain nonnegative numeric requests,
output_tokens, input_bytes and expires_at matching BIFANG_QUOTA_EXPIRES_AT. It is
never initialized or TTL-deleted. Table TTL applies only to the numeric ttl field.
Client budget rows contain the same counters plus ttl. Day expiry is UTC midnight;
lifetime expiry matches the global expiry. Minute rows contain count and ttl.

All five rows are updated atomically. No prompts or raw IPs enter this service.
create_handler injects the SDK client, clock and environment for offline tests.
Importing never imports boto3 or contacts AWS. Native token deduplication requires
identical transaction parameters; changed timestamp/configuration replays fail
closed with HTTP 503 within DynamoDB's idempotency window.
"""

from __future__ import annotations

import base64
import hmac
import json
import math
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from uuid import UUID

BUDGET_KEY = "budget"
QUOTA_PROTOCOL_VERSION = 2
RATE_TTL_SECONDS = 36 * 60 * 60
MAX_OUTPUT_TOKENS = 8192
MAX_BODY_BYTES = 32768
_TOKEN = re.compile(r"[\x21-\x7e]{1,512}")
_CLIENT_KEY = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True)
class _Limits:
    requests: int
    output_tokens: int
    input_bytes: int


@dataclass(frozen=True)
class _Settings:
    table: str
    expires_at: int
    global_budget: _Limits
    client_budget: _Limits
    daily_budget: _Limits
    per_minute: int
    client_per_minute: int


@dataclass(frozen=True)
class _Counter:
    key: str
    ttl: int | None
    expires_at: int | None = None
    limits: _Limits | None = None
    rate_limit: int | None = None
    reason: str | None = None


def _limit(env, name, default):
    value = env.get(name, str(default))
    if (
        not isinstance(value, str)
        or not value.isascii()
        or not value.isdecimal()
        or len(value) > 19
        or not 1 <= int(value) <= 2**63 - 1
    ):
        raise ValueError("Invalid quota configuration")
    return int(value)


def _limits(env, prefix, defaults):
    return _Limits(
        *(
            _limit(env, "BIFANG_QUOTA_" + prefix + suffix, default)
            for suffix, default in zip(
                ("REQUEST_LIMIT", "OUTPUT_LIMIT", "INPUT_BYTES_LIMIT"),
                defaults,
                strict=True,
            )
        )
    )


def _settings(env):
    table = env.get("BIFANG_QUOTA_TABLE", "")
    if not re.fullmatch(r"[A-Za-z0-9_.-]{3,255}", table):
        raise ValueError("Invalid quota configuration")
    expiry = datetime.fromisoformat(env.get("BIFANG_QUOTA_EXPIRES_AT", ""))
    if expiry.tzinfo is None or expiry.utcoffset() != timedelta(0) or expiry.microsecond:
        raise ValueError("Invalid quota configuration")
    return _Settings(
        table,
        int(expiry.timestamp()),
        _limits(env, "", (1000, 4000000, 16777216)),
        _limits(env, "CLIENT_", (250, 1000000, 4194304)),
        _limits(env, "CLIENT_DAILY_", (100, 262144, 2097152)),
        _limit(env, "BIFANG_QUOTA_PER_MINUTE", 60),
        _limit(env, "BIFANG_QUOTA_CLIENT_PER_MINUTE", 10),
    )


def _reply(status, *, retry_after=None, reason=None, reset_at=None):
    headers = {"content-type": "application/json", "cache-control": "no-store"}
    body = {"allowed": status == 200}
    if retry_after is not None:
        headers["retry-after"] = str(retry_after)
    if reason is not None:
        body["reason"] = reason
    if reset_at is not None:
        body["reset_at"] = reset_at
    return {
        "statusCode": status,
        "headers": headers,
        "body": json.dumps(body, separators=(",", ":")),
    }


def _budget_reply(reason, now):
    return _reply(
        403,
        reason=reason,
        reset_at=(now // 86400 + 1) * 86400 if reason == "client_daily_budget" else None,
    )


def _header(event, name):
    headers = event.get("headers", {})
    if not isinstance(headers, dict):
        return ""
    values = [
        value for key, value in headers.items() if isinstance(key, str) and key.lower() == name
    ]
    return values[0] if len(values) == 1 and isinstance(values[0], str) else ""


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON field")
        result[key] = value
    return result


def _payload(event):
    if event.get("requestContext", {}).get("http", {}).get("method") != "POST" or _header(
        event, "x-bifang-quota-protocol"
    ) != str(QUOTA_PROTOCOL_VERSION):
        raise ValueError("Invalid quota request")
    raw = event.get("body")
    encoded = event.get("isBase64Encoded", False)
    if not isinstance(raw, str) or len(raw) > 2048 or type(encoded) is not bool:
        raise ValueError("Invalid quota request")
    raw = base64.b64decode(raw, validate=True) if encoded else raw.encode()
    if not 1 <= len(raw) <= 1024:
        raise ValueError("Invalid quota request")
    value = json.loads(raw, object_pairs_hook=_unique_object)
    if type(value) is not dict or set(value) != {
        "request_id",
        "client_key",
        "output_tokens",
        "body_bytes",
    }:
        raise ValueError("Invalid quota request")
    request_id, client_key = value["request_id"], value["client_key"]
    if (
        not isinstance(request_id, str)
        or len(request_id) != 36
        or str(UUID(request_id)) != request_id
        or not isinstance(client_key, str)
        or not _CLIENT_KEY.fullmatch(client_key)
    ):
        raise ValueError("Invalid quota request")
    if (
        type(value["output_tokens"]) is not int
        or not 1 <= value["output_tokens"] <= MAX_OUTPUT_TOKENS
        or type(value["body_bytes"]) is not int
        or not 1 <= value["body_bytes"] <= MAX_BODY_BYTES
    ):
        raise ValueError("Invalid quota request")
    return request_id, client_key, value["output_tokens"], value["body_bytes"]


def _rows(settings, now, client_key):
    minute, day = now // 60, now // 86400
    minute_ttl, day_end = minute * 60 + RATE_TTL_SECONDS, (day + 1) * 86400
    return (
        _Counter(
            BUDGET_KEY, None, settings.expires_at, settings.global_budget, reason="global_budget"
        ),
        _Counter(f"minute:{minute}", minute_ttl, rate_limit=settings.per_minute),
        _Counter(
            f"client:{client_key}",
            settings.expires_at + RATE_TTL_SECONDS,
            settings.expires_at,
            settings.client_budget,
            reason="client_budget",
        ),
        _Counter(
            f"client-day:{day}:{client_key}",
            day_end + RATE_TTL_SECONDS,
            day_end,
            settings.daily_budget,
            reason="client_daily_budget",
        ),
        _Counter(
            f"client-minute:{minute}:{client_key}",
            minute_ttl,
            rate_limit=settings.client_per_minute,
        ),
    )


def _number(value):
    return {"N": str(value)}


def _update(settings, now, row, output_tokens, body_bytes):
    names = {"#pk": "pk", "#ttl": "ttl"}
    values = {":one": _number(1), ":zero": _number(0), ":number": {"S": "N"}}
    if row.limits is None:
        names["#count"] = "count"
        values.update(
            {
                ":limit": _number(row.rate_limit),
                ":remaining": _number(row.rate_limit - 1),
                ":ttl": _number(row.ttl),
            }
        )
        update = (
            "SET #count = if_not_exists(#count, :zero) + :one, #ttl = if_not_exists(#ttl, :ttl)"
        )
        condition = (
            "attribute_not_exists(#pk) OR (attribute_type(#count, :number) "
            "AND #count >= :zero AND #count < :limit AND #count <= :remaining "
            "AND attribute_type(#ttl, :number) AND #ttl = :ttl)"
        )
    else:
        limits = row.limits
        names.update(
            {
                "#requests": "requests",
                "#output": "output_tokens",
                "#input": "input_bytes",
                "#expiry": "expires_at",
            }
        )
        values.update(
            {
                ":request_limit": _number(limits.requests),
                ":request_remaining": _number(limits.requests - 1),
                ":output": _number(output_tokens),
                ":input": _number(body_bytes),
                ":output_remaining": _number(limits.output_tokens - output_tokens),
                ":input_remaining": _number(limits.input_bytes - body_bytes),
                ":expiry": _number(row.expires_at),
                ":now": _number(now),
            }
        )
        condition = (
            "attribute_exists(#requests) AND attribute_type(#requests, :number) "
            "AND #requests >= :zero AND #requests < :request_limit AND #requests <= :request_remaining "
            "AND attribute_exists(#output) AND attribute_type(#output, :number) "
            "AND #output >= :zero AND #output <= :output_remaining "
            "AND attribute_exists(#input) AND attribute_type(#input, :number) "
            "AND #input >= :zero AND #input <= :input_remaining "
            "AND attribute_type(#expiry, :number) AND #expiry = :expiry AND #expiry > :now"
        )
        if row.ttl is None:
            condition = "attribute_exists(#pk) AND attribute_not_exists(#ttl) AND " + condition
            update = "SET #requests = #requests + :one, #output = #output + :output, #input = #input + :input"
        else:
            values[":ttl"] = _number(row.ttl)
            condition = (
                "attribute_not_exists(#pk) OR ("
                + condition
                + " AND attribute_type(#ttl, :number) AND #ttl = :ttl)"
            )
            update = (
                "SET #requests = if_not_exists(#requests, :zero) + :one, "
                "#output = if_not_exists(#output, :zero) + :output, "
                "#input = if_not_exists(#input, :zero) + :input, "
                "#expiry = if_not_exists(#expiry, :expiry), #ttl = if_not_exists(#ttl, :ttl)"
            )
    return {
        "Update": {
            "TableName": settings.table,
            "Key": {"pk": {"S": row.key}},
            "UpdateExpression": update,
            "ConditionExpression": condition,
            "ExpressionAttributeNames": names,
            "ExpressionAttributeValues": values,
            "ReturnValuesOnConditionCheckFailure": "ALL_OLD",
        }
    }


def _stored_number(item, name):
    value = item.get(name)
    if not isinstance(value, dict) or set(value) != {"N"} or not isinstance(value["N"], str):
        return None
    try:
        number = Decimal(value["N"])
    except InvalidOperation:
        return None
    return number if number.is_finite() and number >= 0 else None


def _valid_old_item(item, row):
    if not isinstance(item, dict) or item.get("pk") != {"S": row.key}:
        return False
    if row.ttl is None:
        if "ttl" in item:
            return False
    elif _stored_number(item, "ttl") != row.ttl:
        return False
    if row.limits is None:
        return _stored_number(item, "count") is not None
    return (
        all(
            _stored_number(item, name) is not None
            for name in ("requests", "output_tokens", "input_bytes")
        )
        and _stored_number(item, "expires_at") == row.expires_at
    )


def _failure_reply(error, rows, now):
    response = getattr(error, "response", {})
    if (
        not isinstance(response, dict)
        or response.get("Error", {}).get("Code") != "TransactionCanceledException"
    ):
        return _reply(503)
    reasons = response.get("CancellationReasons", [])
    if not isinstance(reasons, list) or len(reasons) != len(rows):
        return _reply(503)
    failed = []
    for row, reason in zip(rows, reasons, strict=True):
        if not isinstance(reason, dict):
            return _reply(503)
        code = reason.get("Code")
        if code == "ConditionalCheckFailed":
            if not _valid_old_item(reason.get("Item"), row):
                return _reply(503)
            failed.append(row.reason)
        elif code != "None":
            return _reply(503)
    for reason in ("global_budget", "client_budget", "client_daily_budget"):
        if reason in failed:
            return _budget_reply(reason, now)
    return _reply(429, retry_after=60 - now % 60) if failed else _reply(503)


def create_handler(*, dynamodb=None, clock=time.time, environ=None):
    """Inject only the SDK client; quota counters always live in DynamoDB."""
    env = os.environ if environ is None else environ

    def handle(event, context=None):
        nonlocal dynamodb
        try:
            secret = env.get("BIFANG_QUOTA_SECRET", "")
            if not isinstance(secret, str) or not _TOKEN.fullmatch(secret):
                return _reply(503)
            supplied = _header(event, "authorization") if isinstance(event, dict) else ""
            if len(supplied) > 1024 or not hmac.compare_digest(
                supplied.encode(), ("Bearer " + secret).encode()
            ):
                return _reply(401)
            settings = _settings(env)
            timestamp = clock()
            if type(timestamp) not in (int, float) or not math.isfinite(timestamp) or timestamp < 0:
                return _reply(503)
            now = int(timestamp)
            if now >= settings.expires_at:
                return _reply(403)
            request_id, client_key, output_tokens, body_bytes = _payload(event)
            rows = _rows(settings, now, client_key)
            # A new row starts at zero. Reject costs that cannot fit even an empty
            # budget before conditional initialization; existing rows are bounded
            # again by the native transaction conditions.
            for row in rows:
                if row.limits is not None and (
                    output_tokens > row.limits.output_tokens or body_bytes > row.limits.input_bytes
                ):
                    return _budget_reply(row.reason, now)
            if dynamodb is None:
                import boto3

                dynamodb = boto3.client("dynamodb")
            try:
                dynamodb.transact_write_items(
                    TransactItems=[
                        _update(settings, now, row, output_tokens, body_bytes) for row in rows
                    ],
                    ClientRequestToken=request_id,
                )
            except Exception as error:  # noqa: BLE001 - no SDK exception may escape publicly.
                return _failure_reply(error, rows, now)
            return _reply(200)
        except Exception:  # noqa: BLE001 - fail closed, including SDK creation failures.
            return _reply(503)

    return handle


handler = create_handler()
