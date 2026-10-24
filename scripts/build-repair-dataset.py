import argparse
import difflib
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from bifang.dataset_export import encoded_line


CASES = [
    ("plan-atomicity", "task-plan", "src/bifang/tools/tasks.py", "tests/test_task_plan.py",
     "test_rejected_updates_preserve_last_valid_state",
     "        items = TODO_LIST.validate_python(todos, strict=True)",
     "        self._items = []\n        items = TODO_LIST.validate_python(todos, strict=True)",
     "Rejected plan updates destroy the previous valid plan. Preserve state and revision when validation fails."),
    ("plan-snapshot-alias", "task-plan", "src/bifang/tools/tasks.py", "tests/test_task_plan.py",
     "test_plan_replaces_clears_and_does_not_expose_mutable_state",
     "item.model_dump()", "item.__dict__",
     "Mutating a returned task snapshot changes the live plan. Return independent snapshot data."),
    ("plan-single-active", "task-plan", "src/bifang/tools/tasks.py", "tests/test_task_plan.py",
     "test_rejected_updates_preserve_last_valid_state",
     'item.status == "in_progress" for item in items) > 1',
     'item.status == "in_progress" for item in items) > 2',
     "The plan incorrectly permits two active tasks. Enforce at most one without changing accepted statuses."),
    ("export-byte-bound", "dataset-export", "src/bifang/dataset_export.py", "tests/test_dataset_export.py",
     "test_size_cap_never_truncates_a_record",
     "if size + len(line) > max_bytes:", "if size > max_bytes:",
     "The JSONL writer can exceed its exact UTF-8 byte cap. Check the next complete record before writing it."),
    ("final-code-boundary", "dataset-curation", "src/bifang/dataset_curation.py", "tests/test_dataset_curation.py",
     "test_final_code_consistency_does_not_accept_code_only_in_reasoning",
     'final = output.rsplit("</think>", 1)[-1]', 'final = output',
     "Code inside reasoning is being accepted as final answer code. Check only the final response segment."),
    ("question-case-group", "dataset-curation", "src/bifang/dataset_curation.py", "tests/test_dataset_curation.py",
     "test_numeric_variants_share_a_group",
     "question.casefold().split()", "question.split()",
     "Case-only and numeric variants of the same question receive different groups. Restore consistent grouping."),
]


def run_check(root, selector):
    environment = {key: value for key, value in os.environ.items() if key in {"PATH", "LANG", "LC_ALL"}}
    environment.update(PYTHONPATH=str(root / "src"), PYTHONDONTWRITEBYTECODE="1",
                       PYTEST_DISABLE_PLUGIN_AUTOLOAD="1", HOME=str(root / "home"),
                       XDG_STATE_HOME=str(root / "state"))
    command = [sys.executable, "-c",
        "import pathlib,sys,bifang,pytest; "
        "assert pathlib.Path(bifang.__file__).resolve().is_relative_to(pathlib.Path.cwd()); "
        "sys.exit(pytest.main(sys.argv[1:]))", "-q", "-c", "/dev/null", selector]
    result = subprocess.run(command, cwd=root, env=environment, capture_output=True,
                            text=True, timeout=60)
    return {"exit_code": result.returncode,
            "stdout": result.stdout, "stderr": result.stderr,
            "stdout_sha256": hashlib.sha256(result.stdout.encode()).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description="Build locally executed synthetic Bifang regression-repair examples")
    parser.add_argument("--output-directory", type=Path, required=True)
    options = parser.parse_args()
    repository = Path(__file__).resolve().parents[1]
    options.output_directory.mkdir(mode=0o700, exist_ok=False)
    records, receipts = [], []
    for identity, family, filename, testfile, testname, original, mutated, issue in CASES:
        fixed = (repository / filename).read_text()
        test_source = (repository / testfile).read_text()
        if fixed.count(original) != 1:
            raise ValueError(f"Mutation anchor changed for {identity}; review before regenerating")
        broken = fixed.replace(original, mutated, 1)
        patch = "".join(difflib.unified_diff(broken.splitlines(keepends=True), fixed.splitlines(keepends=True),
                                             fromfile=f"a/{filename}", tofile=f"b/{filename}"))
        selector = f"{testfile}::{testname}"
        with tempfile.TemporaryDirectory(prefix="bifang-first-party-repair-") as temporary:
            root = Path(temporary)
            shutil.copytree(repository / "src", root / "src", ignore=shutil.ignore_patterns("__pycache__"))
            (root / testfile).parent.mkdir(parents=True)
            (root / testfile).write_text(test_source)
            (root / filename).write_text(broken)
            before = run_check(root, selector)
            if before["exit_code"] != 1 or "FAILED" not in before["stdout"] or "ERROR collecting" in before["stdout"]:
                raise RuntimeError(f"Baseline did not demonstrate the intended regression: {identity}")
            for arguments in (["git", "apply", "--check", "-"], ["git", "apply", "-"]):
                subprocess.run(arguments, input=patch, text=True, cwd=root, check=True, capture_output=True)
            if (root / filename).read_text() != fixed:
                raise RuntimeError("Applied patch does not match expected fixed source")
            after = run_check(root, selector)
            if after["exit_code"] != 0:
                raise RuntimeError(f"Repair did not pass the regression checks: {identity}")
        prompt = (f"Repair this Bifang regression. {issue}\nReturn only a unified diff for {filename}. "
                  f"Do not change the tests.\n\nFile {filename}:\n```python\n{broken}\n```\n\n"
                  f"Regression tests {testfile}:\n```python\n{test_source}\n```\n\nRun: pytest -q {selector}")
        records.append({"messages": [{"role": "user", "content": prompt},
                                     {"role": "assistant", "content": patch}]})
        receipts.append({"id": identity, "family": family, "license": "Apache-2.0",
            "origin": "Codex-authored synthetic mutations of Bifang local source; not historical commits or model-generated agent trajectories",
            "file": filename, "test_selector": selector,
            "before_sha256": hashlib.sha256(broken.encode()).hexdigest(),
            "after_sha256": hashlib.sha256(fixed.encode()).hexdigest(),
            "tests_sha256": hashlib.sha256(test_source.encode()).hexdigest(),
            "execution_verified_locally": True, "before": before, "after": after})
        print(f"Verified regression -> patch -> passing checks: {identity}", flush=True)
    payload = b"".join(encoded_line(record) for record in records)
    if len(payload) >= 900_000_000:
        raise RuntimeError("First-party seed exceeds its byte cap")
    path = options.output_directory / "train.jsonl"
    path.write_bytes(payload)
    if sum(1 for _ in path.open(encoding="utf-8")) != len(records):
        raise RuntimeError("JSONL record verification failed")
    (options.output_directory / "verification.json").write_bytes(encoded_line({"examples": receipts}))
    manifest = {"examples": len(records), "bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest(),
                "families": sorted({receipt["family"] for receipt in receipts}), "license": "Apache-2.0",
                "limitations": ["Small synthetic mutation-repair training seed, not an independent benchmark.",
                    "Tests establish these regression contracts, not full semantic correctness or model superiority.",
                    "Cases sharing a family must stay in one partition in future mixes.",
                    "No model generated these patches during this run; no data uploaded or model trained."]}
    (options.output_directory / "manifest.json").write_bytes(encoded_line(manifest))
    (options.output_directory / "LICENSE").write_bytes((repository / "LICENSE").read_bytes())
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
