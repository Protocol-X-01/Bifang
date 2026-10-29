import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("demo_replay", ROOT / "scripts/replay-demo-patch.py")
REPLAY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(REPLAY)


def make_patch(tmp_path, target="receipts.py"):
    original = tmp_path / "original.py"
    updated = tmp_path / "updated.py"
    original.write_bytes((ROOT / "examples/demo/receipts.py").read_bytes())
    updated.write_text(
        "import csv\n\n"
        "def parse_receipt(row: str) -> dict[str, str]:\n"
        "    merchant, category, amount = next(csv.reader([row.strip()]))\n"
        '    return {"merchant": merchant, "category": category, "amount": amount}\n'
    )
    result = subprocess.run(
        ["diff", "-u", "--label", f"a/{target}", str(original),
         "--label", f"b/{target}", str(updated)], capture_output=True, text=True, check=False,
    )
    assert result.returncode == 1
    patch = tmp_path / "change.patch"
    patch.write_text(result.stdout)
    return patch


def test_replays_patch_and_preserves_checks(tmp_path):
    report = REPLAY.replay(ROOT / "examples/demo", make_patch(tmp_path))
    assert report["baseline_returncode"] != 0
    assert report["final_returncode"] == 0
    assert report["checks_unchanged"]
    assert report["changed_files"] == ["receipts.py"]
    assert str(tmp_path) not in report["baseline_output"]


def test_rejects_patch_to_check_file(tmp_path):
    with pytest.raises(ValueError, match="only receipts.py"):
        REPLAY.replay(ROOT / "examples/demo", make_patch(tmp_path, "check_receipts.py"))


def test_rejects_patch_that_leaves_failing_checks(tmp_path):
    patch = make_patch(tmp_path)
    patch.write_text(patch.read_text().replace("next(csv.reader([row.strip()]))", 'row.strip().split(",")'))
    with pytest.raises(ValueError, match="preserve and pass"):
        REPLAY.replay(ROOT / "examples/demo", patch)


def test_missing_patch_has_nonzero_cli_exit(tmp_path):
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/replay-demo-patch.py"),
         "--fixture", str(ROOT / "examples/demo"), "--patch", str(tmp_path / "missing.patch")],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode != 0
    assert "Demo replay failed" in result.stderr
