import asyncio
import hashlib
import subprocess
from types import SimpleNamespace

import httpx
import pytest

from bifang import server
from bifang.workspace import Workspace


@pytest.mark.parametrize("git_repository", [True, False])
def test_apply_requires_the_exact_reviewed_patch(tmp_path, monkeypatch, git_repository):
    monkeypatch.setenv("BIFANG_SERVER_HOST", "127.0.0.1")
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    source = tmp_path / "source"
    source.mkdir()
    subprocess.run(["git", "init", str(source)], check=True, capture_output=True)
    (source / "main.py").write_text("value = 0\n")
    subprocess.run(["git", "-C", str(source), "add", "main.py"], check=True)
    subprocess.run(["git", "-C", str(source), "-c", "user.name=Test", "-c",
                    "user.email=test@example.com", "commit", "-m", "fixture"], check=True, capture_output=True)
    root = tmp_path / "worktree"
    subprocess.run(["git", "-C", str(source), "worktree", "add", "-b", "fixture", str(root)],
                   check=True, capture_output=True)
    workspace = Workspace(source, root, "fixture", True)
    if not git_repository:
        folder = tmp_path / "plain"
        folder.mkdir()
        (folder / "main.py").write_text("value = 0\n")
        source = folder
        workspace = Workspace.create(folder)
        root = workspace.root
    session = server.Session("fixture", SimpleNamespace(ws=workspace), 0)
    monkeypatch.setattr(server, "sessions", {"fixture": session})

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app), base_url="http://test") as client:
            (root / "main.py").write_text("value = 1\n")
            shown = (await client.get("/sessions/fixture/diff")).json()
            assert shown["patch_sha256"] == hashlib.sha256(shown["diff"].encode()).hexdigest()
            assert (await client.post("/sessions/fixture/apply")).status_code == 422
            assert (await client.post("/sessions/fixture/apply", json={"patch_sha256": "bad"})).status_code == 422
            (root / "main.py").write_text("value = 2\n")
            stale = await client.post("/sessions/fixture/apply", json={"patch_sha256": shown["patch_sha256"]})
            assert stale.status_code == 409
            assert "changed after review" in stale.json()["detail"]
            assert (source / "main.py").read_text() == "value = 0\n"
            current = (await client.get("/sessions/fixture/diff")).json()
            session.busy = True
            assert (await client.post("/sessions/fixture/apply", json={"patch_sha256": current["patch_sha256"]})).status_code == 409
            session.busy = False
            applied = await client.post("/sessions/fixture/apply", json={"patch_sha256": current["patch_sha256"]})
            assert applied.status_code == 200 and applied.json() == {"applied": True}
            assert (source / "main.py").read_text() == "value = 2\n"

    try:
        asyncio.run(scenario())
    finally:
        workspace.discard()
