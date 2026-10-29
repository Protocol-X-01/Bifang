import asyncio
import hashlib
import sys

import pytest

from bifang.candidate import Candidate
from bifang.verification import verification_argv, verify_candidate


def test_verification_sandbox_has_no_network_host_home_or_writable_candidate(tmp_path):
    command = ["/usr/bin/python3", "-B", "check.py"]
    arguments = verification_argv(tmp_path, command)
    assert "--unshare-all" in arguments
    assert "--share-net" not in arguments
    assert "--clearenv" in arguments
    assert "--bind" not in arguments
    assert arguments[-4:] == ["--", *command]
    assert "/home" not in arguments


def test_verification_requires_confirmation_and_sandbox(tmp_path, monkeypatch):
    (tmp_path / "check.py").write_text("assert True\n")
    with Candidate(tmp_path, ["check.py"], []) as candidate:
        with pytest.raises(PermissionError):
            asyncio.run(verify_candidate(candidate, ["python3", "check.py"]))
        monkeypatch.setattr("bifang.verification.shutil.which", lambda name: None)
        with pytest.raises(RuntimeError, match="no unsandboxed fallback"):
            asyncio.run(verify_candidate(candidate, ["python3", "check.py"], confirmed=True))


def test_verifier_captures_actual_exit_and_output_and_rejects_stale_source(tmp_path, monkeypatch):
    (tmp_path / "check.py").write_text("assert True\n")
    monkeypatch.setattr("bifang.verification.shutil.which", lambda name: "/fixture/bwrap")

    def trusted_fixture(root, command):
        return [sys.executable, "-B", "-c", command[0]]

    monkeypatch.setattr("bifang.verification.verification_argv", trusted_fixture)
    monkeypatch.setattr("bifang.verification.attach_filter", lambda arguments, descriptor: arguments)

    async def scenario():
        with Candidate(tmp_path, ["check.py"], []) as candidate:
            result = await verify_candidate(candidate, ["print('synthetic-check')"], confirmed=True)
            assert result["passed"]
            assert result["stdout"]["sha256"] == hashlib.sha256(b"synthetic-check\n").hexdigest()
            assert result["candidate_sha256"] == candidate.describe()["candidate_sha256"]
            failed = await verify_candidate(candidate, ["raise SystemExit(3)"], confirmed=True)
            assert not failed["passed"] and failed["returncode"] == 3
            (tmp_path / "check.py").write_text("owner changed it\n")
            with pytest.raises(RuntimeError, match="original source changed"):
                await verify_candidate(candidate, ["print('not executed')"], confirmed=True)

    asyncio.run(scenario())


def test_verifier_bounds_retained_output_and_kills_timed_out_process(tmp_path, monkeypatch):
    (tmp_path / "check.py").write_text("assert True\n")
    monkeypatch.setattr("bifang.verification.shutil.which", lambda name: "/fixture/bwrap")
    monkeypatch.setattr("bifang.verification.verification_argv",
                        lambda root, command: [sys.executable, "-B", "-c", command[0]])
    monkeypatch.setattr("bifang.verification.attach_filter", lambda arguments, descriptor: arguments)

    async def scenario():
        with Candidate(tmp_path, ["check.py"], []) as candidate:
            result = await verify_candidate(candidate, ["print('x'*20000)"], confirmed=True)
            assert result["stdout"]["bytes"] == 20001
            assert len(result["stdout"]["text"]) == 16000
            assert result["stdout"]["truncated"]
            timed = await verify_candidate(candidate, ["import time; time.sleep(60)"], confirmed=True, timeout=1)
            assert timed["timed_out"] and not timed["passed"]
            assert timed["returncode"] != 0

    asyncio.run(scenario())
