import asyncio
import base64
import hashlib
import json

import httpx
import pytest

from bifang.remote_jobs import ReviewJobs
from bifang.remote_pairing import PairingStore
from bifang.remote_server import RemoteTokens, create_remote_app
from bifang.totp import TotpCredential


def test_service_startup_keeps_pairing_when_coding_is_enabled(tmp_path, monkeypatch):
    from bifang import remote_server

    monkeypatch.setenv("BIFANG_REMOTE_CLIENTS", json.dumps([{"subject": "owner", "token_sha256": hashlib.sha256(b"a" * 48).hexdigest()}]))
    monkeypatch.setenv("BIFANG_REMOTE_STATE", str(tmp_path / "state"))
    monkeypatch.setenv("BIFANG_REMOTE_AUTHENTICATORS", '{"owner":"GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"}')
    monkeypatch.setenv("BIFANG_REMOTE_CODING_SOCKET", "/run/bifang-executor/check.sock")
    monkeypatch.setattr("bifang.config.Config.load", lambda: object())
    captured = []
    monkeypatch.setattr("uvicorn.run", lambda app, **options: captured.append(app))
    remote_server.main()
    assert len(captured) == 1
    async def exercise():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=captured[0]), base_url="https://fixture.test") as client:
            operator = {"Authorization": "Bearer " + "a" * 48}
            assert (await client.get("/v1/auth/session", headers=operator)).json()["authentication"] == "operator"
            assert (await client.get("/v1/coding/schema", headers=operator)).status_code == 200
            challenge = (await client.post("/v1/auth/device/start", json={"label": "Startup fixture"})).json()
            assert "device_code" in challenge
            assert (await client.post("/v1/auth/device/token", json={"device_code": challenge["device_code"]})).json()["error"] == "authorization_pending"
    asyncio.run(exercise())


def setup(tmp_path, *, enabled=True):
    now = [3000.0]
    credential = TotpCredential(base64.b32encode(b"12345678901234567890").decode())
    jobs = ReviewJobs(tmp_path / "private")
    tokens = RemoteTokens(json.dumps([{"subject": "owner", "token_sha256": hashlib.sha256(b"a" * 48).hexdigest()}]))
    store = PairingStore(tmp_path / "private", {"owner": credential}, clock=lambda: now[0]) if enabled else None
    return create_remote_app(jobs, tokens, pairing=store), store, credential, now


def test_api_pairing_exchange_preserves_subject_and_denies_device_operator_privileges(tmp_path):
    async def exercise():
        app, store, credential, now = setup(tmp_path)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://fixture.test") as client:
            operator = {"Authorization": "Bearer " + "a" * 48}
            assert (await client.get("/v1/reviews")).status_code == 401
            started = await client.post("/v1/auth/device/start", json={"label": "Owner phone"})
            assert started.status_code == 200 and started.headers["Cache-Control"] == "no-store"
            pair = started.json()
            proof = {"device_code": pair["device_code"]}
            assert (await client.get("/v1/reviews", headers={"Authorization": "Bearer " + pair["device_code"]})).status_code == 401
            pending = await client.post("/v1/auth/device/token", json=proof)
            assert pending.status_code == 400 and pending.json()["error"] == "authorization_pending"
            decision = {"user_code": pair["user_code"], "authenticator_code": credential.code(100), "approved": True}
            assert (await client.post("/v1/auth/device/approve", json=decision)).status_code == 401
            assert (await client.post("/v1/auth/device/approve", json=decision, headers=operator)).status_code == 200
            now[0] += 5
            exchanged = await client.post("/v1/auth/device/token", json=proof)
            assert exchanged.status_code == 200 and exchanged.headers["Cache-Control"] == "no-store"
            device = {"Authorization": "Bearer " + exchanged.json()["access_token"]}
            assert (await client.get("/v1/auth/session", headers=device)).json() == {"subject": "owner", "authentication": "device"}
            assert (await client.get("/v1/reviews", headers=device)).json() == {"jobs": []}
            assert (await client.post("/v1/auth/device/approve", headers=device, json=decision)).status_code == 403
            assert (await client.get("/v1/auth/devices", headers=device)).status_code == 403
            identity = store.sessions("owner")[0]["id"]
            assert (await client.delete("/v1/auth/devices/" + identity, headers=operator)).json() == {"revoked": True}
            assert (await client.get("/v1/reviews", headers=device)).status_code == 401
            assert (await client.post("/v1/auth/device/token", json=proof)).json()["error"] == "invalid_grant"
    asyncio.run(exercise())


def test_pairing_is_disabled_without_explicit_authenticator_configuration(tmp_path):
    async def exercise():
        app, _, _, _ = setup(tmp_path, enabled=False)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://fixture.test") as client:
            assert (await client.post("/v1/auth/device/start", json={"label": "Phone"})).status_code == 401
            assert (await client.post("/v1/auth/device/token", json={"device_code": "x" * 43})).status_code == 401
    asyncio.run(exercise())


def test_device_cancellation_and_logout_revoke_without_operator_root_changes(tmp_path):
    async def exercise():
        app, _, credential, now = setup(tmp_path)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://fixture.test") as client:
            operator = {"Authorization": "Bearer " + "a" * 48}
            for cancellation in (True, False):
                pair = (await client.post("/v1/auth/device/start", json={"label": "Phone"})).json()
                proof = {"device_code": pair["device_code"]}
                decision = {"user_code": pair["user_code"], "authenticator_code": credential.code(int(now[0] // 30)), "approved": True}
                assert (await client.post("/v1/auth/device/approve", json=decision, headers=operator)).status_code == 200
                device = {"Authorization": "Bearer " + (await client.post("/v1/auth/device/token", json=proof)).json()["access_token"]}
                assert (await client.get("/v1/auth/session", headers=device)).status_code == 200
                if cancellation:
                    assert (await client.post("/v1/auth/device/cancel", json=proof)).json() == {"cancelled": True}
                else:
                    assert (await client.delete("/v1/auth/session", headers=device)).json() == {"revoked": True}
                assert (await client.get("/v1/auth/session", headers=device)).status_code == 401
                assert (await client.post("/v1/auth/device/token", json=proof)).json()["error"] == ("access_denied" if cancellation else "invalid_grant")
                now[0] += 30
            assert (await client.delete("/v1/auth/session", headers=operator)).json() == {"revoked": False}
            assert (await client.get("/v1/auth/session", headers=operator)).json()["authentication"] == "operator"
    asyncio.run(exercise())


def test_pairing_body_validation_is_bounded_and_never_echoes_credentials(tmp_path):
    async def exercise():
        app, _, _, _ = setup(tmp_path)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://fixture.test") as client:
            marker = "synthetic-sensitive-input"
            response = await client.post("/v1/auth/device/start", json={"label": "Phone", "credential": marker})
            assert response.status_code == 422 and marker not in response.text
            response = await client.post("/v1/auth/device/token", content=b"x" * 1025)
            assert response.status_code == 413
            for method, route in (("GET", "/v1/auth/device/start"), ("POST", "/v1/auth/device/start/extra")):
                assert (await client.request(method, route)).status_code == 401
    asyncio.run(exercise())


def test_pairing_cannot_issue_subjects_outside_operator_registry_or_other_state_directory(tmp_path):
    jobs = ReviewJobs(tmp_path / "private")
    credential = TotpCredential(base64.b32encode(b"12345678901234567890").decode())
    tokens = RemoteTokens(json.dumps([{"subject": "owner", "token_sha256": "a" * 64}]))
    for store in (PairingStore(tmp_path / "private", {"other": credential}), PairingStore(tmp_path / "different", {"owner": credential})):
        with pytest.raises(ValueError, match="existing operator subjects"):
            create_remote_app(jobs, tokens, pairing=store)
