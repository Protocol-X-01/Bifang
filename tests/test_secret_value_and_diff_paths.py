"""Synthetic value regressions and patches serialized by real, local Git repositories."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from bifang.secret_patterns import redact_model_diff, redact_secrets


@pytest.mark.parametrize("value", [
    pytest.param("x", id="short"),
    "1234567",
    "ab!cd",
    "abcdefgh!retained-suffix",
    "p@ss.word:with$%^&*()-+_=",
    "brackets[and]{braces},semi;tail",
    "back\\slash?with#hash",
    "embedded'and\"quotes",
    "!@#$%^&*()[]{};:,.?`|<>",
])
def test_unquoted_credential_values_are_wholly_redacted(value):
    assert redact_secrets(f"password={value} ordinary text\n") == (
        "password=[REDACTED] ordinary text\n"
    )


@pytest.mark.parametrize("name", [
    "PASSWORD", "passwd", "DB_PASSWORD", "CLIENT_SECRET", "api-key",
    "ACCESS_TOKEN", "AWS_SECRET_ACCESS_KEY", "private_key",
])
def test_recognized_assignment_names_cover_short_punctuation_values(name):
    assert redact_secrets(f"{name}=?x! next=ordinary") == f"{name}=[REDACTED] next=ordinary"


@pytest.mark.parametrize(("text", "expected"), [
    ('password="short ! with \\"inner\\" quotes" next="ordinary"',
     'password=[REDACTED] next="ordinary"'),
    ("password='short ! with \\'inner\\' quotes' next=ordinary",
     "password=[REDACTED] next=ordinary"),
    ('{"password":"x!","description":"ordinary"}',
     '{"password":[REDACTED],"description":"ordinary"}'),
    ("password=x! token=? ordinary text", "password=[REDACTED] token=[REDACTED] ordinary text"),
    ("password=escaped\\ space! next=ordinary", "password=[REDACTED] next=ordinary"),
    ("password=\nordinary text", "password=\nordinary text"),
    ("password= \nordinary text", "password= \nordinary text"),
    ("username=alice retries=3 ordinary text", "username=alice retries=3 ordinary text"),
])
def test_assignment_boundaries_preserve_adjacent_text(text, expected):
    assert redact_secrets(text) == expected


@pytest.fixture
def git_repository(tmp_path):
    executable = shutil.which("git")
    if not executable:
        pytest.skip("Git is required for serialized patch fixtures")
    environment = {
        "PATH": os.defpath,
        "LC_ALL": "C",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_TERMINAL_PROMPT": "0",
    }

    def git(*arguments, returncode=0):
        result = subprocess.run(
            [executable, "-c", "core.hooksPath=" + os.devnull, *arguments],
            cwd=tmp_path, env=environment, capture_output=True, text=True,
            check=False, timeout=10,
        )
        assert result.returncode == returncode, result.stderr
        return result.stdout

    git("init", "--quiet")
    return tmp_path, git


def write_fixture(root: Path, relative: str, content: str | bytes):
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content.encode("utf-8") if isinstance(content, str) else content)
    return target


def stage_tree(git):
    # Tree objects exercise real Git serialization without creating any commits.
    git("add", "--all")
    return git("write-tree").strip()


def patch_between(git, before, after, *options):
    return git(
        *options, "diff", "--no-ext-diff", "--no-textconv", "--no-color", "--binary",
        "--find-renames", before, after, "--",
    )


def test_spaced_public_and_private_paths(git_repository):
    root, git = git_repository
    paths = {
        "docs space/guide.txt": "SYNTHETIC_PUBLIC_DOC",
        "public space/settings.json": "SYNTHETIC_PUBLIC_SETTINGS",
        "account space/credentials.json": "SYNTHETIC_PRIVATE_CREDENTIALS",
        "project space/.bifang/sessions/chat.jsonl": "SYNTHETIC_PRIVATE_HISTORY",
    }
    for relative, marker in paths.items():
        write_fixture(root, relative, f"before {marker}\n")
    before = stage_tree(git)
    for relative, marker in paths.items():
        write_fixture(root, relative, f"after {marker}\n")
    diff = patch_between(git, before, stage_tree(git))
    assert all(marker in diff for marker in paths.values())

    redacted = redact_model_diff(diff)
    assert "SYNTHETIC_PUBLIC_DOC" in redacted
    assert "SYNTHETIC_PUBLIC_SETTINGS" in redacted
    assert "SYNTHETIC_PRIVATE_CREDENTIALS" not in redacted
    assert "SYNTHETIC_PRIVATE_HISTORY" not in redacted
    assert redacted.count("[Sensitive file diff omitted]") == 2


@pytest.mark.parametrize("directory", [
    "client's files", 'say "hello"', "tab\tname", "line\nname",
    "café space", "literal\\directory", "room b/area", "unicode\u2028line",
])
@pytest.mark.parametrize("quote_path", ["true", "false"])
@pytest.mark.parametrize("sensitive", [True, False])
def test_git_quoted_and_unusual_paths(git_repository, directory, quote_path, sensitive):
    root, git = git_repository
    relative = directory + ("/private.pem" if sensitive else "/guide.txt")
    write_fixture(root, relative, "SYNTHETIC_UNUSUAL_BEFORE\n")
    before = stage_tree(git)
    write_fixture(root, relative, "SYNTHETIC_UNUSUAL_AFTER\n")
    diff = patch_between(git, before, stage_tree(git), "-c", "core.quotePath=" + quote_path)

    if sensitive:
        assert redact_model_diff(diff) == "[Sensitive file diff omitted]\n"
    else:
        assert redact_model_diff(diff) == diff


@pytest.mark.parametrize(("old", "new", "sensitive"), [
    ("old space/credentials.json", "new space/public.txt", True),
    ("old space/public.txt", "new space/private.key", True),
    ("old b/area/public.txt", "new space/guide.txt", False),
    ('old "quoted"/private.pem', "new space/public.txt", True),
])
def test_rename_checks_both_paths(git_repository, old, new, sensitive):
    root, git = git_repository
    content = "SYNTHETIC_RENAME_BASE\n" * 20
    old_file = write_fixture(root, old, content)
    before = stage_tree(git)
    new_file = root / new
    new_file.parent.mkdir(parents=True, exist_ok=True)
    old_file.rename(new_file)
    new_file.write_text(content + "SYNTHETIC_RENAME_ADDITION\n", encoding="utf-8")
    diff = patch_between(git, before, stage_tree(git))
    assert "rename from " in diff and "rename to " in diff

    if sensitive:
        assert redact_model_diff(diff) == "[Sensitive file diff omitted]\n"
    else:
        assert redact_model_diff(diff) == diff


@pytest.mark.parametrize("sensitive", [True, False])
@pytest.mark.parametrize("directory", ["binary space", "binary b/space", 'binary "quoted"'])
def test_binary_patch_paths(git_repository, sensitive, directory):
    root, git = git_repository
    relative = directory + ("/private.key" if sensitive else "/public.bin")
    write_fixture(root, relative, b"\0SYNTHETIC_BINARY_BEFORE" + bytes(range(64)))
    before = stage_tree(git)
    write_fixture(root, relative, b"\0SYNTHETIC_BINARY_AFTER" + bytes(range(64)))
    diff = patch_between(git, before, stage_tree(git))
    assert "GIT binary patch" in diff

    if sensitive:
        assert redact_model_diff(diff) == "[Sensitive file diff omitted]\n"
    else:
        assert redact_model_diff(diff) == diff


@pytest.mark.parametrize("sensitive", [True, False])
@pytest.mark.parametrize("directory", ["mode space", "mode b/space"])
def test_mode_only_patch_paths(git_repository, sensitive, directory):
    root, git = git_repository
    relative = directory + ("/private.key" if sensitive else "/script.sh")
    write_fixture(root, relative, "SYNTHETIC_MODE_ONLY\n")
    before = stage_tree(git)
    git("update-index", "--chmod=+x", "--", relative)
    after = git("write-tree").strip()
    diff = patch_between(git, before, after)
    assert "old mode " in diff and "new mode " in diff
    assert "@@" not in diff

    if sensitive:
        assert redact_model_diff(diff) == "[Sensitive file diff omitted]\n"
    else:
        assert redact_model_diff(diff) == diff


@pytest.mark.parametrize("sensitive", [True, False])
def test_copy_checks_original_path(git_repository, sensitive):
    root, git = git_repository
    old = "old copy/" + ("private.key" if sensitive else "guide.txt")
    new = "new copy/public.txt"
    content = "SYNTHETIC_COPY_CONTENT\n" * 20
    write_fixture(root, old, content)
    before = stage_tree(git)
    write_fixture(root, new, content)
    after = stage_tree(git)
    diff = git("diff", "--no-ext-diff", "--no-textconv", "--no-color", "--binary",
               "--find-copies-harder", before, after, "--")
    assert "copy from " in diff and "copy to " in diff

    if sensitive:
        assert redact_model_diff(diff) == "[Sensitive file diff omitted]\n"
    else:
        assert redact_model_diff(diff) == diff


@pytest.mark.parametrize("operation", ["add", "delete"])
@pytest.mark.parametrize("sensitive", [True, False])
def test_added_and_deleted_paths(git_repository, operation, sensitive):
    root, git = git_repository
    git("read-tree", "--empty")
    empty = stage_tree(git)
    relative = "added space/" + ("private.pem" if sensitive else "guide.txt")
    write_fixture(root, relative, "SYNTHETIC_ADDED_OR_DELETED\n")
    populated = stage_tree(git)
    before, after = (empty, populated) if operation == "add" else (populated, empty)
    diff = patch_between(git, before, after)
    assert "/dev/null" in diff

    if sensitive:
        assert redact_model_diff(diff) == "[Sensitive file diff omitted]\n"
    else:
        assert redact_model_diff(diff) == diff


@pytest.mark.parametrize("operation", ["add", "delete", "modify"])
@pytest.mark.parametrize("sensitive", [True, False])
def test_folder_snapshot_diff_paths(git_repository, operation, sensitive):
    root, git = git_repository
    (root / "a").mkdir()
    (root / "b").mkdir()
    relative = "snapshot space/" + ("private.pem" if sensitive else "guide.txt")
    if operation != "add":
        write_fixture(root / "a", relative, "SYNTHETIC_SNAPSHOT_BEFORE\n")
    if operation != "delete":
        write_fixture(root / "b", relative, "SYNTHETIC_SNAPSHOT_AFTER\n")
    diff = git("diff", "--no-index", "--no-ext-diff", "--no-textconv", "--binary",
               "--no-prefix", "--", "a", "b", returncode=1)

    if sensitive:
        assert redact_model_diff(diff) == "[Sensitive file diff omitted]\n"
    else:
        assert redact_model_diff(diff) == diff


@pytest.mark.parametrize("sensitive", [True, False])
def test_binary_comparison_keeps_every_possible_path(git_repository, sensitive):
    root, git = git_repository
    old = "a/secrets" if sensitive else "a/first public.bin"
    new = "b/other b/secrets b/other" if sensitive else "b/second public.bin"
    write_fixture(root, old, b"\0SYNTHETIC_COMPARISON_BEFORE" + bytes(range(64)))
    write_fixture(root, new, b"\0SYNTHETIC_COMPARISON_AFTER" + bytes(range(64)))
    diff = git("diff", "--no-index", "--no-ext-diff", "--no-textconv", "--binary",
               "--no-prefix", "--", old, new, returncode=1)
    assert "GIT binary patch" in diff

    if sensitive:
        assert redact_model_diff(diff) == "[Sensitive file diff omitted]\n"
    else:
        assert redact_model_diff(diff) == diff


@pytest.mark.parametrize("header", [
    "diff --git a/guide.txt",
    "diff --git a/guide.txt c/guide.txt",
    'diff --git "a/guide.txt b/guide.txt',
    r'diff --git "a/unknown\q/file" "b/unknown\q/file"',
    r'diff --git "a/private\000.pem" "b/private\000.pem"',
    r'diff --git "a/invalid\777/file" "b/invalid\777/file"',
    "diff --git a/../guide.txt b/../guide.txt",
    "diff --git a/other.txt b/other.txt",
])
def test_unverifiable_headers_omit_the_entire_section(git_repository, header):
    root, git = git_repository
    write_fixture(root, "guide.txt", "SYNTHETIC_UNVERIFIABLE_BEFORE\n")
    before = stage_tree(git)
    write_fixture(root, "guide.txt", "SYNTHETIC_UNVERIFIABLE_AFTER\n")
    diff = patch_between(git, before, stage_tree(git))
    broken = header + "\n" + diff.partition("\n")[2]
    assert redact_model_diff(broken) == "[Sensitive file diff omitted]\n"


def test_ambiguous_header_without_metadata_fails_closed():
    diff = "diff --git a/one b/two b/three\nSYNTHETIC_UNVERIFIABLE_BODY\n"
    assert redact_model_diff(diff) == "[Sensitive file diff omitted]\n"
