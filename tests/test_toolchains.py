import asyncio
import json
from types import SimpleNamespace

from bifang.cli import amain
from bifang.config import Config
from bifang.toolchains import inspect_toolchains


def test_toolchain_preview_detects_locked_profiles_without_executing_manifests(tmp_path, monkeypatch):
    monkeypatch.setattr("bifang.toolchains.shutil.which", lambda manager: "/fixture/tool")
    names = ["pyproject.toml", "uv.lock", "package.json", "package-lock.json", "Cargo.toml", "Cargo.lock"]
    for name in names:
        (tmp_path / name).write_text("unparsed, potentially executable project data")
    before = {path.name: path.read_bytes() for path in tmp_path.iterdir()}
    profiles = inspect_toolchains(tmp_path)["profiles"]
    assert [row["bootstrap_argv"] for row in profiles] == [
        ["uv", "sync", "--locked"], ["npm", "ci", "--ignore-scripts"], ["cargo", "fetch", "--locked"]]
    assert all(not row["automatic_install"] for row in profiles)
    assert {path.name: path.read_bytes() for path in tmp_path.iterdir()} == before


def test_toolchain_preview_does_not_substitute_npm_for_other_lock_managers(tmp_path):
    (tmp_path / "package.json").write_text("{}")
    (tmp_path / "pnpm-lock.yaml").write_text("fixture")
    profile = inspect_toolchains(tmp_path)["profiles"][0]
    assert profile["bootstrap_argv"] == []
    assert profile["manager_selection_required"]


def test_toolchain_preview_skips_symlinked_manifests_and_handles_empty_project(tmp_path):
    (tmp_path / "pyproject.toml").symlink_to(tmp_path / "outside-not-read")
    assert inspect_toolchains(tmp_path)["profiles"] == []


def test_cli_toolchains_does_not_create_worktree_or_print_credentials(tmp_path, monkeypatch, capsys):
    (tmp_path / "pyproject.toml").write_text("fixture")
    monkeypatch.setattr("bifang.cli.Config.load", lambda: Config())

    def forbidden(*args, **kwargs):
        raise AssertionError("Read-only inspection must not create a workspace")

    monkeypatch.setattr("bifang.cli.Workspace.create", forbidden)
    asyncio.run(amain(SimpleNamespace(cmd="toolchains", workspace=str(tmp_path), provider=None)))
    result = json.loads(capsys.readouterr().out)
    assert result["profiles"][0]["id"] == "python-uv"
    assert not result["automatic_install"]
