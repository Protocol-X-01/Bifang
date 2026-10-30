from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

EXCLUDED = {".git", ".bifang", ".arca", ".venv", "node_modules", "__pycache__", "dist", "build",
            ".ssh", ".aws", ".gnupg", ".config", "credentials.json", "service-account.json",
            "target", ".gradle", ".next", ".nuxt", ".cache", "coverage", ".tox", ".mypy_cache",
            ".pytest_cache", "vendor", "site-packages", ".turbo", ".vercel", ".parcel-cache"}
# Large artifact files are skipped rather than failing the whole snapshot:
# they are build outputs, not files the agent writes, and sessions must not
# refuse to start just because a release bundle sits next to the source.
SKIPPED_FILE_LIMIT = 16 * 1024 * 1024
MAX_BYTES = 128 * 1024 * 1024
MAX_FILES = 5000


def excluded(name: str) -> bool:
    return name in EXCLUDED or ((name == ".env" or name.startswith(".env."))
                                and name not in {".env.example", ".env.sample", ".env.template"})


def capture(root: Path) -> dict[str, tuple[bytes, int]]:
    if root.is_symlink() or not root.is_dir():
        raise RuntimeError("Folder snapshot root must remain a regular directory")
    files = {}
    total = 0
    skipped = []
    for current, directories, names in os.walk(root, followlinks=False):
        keep = []
        for name in sorted(directories):
            if excluded(name):
                continue
            child = Path(current) / name
            # Symbolic links inside the tree are skipped instead of aborting
            # the session; the snapshot root itself must still be a real dir.
            if child.is_symlink():
                skipped.append(child.relative_to(root).as_posix() + "/")
                continue
            keep.append(name)
        directories[:] = keep
        for name in sorted(names):
            if excluded(name):
                continue
            path = Path(current) / name
            metadata = path.lstat()
            if not stat.S_ISREG(metadata.st_mode):
                if path.is_symlink() or stat.S_ISFIFO(metadata.st_mode):
                    skipped.append(path.relative_to(root).as_posix())
                    continue
                raise RuntimeError("Folder snapshots require regular files, not links or special files")
            if metadata.st_size > SKIPPED_FILE_LIMIT or len(files) >= MAX_FILES:
                skipped.append(path.relative_to(root).as_posix())
                continue
            if metadata.st_size > MAX_BYTES - total:
                skipped.append(path.relative_to(root).as_posix())
                continue
            descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
            with os.fdopen(descriptor, "rb") as stream:
                opened = os.fstat(stream.fileno())
                if not stat.S_ISREG(opened.st_mode) or (opened.st_dev, opened.st_ino) != (metadata.st_dev, metadata.st_ino):
                    raise RuntimeError("Folder file changed while preparing the snapshot")
                content = stream.read(MAX_BYTES - total + 1)
            total += len(content)
            if total > MAX_BYTES:
                raise RuntimeError("Folder snapshot exceeds 128 MiB")
            relative = path.relative_to(root).as_posix()
            try:
                relative.encode("utf-8")
            except UnicodeEncodeError:
                raise RuntimeError("Folder snapshot filenames must be valid UTF-8") from None
            files[relative] = (content, 0o755 if metadata.st_mode & 0x111 else 0o644)
    if skipped:
        sample = ", ".join(skipped[:5])
        suffix = "" if len(skipped) <= 5 else f" (+{len(skipped)-5} more)"
        print(json.dumps({"snapshot_skipped_files": skipped[:20]}), file=__import__("sys").stderr)
        print(f"Snapshot skipped {len(skipped)} large file(s): {sample}{suffix}", file=__import__("sys").stderr)
    return files


def materialize(root: Path, files: dict[str, tuple[bytes, int]]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    for relative, (content, mode) in files.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        target.chmod(mode)


def git_environment() -> dict[str, str]:
    environment = {name: value for name, value in os.environ.items() if not name.startswith("GIT_")}
    environment.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull, GIT_TERMINAL_PROMPT="0")
    return environment


@dataclass
class FolderSnapshot:
    baseline: dict[str, tuple[bytes, int]]

    def diff(self, root: Path, path: Path | None = None) -> str:
        current = capture(root)
        baseline = self.baseline
        if path is not None:
            relative = path.resolve().relative_to(root.resolve()).as_posix()
            baseline = {name: value for name, value in baseline.items() if name == relative or name.startswith(relative + "/")}
            current = {name: value for name, value in current.items() if name == relative or name.startswith(relative + "/")}
        with tempfile.TemporaryDirectory(prefix="bifang-folder-diff-") as temporary:
            directory = Path(temporary)
            materialize(directory / "a", baseline)
            materialize(directory / "b", current)
            result = subprocess.run(
                ["git", "diff", "--no-index", "--no-ext-diff", "--no-textconv", "--binary", "--no-prefix", "--", "a", "b"],
                cwd=directory, env=git_environment(), capture_output=True, check=False,
            )
            if result.returncode not in (0, 1):
                raise RuntimeError("Could not export the folder snapshot patch")
            return result.stdout.decode("utf-8")

    def apply(self, source: Path, root: Path, expected_patch_sha256: str | None) -> bool:
        if capture(source) != self.baseline:
            raise RuntimeError("The original folder changed after this session started; refusing to apply")
        patch = self.diff(root)
        payload = patch.encode("utf-8", errors="surrogateescape")
        if expected_patch_sha256 is not None and hashlib.sha256(payload).hexdigest() != expected_patch_sha256:
            raise RuntimeError("The worktree patch changed after review; review it again before applying")
        if not patch:
            return False
        for options in (["--check"], []):
            result = subprocess.run(
                ["git", "-C", str(source), "-c", "core.hooksPath=" + os.devnull,
                 "-c", "core.fsmonitor=false", "apply", "--binary", *options, "-"],
                input=payload, env=git_environment(), capture_output=True, check=False,
            )
            if result.returncode:
                raise RuntimeError("Folder snapshot patch does not apply cleanly")
        return True
