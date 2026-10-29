import hashlib
import subprocess

import pytest

from bifang.workspace import Workspace


@pytest.fixture
def folder(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    source = tmp_path / "project"
    source.mkdir()
    return source


@pytest.mark.parametrize("unborn", [False, True])
def test_empty_project_review_apply_and_discard_without_source_git_setup(folder, unborn):
    if unborn:
        subprocess.run(["git", "init", str(folder)], capture_output=True, check=True)
    workspace = Workspace.create(folder)
    try:
        (workspace.root / "hello.py").write_text("print('hello')\n")
        assert not (folder / "hello.py").exists()
        patch = workspace.diff()
        assert "+print('hello')" in patch
        assert workspace.apply(expected_patch_sha256=hashlib.sha256(patch.encode()).hexdigest())
        assert (folder / "hello.py").read_text() == "print('hello')\n"
        assert (folder / ".git").exists() == unborn
        if unborn:
            result = subprocess.run(["git", "-C", str(folder), "rev-parse", "--verify", "HEAD"], check=False, capture_output=True)
            assert result.returncode != 0
    finally:
        workspace.discard()
    assert folder.exists() and not workspace.root.exists()


def test_folder_edit_delete_binary_and_executable_changes(folder):
    (folder / "old.txt").write_text("old\n")
    (folder / "delete.txt").write_text("remove\n")
    workspace = Workspace.create(folder)
    try:
        (workspace.root / "old.txt").write_text("updated\n")
        (workspace.root / "delete.txt").unlink()
        (workspace.root / "image.bin").write_bytes(bytes(range(256)))
        (workspace.root / "run.sh").write_text("#!/bin/sh\nexit 0\n")
        (workspace.root / "run.sh").chmod(0o755)
        assert workspace.apply()
        assert (folder / "old.txt").read_text() == "updated\n"
        assert not (folder / "delete.txt").exists()
        assert (folder / "image.bin").read_bytes() == bytes(range(256))
        assert (folder / "run.sh").stat().st_mode & 0o111
    finally:
        workspace.discard()


def test_source_change_and_stale_review_refuse_apply(folder):
    workspace = Workspace.create(folder)
    try:
        (workspace.root / "new.py").write_text("first\n")
        digest = hashlib.sha256(workspace.diff().encode()).hexdigest()
        (workspace.root / "new.py").write_text("second\n")
        with pytest.raises(RuntimeError, match="changed after review"):
            workspace.apply(expected_patch_sha256=digest)
        assert not (folder / "new.py").exists()
        (folder / "owner.txt").write_text("keep\n")
        with pytest.raises(RuntimeError, match="original folder changed"):
            workspace.apply()
        assert not (folder / "new.py").exists()
    finally:
        workspace.discard()


def test_snapshot_refuses_symlinks_and_omits_internal_state(folder):
    (folder / ".bifang").mkdir()
    (folder / ".bifang" / "state.json").write_text("private\n")
    (folder / ".env").write_text("PRIVATE_FIXTURE=do-not-copy\n")
    (folder / ".env.example").write_text("PUBLIC_PLACEHOLDER=\n")
    workspace = Workspace.create(folder)
    try:
        assert not (workspace.root / ".bifang").exists()
        assert not (workspace.root / ".env").exists()
        assert (workspace.root / ".env.example").exists()
        (workspace.root / "link").symlink_to(folder / ".bifang" / "state.json")
        with pytest.raises(RuntimeError, match="regular files"):
            workspace.diff()
        assert not (folder / "link").exists()
    finally:
        workspace.discard()


def test_snapshot_size_limits_fail_without_source_changes(folder, monkeypatch):
    monkeypatch.setattr("bifang.folder_snapshot.MAX_BYTES", 4)
    (folder / "large.txt").write_text("too large\n")
    with pytest.raises(RuntimeError, match="exceeds"):
        Workspace.create(folder)
    assert (folder / "large.txt").read_text() == "too large\n"
    assert not (folder / ".git").exists()


def test_names_with_spaces_quotes_and_unicode_apply_exactly(folder):
    workspace = Workspace.create(folder)
    try:
        name = 'nested folder/quote"-火.py'
        (workspace.root / "nested folder").mkdir()
        (workspace.root / name).write_text("value = 1\n")
        assert workspace.apply()
        assert (folder / name).read_text() == "value = 1\n"
    finally:
        workspace.discard()


def test_selected_diff_does_not_include_other_files(folder):
    workspace = Workspace.create(folder)
    try:
        (workspace.root / "one.txt").write_text("one\n")
        (workspace.root / "two.txt").write_text("two\n")
        patch = workspace.diff(workspace.root / "one.txt")
        assert "+one" in patch and "+two" not in patch
        with pytest.raises(ValueError):
            workspace.diff(folder / "outside.txt")
    finally:
        workspace.discard()
