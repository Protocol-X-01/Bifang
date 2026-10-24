import asyncio
from types import SimpleNamespace

import httpx
from test_vision import picture

from bifang import server
from bifang.audit import Audit
from bifang.vision import MAX_REQUEST_BYTES


def test_visual_prepare_is_local_bounded_and_errors_do_not_echo_images(monkeypatch):
    monkeypatch.setenv("BIFANG_SERVER_HOST", "127.0.0.1")

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app), base_url="http://test") as client:
            response = await client.post("/vision/prepare", json={"images": [{"data_url": picture("JPEG", metadata=True)}]})
            assert response.status_code == 200
            prepared = response.json()["images"][0]
            assert prepared["data_url"].startswith("data:image/png;base64,") and prepared["metadata_removed"]
            for invalid in ({"images": []}, {"images": [{"data_url": "private-image-sentinel"}]},
                            {"images": [{"data_url": picture(), "filename": "/etc/private"}]}):
                response = await client.post("/vision/prepare", json=invalid)
                assert response.status_code == 422
                assert "private-image-sentinel" not in response.text and "/etc/private" not in response.text
            response = await client.post("/vision/prepare", content=b"x" * (MAX_REQUEST_BYTES + 1))
            assert response.status_code == 413

    asyncio.run(scenario())


def test_image_sharing_confirmation_and_audit_are_separate_from_chat_history(tmp_path, monkeypatch):
    monkeypatch.setenv("BIFANG_SERVER_HOST", "127.0.0.1")
    agent = SimpleNamespace(cfg=object(), audit=Audit(tmp_path))
    session = server.Session("visual", agent, 0)
    monkeypatch.setattr(server, "sessions", {"visual": session})
    calls = []

    async def inspect(config, request):
        calls.append(request)
        return {"analysis": "private-analysis-sentinel", "verification": "unverified_visual_analysis",
                "images": [{"sha256": "a" * 64, "bytes": 10, "width": 1, "height": 1,
                            "mime_type": "image/png", "metadata_removed": True}],
                "receipt": {"provider": "nebius", "requested_model": request.model, "reported_model": None,
                            "usage": {"total_tokens": 10}, "tools_enabled": False}}

    monkeypatch.setattr(server, "inspect_images", inspect)
    body = {"provider": "nebius", "model": "explicit-visual", "prompt": "private-question-sentinel",
            "images": [{"data_url": picture()}]}

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app), base_url="http://test") as client:
            assert (await client.post("/sessions/missing/vision", json=body)).status_code == 404
            assert (await client.post("/sessions/visual/vision", json=body)).status_code == 400
            assert (await client.post("/sessions/visual/vision", json={**body, "sharing_confirmed": "true"})).status_code == 422
            assert not calls
            response = await client.post("/sessions/visual/vision", json={**body, "sharing_confirmed": True})
            assert response.status_code == 200 and response.json()["analysis"] == "private-analysis-sentinel"
            assert not session.busy and session.vision_task is None and session.message_count == 0
            assert (await client.post("/sessions/visual/vision/cancel")).json() == {"cancelled": False}

    asyncio.run(scenario())
    recorded = agent.audit.path.read_text()
    assert "vision_review" in recorded
    assert all(secret not in recorded for secret in ["private-question-sentinel", "private-analysis-sentinel", body["images"][0]["data_url"]])


def test_early_cancellation_prevents_inference_and_never_cancels_another_request(tmp_path, monkeypatch):
    monkeypatch.setenv("BIFANG_SERVER_HOST", "127.0.0.1")
    session = server.Session("visual", SimpleNamespace(cfg=object(), audit=Audit(tmp_path)), 0)
    monkeypatch.setattr(server, "sessions", {"visual": session})

    async def forbidden(config, request):
        raise AssertionError("Cancelled-before-start image reached inference")

    monkeypatch.setattr(server, "inspect_images", forbidden)

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app), base_url="http://test") as client:
            identity = "a" * 32
            response = await client.post(f"/sessions/visual/vision/cancel?request_id={identity}")
            assert response.json() == {"cancelled": True, "pending": True}
            response = await client.post("/sessions/visual/vision", json={"provider": "nebius", "model": "explicit-visual",
                "prompt": "Look", "images": [{"data_url": picture()}], "sharing_confirmed": True, "request_id": identity})
            assert response.status_code == 409 and not session.busy
            session.busy = True
            session.vision_request_id = "b" * 32
            response = await client.post(f"/sessions/visual/vision/cancel?request_id={identity}")
            assert response.json()["pending"] and session.busy and session.vision_request_id == "b" * 32
            for count in range(70):
                await client.post(f"/sessions/visual/vision/cancel?request_id={count:032x}")
            assert len(session.vision_cancelled) == 64

    asyncio.run(scenario())


def test_cancellation_owns_only_visual_work_and_releases_session_busy(tmp_path, monkeypatch):
    monkeypatch.setenv("BIFANG_SERVER_HOST", "127.0.0.1")
    agent = SimpleNamespace(cfg=object(), audit=Audit(tmp_path))
    session = server.Session("visual", agent, 0)
    monkeypatch.setattr(server, "sessions", {"visual": session})

    async def scenario():
        started, stopped = asyncio.Event(), asyncio.Event()

        async def inspect(config, request):
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                stopped.set()

        monkeypatch.setattr(server, "inspect_images", inspect)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app), base_url="http://test") as client:
            body = {"provider": "nebius", "model": "explicit-visual", "prompt": "Look",
                    "images": [{"data_url": picture()}], "sharing_confirmed": True}
            pending = asyncio.create_task(client.post("/sessions/visual/vision", json=body))
            await asyncio.wait_for(started.wait(), 2)
            assert session.busy
            assert (await client.post("/sessions/visual/vision", json=body)).status_code == 409
            assert (await client.post("/sessions/visual/apply")).status_code == 409
            assert (await client.delete("/sessions/visual")).status_code == 409
            assert (await client.post("/sessions/visual/vision/cancel")).json() == {"cancelled": True}
            assert (await pending).status_code == 409
            assert stopped.is_set() and session.vision_task is None and not session.busy
            session.busy = True
            assert (await client.post("/sessions/visual/vision/cancel")).json() == {"cancelled": False}
            assert session.busy

    asyncio.run(scenario())


def test_model_discovery_is_explicit_and_remote_auth_covers_image_routes(monkeypatch):
    monkeypatch.setenv("BIFANG_SERVER_HOST", "0.0.0.0")
    monkeypatch.setenv("BIFANG_SERVER_API_KEY", "synthetic-api-auth")

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app), base_url="http://test") as client:
            for path in ("/vision/prepare", "/sessions/visual/vision", "/sessions/visual/vision/cancel"):
                assert (await client.post(path, json={})).status_code == 401
            assert (await client.get("/vision/models")).status_code == 401
            response = await client.get("/vision/models?provider=unconfigured", headers={"X-API-Key": "synthetic-api-auth"})
            assert response.status_code == 422

    asyncio.run(scenario())
