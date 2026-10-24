from pathlib import Path

import pytest

from bifang.coding_eval import TASK_IDS, run_checks, verify_fixtures


ROOT = Path(__file__).resolve().parents[1] / "evaluations/coding-v1"


def test_authored_fixtures_fail_before_and_pass_after():
    report = verify_fixtures(ROOT)
    assert report["passed"]
    assert [row["task"] for row in report["tasks"]] == list(TASK_IDS)
    assert len(report["manifest"]) == 3


def test_missing_sandbox_never_executes_candidate(tmp_path, monkeypatch):
    monkeypatch.setattr("bifang.coding_eval.shutil.which", lambda command: None)
    monkeypatch.setattr("bifang.coding_eval.subprocess.run",
                        lambda *args, **kwargs: pytest.fail("Candidate executed without sandbox"))
    assert run_checks(ROOT / TASK_IDS[0], "raise RuntimeError('must not run')", sandbox=True) == {
        "status": "sandbox_unavailable", "passed": False}


def test_oversize_candidate_is_rejected():
    with pytest.raises(ValueError, match="64 KiB"):
        run_checks(ROOT / TASK_IDS[0], "🙂" * 20000, sandbox=True)


def test_real_sandbox_excludes_private_files_environment_and_network(tmp_path, monkeypatch):
    private = tmp_path / "private.txt"
    private.write_text("synthetic private marker")
    monkeypatch.setenv("BIFANG_EVAL_PRIVATE_MARKER", "synthetic environment marker")
    probe = f'''import os, socket
assert os.getenv("BIFANG_EVAL_PRIVATE_MARKER") is None
assert not os.path.exists({str(private)!r})
assert not os.path.exists("/home/protocol-x/.ssh")
try:
    open("module.py", "w")
except OSError:
    pass
else:
    raise AssertionError("Candidate filesystem is writable")
with socket.socket() as connection:
    connection.settimeout(0.2)
    try:
        connection.connect(("1.1.1.1", 443))
    except OSError:
        pass
    else:
        raise AssertionError("Sandbox has network access")
'''
    task = ROOT / TASK_IDS[0]
    report = run_checks(task, probe + (task / "reference.py").read_text(), sandbox=True)
    if report["status"] == "sandbox_unavailable":
        pytest.skip("Host bubblewrap user namespaces unavailable; candidate execution must remain disabled")
    assert report["passed"], report
