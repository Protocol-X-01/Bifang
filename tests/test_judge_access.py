import asyncio
import json
import stat

import httpx
import pytest

from bifang.judge_access import (
    MAX_METADATA_BYTES,
    check_access,
    load_judge_token,
    relay_origin,
    save_access_report,
    validate_judge_token,
)
from bifang.model_ids import TOKEN_FACTORY_ROLES

TOKEN = "synthetic-private-judge-token-1234567890"


def metadata_response(request):
    if request.url.path == "/health":
        return httpx.Response(200, json={"status": "ok", "scope": "inference-only"})
    if request.headers.get("authorization") != "Bearer " + TOKEN:
        return httpx.Response(401, json={"detail": "Judge authorization required"})
    if request.url.path == "/v1/models":
        return httpx.Response(200, json={"data": [{"id": model} for model in TOKEN_FACTORY_ROLES.values()]})
    return httpx.Response(404)


def exercise(handler, *, follow_redirects=False):
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler),
                                     follow_redirects=follow_redirects) as client:
            return await check_access("https://relay.example/v1", TOKEN, client=client)
    return asyncio.run(run())


def test_success_sends_only_metadata_gets_and_never_prints_credentials():
    requests = []

    def handler(request):
        requests.append(request)
        return metadata_response(request)

    report = exercise(handler)
    assert report["passed"]
    assert report["completion_requests_sent"] == 0
    assert len(requests) == report["metadata_get_requests"] == 7
    assert all(request.method == "GET" for request in requests)
    assert all(request.url.host == "relay.example" for request in requests)
    assert not requests[0].headers.get("authorization")
    assert not requests[1].headers.get("authorization")
    assert TOKEN not in json.dumps(report)


def test_redirects_never_forward_judge_token_even_with_redirecting_client():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(302, headers={"location": "https://other.example/collect"})

    report = exercise(handler, follow_redirects=True)
    assert not report["passed"]
    assert len(requests) == 7
    assert all(request.url.host == "relay.example" for request in requests)
    assert all(check["failure"] == "unexpected_status" for check in report["checks"])


def test_provider_error_bodies_and_transport_details_are_not_reported():
    report = exercise(lambda request: httpx.Response(502, text=TOKEN))
    assert not report["passed"] and TOKEN not in json.dumps(report)

    def unavailable(request):
        raise httpx.ConnectError(TOKEN)

    report = exercise(unavailable)
    assert not report["passed"] and TOKEN not in json.dumps(report)
    assert all(check["failure"] == "transport_error" for check in report["checks"])


@pytest.mark.parametrize("catalog", [{"data": []}, {"data": [TOKEN]}, {"data": {"id": TOKEN}},
                                     {"data": [{"id": TOKEN}]}, [TOKEN]])
def test_unexpected_catalog_fails_without_echoing_unknown_identifiers(catalog):
    def handler(request):
        if request.url.path == "/v1/models" and request.headers.get("authorization") == "Bearer " + TOKEN:
            return httpx.Response(200, json=catalog)
        return metadata_response(request)

    report = exercise(handler)
    assert not report["passed"] and TOKEN not in json.dumps(report)


def test_oversize_response_is_closed_and_rejected():
    class Oversize(httpx.AsyncByteStream):
        closed = False

        async def __aiter__(self):
            yield b"x" * (MAX_METADATA_BYTES + 1)

        async def aclose(self):
            self.closed = True

    stream = Oversize()

    def handler(request):
        if request.url.path == "/health":
            return httpx.Response(200, stream=stream)
        return metadata_response(request)

    report = exercise(handler)
    assert not report["passed"] and stream.closed
    assert report["checks"][0]["failure"] == "invalid_or_oversize_metadata"


@pytest.mark.parametrize("url", ["http://relay.example", "https://user:pass@relay.example",
                                 "https://relay.example:8443", "https://relay.example?token=secret",
                                 "https://relay.example/#fragment", "https://relay.example/other",
                                 "https://relay.example:invalid", "https://relay.example/\n"])
def test_invalid_url_is_rejected_without_echoing_input(url):
    with pytest.raises(ValueError) as error:
        relay_origin(url)
    assert url not in str(error.value)


@pytest.mark.parametrize("token", [None, 42, "short", "x" * 1025, "x" * 32 + "\n", "🙂" * 40])
def test_bad_tokens_are_rejected_without_echoing_them(token):
    with pytest.raises(ValueError, match="judge-only token"):
        validate_judge_token(token)


def test_private_token_file_and_exclusive_owner_only_report(tmp_path, monkeypatch):
    monkeypatch.setenv("NEBIUS_API_KEY", "synthetic-provider-must-not-load")
    private = tmp_path / "judge.json"
    private.write_text(json.dumps({"judge_token": TOKEN}))
    assert load_judge_token(private) == TOKEN
    report = exercise(metadata_response)
    path = tmp_path / "report.json"
    save_access_report(path, report)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert json.loads(path.read_text()) == report
    with pytest.raises(FileExistsError):
        save_access_report(path, {"overwritten": True})
    assert json.loads(path.read_text()) == report


@pytest.mark.parametrize("payload", ["[1]", '{"judge_token":3}', "invalid JSON", "x" * 4097])
def test_malformed_private_file_does_not_expose_contents(tmp_path, payload):
    path = tmp_path / "judge.json"
    path.write_text(payload)
    with pytest.raises(ValueError) as error:
        load_judge_token(path)
    assert payload not in str(error.value)
