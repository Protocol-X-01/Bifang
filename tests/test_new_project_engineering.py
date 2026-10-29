import asyncio
import hashlib
import os
from types import SimpleNamespace

import pytest

from bifang.implementation import EngineeringWorkflow
from bifang.server import CandidateRequest
from bifang.terminal_engineering import TerminalEngineering
from bifang.workspace import Workspace


def test_candidate_request_accepts_explicit_new_outputs():
    request = CandidateRequest(prompt="Create hello.py", writable=["hello.py"], inference_confirmed=True)
    assert request.files == [] and request.writable == ["hello.py"]


def test_terminal_allows_empty_source_but_not_empty_check():
    panel = SimpleNamespace(query_one=lambda *args: SimpleNamespace(value="[]"))
    assert TerminalEngineering.array(panel, "#engineering-files", allow_empty=True) == []
    with pytest.raises(ValueError):
        TerminalEngineering.array(panel, "#engineering-command")


@pytest.mark.parametrize("real_check", [False, pytest.param(True, marks=pytest.mark.skipif(
    os.getenv("BIFANG_TEST_REAL_BWRAP") != "1", reason="Explicit real Bubblewrap execution opt-in"))])
def test_output_only_candidate_check_stage_and_separate_apply(tmp_path, monkeypatch, real_check):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    source = tmp_path / "fresh"
    source.mkdir()
    workspace = Workspace.create(source)
    workflow = EngineeringWorkflow(SimpleNamespace(ws=workspace), [], ["hello.py"], "Create hello.py")

    async def fixture_check(candidate, command, **kwargs):
        return {"passed": True, "candidate_sha256": candidate.describe()["candidate_sha256"],
                "scope": "Synthetic control-flow fixture only"}

    if not real_check:
        monkeypatch.setattr("bifang.implementation.verify_candidate", fixture_check)

    async def scenario():
        try:
            (workflow.candidate.root / "hello.py").write_text("value = 42\n")
            digest = workflow.candidate.describe()["candidate_sha256"]
            with pytest.raises(ValueError):
                workflow.stage(digest)
            await workflow.check(["python3", "-B", "-c", "import hello; assert hello.value == 42"], 10)
            assert workflow.status == "verified" and workflow.receipt["passed"]
            assert not (source / "hello.py").exists() and not (workspace.root / "hello.py").exists()
            (workflow.candidate.root / "hello.py").write_text("value = 43\n")
            with pytest.raises(ValueError):
                workflow.stage(digest)
            (workflow.candidate.root / "hello.py").write_text("value = 42\n")
            workflow.stage(digest)
            assert (workspace.root / "hello.py").read_text() == "value = 42\n"
            assert not (source / "hello.py").exists()
            patch_hash = hashlib.sha256(workspace.diff().encode()).hexdigest()
            assert workspace.apply(expected_patch_sha256=patch_hash)
            assert (source / "hello.py").read_text() == "value = 42\n"
            assert not (source / ".git").exists()
        finally:
            await workflow.close()
            workspace.discard()

    asyncio.run(scenario())
