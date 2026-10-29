from __future__ import annotations

import argparse
import json
import mmap
import os
import re
import shutil
import struct
import subprocess
import tempfile
from pathlib import Path


def rpm_override(version: str) -> dict:
    match = re.fullmatch(r"(\d+\.\d+\.\d+)(?:-([A-Za-z0-9]+(?:\.[A-Za-z0-9]+)*))?", version)
    if not match:
        raise ValueError("RPM mapping supports a numeric release and dotted alphanumeric prerelease only")
    release, prerelease = match.groups()
    if not prerelease:
        return {}
    return {"version": release, "bundle": {"linux": {"rpm": {"release": f"0.{prerelease}"}}}}


def bundle(root: Path, formats: list[str], debug: bool = False) -> None:
    binary = root / "desktop/src-tauri/target" / ("debug" if debug else "release") / "bifang-desktop"
    with binary.open("rb") as source, mmap.mmap(source.fileno(), 0, access=mmap.ACCESS_READ) as contents:
        if contents.find(b"__TAURI_BUNDLE_TYPE_VAR_UNK") == -1:
            raise ValueError("Build an unbundled desktop first; refusing to reuse an already patched executable")
    configuration = json.loads((root / "desktop/src-tauri/tauri.conf.json").read_text())
    override = rpm_override(configuration["version"])
    runtime = re.fullmatch(r"glibc (\d+\.\d+)", os.confstr("CS_GNU_LIBC_VERSION") or "")
    if runtime is None:
        raise ValueError("Package on the selected GNU glibc baseline")
    capability_suffix = "(64bit)" if struct.calcsize("P") == 8 else ""
    override.setdefault("bundle", {}).setdefault("linux", {}).setdefault("rpm", {})["depends"] = [
        f"libc.so.6(GLIBC_{runtime[1]}){capability_suffix}"
    ]
    with tempfile.TemporaryDirectory(prefix=".bifang-unbundled-", dir=binary.parent) as temporary:
        snapshot = Path(temporary) / "snapshot"
        staged = Path(temporary) / "staged"
        shutil.copy2(binary, snapshot)

        def restore() -> None:
            shutil.copy2(snapshot, staged)
            staged.replace(binary)

        try:
            for selected in formats:
                if selected not in {"deb", "appimage", "rpm"}:
                    raise ValueError("Select deb, appimage or rpm")
                restore()
                command = ["npm", "--prefix", str(root / "desktop"), "run", "tauri", "--", "bundle", "--bundles", selected]
                if debug:
                    command.append("--debug")
                if selected == "rpm" and override:
                    command.extend(["--config", json.dumps(override, separators=(",", ":"))])
                subprocess.run(command, cwd=root, check=True)
        finally:
            restore()


def main() -> None:
    parser = argparse.ArgumentParser(description="Bundle each Linux format from the same pristine compiled desktop")
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--formats", nargs="+", choices=["deb", "appimage", "rpm"], default=["deb", "appimage", "rpm"])
    arguments = parser.parse_args()
    bundle(Path(__file__).resolve().parents[1], arguments.formats, arguments.debug)


if __name__ == "__main__":
    main()
