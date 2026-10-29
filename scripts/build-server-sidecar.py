from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def validate_target(target: str, python_info: dict) -> bool:
    platforms = {
        "x86_64-unknown-linux-gnu": ("linux", "x86_64"),
        "aarch64-unknown-linux-gnu": ("linux", "aarch64"),
        "x86_64-apple-darwin": ("darwin", "x86_64"),
        "aarch64-apple-darwin": ("darwin", "aarch64"),
        "x86_64-pc-windows-msvc": ("win32", "x86_64"),
        "aarch64-pc-windows-msvc": ("win32", "aarch64"),
    }
    expected = platforms.get(target)
    if expected is None:
        raise ValueError("Unsupported native sidecar target")
    if python_info.get("version") != [3, 11]:
        raise ValueError("Bifang desktop sidecar requires Python 3.11")
    machine = str(python_info.get("machine", "")).lower()
    machine = {"amd64": "x86_64", "arm64": "aarch64"}.get(machine, machine)
    if (python_info.get("platform"), machine) != expected:
        raise ValueError("Python and Rust must use the same native OS and architecture")
    return expected[0] == "win32"


def build(root: Path) -> Path:
    root = root.resolve(strict=True)
    environment = dict(os.environ, BIFANG_NO_DOTENV="1")
    python = os.environ.get("PYTHON_BIN") or sys.executable
    probe = "import json,platform,sys; print(json.dumps({'version':list(sys.version_info[:2]),'platform':sys.platform,'machine':platform.machine()}))"
    information = subprocess.run([python, "-c", probe], check=True, capture_output=True,
                                 text=True, cwd=root, env=environment)
    target = subprocess.run(["rustc", "--print", "host-tuple"], check=True, capture_output=True,
                            text=True, cwd=root, env=environment).stdout.strip()
    windows = validate_target(target, json.loads(information.stdout))
    build_venv = root / ".build-server-venv"
    environment["UV_PROJECT_ENVIRONMENT"] = str(build_venv)
    subprocess.run(["uv", "sync", "--locked", "--python", python, "--extra", "dev",
                    "--extra", "observability"], check=True, cwd=root, env=environment)
    interpreter = build_venv / ("Scripts/python.exe" if windows else "bin/python")
    destination = root / "desktop/src-tauri/binaries"
    destination.mkdir(parents=True, exist_ok=True)
    name = f"bifang-server-{target}"
    subprocess.run([
        str(interpreter), "-m", "PyInstaller", "--clean", "--noconfirm", "--onefile",
        "--name", name, "--distpath", str(destination),
        "--workpath", str(build_venv / "pyinstaller-work"), "--specpath", str(build_venv / "spec"),
        "--paths", str(root / "src"), "--collect-all", "uvicorn",
        str(root / "scripts/bifang-server-entry.py"),
    ], check=True, cwd=root, env=environment)
    artifact = destination / (name + (".exe" if windows else ""))
    if not artifact.is_file() or artifact.stat().st_size == 0:
        raise RuntimeError("PyInstaller did not produce the required native sidecar")
    return artifact


if __name__ == "__main__":
    print(build(Path(__file__).resolve().parents[1]))
