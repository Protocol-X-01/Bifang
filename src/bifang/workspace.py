from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import tempfile
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from .config import state_home
from .folder_snapshot import FolderSnapshot, capture, materialize


@dataclass
class Workspace:
    source: Path
    root: Path
    branch: str | None = None
    isolated: bool = False
    snapshot: FolderSnapshot | None = None

    @staticmethod
    def resolve_source(path: Path) -> Path:
        source = path.resolve()
        if not shutil.which("git"):
            return source
        result = subprocess.run(
            ["git", "-C", str(source), "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, check=False,
        )
        return Path(result.stdout.strip()).resolve() if result.returncode == 0 else source

    @classmethod
    def create(cls, path: Path, use_worktree: bool = True) -> Workspace:
        source = path.resolve()
        if not use_worktree:
            return cls(source, source)
        if not shutil.which("git"):
            raise RuntimeError("Git is required for isolated workspace review and Apply")

        result = subprocess.run(
            ["git", "-C", str(source), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode:
            return cls.create_snapshot(source)

        source = Path(result.stdout.strip())
        head = subprocess.run(["git", "-C", str(source), "rev-parse", "--verify", "HEAD"],
                              capture_output=True, check=False)
        if head.returncode:
            return cls.create_snapshot(source)
        identity = uuid.uuid4().hex[:8]
        root = state_home() / "boxes" / identity
        root.parent.mkdir(parents=True, exist_ok=True)
        branch = f"bifang/{identity}"
        result = subprocess.run(
            ["git", "-C", str(source), "worktree", "add", "-b", branch, str(root), "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode:
            raise RuntimeError(result.stderr.strip())
        return cls(source, root, branch, True)

    @classmethod
    def create_snapshot(cls, source: Path) -> Workspace:
        boxes = state_home() / "boxes"
        if boxes.resolve().is_relative_to(source.resolve()):
            raise RuntimeError("Isolated workspace storage must be outside the source folder")
        boxes.mkdir(parents=True, exist_ok=True)
        root = Path(tempfile.mkdtemp(prefix="folder-", dir=boxes))
        try:
            # Live folders change while the copy is in flight (logs, editors,
            # caches). Re-baseline and retry a few times instead of refusing
            # the session; only give up when churn never settles.
            baseline = capture(source)
            for _ in range(4):
                materialize(root, baseline)
                check = capture(source)
                if check == baseline:
                    return cls(source, root, isolated=True, snapshot=FolderSnapshot(baseline))
                baseline = check
                shutil.rmtree(root)
                root = Path(tempfile.mkdtemp(prefix="folder-", dir=boxes))
                time.sleep(0.5)
            raise RuntimeError("The source folder kept changing while preparing the isolated workspace")
        except BaseException:
            shutil.rmtree(root)
            raise

    def diff(self, path: Path | None = None) -> str:
        if self.snapshot is not None:
            return self.snapshot.diff(self.root, path)
        paths = [".", ":(top,exclude).bifang", ":(top,exclude).arca"]
        if path is not None:
            relative = path.resolve().relative_to(self.root.resolve())
            if {".git", ".bifang", ".arca"}.intersection(relative.parts):
                raise ValueError("Internal state is not a source diff target")
            paths = [f":(literal){relative.as_posix()}"]
        with tempfile.TemporaryDirectory(prefix="bifang-diff-index-") as temporary:
            environment = {**os.environ, "GIT_INDEX_FILE": str(Path(temporary) / "index")}
            baseline = subprocess.run(["git", "-C", str(self.root), "read-tree", "HEAD"],
                                      env=environment, capture_output=True, check=False)
            if baseline.returncode:
                return ""
            untracked = subprocess.run(
                ["git", "-C", str(self.root), "ls-files", "-z", "--others", "--exclude-standard",
                 "--", ".", ":(top,exclude).bifang", ":(top,exclude).arca"],
                env=environment, capture_output=True, text=True, check=False)
            if untracked.returncode:
                raise RuntimeError("Could not enumerate workspace files for patch export")
            for relative_path in filter(None, untracked.stdout.split("\0")):
                added = subprocess.run(["git", "-C", str(self.root), "add", "-N", "--", relative_path],
                                       env=environment, capture_output=True, check=False)
                if added.returncode:
                    raise RuntimeError("Could not prepare a temporary patch index")
            result = subprocess.run(["git", "-C", str(self.root), "diff", "--binary", "HEAD", "--", *paths],
                                    env=environment, capture_output=True, text=True, check=False)
            if result.returncode:
                raise RuntimeError("Could not export the workspace patch")
            return result.stdout

    @classmethod
    def list_existing(cls, path: Path) -> list[Workspace]:
        source = cls.resolve_source(path)
        result = subprocess.run(["git", "-C", str(source), "worktree", "list", "--porcelain", "-z"],
                                capture_output=True, text=True, check=False)
        if result.returncode:
            return []
        boxes = (state_home() / "boxes").resolve()
        workspaces = []
        for block in result.stdout.split("\0\0"):
            fields = dict(item.partition(" ")[::2] for item in block.split("\0") if item)
            value = fields.get("worktree")
            if not value:
                continue
            root = Path(value)
            identity = root.name
            if (not re.fullmatch(r"[0-9a-f]{8}", identity) or not root.is_dir() or root.is_symlink()
                    or root.resolve() != boxes / identity
                    or fields.get("branch") != f"refs/heads/bifang/{identity}" or root.resolve() == source):
                continue
            workspaces.append(cls(source, root.resolve(), f"bifang/{identity}", True))
        return sorted(workspaces, key=lambda workspace: workspace.root.name)

    @classmethod
    def open_existing(cls, path: Path, identity: str | None = None) -> Workspace:
        if identity is not None and not re.fullmatch(r"[0-9a-f]{8}", identity):
            raise ValueError("Use an eight-character workspace ID from bifang boxes")
        workspaces = cls.list_existing(path)
        if identity is not None:
            workspaces = [workspace for workspace in workspaces if workspace.root.name == identity]
        if not workspaces:
            raise RuntimeError("No matching isolated workspace. Use bifang chat to create one, or bifang boxes to list them")
        if len(workspaces) != 1:
            raise RuntimeError("Multiple isolated workspaces. Select one explicitly with --box ID from bifang boxes")
        return workspaces[0]

    def apply(self, *, expected_patch_sha256: str | None = None) -> bool:
        if self.snapshot is not None:
            return self.snapshot.apply(self.source, self.root, expected_patch_sha256)
        if not self.isolated:
            raise RuntimeError("Changes can only be applied from an isolated Git worktree")

        source_head = subprocess.run(
            ["git", "-C", str(self.source), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
        worktree_head = subprocess.run(
            ["git", "-C", str(self.root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
        if (
            source_head.returncode
            or worktree_head.returncode
            or source_head.stdout.strip() != worktree_head.stdout.strip()
        ):
            raise RuntimeError("The original repository has moved to a different commit; refusing to apply")

        status = subprocess.run(
            ["git", "-C", str(self.source), "status", "--porcelain", "--untracked-files=all"],
            capture_output=True,
            text=True,
            check=False,
        )
        if status.returncode or status.stdout.strip():
            raise RuntimeError("The original repository has local changes; commit or stash them before applying")

        patch = self.diff()
        if expected_patch_sha256 is not None and hashlib.sha256(patch.encode()).hexdigest() != expected_patch_sha256:
            raise RuntimeError("The worktree patch changed after review; review it again before applying")
        if not patch:
            return False
        check = subprocess.run(
            ["git", "-C", str(self.source), "apply", "--binary", "--check", "-"],
            input=patch,
            capture_output=True,
            text=True,
            check=False,
        )
        if check.returncode:
            raise RuntimeError(check.stderr.strip() or "Patch does not apply cleanly")

        applied = subprocess.run(
            ["git", "-C", str(self.source), "apply", "--binary", "-"],
            input=patch,
            capture_output=True,
            text=True,
            check=False,
        )
        if applied.returncode:
            raise RuntimeError(applied.stderr.strip() or "Could not apply patch")
        return True

    def discard(self) -> None:
        if self.snapshot is not None:
            if self.root.parent.resolve() != (state_home() / "boxes").resolve() or not self.root.name.startswith("folder-"):
                raise RuntimeError("Refusing to remove an unmanaged folder snapshot")
            if self.root.exists():
                shutil.rmtree(self.root)
            return
        if self.isolated:
            subprocess.run(
                ["git", "-C", str(self.source), "worktree", "remove", "--force", str(self.root)],
                check=False,
                capture_output=True,
            )
            subprocess.run(
                ["git", "-C", str(self.source), "branch", "-D", self.branch or ""],
                check=False,
                capture_output=True,
            )
