import asyncio
import json
import shlex
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from bifang.cli import amain
from bifang.config import Config
from bifang.workspace import Workspace


def git(root, *arguments):
    return subprocess.check_output(["git", "-C", str(root), *arguments])


def repository(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    subprocess.run(["git", "init", str(root)], check=True, capture_output=True)
    git(root, "config", "user.name", "Fixture")
    git(root, "config", "user.email", "fixture@example.test")
    (root / "code.py").write_text("before\n")
    git(root, "add", ".")
    git(root, "commit", "-m", "Fixture")
    return root


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setattr("bifang.cli.Config.load", lambda: Config(enable_memory=False, enable_conversation_history=False))
    return repository(tmp_path)


def arguments(source, operation, **extra):
    return SimpleNamespace(workspace=str(source), cmd=operation, provider=None, box=None, **extra)


def test_cli_patch_uses_existing_box_without_creating_another_or_mutating_index(project, capsys):
    box = Workspace.create(project)
    (box.root / "code.py").write_text("after\n")
    (box.root / "new.py").write_text("new file\n")
    (box.root / "staged.py").write_text("staged file\n")
    git(box.root, "add", "staged.py")
    index = Path(git(box.root, "rev-parse", "--git-path", "index").decode().strip())
    previous_index = index.read_bytes()
    previous_trees = git(project, "worktree", "list", "--porcelain")
    asyncio.run(amain(arguments(project, "patch")))
    patch = capsys.readouterr().out
    assert "+after" in patch and "+new file" in patch and "+staged file" in patch
    assert index.read_bytes() == previous_index
    assert git(project, "worktree", "list", "--porcelain") == previous_trees
    assert (project / "code.py").read_text() == "before\n"


def test_missing_box_patch_does_not_create_one(project):
    before = git(project, "worktree", "list", "--porcelain")
    with pytest.raises(RuntimeError, match="No matching"):
        asyncio.run(amain(arguments(project, "patch")))
    assert git(project, "worktree", "list", "--porcelain") == before


def test_multiple_boxes_require_explicit_selection_and_listing_is_read_only(project, capsys):
    first, second = Workspace.create(project), Workspace.create(project)
    (first.root / "code.py").write_text("first candidate\n")
    (second.root / "code.py").write_text("second candidate\n")
    before = git(project, "worktree", "list", "--porcelain")
    with pytest.raises(RuntimeError, match="Multiple"):
        asyncio.run(amain(arguments(project, "patch")))
    asyncio.run(amain(arguments(project, "boxes")))
    listing = json.loads(capsys.readouterr().out)
    assert {row["id"] for row in listing} == {first.root.name, second.root.name}
    selected = arguments(project, "patch")
    selected.box = second.root.name
    asyncio.run(amain(selected))
    patch = capsys.readouterr().out
    assert "+second candidate" in patch and "+first candidate" not in patch
    assert git(project, "worktree", "list", "--porcelain") == before


def test_discard_denial_preserves_box_and_yes_removes_only_selected_box(project, monkeypatch):
    first, second = Workspace.create(project), Workspace.create(project)
    (first.root / "code.py").write_text("preserve until confirmed\n")
    selected = arguments(project, "discard", yes=False)
    selected.box = first.root.name
    monkeypatch.setattr("builtins.input", lambda prompt: "n")
    asyncio.run(amain(selected))
    assert first.root.exists() and second.root.exists()
    selected.yes = True
    asyncio.run(amain(selected))
    assert not first.root.exists() and second.root.exists()
    assert (project / "code.py").read_text() == "before\n"


def test_box_selection_cannot_cross_repository_or_follow_a_symlink(project, tmp_path):
    first = Workspace.create(project)
    other_parent = tmp_path / "other"
    other_parent.mkdir()
    other = Workspace.create(repository(other_parent))
    with pytest.raises(RuntimeError, match="No matching"):
        Workspace.open_existing(project, other.root.name)
    saved = first.root.with_name("saved-fixture")
    first.root.rename(saved)
    first.root.symlink_to(saved, target_is_directory=True)
    try:
        assert not Workspace.list_existing(project)
    finally:
        first.root.unlink()
        saved.rename(first.root)


@pytest.mark.parametrize("identity", ["../outside", "not-a-box", "", "deadbeef0"])
def test_box_id_is_bounded(project, identity):
    with pytest.raises(ValueError):
        Workspace.open_existing(project, identity)


def test_run_strips_separator_preserves_argv_and_can_use_existing_box(project, monkeypatch):
    box = Workspace.create(project)
    seen = []

    async def execute(policy, command, timeout, use_bwrap):
        seen.append((policy.root, command, use_bwrap))
        return {"returncode": 0}

    monkeypatch.setattr("bifang.cli.run_command", execute)
    monkeypatch.setattr("builtins.input", lambda prompt: "y")
    selected = arguments(project, "run", command=["--", "python3", "-c", "print('quoted argument')"])
    selected.box = box.root.name
    asyncio.run(amain(selected))
    assert seen == [(box.root, shlex.join(selected.command[1:]), True)]


def test_diff_with_newline_filename_preserves_real_index(project):
    (project / "newline\nfile.py").write_text("new content\n")
    original_index = (project / ".git/index").read_bytes()
    assert "+new content" in Workspace(project, project).diff()
    assert (project / ".git/index").read_bytes() == original_index
