"""Lambda Function URL quota guard; only boto3 is required beyond the stdlib.

Table hash key: pk (S). Explicitly initialize pk=budget with nonnegative numeric
requests, output_tokens, input_bytes, and expires_at (UTC epoch seconds matching
BIFANG_QUOTA_EXPIRES_AT). Never TTL the budget. Enable table TTL on `ttl` only.
Rate items are minute:<epoch // 60> with numeric count and ttl (36 hours).

create_handler injects a low-level DynamoDB client, clock and environment for
offline tests. Importing this module never imports boto3 or contacts AWS.
Native ClientRequestToken deduplication requires identical transaction parameters;
replays with a changed timestamp/bucket/configuration fail closed with HTTP 503.
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
RATE_TTL_SECONDS = 36 * 60 * 60
MAX_OUTPUT_TOKENS = 8192
MAX_BODY_BYTES = 32768
_TOKEN = re.compile(r"[\x21-\x7e]{1,512}")


@dataclass(frozen=True)
class _Settings:
    table: str
    expires_at: int
    requests: int
    output_tokens: int
    input_bytes: int
    per_minute: int


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
        _limit(env, "BIFANG_QUOTA_REQUEST_LIMIT", 1000),
        _limit(env, "BIFANG_QUOTA_OUTPUT_LIMIT", 4000000),
        _limit(env, "BIFANG_QUOTA_INPUT_BYTES_LIMIT", 16777216),
        _limit(env, "BIFANG_QUOTA_PER_MINUTE", 60),
    )


def _reply(status, retry_after=None):
    headers = {"content-type": "application/json", "cache-control": "no-store"}
    if retry_after is not None:
        headers["retry-after"] = str(retry_after)
    return {
        "statusCode": status,
        "headers": headers,
        "body": json.dumps({"allowed": status == 200}, separators=(",", ":")),
    }


def _authorized(event, secret):
    headers = event.get("headers", {})
    if not isinstance(headers, dict):
        return False
    values = [
        value
        for name, value in headers.items()
        if isinstance(name, str) and name.lower() == "authorization"
    ]
    return (
        len(values) == 1
        and isinstance(values[0], str)
        and len(values[0]) <= 1024
        and hmac.compare_digest(values[0].encode(), ("Bearer " + secret).encode())
    )


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON field")
        result[key] = value
    return result


def _payload(event):
    if event.get("requestContext", {}).get("http", {}).get("method") != "POST":
        raise ValueError("Invalid quota request")
    raw = event.get("body")
    encoded = event.get("isBase64Encoded", False)
    if not isinstance(raw, str) or len(raw) > 2048 or type(encoded) is not bool:
        raise ValueError("Invalid quota request")
    raw = base64.b64decode(raw, validate=True) if encoded else raw.encode()
    if not 1 <= len(raw) <= 1024:
        raise ValueError("Invalid quota request")
    value = json.loads(raw, object_pairs_hook=_unique_object)
    if type(value) is not dict or set(value) != {"request_id", "output_tokens", "body_bytes"}:
        raise ValueError("Invalid quota request")
    request_id = value["request_id"]
    if (
        not isinstance(request_id, str)
        or len(request_id) != 36
        or str(UUID(request_id)) != request_id
    ):
        raise ValueError("Invalid quota request")
    if (
        type(value["output_tokens"]) is not int
        or not 1 <= value["output_tokens"] <= MAX_OUTPUT_TOKENS
        or type(value["body_bytes"]) is not int
        or not 1 <= value["body_bytes"] <= MAX_BODY_BYTES
    ):
        raise ValueError("Invalid quota request")
    return request_id, value["output_tokens"], value["body_bytes"]


def _number(value):
    return {"N": str(value)}


def _transaction(settings, now, output_tokens, body_bytes):
    minute = now // 60
    return [
        {
            "Update": {
                "TableName": settings.table,
                "Key": {"pk": {"S": BUDGET_KEY}},
                "UpdateExpression": (
                    "SET #requests = #requests + :one, #output = #output + :output, "
                    "#input = #input + :input"
                ),
                "ConditionExpression": (
                    "attribute_exists(#pk) AND attribute_not_exists(#ttl) "
                    "AND attribute_exists(#requests) AND attribute_type(#requests, :number) "
                    "AND #requests >= :zero AND #requests < :request_limit "
                    "AND #requests <= :request_remaining "
                    "AND attribute_exists(#output) AND attribute_type(#output, :number) "
                    "AND #output >= :zero AND #output <= :output_remaining "
                    "AND attribute_exists(#input) AND attribute_type(#input, :number) "
                    "AND #input >= :zero AND #input <= :input_remaining "
                    "AND attribute_type(#expiry, :number) AND #expiry = :expiry AND #expiry > :now"
                ),
                "ExpressionAttributeNames": {
                    "#pk": "pk",
                    "#requests": "requests",
                    "#output": "output_tokens",
                    "#input": "input_bytes",
                    "#expiry": "expires_at",
                    "#ttl": "ttl",
                },
                "ExpressionAttributeValues": {
                    ":one": _number(1),
                    ":zero": _number(0),
                    ":number": {"S": "N"},
                    ":request_limit": _number(settings.requests),
                    ":request_remaining": _number(settings.requests - 1),
                    ":output": _number(output_tokens),
                    ":input": _number(body_bytes),
                    ":output_remaining": _number(settings.output_tokens - output_tokens),
                    ":input_remaining": _number(settings.input_bytes - body_bytes),
                    ":expiry": _number(settings.expires_at),
                    ":now": _number(now),
                },
                "ReturnValuesOnConditionCheckFailure": "ALL_OLD",
            }
        },
        {
            "Update": {
                "TableName": settings.table,
                "Key": {"pk": {"S": f"minute:{minute}"}},
                "UpdateExpression": (
                    "SET #count = if_not_exists(#count, :zero) + :one, "
                    "#ttl = if_not_exists(#ttl, :ttl)"
                ),
                "ConditionExpression": (
                    "attribute_not_exists(#pk) OR (attribute_type(#count, :number) "
                    "AND #count >= :zero AND #count < :limit "
                    "AND #count <= :remaining "
                    "AND attribute_type(#ttl, :number) AND #ttl = :ttl)"
                ),
                "ExpressionAttributeNames": {"#pk": "pk", "#count": "count", "#ttl": "ttl"},
                "ExpressionAttributeValues": {
                    ":zero": _number(0),
                    ":one": _number(1),
                    ":number": {"S": "N"},
                    ":limit": _number(settings.per_minute),
                    ":remaining": _number(settings.per_minute - 1),
                    ":ttl": _number(minute * 60 + RATE_TTL_SECONDS),
                },
                "ReturnValuesOnConditionCheckFailure": "ALL_OLD",
            }
        },
    ]


def _stored_number(item, name):
    value = item.get(name)
    if not isinstance(value, dict) or set(value) != {"N"} or not isinstance(value["N"], str):
        return None
    try:
        number = Decimal(value["N"])
    except InvalidOperation:
        return None
    return number if number.is_finite() and number >= 0 else None


def _valid_old_item(item, index, settings, now):
    if not isinstance(item, dict):
        return False
    if index == 0:
        return (
            item.get("pk") == {"S": BUDGET_KEY}
            and "ttl" not in item
            and all(
                _stored_number(item, name) is not None
                for name in ("requests", "output_tokens", "input_bytes")
            )
            and _stored_number(item, "expires_at") == settings.expires_at
        )
    return (
        item.get("pk") == {"S": f"minute:{now // 60}"}
        and _stored_number(item, "count") is not None
        and _stored_number(item, "ttl") == now // 60 * 60 + RATE_TTL_SECONDS
    )


def _failure_status(error, settings, now):
    response = getattr(error, "response", {})
    if not isinstance(response, dict):
        return 503
    if response.get("Error", {}).get("Code") != "TransactionCanceledException":
        return 503
    reasons = response.get("CancellationReasons", [])
    if not isinstance(reasons, list) or len(reasons) != 2:
        return 503
    limited = False
    for index, reason in enumerate(reasons):
        if not isinstance(reason, dict):
            return 503
        code = reason.get("Code")
        if code == "ConditionalCheckFailed":
            if not _valid_old_item(reason.get("Item"), index, settings, now):
                return 503
            limited = True
        elif code != "None":
            return 503
    return 429 if limited else 503


def create_handler(*, dynamodb=None, clock=time.time, environ=None):
    """Inject only the SDK client; quota counters always live in DynamoDB."""
    env = os.environ if environ is None else environ

    def handle(event, context=None):
        nonlocal dynamodb
        try:
            secret = env.get("BIFANG_QUOTA_SECRET", "")
            if not isinstance(secret, str) or not _TOKEN.fullmatch(secret):
                return _reply(503)
            if not isinstance(event, dict) or not _authorized(event, secret):
                return _reply(401)
            settings = _settings(env)
            timestamp = clock()
            if type(timestamp) not in (int, float) or not math.isfinite(timestamp) or timestamp < 0:
                return _reply(503)
            now = int(timestamp)
            if now >= settings.expires_at:
                return _reply(403)
            request_id, output_tokens, body_bytes = _payload(event)
            retry_after = 60 - now % 60
            if output_tokens > settings.output_tokens or body_bytes > settings.input_bytes:
                return _reply(429, retry_after)
            if dynamodb is None:
                import boto3

                dynamodb = boto3.client("dynamodb")
            try:
                dynamodb.transact_write_items(
                    TransactItems=_transaction(settings, now, output_tokens, body_bytes),
                    ClientRequestToken=request_id,
                )
            except Exception as error:  # noqa: BLE001 - no SDK exception may escape publicly.
                status = _failure_status(error, settings, now)
                return _reply(status, retry_after if status == 429 else None)
            return _reply(200)
        except Exception:  # noqa: BLE001 - fail closed, including SDK creation failures.
            return _reply(503)

    return handle


handler = create_handler()
