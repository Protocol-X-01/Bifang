from __future__ import annotations

import hashlib
import json
import os
import re
import resource
import shutil
import subprocess
import tempfile
from pathlib import Path


TASK_IDS = ("config-merge", "dependency-order", "text-edits")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def task_manifest(root: Path) -> list[dict]:
    return [{"task": identity, "sha256": {name: digest(root / identity / name)
             for name in ("baseline.py", "reference.py", "checks.py", "brief.md")}}
            for identity in TASK_IDS]


def limits():
    resource.setrlimit(resource.RLIMIT_CPU, (5, 5))
    resource.setrlimit(resource.RLIMIT_AS, (256 * 1024 * 1024, 256 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_FSIZE, (1024 * 1024, 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def run_checks(task: Path, source: str, *, sandbox: bool) -> dict:
    if len(source.encode("utf-8")) > 65536:
        raise ValueError("Candidate module exceeds 64 KiB")
    if sandbox and not shutil.which("bwrap"):
        return {"status": "sandbox_unavailable", "passed": False}
    with tempfile.TemporaryDirectory(prefix="bifang-eval-") as temporary:
        root = Path(temporary)
        (root / "module.py").write_text(source)
        shutil.copyfile(task / "checks.py", root / "checks.py")
        code = "import sys,runpy; sys.path.insert(0,'.'); runpy.run_path('checks.py',run_name='__main__')"
        command = ["/usr/bin/python3", "-I", "-B", "-c", code]
        if sandbox:
            command = ["bwrap", "--unshare-all", "--die-with-parent", "--new-session",
                       "--clearenv", "--ro-bind", "/usr", "/usr"] + [
                argument for directory in ("/lib", "/lib64") if Path(directory).exists()
                for argument in ("--ro-bind", directory, directory)] + [
                "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp",
                "--ro-bind", str(root), "/work", "--chdir", "/work",
                "--setenv", "PATH", "/usr/bin", *command]
        environment = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "HOME": str(root)}
        with (root / "stdout").open("wb") as stdout, (root / "stderr").open("wb") as stderr:
            try:
                result = subprocess.run(command, cwd=root, env=environment, stdout=stdout,
                    stderr=stderr, timeout=10, check=False, preexec_fn=limits)
            except subprocess.TimeoutExpired:
                return {"status": "timeout", "passed": False}
        output = (root / "stderr").read_bytes()[:1024 * 1024]
        count = re.search(rb"\nRan (\d+) tests? in ", output)
        failures = re.search(rb"FAILED \(failures=(\d+)", output)
        status = "completed"
        if sandbox and output.startswith(b"bwrap:"):
            status = "sandbox_unavailable"
        return {"status": status, "passed": result.returncode == 0 and b"\nOK\n" in output,
                "exit_code": result.returncode,
                "test_count": int(count[1]) if count else None,
                "assertion_failures": int(failures[1]) if failures else 0,
                "stdout_sha256": digest(root / "stdout"),
                "stderr_sha256": hashlib.sha256(output).hexdigest()}


def verify_fixtures(root: Path) -> dict:
    reports = []
    for identity in TASK_IDS:
        task = root / identity
        before = run_checks(task, (task / "baseline.py").read_text(), sandbox=False)
        after = run_checks(task, (task / "reference.py").read_text(), sandbox=False)
        reports.append({"task": identity, "baseline": before, "reference": after})
    return {"passed": all(row["baseline"]["exit_code"] == 1
                           and row["baseline"]["assertion_failures"] > 0
                           and row["baseline"]["test_count"] == row["reference"]["test_count"]
                           and not row["baseline"]["passed"] and row["reference"]["passed"]
                           for row in reports), "tasks": reports, "manifest": task_manifest(root),
            "scope": "Locally authored fixture validation only; no model evaluated."}


def evaluate_candidates(root: Path, candidates: Path) -> dict:
    reports = [{"task": identity, "candidate_sha256": digest(candidates / f"{identity}.py"),
                **run_checks(root / identity, (candidates / f"{identity}.py").read_text(), sandbox=True)}
               for identity in TASK_IDS]
    return {"passed": all(row["passed"] for row in reports), "tasks": reports,
            "manifest": task_manifest(root), "sandbox_required": True,
            "scope": "Three small synthetic engineering tasks; not broad coding superiority or adversarial evaluator integrity."}


def save_report(path: Path, report: dict):
    with open(path, "x", opener=lambda name, flags: os.open(name, flags, 0o600)) as output:
        json.dump(report, output, indent=2)
        output.write("\n")
