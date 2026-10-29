from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def collect(root: Path, target: str) -> dict:
    if target == "x86_64-pc-windows-msvc":
        formats = {"nsis": "*.exe", "msi": "*.msi"}
    elif target in {"x86_64-apple-darwin", "aarch64-apple-darwin"}:
        formats = {"dmg": "*.dmg"}
    else:
        raise ValueError("Unsupported platform package target")
    packages = []
    for application in ("desktop", "companion"):
        for kind, pattern in formats.items():
            candidates = sorted((root / application / "src-tauri/target/release/bundle" / kind).glob(pattern))
            if len(candidates) != 1:
                raise ValueError(f"Expected exactly one {application} {kind} installer")
            path = candidates[0]
            if path.is_symlink() or path.stat().st_size == 0:
                raise ValueError("Installer must be a nonempty regular file")
            with path.open("rb") as source:
                digest = hashlib.file_digest(source, "sha256").hexdigest()
            packages.append({"application": application, "format": kind,
                             "path": path.relative_to(root).as_posix(),
                             "sha256": digest, "bytes": path.stat().st_size})
    return {"target": target, "packages": packages,
            "scope": "Native runner build artifacts, not installed GUI or signing acceptance"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", required=True)
    parser.add_argument("--output", required=True, type=Path)
    arguments = parser.parse_args()
    report = collect(Path(__file__).resolve().parents[1], arguments.target)
    with arguments.output.open("x", encoding="utf-8") as output:
        output.write(json.dumps(report, indent=2) + "\n")
