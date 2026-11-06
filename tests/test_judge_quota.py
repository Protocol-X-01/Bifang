"""Synthetic SDK/HTTP tests: no AWS service, credentials or external transport."""

import asyncio
import base64
import copy
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
    HttpPublicQuota,
    PublicQuotaExceeded,
    PublicQuotaUnavailable,
    public_quota_from_env,
)

NOW = 1800000007
EXPIRY = NOW + 86400
SECRET = "synthetic-quota-secret-only"
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


def event(*, request_id=None, output_tokens=7, body_bytes=11):
    return {
        "headers": {"authorization": "Bearer " + SECRET},
        "requestContext": {"http": {"method": "POST"}},
        "body": json.dumps(
            {
                "request_id": request_id or str(uuid4()),
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
    """Shared, locked, all-or-nothing two-item SDK fake with token deduplication."""

    def __init__(self):
        self.items = {"budget": budget()}
        self.tokens = {}
        self.calls = []
        self.lock = threading.Lock()

    def transact_write_items(self, *, TransactItems, ClientRequestToken):
        with self.lock:
            self.calls.append(copy.deepcopy(TransactItems))
            assert len(TransactItems) == 2
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
    assert json.loads(response["body"]) == {"allowed": response["statusCode"] == 200}
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
        results = list(pool.map(lambda index: status(handlers[index % 8](event())), range(160)))
    assert results.count(200) == 13
    assert results.count(429) == 147
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
    assert len(store.items) == 2


def test_rate_reset_and_redeployment_never_reset_global_counters(lambda_module):
    store = AtomicDynamo()
    env = {**ENV, "BIFANG_QUOTA_REQUEST_LIMIT": "3", "BIFANG_QUOTA_PER_MINUTE": "2"}
    first = lambda_module.create_handler(dynamodb=store, environ=env, clock=lambda: NOW)
    assert [status(first(event())) for _ in range(3)] == [200, 200, 429]
    second = lambda_module.create_handler(dynamodb=store, environ=env, clock=lambda: NOW + 60)
    assert [status(second(event())) for _ in range(2)] == [200, 429]
    third = lambda_module.create_handler(dynamodb=store, environ=env, clock=lambda: NOW + 120)
    assert status(third(event())) == 429
    assert store.items["budget"]["requests"] == number(3)
    assert f"minute:{NOW // 60 + 2}" not in store.items


def test_raising_limit_preserves_consumed_budget(lambda_module):
    store = AtomicDynamo()
    first = lambda_module.create_handler(
        dynamodb=store, clock=lambda: NOW, environ={**ENV, "BIFANG_QUOTA_REQUEST_LIMIT": "2"}
    )
    assert [status(first(event())) for _ in range(3)] == [200, 200, 429]
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
    assert status(handle(event())) == 429
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
def test_existing_malformed_minute_is_never_reset(lambda_module, field, bad):
    store = AtomicDynamo()
    key = f"minute:{NOW // 60}"
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
    assert status(handle(event())) == 429
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
        assert set(payload) == {"request_id", "output_tokens", "body_bytes"}
        assert UUID(payload["request_id"]).version == 4
        assert request.headers["authorization"] == "Bearer " + SECRET
        assert "x-api-key" not in request.headers and "cookie" not in request.headers
        assert request.url == httpx.URL(URL)
        response = handle({**event(), "body": request.content.decode()})
        return httpx.Response(
            response["statusCode"], content=response["body"], headers=response["headers"]
        )

    async def scenario(quota, client):
        assert await quota.reserve(output_tokens=7, body_bytes=11) is None
        assert await quota.reserve(output_tokens=7, body_bytes=11) is None
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
            await quota.reserve(output_tokens=7, body_bytes=11)
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
            await quota.reserve(output_tokens=1, body_bytes=1)

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
            await quota.reserve(output_tokens=1, body_bytes=1)
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
    [("17", 17), ("0", 1), ("9999", 3600), (SECRET, 60), ("-1", 60), ("99999999", 60)],
)
def test_quota_exceeded_has_safe_bounded_retry_after(header, expected):
    async def scenario(quota, client):
        with pytest.raises(PublicQuotaExceeded) as caught:
            await quota.reserve(output_tokens=1, body_bytes=1)
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
            await quota.reserve(output_tokens=1, body_bytes=1)

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
            await quota.reserve(output_tokens=output_tokens, body_bytes=body_bytes)

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
        assert await quota.reserve(output_tokens=8192, body_bytes=32768) is None
        await quota.aclose()
        assert created[0].is_closed

    asyncio.run(scenario())
    monkeypatch.delenv("BIFANG_PUBLIC_QUOTA_TOKEN")
    with pytest.raises(ValueError, match="^Public quota configuration is invalid\\.$"):
        public_quota_from_env()
    assert len(created) == 1
