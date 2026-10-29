from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import quote


def digest(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def payload_file(root: Path, relative: str) -> Path:
    name = Path(relative)
    candidate = root / name
    if name.is_absolute() or ".." in name.parts or candidate.is_symlink():
        raise ValueError("Expected a regular relative payload file")
    if not candidate.resolve(strict=True).is_relative_to(root.resolve(strict=True)) or not candidate.is_file():
        raise ValueError("Payload path escapes its extracted root")
    return candidate


def owners(output: str) -> list[tuple[str, Path]]:
    matches = []
    for line in output.splitlines():
        package, separator, filename = line.partition(": ")
        if separator and ", " not in package and re.fullmatch(r"[a-z0-9][a-z0-9+.-]*(?::[a-z0-9-]+)?", package):
            path = Path(filename)
            if path.is_absolute() and path.is_file():
                matches.append((package, path))
    return sorted(set(matches), key=lambda item: (item[0], str(item[1])))


def fingerprint(path: Path) -> dict:
    notes = subprocess.run(["readelf", "--notes", str(path)], check=True, capture_output=True, text=True, timeout=30)
    build_ids = re.findall(r"Build ID: ([0-9a-fA-F]+)", notes.stdout)
    with tempfile.TemporaryDirectory(prefix="bifang-native-notice-") as temporary:
        section_file = Path(temporary) / "sections.bin"
        subprocess.run(["objcopy", "-O", "binary", "--only-section=.text", "--only-section=.rodata", str(path), str(section_file)],
                       check=True, capture_output=True, timeout=60)
        size = section_file.stat().st_size
        if not size or size > 268_435_456:
            raise ValueError("Missing or excessive text/rodata fingerprint input")
        return {"build_ids": build_ids, "text_rodata_sha256": digest(section_file), "text_rodata_bytes": size}


def correspondence(payload: dict, original: dict) -> bool:
    return bool(payload["build_ids"]) and payload == original


def retain_notice(documentation: Path, package: str, output: Path) -> dict:
    name = package.partition(":")[0]
    if not re.fullmatch(r"[a-z0-9][a-z0-9+.-]*", name):
        raise ValueError("Invalid distribution package name")
    source = documentation / name / "copyright"
    if not source.is_file() or not source.resolve().is_relative_to(documentation.resolve()):
        return {"retained": False}
    content = source.read_bytes()
    if len(content) > 8_388_608:
        raise ValueError("Distribution notice exceeds review bound")
    destination = output / (package.replace(":", "_") + ".copyright")
    destination.write_bytes(content)
    return {"retained": True, "file": destination.name, "sha256": hashlib.sha256(content).hexdigest()}


def audit(payload_root: Path, runtime_report: dict, output: Path) -> dict:
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    notices = output / "distribution-notices"
    notices.mkdir()
    binaries = []
    providers = {}
    fingerprints = {}
    for binary in runtime_report["binaries"]:
        relative = binary["path"]
        path = payload_file(payload_root, relative)
        if digest(path) != binary["sha256"]:
            raise ValueError("Extracted payload does not match the supplied runtime audit")
        entry = {"path": relative, "sha256": binary["sha256"], "distribution_provider": None}
        if relative in {"usr/bin/bifang-desktop", "usr/bin/bifang-server"}:
            entry["classification"] = "Bifang build payload; dependency/runtime inventory remains separate"
            binaries.append(entry)
            continue
        if not re.fullmatch(r"[A-Za-z0-9_.+-]+", path.name):
            raise ValueError("Unexpected native payload filename")
        result = subprocess.run(["dpkg-query", "--search", "*/" + path.name], check=False,
                                capture_output=True, text=True, timeout=30)
        if result.returncode not in {0, 1}:
            raise RuntimeError("Distribution ownership query failed")
        signature = fingerprint(path)
        for package, candidate in owners(result.stdout):
            key = str(candidate.resolve())
            if key not in fingerprints:
                fingerprints[key] = fingerprint(candidate)
            if not correspondence(signature, fingerprints[key]):
                continue
            if package not in providers:
                metadata = subprocess.run(["dpkg-query", "-W", "-f=${binary:Package}\t${Version}\t${source:Package}\t${source:Version}", package],
                                          check=True, capture_output=True, text=True, timeout=30).stdout.split("\t")
                if len(metadata) != 4:
                    raise RuntimeError("Invalid distribution source metadata")
                providers[package] = {"package": metadata[0], "version": metadata[1], "source_package": metadata[2],
                    "source_version": metadata[3], "notice": retain_notice(Path("/usr/share/doc"), package, notices),
                    "distribution_source_page": "https://launchpad.net/ubuntu/+source/" + quote(metadata[2], safe="") + "/" + quote(metadata[3], safe="")}
            entry.update(distribution_provider=package, matching_system_path=str(candidate),
                         correspondence="GNU build ID plus identical text/rodata fingerprint; not full-file equality",
                         fingerprint=signature, system_file_sha256=digest(candidate))
            break
        binaries.append(entry)
    unresolved = [item["path"] for item in binaries if item["distribution_provider"] is None and "classification" not in item]
    report = {"scope": "Actual extracted native-file/provider correspondence and distribution copyright capture; not complete licence/source-delivery certification",
        "elf_files": len(binaries), "distribution_matched_files": sum(item["distribution_provider"] is not None for item in binaries),
        "bifang_build_files": sum("classification" in item for item in binaries), "unresolved_files": unresolved,
        "providers_without_notices": [name for name, item in providers.items() if not item["notice"]["retained"]],
        "providers": providers, "binaries": binaries,
        "corresponding_source_bundled": False, "pyinstaller_embedded_runtime_inventoried": False}
    (output / "runtime-provenance.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("payload", type=Path)
    parser.add_argument("--runtime-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    options = parser.parse_args()
    report = audit(options.payload, json.loads(options.runtime_report.read_text()), options.output)
    print(json.dumps({key: report[key] for key in ("elf_files", "distribution_matched_files", "bifang_build_files", "unresolved_files", "providers_without_notices")}))


if __name__ == "__main__":
    main()
