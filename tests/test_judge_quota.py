"""Synthetic SDK/HTTP tests: no AWS service, credentials or external transport."""

import asyncio
import base64
import copy
import hashlib
import hmac
import importlib.util
import json
import re
import socket
import sys
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import pytest

from bifang.judge_quota import (
    QUOTA_PROTOCOL_VERSION,
    HttpPublicQuota,
    PublicQuotaExceeded,
    PublicQuotaExhausted,
    PublicQuotaUnavailable,
    public_quota_from_env,
)

NOW = 1800000007
EXPIRY = NOW + 86400
SECRET = "synthetic-quota-secret-only"
CLIENT_IP = "192.0.2.10"
CLIENT_KEY = "c" * 64
URL = "https://" + "a" * 32 + ".lambda-url.us-east-1.on.aws/"
ENV = {
    "BIFANG_QUOTA_SECRET": SECRET,
    "BIFANG_QUOTA_TABLE": "bifang-public-demo-quota",
    "BIFANG_QUOTA_EXPIRES_AT": datetime.fromtimestamp(EXPIRY, UTC).isoformat(),
}


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("External transport is forbidden in quota tests")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)


@pytest.fixture
def lambda_module(monkeypatch):
    path = Path(__file__).parents[1] / "deploy/aws-judge-quota/handler.py"
    spec = importlib.util.spec_from_file_location("synthetic_quota_lambda", path)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    return module


def event(*, request_id=None, client_key=CLIENT_KEY, output_tokens=7, body_bytes=11):
    return {
        "headers": {"authorization": "Bearer " + SECRET, "x-bifang-quota-protocol": "2"},
        "requestContext": {"http": {"method": "POST"}},
        "body": json.dumps(
            {
                "request_id": request_id or str(uuid4()),
                "client_key": client_key,
                "output_tokens": output_tokens,
                "body_bytes": body_bytes,
            }
        ),
        "isBase64Encoded": False,
    }


def number(value):
    return {"N": str(value)}


def budget():
    return {
        "pk": {"S": "budget"},
        "requests": number(0),
        "output_tokens": number(0),
        "input_bytes": number(0),
        "expires_at": number(EXPIRY),
    }


class DDBError(Exception):
    def __init__(self, code, reasons=None):
        super().__init__("synthetic-private-upstream-detail " + SECRET)
        self.response = {"Error": {"Code": code, "Message": str(self)}}
        if reasons is not None:
            self.response["CancellationReasons"] = reasons


class Expression:
    """Evaluate actual expression syntax, rather than special-casing quota rules."""

    def __init__(self, text, operation, item):
        self.tokens = re.findall(r"[#:][A-Za-z_]+|>=|<=|[=<>(),+]|[A-Za-z_]+", text)
        self.index = 0
        self.names = operation["ExpressionAttributeNames"]
        self.values = operation["ExpressionAttributeValues"]
        self.item = item

    def take(self, expected=None):
        token = self.tokens[self.index]
        self.index += 1
        assert expected is None or token == expected
        return token

    def peek(self, token):
        return self.index < len(self.tokens) and self.tokens[self.index] == token

    def value(self):
        token = self.take()
        if token == "if_not_exists":
            self.take("(")
            existing = self.value()
            self.take(",")
            default = self.value()
            self.take(")")
            return default if existing is None else existing
        if token.startswith("#"):
            return self.item.get(self.names[token])
        return self.values[token]

    @staticmethod
    def decode(value):
        if "N" in value:
            return Decimal(value["N"])
        return value["S"]

    def atom(self):
        if self.peek("("):
            self.take("(")
            result = self.condition()
            self.take(")")
            return result
        if self.tokens[self.index].startswith("attribute_"):
            function = self.take()
            self.take("(")
            value = self.value()
            if function == "attribute_type":
                self.take(",")
                kind = self.value()["S"]
                result = value is not None and set(value) == {kind}
            else:
                assert function in ("attribute_exists", "attribute_not_exists")
                result = (value is not None) == (function == "attribute_exists")
            self.take(")")
            return result
        left, operator, right = self.value(), self.take(), self.value()
        if left is None or right is None or set(left) != set(right):
            return False
        left, right = self.decode(left), self.decode(right)
        return {
            "=": lambda: left == right,
            ">": lambda: left > right,
            "<": lambda: left < right,
            ">=": lambda: left >= right,
            "<=": lambda: left <= right,
        }[operator]()

    def conjunction(self):
        result = self.atom()
        while self.peek("AND"):
            self.take("AND")
            right = self.atom()
            result = result and right
        return result

    def condition(self):
        result = self.conjunction()
        while self.peek("OR"):
            self.take("OR")
            right = self.conjunction()
            result = result or right
        return result

    def update(self):
        self.take("SET")
        while True:
            field = self.names[self.take()]
            self.take("=")
            value = self.value()
            if self.peek("+"):
                self.take("+")
                value = number(self.decode(value) + self.decode(self.value()))
            self.item[field] = value
            if not self.peek(","):
                break
            self.take(",")
        assert self.index == len(self.tokens)


class AtomicDynamo:
    """Shared, locked, all-or-nothing five-item SDK fake with token deduplication."""

    def __init__(self):
        self.items = {"budget": budget()}
        self.tokens = {}
        self.calls = []
        self.lock = threading.Lock()

    def transact_write_items(self, *, TransactItems, ClientRequestToken):
        with self.lock:
            self.calls.append(copy.deepcopy(TransactItems))
            assert len(TransactItems) == 5
            assert len({row["Update"]["Key"]["pk"]["S"] for row in TransactItems}) == 5
            assert str(UUID(ClientRequestToken)) == ClientRequestToken
            if ClientRequestToken in self.tokens:
                if self.tokens[ClientRequestToken] != TransactItems:
                    raise DDBError("IdempotentParameterMismatchException")
                return {}
            updated, reasons = {}, []
            for action in TransactItems:
                assert set(action) == {"Update"}
                operation = action["Update"]
                assert operation["TableName"] == ENV["BIFANG_QUOTA_TABLE"]
                assert operation["ReturnValuesOnConditionCheckFailure"] == "ALL_OLD"
                text = operation["ConditionExpression"] + " " + operation["UpdateExpression"]
                assert set(re.findall(r"#[A-Za-z_]+", text)) == set(
                    operation["ExpressionAttributeNames"]
                )
                assert set(re.findall(r":[A-Za-z_]+", text)) == set(
                    operation["ExpressionAttributeValues"]
                )
                key = operation["Key"]["pk"]["S"]
                old = self.items.get(key, {})
                condition = Expression(operation["ConditionExpression"], operation, old)
                allowed = condition.condition()
                assert condition.index == len(condition.tokens)
                reasons.append(
                    {"Code": "None"}
                    if allowed
                    else {
                        "Code": "ConditionalCheckFailed",
                        "Item": copy.deepcopy(old),
                    }
                )
                if allowed:
                    item = copy.deepcopy(old or operation["Key"])
                    Expression(operation["UpdateExpression"], operation, item).update()
                    updated[key] = item
            if any(reason["Code"] != "None" for reason in reasons):
                raise DDBError("TransactionCanceledException", reasons)
            self.items.update(updated)
            self.tokens[ClientRequestToken] = copy.deepcopy(TransactItems)
            return {}


def status(response):
    body = json.loads(response["body"])
    assert body["allowed"] is (response["statusCode"] == 200)
    if response["statusCode"] == 403 and "reason" in body:
        assert body["reason"] in {"global_budget", "client_budget", "client_daily_budget"}
        assert set(body) == (
            {"allowed", "reason", "reset_at"}
            if body["reason"] == "client_daily_budget"
            else {"allowed", "reason"}
        )
    else:
        assert set(body) == {"allowed"}
    if response["statusCode"] == 429:
        assert 1 <= int(response["headers"]["retry-after"]) <= 60
    else:
        assert "retry-after" not in response["headers"]
    assert response["headers"]["cache-control"] == "no-store"
    assert SECRET not in json.dumps(response)
    return response["statusCode"]


@pytest.mark.parametrize("limiting", ["requests", "output", "input", "minute"])
def test_atomic_concurrency_across_handlers_never_exceeds_any_budget(lambda_module, limiting):
    store = AtomicDynamo()
    env = {**ENV, "BIFANG_QUOTA_PER_MINUTE": "1000"}
    env[
        {
            "requests": "BIFANG_QUOTA_REQUEST_LIMIT",
            "output": "BIFANG_QUOTA_OUTPUT_LIMIT",
            "input": "BIFANG_QUOTA_INPUT_BYTES_LIMIT",
            "minute": "BIFANG_QUOTA_PER_MINUTE",
        }[limiting]
    ] = {
        "requests": "13",
        "output": "91",
        "input": "143",
        "minute": "13",
    }[limiting]
    handlers = [
        lambda_module.create_handler(dynamodb=store, environ=env.copy(), clock=lambda: NOW)
        for _ in range(8)
    ]
    with ThreadPoolExecutor(max_workers=16) as pool:
        results = list(
            pool.map(
                lambda index: status(handlers[index % 8](event(client_key=f"{index:064x}"))),
                range(160),
            )
        )
    assert results.count(200) == 13
    assert results.count(429 if limiting == "minute" else 403) == 147
    assert store.items["budget"] == {
        **budget(),
        "requests": number(13),
        "output_tokens": number(91),
        "input_bytes": number(143),
    }
    assert store.items[f"minute:{NOW // 60}"] == {
        "pk": {"S": f"minute:{NOW // 60}"},
        "count": number(13),
        "ttl": number(NOW // 60 * 60 + 36 * 3600),
    }
    assert "ttl" not in store.items["budget"]


def test_same_request_is_idempotent_across_handlers_and_payload_changes_fail_closed(lambda_module):
    store = AtomicDynamo()
    handlers = [
        lambda_module.create_handler(dynamodb=store, environ=ENV, clock=lambda: NOW)
        for _ in range(4)
    ]
    request = event()
    with ThreadPoolExecutor(max_workers=16) as pool:
        results = list(pool.map(lambda index: status(handlers[index % 4](request)), range(80)))
    assert results == [200] * 80
    before = copy.deepcopy(store.items)
    changed = event(request_id=json.loads(request["body"])["request_id"], output_tokens=8)
    assert status(handlers[0](changed)) == 503
    assert store.items == before
    assert store.items["budget"]["requests"] == number(1)


def test_time_changed_replay_fails_closed_without_a_second_reservation(lambda_module):
    store = AtomicDynamo()
    request = event()
    for offset, expected in [(0, 200), (1, 503), (60, 503)]:
        handle = lambda_module.create_handler(
            dynamodb=store, environ=ENV, clock=lambda offset=offset: NOW + offset
        )
        assert status(handle(request)) == expected
    assert store.items["budget"]["requests"] == number(1)
    assert len(store.items) == 5


def test_rate_reset_and_redeployment_never_reset_global_counters(lambda_module):
    store = AtomicDynamo()
    env = {**ENV, "BIFANG_QUOTA_REQUEST_LIMIT": "3", "BIFANG_QUOTA_PER_MINUTE": "2"}
    first = lambda_module.create_handler(dynamodb=store, environ=env, clock=lambda: NOW)
    assert [status(first(event())) for _ in range(3)] == [200, 200, 429]
    second = lambda_module.create_handler(dynamodb=store, environ=env, clock=lambda: NOW + 60)
    assert [status(second(event())) for _ in range(2)] == [200, 403]
    third = lambda_module.create_handler(dynamodb=store, environ=env, clock=lambda: NOW + 120)
    assert status(third(event())) == 403
    assert store.items["budget"]["requests"] == number(3)
    assert f"minute:{NOW // 60 + 2}" not in store.items


def test_raising_limit_preserves_consumed_budget(lambda_module):
    store = AtomicDynamo()
    first = lambda_module.create_handler(
        dynamodb=store, clock=lambda: NOW, environ={**ENV, "BIFANG_QUOTA_REQUEST_LIMIT": "2"}
    )
    assert [status(first(event())) for _ in range(3)] == [200, 200, 403]
    second = lambda_module.create_handler(
        dynamodb=store,
        clock=lambda: NOW + 60,
        environ={**ENV, "BIFANG_QUOTA_REQUEST_LIMIT": "1000"},
    )
    assert status(second(event())) == 200
    assert store.items["budget"]["requests"] == number(3)


@pytest.mark.parametrize("counter", ["budget", "minute"])
def test_fractional_number_cannot_allow_one_request_to_cross_a_cap(lambda_module, counter):
    store = AtomicDynamo()
    if counter == "budget":
        store.items["budget"]["requests"] = number("1.5")
    else:
        key = f"minute:{NOW // 60}"
        store.items[key] = {
            "pk": {"S": key},
            "count": number("1.5"),
            "ttl": number(NOW // 60 * 60 + 36 * 3600),
        }
    before = copy.deepcopy(store.items)
    handle = lambda_module.create_handler(
        dynamodb=store,
        clock=lambda: NOW,
        environ={**ENV, "BIFANG_QUOTA_REQUEST_LIMIT": "2", "BIFANG_QUOTA_PER_MINUTE": "2"},
    )
    assert status(handle(event())) == (403 if counter == "budget" else 429)
    assert store.items == before


@pytest.mark.parametrize("field", ["requests", "output_tokens", "input_bytes", "expires_at"])
@pytest.mark.parametrize("bad", [None, {"S": "0"}, {"NULL": True}, {"N": "-1"}])
def test_missing_or_malformed_budget_is_not_initialized(lambda_module, field, bad):
    store = AtomicDynamo()
    if bad is None:
        del store.items["budget"][field]
    else:
        store.items["budget"][field] = bad
    before = copy.deepcopy(store.items)
    handle = lambda_module.create_handler(dynamodb=store, environ=ENV, clock=lambda: NOW)
    assert status(handle(event())) == 503
    assert store.items == before


@pytest.mark.parametrize("mode", ["absent", "expiry-drift", "global-ttl"])
def test_absent_budget_expiry_drift_and_global_ttl_fail_closed(lambda_module, mode):
    store = AtomicDynamo()
    if mode == "absent":
        store.items.clear()
    elif mode == "expiry-drift":
        store.items["budget"]["expires_at"] = number(EXPIRY + 1)
    else:
        store.items["budget"]["ttl"] = number(EXPIRY)
    before = copy.deepcopy(store.items)
    handle = lambda_module.create_handler(dynamodb=store, environ=ENV, clock=lambda: NOW)
    assert status(handle(event())) == 503
    assert store.items == before


@pytest.mark.parametrize(
    "field,bad",
    [
        ("count", None),
        ("ttl", None),
        ("count", {"S": "0"}),
        ("count", number(-1)),
        ("ttl", number(NOW)),
    ],
)
@pytest.mark.parametrize("client_bucket", [False, True])
def test_existing_malformed_minute_is_never_reset(lambda_module, field, bad, client_bucket):
    store = AtomicDynamo()
    key = f"client-minute:{NOW // 60}:{CLIENT_KEY}" if client_bucket else f"minute:{NOW // 60}"
    store.items[key] = {
        "pk": {"S": key},
        "count": number(0),
        "ttl": number(NOW // 60 * 60 + 36 * 3600),
    }
    if bad is None:
        del store.items[key][field]
    else:
        store.items[key][field] = bad
    before = copy.deepcopy(store.items)
    handle = lambda_module.create_handler(dynamodb=store, environ=ENV, clock=lambda: NOW)
    assert status(handle(event())) == 503
    assert store.items == before


def test_auth_and_expiry_precede_even_sdk_creation(lambda_module, monkeypatch):
    class ForbiddenBoto:
        def client(self, *args, **kwargs):
            pytest.fail("SDK creation must follow authentication/validation")

    monkeypatch.setitem(sys.modules, "boto3", ForbiddenBoto())
    handle = lambda_module.create_handler(environ=ENV, clock=lambda: NOW)
    for headers in (
        {},
        {"authorization": "Bearer wrong"},
        {"authorization": "Bearer " + SECRET, "Authorization": "Bearer " + SECRET},
        {"authorization": "Bearer " + SECRET + "\n"},
    ):
        assert status(handle({**event(), "headers": headers})) == 401
    expired = lambda_module.create_handler(environ=ENV, clock=lambda: EXPIRY)
    assert status(expired(event())) == 403
    assert status(handle({**event(), "body": "not JSON"})) == 503


@pytest.mark.parametrize(
    "name,value",
    [
        ("BIFANG_QUOTA_SECRET", ""),
        ("BIFANG_QUOTA_TABLE", ""),
        ("BIFANG_QUOTA_EXPIRES_AT", "2035-01-01"),
        ("BIFANG_QUOTA_EXPIRES_AT", "2035-01-01T00:00:00+01:00"),
        ("BIFANG_QUOTA_REQUEST_LIMIT", "0"),
        ("BIFANG_QUOTA_OUTPUT_LIMIT", "-1"),
        ("BIFANG_QUOTA_INPUT_BYTES_LIMIT", "NaN"),
        ("BIFANG_QUOTA_PER_MINUTE", " 60"),
        ("BIFANG_QUOTA_CLIENT_REQUEST_LIMIT", "0"),
        ("BIFANG_QUOTA_CLIENT_OUTPUT_LIMIT", "-1"),
        ("BIFANG_QUOTA_CLIENT_INPUT_BYTES_LIMIT", "NaN"),
        ("BIFANG_QUOTA_CLIENT_DAILY_REQUEST_LIMIT", "0"),
        ("BIFANG_QUOTA_CLIENT_DAILY_OUTPUT_LIMIT", "-1"),
        ("BIFANG_QUOTA_CLIENT_DAILY_INPUT_BYTES_LIMIT", "Infinity"),
        ("BIFANG_QUOTA_CLIENT_PER_MINUTE", " 10"),
    ],
)
def test_bad_configuration_never_contacts_dynamo(lambda_module, name, value):
    store = AtomicDynamo()
    handle = lambda_module.create_handler(
        dynamodb=store, clock=lambda: NOW, environ={**ENV, name: value}
    )
    assert status(handle(event())) == 503
    assert not store.calls


@pytest.mark.parametrize(
    "field,value",
    [
        ("request_id", "not-a-uuid"),
        ("request_id", ""),
        ("client_key", None),
        ("client_key", "A" * 64),
        ("client_key", "g" * 64),
        ("client_key", "a" * 63),
        ("client_key", "a" * 65),
        ("client_key", CLIENT_IP),
        ("output_tokens", True),
        ("output_tokens", 0),
        ("output_tokens", 8193),
        ("output_tokens", 1.0),
        ("body_bytes", False),
        ("body_bytes", 0),
        ("body_bytes", 32769),
        ("body_bytes", "12"),
        ("messages", [{"content": "must never be stored"}]),
    ],
)
def test_bad_payload_never_reserves(lambda_module, field, value):
    store = AtomicDynamo()
    handle = lambda_module.create_handler(dynamodb=store, environ=ENV, clock=lambda: NOW)
    request = event()
    body = json.loads(request["body"])
    body[field] = value
    request["body"] = json.dumps(body)
    assert status(handle(request)) == 503
    assert not store.calls


def test_valid_base64_caps_and_request_envelope(lambda_module):
    store = AtomicDynamo()
    handle = lambda_module.create_handler(dynamodb=store, environ=ENV, clock=lambda: NOW)
    request = event(output_tokens=8192, body_bytes=32768)
    request["body"] = base64.b64encode(request["body"].encode()).decode()
    request["isBase64Encoded"] = True
    assert status(handle(request)) == 200
    assert store.items["budget"]["output_tokens"] == number(8192)
    assert store.items["budget"]["input_bytes"] == number(32768)
    for overrides in (
        {"body": "x" * 2049},
        {"body": "{}", "isBase64Encoded": True},
        {"requestContext": {"http": {"method": "GET"}}},
        {"body": '{"output_tokens":1,"output_tokens":2}'},
        {"body": "[]"},
        {"body": None},
    ):
        assert status(handle({**event(), **overrides})) == 503
    assert len(store.calls) == 1


def test_cost_larger_than_configured_cap_is_refused_without_a_transaction(lambda_module):
    store = AtomicDynamo()
    handle = lambda_module.create_handler(
        dynamodb=store,
        clock=lambda: NOW,
        environ={**ENV, "BIFANG_QUOTA_OUTPUT_LIMIT": "6", "BIFANG_QUOTA_INPUT_BYTES_LIMIT": "10"},
    )
    assert status(handle(event())) == 403
    assert not store.calls
    assert store.items == {"budget": budget()}


@pytest.mark.parametrize(
    "code,reasons",
    [
        ("AccessDeniedException", None),
        ("TransactionConflictException", None),
        ("TransactionCanceledException", None),
        ("TransactionCanceledException", [{"Code": "TransactionConflict"}, {"Code": "None"}]),
        ("TransactionCanceledException", [{"Code": "ConditionalCheckFailed"}, {"Code": "None"}]),
    ],
)
def test_upstream_errors_are_unavailable_and_redacted(lambda_module, capsys, code, reasons):
    class Unavailable:
        def transact_write_items(self, **kwargs):
            raise DDBError(code, reasons)

    handle = lambda_module.create_handler(dynamodb=Unavailable(), environ=ENV, clock=lambda: NOW)
    assert status(handle(event())) == 503
    assert capsys.readouterr() == ("", "")


def test_boto3_is_optional_until_an_authenticated_valid_request(lambda_module, monkeypatch):
    monkeypatch.setitem(sys.modules, "boto3", None)
    handle = lambda_module.create_handler(environ=ENV, clock=lambda: NOW)
    assert status(handle(event())) == 503
    offline = lambda_module.create_handler(dynamodb=AtomicDynamo(), environ=ENV, clock=lambda: NOW)
    assert status(offline(event())) == 200


def run_with_transport(respond, scenario, **client_kwargs):
    async def run():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(respond), trust_env=False, **client_kwargs
        ) as client:
            await scenario(HttpPublicQuota(URL, SECRET, client=client), client)

    asyncio.run(run())


def test_http_client_round_trip_sends_only_costs_and_internal_uuid(lambda_module):
    store = AtomicDynamo()
    handle = lambda_module.create_handler(dynamodb=store, environ=ENV, clock=lambda: NOW)
    requests = []

    def respond(request):
        requests.append(request)
        payload = json.loads(request.content)
        assert set(payload) == {"request_id", "client_key", "output_tokens", "body_bytes"}
        assert re.fullmatch(r"[0-9a-f]{64}", payload["client_key"])
        assert CLIENT_IP.encode() not in request.content
        assert request.headers["x-bifang-quota-protocol"] == str(QUOTA_PROTOCOL_VERSION) == "2"
        assert UUID(payload["request_id"]).version == 4
        assert request.headers["authorization"] == "Bearer " + SECRET
        assert "x-api-key" not in request.headers and "cookie" not in request.headers
        assert request.url == httpx.URL(URL)
        response = handle({**event(), "body": request.content.decode()})
        return httpx.Response(
            response["statusCode"], content=response["body"], headers=response["headers"]
        )

    async def scenario(quota, client):
        assert await quota.reserve(client_ip=CLIENT_IP, output_tokens=7, body_bytes=11) is None
        assert await quota.reserve(client_ip=CLIENT_IP, output_tokens=7, body_bytes=11) is None
        assert (
            json.loads(requests[0].content)["request_id"]
            != json.loads(requests[1].content)["request_id"]
        )
        await quota.aclose()
        assert not client.is_closed

    run_with_transport(
        respond,
        scenario,
        headers={"x-api-key": "synthetic-provider-secret"},
        params={"provider_secret": "synthetic"},
        cookies={"session": "synthetic"},
        auth=("synthetic-provider", "synthetic-password"),
    )
    assert store.items["budget"]["requests"] == number(2)


def test_uncertain_write_is_consumed_and_is_never_retried(lambda_module):
    store = AtomicDynamo()
    handle = lambda_module.create_handler(dynamodb=store, environ=ENV, clock=lambda: NOW)
    requests = []

    def respond(request):
        requests.append(request)
        assert status(handle({**event(), "body": request.content.decode()})) == 200
        raise httpx.ReadTimeout("synthetic private detail " + SECRET, request=request)

    async def scenario(quota, client):
        with pytest.raises(PublicQuotaUnavailable) as caught:
            await quota.reserve(client_ip=CLIENT_IP, output_tokens=7, body_bytes=11)
        assert caught.value.__cause__ is None and caught.value.__context__ is None
        assert SECRET not in "".join(traceback.format_exception(caught.value))

    run_with_transport(respond, scenario)
    assert len(requests) == 1
    assert store.items["budget"]["requests"] == number(1)


@pytest.mark.parametrize("code", [301, 302, 303, 307, 308])
@pytest.mark.parametrize("destination", ["https://unrelated.invalid/", URL + "other"])
def test_redirects_are_refused_even_with_an_injected_redirecting_client(code, destination):
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(code, headers={"location": destination})

    async def scenario(quota, client):
        with pytest.raises(PublicQuotaUnavailable):
            await quota.reserve(client_ip=CLIENT_IP, output_tokens=1, body_bytes=1)

    run_with_transport(respond, scenario, follow_redirects=True)
    assert len(requests) == 1
    assert str(requests[0].url) == URL


@pytest.mark.parametrize(
    "code,body,headers",
    [
        (503, SECRET, {}),
        (401, SECRET, {}),
        (403, SECRET, {}),
        (200, SECRET, {}),
        (200, "[]", {}),
        (200, '{"allowed":false}', {}),
        (200, '{"allowed":1}', {}),
        (200, '{"allowed":true,"detail":"private"}', {}),
        (200, '{"allowed":false,"allowed":true}', {}),
        (429, '{"allowed":true}', {}),
        (429, SECRET, {}),
        (200, '{"allowed":true}', {"content-encoding": "gzip"}),
    ],
)
def test_http_failures_and_malformed_decisions_are_redacted(code, body, headers):
    async def scenario(quota, client):
        with pytest.raises(PublicQuotaUnavailable) as caught:
            await quota.reserve(client_ip=CLIENT_IP, output_tokens=1, body_bytes=1)
        assert SECRET not in "".join(traceback.format_exception(caught.value))
        assert caught.value.__context__ is None

    # Bytes use a stream so httpx does not eagerly decode synthetic compression.
    run_with_transport(
        lambda request: httpx.Response(
            code, stream=httpx.ByteStream(body.encode()), headers=headers
        ),
        scenario,
    )


@pytest.mark.parametrize(
    "header,expected",
    [("1", 1), ("17", 17), ("60", 60)],
)
def test_quota_exceeded_has_safe_bounded_retry_after(header, expected):
    async def scenario(quota, client):
        with pytest.raises(PublicQuotaExceeded) as caught:
            await quota.reserve(client_ip=CLIENT_IP, output_tokens=1, body_bytes=1)
        assert caught.value.retry_after == expected
        assert SECRET not in str(caught.value)

    run_with_transport(
        lambda request: httpx.Response(
            429, json={"allowed": False}, headers={"retry-after": header}
        ),
        scenario,
    )
    assert PublicQuotaExceeded().retry_after == 60
    assert str(PublicQuotaUnavailable())


def test_response_read_is_bounded_and_stream_closed():
    class LargeStream(httpx.AsyncByteStream):
        chunks_read = 0
        closed = False

        async def __aiter__(self):
            for _ in range(10000):
                self.chunks_read += 1
                yield b" " * 512

        async def aclose(self):
            self.closed = True

    stream = LargeStream()

    async def scenario(quota, client):
        with pytest.raises(PublicQuotaUnavailable):
            await quota.reserve(client_ip=CLIENT_IP, output_tokens=1, body_bytes=1)

    run_with_transport(lambda request: httpx.Response(200, stream=stream), scenario)
    assert stream.chunks_read <= 9
    assert stream.closed


@pytest.mark.parametrize(
    "bad_url",
    [
        URL.replace("https://", "http://"),
        URL.replace("https://", "https://user@"),
        URL.replace("https://", "https://user:password@"),
        URL[:-1] + ":443/",
        URL + "?secret=private",
        URL + "?",
        URL + "#private",
        URL + "#",
        URL + "reserve",
        URL.replace(".on.aws", ".on.aws.evil.invalid"),
        "https://example.com/",
        "https://127.0.0.1/",
        " " + URL,
        URL + "\n",
        "https://[broken/",
    ],
)
def test_client_url_is_only_a_bare_https_lambda_function_url(bad_url):
    with pytest.raises(ValueError) as caught:
        HttpPublicQuota(bad_url, SECRET)
    assert str(caught.value) == "Public quota configuration is invalid."
    assert SECRET not in str(caught.value)


@pytest.mark.parametrize("secret", ["", "with space", "with\nnewline", "nonascii-£", "x" * 513])
def test_client_bad_secret_is_redacted(secret):
    with pytest.raises(ValueError, match="^Public quota configuration is invalid\\.$"):
        HttpPublicQuota(URL, secret)


@pytest.mark.parametrize(
    "output_tokens,body_bytes",
    [(0, 1), (8193, 1), (True, 1), (1, 0), (1, 32769), (1, False), (1.0, 1)],
)
def test_invalid_client_costs_fail_before_http(output_tokens, body_bytes):
    calls = []

    async def scenario(quota, client):
        with pytest.raises(PublicQuotaUnavailable):
            await quota.reserve(
                client_ip=CLIENT_IP, output_tokens=output_tokens, body_bytes=body_bytes
            )

    run_with_transport(lambda request: calls.append(request), scenario)
    assert not calls


def test_env_factory_owned_client_ignores_proxy_env_disables_redirects_and_closes(monkeypatch):
    real_client = httpx.AsyncClient
    created = []

    def factory(**kwargs):
        assert kwargs == {"timeout": 10, "trust_env": False, "follow_redirects": False}
        client = real_client(
            **kwargs,
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, json={"allowed": True})
            ),
        )
        created.append(client)
        return client

    monkeypatch.setattr(httpx, "AsyncClient", factory)
    monkeypatch.setenv("HTTPS_PROXY", "http://unrelated.invalid:1234")
    monkeypatch.setenv("BIFANG_PUBLIC_QUOTA_URL", URL)
    monkeypatch.setenv("BIFANG_PUBLIC_QUOTA_TOKEN", SECRET)
    monkeypatch.setenv("NEBIUS_API_KEY", "synthetic-provider-secret-never-used")

    async def scenario():
        quota = public_quota_from_env()
        assert (
            await quota.reserve(client_ip=CLIENT_IP, output_tokens=8192, body_bytes=32768) is None
        )
        await quota.aclose()
        assert created[0].is_closed

    asyncio.run(scenario())
    monkeypatch.delenv("BIFANG_PUBLIC_QUOTA_TOKEN")
    with pytest.raises(ValueError, match="^Public quota configuration is invalid\\.$"):
        public_quota_from_env()
    assert len(created) == 1


@pytest.mark.parametrize(
    "limiting",
    [
        "CLIENT_REQUEST_LIMIT",
        "CLIENT_OUTPUT_LIMIT",
        "CLIENT_INPUT_BYTES_LIMIT",
        "CLIENT_DAILY_REQUEST_LIMIT",
        "CLIENT_DAILY_OUTPUT_LIMIT",
        "CLIENT_DAILY_INPUT_BYTES_LIMIT",
        "CLIENT_PER_MINUTE",
    ],
)
def test_concurrent_clients_have_independent_atomic_budgets(lambda_module, limiting):
    store = AtomicDynamo()
    value = (
        "21" if limiting.endswith("OUTPUT_LIMIT") else "33" if "INPUT_BYTES" in limiting else "3"
    )
    env = {
        **ENV,
        "BIFANG_QUOTA_PER_MINUTE": "1000",
        "BIFANG_QUOTA_CLIENT_PER_MINUTE": "1000",
        "BIFANG_QUOTA_" + limiting: value,
    }
    handlers = [
        lambda_module.create_handler(dynamodb=store, environ=env.copy(), clock=lambda: NOW)
        for _ in range(6)
    ]

    def reserve(index):
        client_key = f"{index % 3:064x}"
        return handlers[index % 6](event(client_key=client_key))

    with ThreadPoolExecutor(max_workers=16) as pool:
        replies = list(pool.map(reserve, range(90)))
    expected_reason = "client_daily_budget" if "DAILY" in limiting else "client_budget"
    assert sum(status(reply) == 200 for reply in replies) == 9
    for reply in replies:
        if reply["statusCode"] != 200:
            if limiting == "CLIENT_PER_MINUTE":
                assert status(reply) == 429
                assert reply["headers"]["retry-after"] == str(60 - NOW % 60)
            else:
                assert status(reply) == 403
                assert json.loads(reply["body"])["reason"] == expected_reason
    assert store.items["budget"] == {
        **budget(),
        "requests": number(9),
        "output_tokens": number(63),
        "input_bytes": number(99),
    }
    assert store.items[f"minute:{NOW // 60}"]["count"] == number(9)
    for client in range(3):
        client_key = f"{client:064x}"
        lifetime = store.items[f"client:{client_key}"]
        daily = store.items[f"client-day:{NOW // 86400}:{client_key}"]
        minute = store.items[f"client-minute:{NOW // 60}:{client_key}"]
        for row in (lifetime, daily):
            assert row["requests"] == number(3)
            assert row["output_tokens"] == number(21)
            assert row["input_bytes"] == number(33)
        assert lifetime["ttl"] == number(EXPIRY + 36 * 3600)
        assert daily["expires_at"] == number((NOW // 86400 + 1) * 86400)
        assert daily["ttl"] == number((NOW // 86400 + 1) * 86400 + 36 * 3600)
        assert minute["count"] == number(3)
        assert minute["ttl"] == number(NOW // 60 * 60 + 36 * 3600)


def test_default_limits_prevent_one_client_draining_multiweek_global_budget(lambda_module):
    store = AtomicDynamo()
    expiry = NOW + 14 * 86400
    store.items["budget"]["expires_at"] = number(expiry)
    current = [NOW]
    env = {**ENV, "BIFANG_QUOTA_EXPIRES_AT": datetime.fromtimestamp(expiry, UTC).isoformat()}
    handle = lambda_module.create_handler(dynamodb=store, environ=env, clock=lambda: current[0])
    first_day = NOW // 86400 + 1
    allowed = 0
    for day in range(3):
        for minute in range(101):
            current[0] = (first_day + day) * 86400 + minute * 60 + 1
            reply = handle(event(output_tokens=1, body_bytes=1))
            if status(reply) == 200:
                allowed += 1
            else:
                body = json.loads(reply["body"])
                assert body["reason"] == ("client_daily_budget" if day < 2 else "client_budget")
                if day < 2:
                    assert body["reset_at"] == (first_day + day + 1) * 86400
    assert allowed == 250
    assert store.items["budget"]["requests"] == number(250)
    assert store.items[f"client:{CLIENT_KEY}"]["requests"] == number(250)
    before = copy.deepcopy(store.items)
    current[0] += 86400
    redeployed = lambda_module.create_handler(
        dynamodb=store, environ=env.copy(), clock=lambda: current[0]
    )
    assert status(redeployed(event(output_tokens=1, body_bytes=1))) == 403
    assert store.items == before
    assert status(redeployed(event(client_key="d" * 64, output_tokens=1, body_bytes=1))) == 200
    assert store.items["budget"]["requests"] == number(251)


@pytest.mark.parametrize("scope", ["client", "client-day"])
@pytest.mark.parametrize("field", ["requests", "output_tokens", "input_bytes", "expires_at", "ttl"])
@pytest.mark.parametrize("bad", [None, {"S": "0"}, {"N": "-1"}])
def test_malformed_existing_client_budget_never_resets_or_partially_reserves(
    lambda_module,
    scope,
    field,
    bad,
):
    store = AtomicDynamo()
    handle = lambda_module.create_handler(dynamodb=store, environ=ENV, clock=lambda: NOW)
    assert status(handle(event())) == 200
    key = f"client:{CLIENT_KEY}" if scope == "client" else f"client-day:{NOW // 86400}:{CLIENT_KEY}"
    if bad is None:
        del store.items[key][field]
    else:
        store.items[key][field] = bad
    before = copy.deepcopy(store.items)
    assert status(handle(event())) == 503
    assert store.items == before


def test_retained_existing_global_counter_and_client_rows_survive_redeployment(lambda_module):
    store = AtomicDynamo()
    store.items["budget"].update(
        {"requests": number(4), "output_tokens": number(2760), "input_bytes": number(636)}
    )
    for _ in range(2):
        handle = lambda_module.create_handler(dynamodb=store, environ=ENV.copy(), clock=lambda: NOW)
        assert status(handle(event())) == 200
    assert store.items["budget"] == {
        **budget(),
        "requests": number(6),
        "output_tokens": number(2774),
        "input_bytes": number(658),
    }
    assert store.items[f"client:{CLIENT_KEY}"]["requests"] == number(2)


@pytest.mark.parametrize(
    "reason,setting",
    [
        ("global_budget", "BIFANG_QUOTA_REQUEST_LIMIT"),
        ("client_budget", "BIFANG_QUOTA_CLIENT_REQUEST_LIMIT"),
        ("client_daily_budget", "BIFANG_QUOTA_CLIENT_DAILY_REQUEST_LIMIT"),
    ],
)
def test_budget_exhaustion_precedes_simultaneous_minute_exhaustion(lambda_module, reason, setting):
    store = AtomicDynamo()
    env = {
        **ENV,
        setting: "1",
        "BIFANG_QUOTA_PER_MINUTE": "1",
        "BIFANG_QUOTA_CLIENT_PER_MINUTE": "1",
    }
    handle = lambda_module.create_handler(dynamodb=store, environ=env, clock=lambda: NOW)
    assert status(handle(event())) == 200
    before = copy.deepcopy(store.items)
    reply = handle(event())
    assert status(reply) == 403
    assert json.loads(reply["body"])["reason"] == reason
    assert store.items == before


@pytest.mark.parametrize("setting", ["BIFANG_QUOTA_PER_MINUTE", "BIFANG_QUOTA_CLIENT_PER_MINUTE"])
@pytest.mark.parametrize("second,retry_after", [(0, 60), (1, 59), (59, 1)])
def test_only_minute_exhaustion_returns_accurate_retry_after(
    lambda_module, setting, second, retry_after
):
    store = AtomicDynamo()
    current = [NOW // 60 * 60 + second]
    handle = lambda_module.create_handler(
        dynamodb=store, environ={**ENV, setting: "1"}, clock=lambda: current[0]
    )
    assert status(handle(event())) == 200
    reply = handle(event())
    assert status(reply) == 429
    assert reply["headers"]["retry-after"] == str(retry_after)
    current[0] = NOW // 60 * 60 + 60
    assert status(handle(event())) == 200
    assert store.items["budget"]["requests"] == number(2)


def test_protocol_two_is_mandatory_and_no_raw_ip_payload_is_accepted(lambda_module):
    store = AtomicDynamo()
    handle = lambda_module.create_handler(dynamodb=store, environ=ENV, clock=lambda: NOW)
    for version in (None, "1", "3", " 2", "2,2"):
        request = event()
        if version is None:
            del request["headers"]["x-bifang-quota-protocol"]
        else:
            request["headers"]["x-bifang-quota-protocol"] = version
        assert status(handle(request)) == 503
    for change in ("missing-key", "raw-ip"):
        request = event()
        payload = json.loads(request["body"])
        if change == "missing-key":
            del payload["client_key"]
        else:
            payload["client_ip"] = CLIENT_IP
        request["body"] = json.dumps(payload)
        assert status(handle(request)) == 503
    assert QUOTA_PROTOCOL_VERSION == lambda_module.QUOTA_PROTOCOL_VERSION == 2
    assert not store.calls


def test_client_hmac_normalizes_networks_and_never_transfers_ip(capsys):
    identities = [
        (CLIENT_IP, "192.0.2.10/32"),
        ("::ffff:192.0.2.10", "192.0.2.10/32"),
        ("2001:db8:1:2::1", "2001:db8:1:2::/64"),
        ("2001:0DB8:0001:0002:ffff:0:0:99", "2001:db8:1:2::/64"),
        ("2001:db8:1:3::1", "2001:db8:1:3::/64"),
    ]
    keys = []

    def respond(request):
        payload = json.loads(request.content)
        assert set(payload) == {"client_key", "request_id", "output_tokens", "body_bytes"}
        assert request.headers["x-bifang-quota-protocol"] == "2"
        for address, _ in identities:
            assert address.encode() not in request.content
            assert address not in str(request.url)
            assert address not in str(request.headers)
        keys.append(payload["client_key"])
        return httpx.Response(200, json={"allowed": True})

    async def scenario(quota, client):
        for address, _ in identities:
            await quota.reserve(client_ip=address, output_tokens=1, body_bytes=1)

    run_with_transport(respond, scenario)
    expected = [
        hmac.new(
            SECRET.encode(), b"bifang-public-quota-client:v1:" + network.encode(), hashlib.sha256
        ).hexdigest()
        for _, network in identities
    ]
    assert keys == expected
    assert keys[0] == keys[1]
    assert keys[2] == keys[3] and keys[3] != keys[4]
    assert capsys.readouterr() == ("", "")


@pytest.mark.parametrize(
    "value",
    [
        None,
        3221225994,
        b"192.0.2.10",
        "",
        "unknown",
        "example.com",
        "192.0.2.10, 198.51.100.1",
        "for=192.0.2.10",
        "192.0.2.10:443",
        "[2001:db8::1]",
        "fe80::1%eth0",
        "fe80::1%2",
        "192.168.001.1",
        "192.0.2.10/32",
        "2001:db8::/64",
        " 192.0.2.10",
        "192.0.2.10\n",
        "\t2001:db8::1",
        "0xc000020a",
        "192.0.2",
        "192.0.2.10\x00",
    ],
    ids=lambda value: type(value).__name__,
)
def test_malformed_or_spoof_style_client_ip_fails_before_rpc_and_is_redacted(value, capsys):
    calls = []

    async def scenario(quota, client):
        with pytest.raises(PublicQuotaUnavailable) as caught:
            await quota.reserve(client_ip=value, output_tokens=1, body_bytes=1)
        rendered = "".join(traceback.format_exception(caught.value))
        assert SECRET not in rendered
        if isinstance(value, str) and value:
            assert value not in rendered
        assert caught.value.__context__ is None and caught.value.__cause__ is None

    run_with_transport(lambda request: calls.append(request), scenario)
    assert not calls
    assert capsys.readouterr() == ("", "")


@pytest.mark.parametrize("reason", ["global_budget", "client_budget", "client_daily_budget"])
def test_client_exhaustion_exception_has_reason_and_daily_reset_only(reason):
    payload = {"allowed": False, "reason": reason}
    reset_at = (NOW // 86400 + 1) * 86400 if reason == "client_daily_budget" else None
    if reset_at is not None:
        payload["reset_at"] = reset_at

    async def scenario(quota, client):
        with pytest.raises(PublicQuotaExhausted) as caught:
            await quota.reserve(client_ip=CLIENT_IP, output_tokens=1, body_bytes=1)
        assert caught.value.reason == reason
        assert caught.value.reset_at == reset_at
        assert not hasattr(caught.value, "retry_after")
        assert SECRET not in str(caught.value)

    run_with_transport(lambda request: httpx.Response(403, json=payload), scenario)


@pytest.mark.parametrize("value", [None, "0", "61", "-1", "9999", "1.0", "tomorrow", " 1", "1,2"])
def test_client_refuses_missing_or_invalid_minute_retry_after(value):
    headers = {} if value is None else {"retry-after": value}

    async def scenario(quota, client):
        with pytest.raises(PublicQuotaUnavailable):
            await quota.reserve(client_ip=CLIENT_IP, output_tokens=1, body_bytes=1)

    run_with_transport(
        lambda request: httpx.Response(429, json={"allowed": False}, headers=headers), scenario
    )


@pytest.mark.parametrize(
    "payload,headers",
    [
        ({"allowed": False, "reason": "unknown"}, {}),
        ({"allowed": True, "reason": "global_budget"}, {}),
        ({"allowed": False, "reason": "global_budget", "reset_at": 86400}, {}),
        ({"allowed": False, "reason": "client_budget", "reset_at": 86400}, {}),
        ({"allowed": False, "reason": "client_daily_budget"}, {}),
        ({"allowed": False, "reason": "client_daily_budget", "reset_at": True}, {}),
        ({"allowed": False, "reason": "client_daily_budget", "reset_at": "86400"}, {}),
        ({"allowed": False, "reason": "client_daily_budget", "reset_at": 86400.0}, {}),
        ({"allowed": False, "reason": "client_daily_budget", "reset_at": -86400}, {}),
        ({"allowed": False, "reason": "client_daily_budget", "reset_at": NOW}, {}),
        ({"allowed": False, "reason": "client_daily_budget", "reset_at": 10**30}, {}),
        ({"allowed": False, "reason": "client_budget"}, {"retry-after": "60"}),
        ({"allowed": False, "reason": "global_budget", "detail": SECRET}, {}),
    ],
)
def test_client_rejects_malformed_budget_denials_and_false_retry_after(payload, headers):
    async def scenario(quota, client):
        with pytest.raises(PublicQuotaUnavailable) as caught:
            await quota.reserve(client_ip=CLIENT_IP, output_tokens=1, body_bytes=1)
        assert SECRET not in "".join(traceback.format_exception(caught.value))
        assert caught.value.__context__ is None

    run_with_transport(lambda request: httpx.Response(403, json=payload, headers=headers), scenario)
