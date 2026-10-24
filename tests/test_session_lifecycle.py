import asyncio
from types import SimpleNamespace
from unittest.mock import Mock

import httpx

from bifang import server


def test_delete_waits_for_running_chat(monkeypatch):
    monkeypatch.setenv("BIFANG_SERVER_HOST", "127.0.0.1")
    monkeypatch.setattr(server, "sessions", {})
    closed = []
    monkeypatch.setattr(server, "close_session", lambda session: closed.append(session.id))

    async def scenario():
        started = asyncio.Event()
        release = asyncio.Event()

        async def ask(prompt, *, selection=None):
            assert selection is None
            started.set()
            await release.wait()
            return "Finished"

        session = server.Session(id="test-session", agent=SimpleNamespace(
            ask=ask, cfg=SimpleNamespace(approval_mode="manual"), audit=Mock(),
            provider=SimpleNamespace(requests=[])), created_at=0)
        server.sessions[session.id] = session
        transport = httpx.ASGITransport(app=server.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            chat = asyncio.create_task(client.post("/sessions/test-session/chat", json={"prompt": "Fix a bug"}))
            try:
                await asyncio.wait_for(started.wait(), timeout=2)
                rejected = await client.delete("/sessions/test-session")
                assert rejected.status_code == 409
                assert server.sessions[session.id] is session
                assert closed == []
            finally:
                release.set()
                completed = await asyncio.wait_for(chat, timeout=2)
            assert completed.status_code == 200
            deleted = await client.delete("/sessions/test-session")
            assert deleted.status_code == 200
            assert closed == [session.id]
            assert session.id not in server.sessions

    asyncio.run(scenario())
