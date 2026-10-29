import asyncio
import json
import subprocess
from types import SimpleNamespace

import httpx
import pytest

from bifang import server
from bifang.agent import Agent
from bifang.candidate import Candidate
from bifang.config import Config
from bifang.implementation import EngineeringWorkflow
from bifang.workspace import Workspace


@pytest.mark.parametrize("new_project", [False, True])
def test_candidate_api_runs_isolated_writer_and_enforces_check_stage_and_busy_gates(tmp_path, monkeypatch, new_project):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("BIFANG_SERVER_HOST", "127.0.0.1")
    if not new_project:
        (tmp_path / "code.py").write_text("original\n")
    (tmp_path / ".env").write_text("synthetic-private-not-for-workers")

    async def scenario():
        started, release = asyncio.Event(), asyncio.Event()
        providers = []

        class Provider:
            def __init__(self):
                self.requests, self.closed = [], False
                providers.append(self)

            async def complete(self, *args, **kwargs):
                started.set()
                await release.wait()
                self.requests.append({"provider": "synthetic"})
                if len(self.requests) == 1:
                    return {"role": "assistant", "content": "", "tool_calls": [{"id": "write", "type": "function",
                            "function": {"name": "write_file", "arguments": json.dumps({"path": "code.py", "content": "candidate\n"})}}]}
                return {"role": "assistant", "content": "Tests passed: unsupported synthetic claim"}

            async def close(self):
                self.closed = True

        async def synthetic_check(candidate, command, **kwargs):
            assert command == ["synthetic-check"]
            return {"passed": True, "candidate_sha256": candidate.describe()["candidate_sha256"],
                    "returncode": 0, "scope": "synthetic orchestration fixture, not sandbox evidence"}

        monkeypatch.setattr("bifang.agent.create_tiered_provider", lambda config: Provider())
        monkeypatch.setattr("bifang.implementation.verify_candidate", synthetic_check)
        parent = Agent(Config(enable_memory=False, enable_conversation_history=False), Workspace(tmp_path, tmp_path),
                       approve=lambda prompt: True)
        session = server.Session("fixture", parent, 0)
        monkeypatch.setattr(server, "sessions", {"fixture": session})
        request = {"prompt": "Create or fix code.py", "files": [] if new_project else ["code.py"], "writable": ["code.py"]}
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app), base_url="http://test") as client:
                assert (await client.get("/sessions/missing/candidate")).status_code == 404
                assert (await client.post("/sessions/fixture/candidate", json=request)).status_code == 400
                request["inference_confirmed"] = True
                assert (await client.post("/sessions/fixture/candidate", json={**request, "files": [".env"]})).status_code == 422
                response = await client.post("/sessions/fixture/candidate", json=request)
                assert response.status_code == 200
                await asyncio.wait_for(started.wait(), 2)
                assert (await client.post("/sessions/fixture/review", json={"prompt": "Review", "inference_confirmed": True})).status_code == 409
                assert (await client.delete("/sessions/fixture")).status_code == 409
                assert (await client.get("/sessions/fixture/candidate/patch")).status_code == 409
                release.set()
                await asyncio.wait_for(session.engineering.task, 2)
                snapshot = (await client.get("/sessions/fixture/candidate")).json()
                assert snapshot["status"] == "ready" and not session.busy
                assert snapshot["result"]["verification"] == "unverified_model_analysis"
                if new_project:
                    assert not (tmp_path / "code.py").exists()
                else:
                    assert (tmp_path / "code.py").read_text() == "original\n"
                assert not (session.engineering.candidate.root / ".env").exists()
                patch = (await client.get("/sessions/fixture/candidate/patch")).json()
                assert "+candidate" in patch["patch"]
                stage = {"candidate_sha256": patch["candidate_sha256"], "confirmed": True}
                assert (await client.post("/sessions/fixture/candidate/stage", json=stage)).status_code == 409
                assert (await client.post("/sessions/fixture/candidate/check", json={"command": ["synthetic-check"]})).status_code == 400
                assert (await client.post("/sessions/fixture/candidate/check", json={"command": ["synthetic-check"], "confirmed": True})).status_code == 200
                await asyncio.wait_for(session.engineering.task, 2)
                assert session.engineering.status == "verified"
                assert (await client.post("/sessions/fixture/candidate/stage", json=stage)).status_code == 409
                session.busy = True
                await client.post("/sessions/fixture/candidate/cancel")
                assert session.busy
                session.busy = False
                old_candidate_root = session.engineering.candidate.root
                started.clear()
                release.clear()
                assert (await client.post("/sessions/fixture/candidate", json=request)).status_code == 200
                await asyncio.wait_for(started.wait(), 2)
                cancelled = await client.post("/sessions/fixture/candidate/cancel")
                assert cancelled.json()["status"] == "cancelled"
                assert not session.busy
                assert all(provider.closed for provider in providers[1:])
                assert not old_candidate_root.exists()
        finally:
            await session.engineering.close()
            await parent.close()
        assert all(provider.closed for provider in providers)

    asyncio.run(scenario())


@pytest.mark.parametrize("original,proposed", [("before", "after"), ("before\n", "after\n"), ("", "new")])
def test_candidate_patch_preserves_text_with_and_without_final_newlines(tmp_path, original, proposed):
    (tmp_path / "code.py").write_text(original)
    with Candidate(tmp_path, ["code.py"], ["code.py", "new.py"]) as candidate:
        (candidate.root / "code.py").write_text(proposed)
        (candidate.root / "new.py").write_text("new file")
        applied = subprocess.run(["git", "-C", str(tmp_path), "apply", "-"], input=candidate.patch(),
                                 text=True, capture_output=True, check=False)
        assert applied.returncode == 0, applied.stderr
        assert (tmp_path / "code.py").read_text() == proposed
        assert (tmp_path / "new.py").read_text() == "new file"


def test_staging_keeps_original_untouched_until_separate_apply(tmp_path, monkeypatch):
    source, worktree = tmp_path / "source", tmp_path / "worktree"
    source.mkdir()
    for arguments in (["init", str(source)], ["-C", str(source), "config", "user.email", "fixture@example.com"],
                      ["-C", str(source), "config", "user.name", "Synthetic fixture"]):
        subprocess.run(["git", *arguments], check=True, capture_output=True)
    (source / "code.py").write_text("original\n")
    for arguments in (["add", "code.py"], ["commit", "-m", "Synthetic fixture baseline"],
                      ["worktree", "add", "--detach", str(worktree), "HEAD"]):
        subprocess.run(["git", "-C", str(source), *arguments], check=True, capture_output=True)
    workspace = Workspace(source, worktree, isolated=True)
    workflow = EngineeringWorkflow(SimpleNamespace(ws=workspace), ["code.py"], ["code.py"], "Fix")
    try:
        (workflow.candidate.root / "code.py").write_text("candidate\n")
        digest = workflow.candidate.describe()["candidate_sha256"]
        with pytest.raises(ValueError):
            workflow.stage(digest)
        workflow.status = "verified"
        workflow.receipt = {"passed": True, "candidate_sha256": digest}
        with pytest.raises(ValueError):
            workflow.stage("0" * 64)
        (worktree / "code.py").write_text("concurrent owner edit\n")
        with pytest.raises(ValueError):
            workflow.stage(digest)
        (worktree / "code.py").write_text("original\n")
        (workflow.candidate.root / "code.py").write_text("unchecked candidate edit\n")
        with pytest.raises(ValueError):
            workflow.stage(digest)
        (workflow.candidate.root / "code.py").write_text("candidate\n")
        session = server.Session("fixture", SimpleNamespace(ws=workspace), 0, engineering=workflow)
        monkeypatch.setattr(server, "sessions", {"fixture": session})

        async def stage_request():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app), base_url="http://test") as client:
                response = await client.post("/sessions/fixture/candidate/stage", json={"candidate_sha256": digest, "confirmed": True})
                assert response.status_code == 200
                return response.json()

        staged = asyncio.run(stage_request())
        assert staged["original_checkout_modified"] is False
        assert staged["receipt"]["passed"]
        assert staged["receipt"]["candidate_sha256"] == digest
        assert (worktree / "code.py").read_text() == "candidate\n"
        assert (source / "code.py").read_text() == "original\n"
        assert workspace.apply()
        assert (source / "code.py").read_text() == "candidate\n"
    finally:
        asyncio.run(workflow.close())
        workspace.discard()


def test_candidate_cancel_before_start_releases_api_busy_state(tmp_path, monkeypatch):
    (tmp_path / "code.py").write_text("original\n")
    parent = SimpleNamespace(ws=Workspace(tmp_path, tmp_path))
    session = server.Session("fixture", parent, 0)
    monkeypatch.setattr(server, "sessions", {"fixture": session})

    async def scenario():
        workflow = EngineeringWorkflow(parent, ["code.py"], ["code.py"], "Fix")
        session.engineering = workflow
        server.launch_candidate(session, workflow, workflow.run)
        try:
            result = await server.cancel_candidate("fixture")
            assert result["status"] == "cancelled"
            assert not session.busy and workflow.task.done()
        finally:
            await workflow.close()

    asyncio.run(scenario())
