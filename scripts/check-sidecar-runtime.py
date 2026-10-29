from __future__ import annotations

import argparse
import hashlib
import json
import runpy
import tempfile
from pathlib import Path


def extract_native(reader, destination: Path) -> int:
    total = 0
    count = 0
    if len(reader.toc) > 10000:
        raise ValueError("Archive member count exceeds audit bound")
    for name, metadata in reader.toc.items():
        if metadata[-1] not in {"b", "x"}:
            continue
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts or "\\" in name:
            raise ValueError("Unsafe archive member path")
        total += metadata[2]
        if metadata[2] < 0 or metadata[2] > 268435456 or total > 536870912:
            raise ValueError("Archive extraction size exceeds audit bound")
        content = reader.extract(name)
        if len(content) != metadata[2]:
            raise ValueError("Archive member size mismatch")
        if not content.startswith(b"\x7fELF"):
            continue
        output = destination / relative
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("xb") as target:
            target.write(content)
        count += 1
    return count


def audit(sidecar: Path, ceiling: str) -> dict:
    from PyInstaller.archive.readers import CArchiveReader

    runtime = runpy.run_path(str(Path(__file__).with_name("check-linux-runtime.py")))
    with tempfile.TemporaryDirectory(prefix="bifang-runtime-") as temporary:
        destination = Path(temporary)
        extract_native(CArchiveReader(str(sidecar)), destination)
        report = runtime["audit"](destination, ceiling)
    with sidecar.open("rb") as source:
        report["sidecar_sha256"] = hashlib.file_digest(source, "sha256").hexdigest()
    report["scope"] = "Static ELF audit of PyInstaller binary/data members; not dependency resolution, licence review or GUI validation"
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("sidecar", type=Path)
    parser.add_argument("--max-glibc", required=True)
    parser.add_argument("--output", type=Path, required=True)
    options = parser.parse_args()
    report = audit(options.sidecar, options.max_glibc)
    with options.output.open("x") as output:
        output.write(json.dumps(report, indent=2) + "\n")
    print(f"{'PASS' if report['passed'] else 'FAIL'}: {report['elf_count']} embedded ELF files")
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
