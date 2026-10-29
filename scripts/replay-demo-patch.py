import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def run_checks(workspace):
    result = subprocess.run(
        [sys.executable, "-m", "unittest", "-v", "check_receipts"],
        cwd=workspace, capture_output=True, text=True, timeout=30, check=False,
    )
    return result.returncode, result.stdout + result.stderr


def replay(fixture, patch):
    patch = patch.resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix="bifang-patch-replay-") as directory:
        workspace = Path(directory)
        for name in ("receipts.py", "check_receipts.py"):
            shutil.copyfile(fixture / name, workspace / name)
        checks_hash = hashlib.sha256((workspace / "check_receipts.py").read_bytes()).hexdigest()
        baseline_code, baseline_output = run_checks(workspace)
        if baseline_code == 0 or "Ran 5 tests" not in baseline_output:
            raise ValueError("Expected the original five-check failing baseline")
        subprocess.run(["git", "init", "-q", str(workspace)], check=True, capture_output=True)
        stats = subprocess.run(
            ["git", "apply", "--numstat", str(patch)], cwd=workspace,
            capture_output=True, text=True, check=True, timeout=30,
        )
        changed = [line.split("\t", 2)[-1] for line in stats.stdout.splitlines()]
        if changed != ["receipts.py"]:
            raise ValueError("The demonstration patch must change only receipts.py")
        subprocess.run(
            ["git", "apply", "--check", str(patch)], cwd=workspace,
            capture_output=True, check=True, timeout=30,
        )
        subprocess.run(
            ["git", "apply", str(patch)], cwd=workspace,
            capture_output=True, check=True, timeout=30,
        )
        final_code, final_output = run_checks(workspace)
        checks_unchanged = checks_hash == hashlib.sha256(
            (workspace / "check_receipts.py").read_bytes()
        ).hexdigest()
        if final_code != 0 or "Ran 5 tests" not in final_output or not checks_unchanged:
            raise ValueError("Applied patch did not preserve and pass the original five checks")
        return {
            "scope": "offline replay of a retained model-generated patch, not new inference",
            "baseline_returncode": baseline_code,
            "final_returncode": final_code,
            "changed_files": changed,
            "checks_unchanged": checks_unchanged,
            "patch_sha256": hashlib.sha256(patch.read_bytes()).hexdigest(),
            "baseline_output": baseline_output.replace(str(workspace), "<temporary-demo>"),
            "final_output": final_output,
        }


def main():
    parser = argparse.ArgumentParser(description="Replay the retained demo patch without API keys")
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--patch", type=Path, required=True)
    options = parser.parse_args()
    try:
        print(json.dumps(replay(options.fixture, options.patch), indent=2))
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        parser.exit(1, f"Demo replay failed: {type(error).__name__}: {error}\n")


if __name__ == "__main__":
    main()
