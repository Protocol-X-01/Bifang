import json
import runpy
import subprocess
from pathlib import Path

import pytest

BUILDER = runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts/build-server-sidecar.py"))


@pytest.mark.parametrize("target,platform,machine,windows", [
    ("x86_64-unknown-linux-gnu", "linux", "x86_64", False),
    ("aarch64-unknown-linux-gnu", "linux", "aarch64", False),
    ("x86_64-apple-darwin", "darwin", "x86_64", False),
    ("aarch64-apple-darwin", "darwin", "arm64", False),
    ("x86_64-pc-windows-msvc", "win32", "AMD64", True),
    ("aarch64-pc-windows-msvc", "win32", "ARM64", True),
])
def test_native_plan_has_correct_interpreter_and_artifact(tmp_path, monkeypatch, target, platform, machine, windows):
    root = tmp_path / "project with spaces"
    root.mkdir()
    commands = []
    selected = str(tmp_path / "python with spaces")
    monkeypatch.setenv("PYTHON_BIN", selected)

    def run(command, **options):
        commands.append(command)
        assert options["cwd"] == root
        assert options["env"]["BIFANG_NO_DOTENV"] == "1"
        assert options.get("shell", False) is False
        if command[0] == selected:
            return subprocess.CompletedProcess(command, 0, json.dumps({
                "version": [3, 11], "platform": platform, "machine": machine,
            }))
        if command[0] == "rustc":
            return subprocess.CompletedProcess(command, 0, target + "\n")
        assert options["env"]["UV_PROJECT_ENVIRONMENT"] == str(root / ".build-server-venv")
        if "PyInstaller" in command:
            artifact = root / "desktop/src-tauri/binaries" / (f"bifang-server-{target}" + (".exe" if windows else ""))
            artifact.write_bytes(b"fixture artifact")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(subprocess, "run", run)
    artifact = BUILDER["build"](root)
    assert artifact.name == f"bifang-server-{target}" + (".exe" if windows else "")
    assert commands[2] == ["uv", "sync", "--locked", "--python", selected, "--extra", "dev", "--extra", "observability"]
    assert commands[3][0] == str(root / ".build-server-venv" / ("Scripts/python.exe" if windows else "bin/python"))
    assert commands[3][1:6] == ["-m", "PyInstaller", "--clean", "--noconfirm", "--onefile"]


@pytest.mark.parametrize("information", [
    {"version": [3, 12], "platform": "linux", "machine": "x86_64"},
    {"version": [3, 10], "platform": "linux", "machine": "x86_64"},
    {"version": [3, 11], "platform": "win32", "machine": "AMD64"},
    {"version": [3, 11], "platform": "linux", "machine": "aarch64"},
])
def test_incompatible_python_is_rejected_before_sync(tmp_path, monkeypatch, information):
    commands = []

    def run(command, **options):
        commands.append(command)
        return subprocess.CompletedProcess(command, 0, "x86_64-unknown-linux-gnu" if command[0] == "rustc" else json.dumps(information))

    monkeypatch.setattr(subprocess, "run", run)
    with pytest.raises(ValueError):
        BUILDER["build"](tmp_path)
    assert len(commands) == 2


def test_python_failure_stops_before_dependency_installation(tmp_path, monkeypatch):
    commands = []

    def run(command, **options):
        commands.append(command)
        raise subprocess.CalledProcessError(17, command)

    monkeypatch.setattr(subprocess, "run", run)
    with pytest.raises(subprocess.CalledProcessError) as error:
        BUILDER["build"](tmp_path)
    assert error.value.returncode == 17
    assert len(commands) == 1


def test_unknown_target_cannot_label_a_host_binary():
    with pytest.raises(ValueError, match="Unsupported"):
        BUILDER["validate_target"]("universal-apple-darwin", {"version": [3, 11]})


def test_shell_and_npm_entrypoints_use_the_same_portable_builder():
    root = Path(__file__).resolve().parents[1]
    shell = (root / "scripts/build-server-sidecar.sh").read_text()
    package = json.loads((root / "desktop/package.json").read_text())
    assert "build-server-sidecar.py" in shell
    assert "build-server-sidecar.py" in package["scripts"]["build:server"]
    assert "bash" not in package["scripts"]["build:server"]
