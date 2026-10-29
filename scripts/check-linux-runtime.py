from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path


def version_tuple(value: str) -> tuple[int, ...]:
    if not re.fullmatch(r"[0-9]+(?:\.[0-9]+)+", value):
        raise ValueError("Expected a numeric dotted runtime version")
    return tuple(int(part) for part in value.split("."))


def requirements(output: str) -> dict[str, str]:
    needs = output.partition("Version needs section")[2]
    versions: dict[str, str] = {}
    for family, version in re.findall(r"Name: (GLIBC|GLIBCXX|CXXABI)_([0-9]+(?:\.[0-9]+)+)", needs):
        if version_tuple(version) > version_tuple(versions.get(family, "0.0")):
            versions[family] = version
    return versions


def audit(root: Path, max_glibc: str | None = None) -> dict:
    root = root.resolve(strict=True)
    if max_glibc is not None:
        version_tuple(max_glibc)
    binaries = []
    violations = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            if not path.resolve().is_relative_to(root):
                violations.append(f"External symlink: {relative}")
            continue
        if not path.is_file():
            continue
        with path.open("rb") as source:
            if source.read(4) != b"\x7fELF":
                continue
            source.seek(0)
            digest = hashlib.file_digest(source, "sha256").hexdigest()
        versions = subprocess.run(["readelf", "--version-info", "--wide", str(path)],
                                  check=True, capture_output=True, text=True, timeout=20)
        dynamic = subprocess.run(["readelf", "--dynamic", "--wide", str(path)],
                                 check=True, capture_output=True, text=True, timeout=20)
        runtime = requirements(versions.stdout)
        if max_glibc and version_tuple(runtime.get("GLIBC", "0.0")) > version_tuple(max_glibc):
            violations.append(f"{relative} requires GLIBC_{runtime['GLIBC']}, above {max_glibc}")
        binaries.append({"path": relative, "sha256": digest, "runtime_requirements": runtime,
                         "needed": re.findall(r"\(NEEDED\).*?\[(.*?)\]", dynamic.stdout),
                         "search_paths": re.findall(r"\((?:RUNPATH|RPATH)\).*?\[(.*?)\]", dynamic.stdout)})
    if not binaries:
        violations.append("No ELF binaries found")
    return {"scope": "Static extracted-payload audit; not installation, dependency resolution or GUI acceptance",
            "glibc_ceiling": max_glibc, "elf_count": len(binaries), "binaries": binaries,
            "violations": violations, "passed": not violations}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("--max-glibc")
    parser.add_argument("--output", required=True, type=Path)
    arguments = parser.parse_args()
    report = audit(arguments.root, arguments.max_glibc)
    arguments.output.write_text(json.dumps(report, indent=2) + "\n")
    print(f"{'PASS' if report['passed'] else 'FAIL'}: {report['elf_count']} ELF files, {len(report['violations'])} violations")
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
