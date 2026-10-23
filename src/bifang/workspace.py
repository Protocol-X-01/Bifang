from __future__ import annotations

import shutil
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path

from .config import state_home


@dataclass
class Workspace:
    source: Path
    root: Path
    branch: str | None = None
    isolated: bool = False

    @classmethod
    def create(cls, path: Path, use_worktree: bool = True) -> Workspace:
        source = path.resolve()
        if not shutil.which("git") or not use_worktree:
            return cls(source, source)

        result = subprocess.run(
            ["git", "-C", str(source), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode:
            return cls(source, source)

        source = Path(result.stdout.strip())
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

    def diff(self) -> str:
        untracked = subprocess.run(
            ["git", "-C", str(self.root), "ls-files", "--others", "--exclude-standard"],
            capture_output=True,
            text=True,
            check=False,
        )
        if untracked.returncode:
            return ""
        for relative_path in untracked.stdout.splitlines():
            subprocess.run(
                ["git", "-C", str(self.root), "add", "-N", "--", relative_path],
                capture_output=True,
                check=False,
            )
        result = subprocess.run(
            ["git", "-C", str(self.root), "diff", "--binary", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
        return result.stdout if result.returncode == 0 else ""

    def apply(self) -> bool:
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
