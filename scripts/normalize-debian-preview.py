from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import tarfile
import tempfile
from pathlib import Path, PurePosixPath


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def payload_manifest(package: Path) -> dict:
    process = subprocess.Popen(["dpkg-deb", "--fsys-tarfile", str(package)], stdout=subprocess.PIPE)
    files = {}
    try:
        with tarfile.open(fileobj=process.stdout, mode="r|") as archive:
            for member in archive:
                name = PurePosixPath(member.name).as_posix()
                if name == "." and member.isdir():
                    continue
                if (name in files or PurePosixPath(name).is_absolute() or ".." in PurePosixPath(name).parts
                        or not (member.isfile() or member.isdir() or member.issym() or member.islnk())):
                    raise ValueError("Unexpected or duplicate Debian payload member")
                content = archive.extractfile(member) if member.isfile() else None
                files[name] = {
                    "type": member.type.decode("ascii"), "mode": member.mode,
                    "uid": member.uid, "gid": member.gid, "size": member.size,
                    "link": member.linkname,
                    "sha256": hashlib.file_digest(content, "sha256").hexdigest() if content else None,
                }
        if process.wait(timeout=30):
            raise RuntimeError("Could not inspect Debian payload")
    finally:
        process.stdout.close()
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=10)
    return files


def normalize(package: Path, output: Path, version: str, previous: str, stable: str, expected_sha256: str) -> dict:
    package = package.resolve(strict=True)
    if output.exists() or output.is_symlink():
        raise ValueError("Refusing to overwrite an existing package")
    if digest(package) != expected_sha256:
        raise ValueError("Input package checksum does not match the reviewed artifact")
    if not re.fullmatch(r"\d+\.\d+\.\d+~[A-Za-z0-9.+]+", version):
        raise ValueError("Use an explicit Debian prerelease version with a tilde")
    for earlier, later in ((previous, version), (version, stable)):
        if subprocess.run(["dpkg", "--compare-versions", earlier, "lt", later], check=False).returncode:
            raise ValueError("Preview must sort after the published version and before stable")
    original_version = subprocess.run(["dpkg-deb", "-f", str(package), "Version"],
                                      check=True, capture_output=True, text=True).stdout.strip()
    original_payload = payload_manifest(package)
    with tempfile.TemporaryDirectory(prefix="bifang-debian-version-") as temporary:
        root = Path(temporary) / "package"
        candidate = Path(temporary) / "normalized.deb"
        subprocess.run(["dpkg-deb", "--raw-extract", str(package), str(root)], check=True)
        metadata = root / "DEBIAN"
        control = metadata / "control"
        if control.is_symlink() or not control.is_file():
            raise ValueError("Expected a regular Debian control file")
        before = {path.relative_to(metadata).as_posix(): digest(path) for path in metadata.rglob("*") if path.is_file()}
        content = control.read_text()
        updated, count = re.subn(r"^Version: [^\n]+$", f"Version: {version}", content, flags=re.MULTILINE)
        if count != 1:
            raise ValueError("Expected exactly one Debian Version field")
        control.write_text(updated)
        subprocess.run(["dpkg-deb", "--build", "--root-owner-group", "-Zxz", str(root), str(candidate)],
                       check=True, capture_output=True)
        if payload_manifest(candidate) != original_payload:
            raise RuntimeError("Package version rewrite changed installed payload metadata or content")
        for name, expected in before.items():
            if name != "control" and digest(metadata / name) != expected:
                raise RuntimeError("Package version rewrite changed a control companion file")
        with candidate.open("rb") as source, output.open("xb") as destination:
            while block := source.read(1024 * 1024):
                destination.write(block)
    return {
        "input_sha256": expected_sha256, "output_sha256": digest(output),
        "original_debian_version": original_version, "debian_version": version,
        "published_predecessor": previous, "future_stable": stable,
        "upgrade_order_verified": True, "payload_manifest_unchanged": True,
        "payload_members": len(original_payload), "other_control_files_unchanged": True,
        "scope": "Debian control Version correction; installed contents, ownership, permissions and links compared",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("package", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--version", required=True)
    parser.add_argument("--previous-version", required=True)
    parser.add_argument("--stable-version", required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--report", required=True, type=Path)
    arguments = parser.parse_args()
    if arguments.report.exists() or arguments.report.is_symlink():
        raise ValueError("Refusing to overwrite an existing report")
    report = normalize(arguments.package, arguments.output, arguments.version, arguments.previous_version,
                       arguments.stable_version, arguments.expected_sha256)
    with arguments.report.open("x") as stream:
        stream.write(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
