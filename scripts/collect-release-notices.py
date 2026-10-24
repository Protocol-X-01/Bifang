import argparse
import importlib.metadata
import json
import sys
import sysconfig
from pathlib import Path


def license_files(root):
    candidates = []
    for entry in root.iterdir():
        if entry.name.lower().startswith(("license", "licence", "copying", "notice", "copyright")):
            candidates.extend(entry.rglob("*") if entry.is_dir() else [entry])
    return sorted(candidate for candidate in candidates
                  if candidate.is_file() and candidate.resolve().is_relative_to(root.resolve()))


def main():
    parser = argparse.ArgumentParser(description="Collect installed dependency notices for release review")
    parser.add_argument("--cargo-metadata", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--supplementary-notices", type=Path)
    options = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    options.output.mkdir(parents=True, exist_ok=False)
    components = []
    sections = ["Bifang third-party notices\n\nGenerated from the build environment. Includes build dependencies conservatively.\nThis inventory is not a legal certification or a complete binary SBOM.\nSystem-provided dynamic libraries retain their distribution's licensing.\n"]

    def collect(ecosystem, name, version, license_name, files, authors=""):
        readable = []
        for file in files:
            try:
                readable.append((file.name, file.read_text(encoding="utf-8")))
            except (UnicodeError, OSError):
                continue
        components.append({"ecosystem": ecosystem, "name": name, "version": version,
                           "declared_license": license_name, "notice_files": [name for name, _ in readable]})
        sections.append(f"\n{'=' * 72}\n{ecosystem}: {name} {version}\nDeclared license: {license_name}\nAuthors: {authors}\n")
        for filename, contents in readable:
            sections.append(f"\n--- {filename} ---\n{contents}\n")

    for distribution in sorted(importlib.metadata.distributions(), key=lambda item: item.metadata["Name"].lower()):
        files = [distribution.locate_file(file) for file in (distribution.files or [])
                 if ".dist-info" in str(file) and any(word in str(file).lower() for word in ("license", "licence", "copying", "notice"))]
        metadata = distribution.metadata
        collect("Python", metadata["Name"], distribution.version,
                metadata.get("License-Expression") or metadata.get("License") or "Not declared",
                files, metadata.get("Author-email") or metadata.get("Author", ""))
    python_license = Path(sysconfig.get_path("stdlib")) / "LICENSE.txt"
    if not python_license.is_file():
        raise RuntimeError("Python runtime license is missing from the build environment")
    collect("Runtime", "CPython", ".".join(map(str, sys.version_info[:3])),
            "PSF-2.0 and included notices", [python_license])

    lock = json.loads((root / "desktop/package-lock.json").read_text())
    for relative, package in sorted(lock["packages"].items()):
        if not relative or package.get("dev"):
            continue
        directory = root / "desktop" / relative
        metadata = json.loads((directory / "package.json").read_text())
        collect("npm", metadata["name"], metadata["version"],
                str(metadata.get("license", "Not declared")), license_files(directory))

    metadata = json.loads(options.cargo_metadata.read_text())
    resolved = {node["id"] for node in metadata["resolve"]["nodes"]}
    for package in sorted(metadata["packages"], key=lambda item: item["name"]):
        if package["id"] not in resolved or package["source"] is None:
            continue
        directory = Path(package["manifest_path"]).parent
        files = license_files(directory)
        if package.get("license_file"):
            declared = directory / package["license_file"]
            if declared.is_file() and declared not in files:
                files.append(declared)
        if not files and options.supplementary_notices:
            supplementary = options.supplementary_notices / f"{package['name']}-{package['version']}"
            if supplementary.is_dir():
                files.extend(license_files(supplementary))
        collect("Cargo", package["name"], package["version"],
                package.get("license") or "See declared license file", files,
                ", ".join(package.get("authors", [])))
        source = f"https://crates.io/api/v1/crates/{package['name']}/{package['version']}/download"
        components[-1]["upstream_source"] = source
        sections.append(f"Unmodified crate source: {source}\n")

    for directory in ("libssl3t64", "libffi8", "libbz2-1.0", "liblzma5", "zlib1g", "libsqlite3-0", "libgcc-s1", "libexpat1", "libuuid1", "libedit2"):
        file = Path("/usr/share/doc") / directory / "copyright"
        if file.is_file():
            collect("Supplementary distribution notice", directory, "build-host copy",
                    "See notice; not a binary version assertion", [file])
    for name in ("GPL-3", "LGPL-2.1"):
        file = Path("/usr/share/common-licenses") / name
        if file.is_file():
            collect("Supplementary license text", name, "standard text",
                    "Referenced by distribution notices; not Bifang's license", [file])

    (options.output / "THIRD_PARTY_NOTICES.txt").write_text("\n".join(sections))
    (options.output / "dependency-inventory.json").write_text(json.dumps({"components": components}, indent=2) + "\n")
    print(json.dumps({"components": len(components), "without_notice_files": sum(not component["notice_files"] for component in components)}))


if __name__ == "__main__":
    main()
