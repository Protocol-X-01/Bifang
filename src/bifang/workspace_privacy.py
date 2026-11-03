from __future__ import annotations

import os
from collections.abc import Iterable
from pathlib import Path

from .sandbox_network import SandboxUnavailableError
from .secret_patterns import is_sensitive_command_path

_UNSCANNED_BUILD_OR_DEPENDENCY_DIRECTORIES = {
    ".git", ".next", ".pytest_cache", ".ruff_cache", ".tox", ".venv", ".cache",
    "__pycache__", "build", "dist", "node_modules", "out", "target", "vendor", "venv",
}


def private_workspace_paths(
    root: Path, *, allow_subtrees: Iterable[str | Path] = ()
) -> tuple[list[Path], list[Path]]:
    """Find conventional sensitive paths while skipping VCS/build/dependency stores."""
    allowed = tuple(Path(path) for path in allow_subtrees)
    if any(path.is_absolute() or not path.parts or ".." in path.parts for path in allowed):
        raise ValueError("Allowed workspace subtrees must be safe relative paths")

    def is_allowed(relative: Path) -> bool:
        return any(relative == path or relative.is_relative_to(path) for path in allowed)

    def contains_allowed(relative: Path) -> bool:
        return any(path.is_relative_to(relative) for path in allowed)

    directories: list[Path] = []
    files: list[Path] = []
    pending = [(root, Path())]

    while pending:
        current, relative = pending.pop()
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    child_relative = relative / entry.name
                    try:
                        if is_allowed(child_relative):
                            continue
                        if contains_allowed(child_relative):
                            if entry.is_symlink() or not entry.is_dir(follow_symlinks=False):
                                raise SandboxUnavailableError(
                                    f"Cannot safely expose allowed workspace subtree through {child_relative}."
                                )
                            pending.append((Path(entry.path), child_relative))
                            continue
                        if is_sensitive_command_path(child_relative):
                            if entry.is_symlink():
                                raise SandboxUnavailableError(
                                    f"Cannot safely hide sensitive symbolic link {child_relative}; "
                                    "replace it with a regular file or directory before running commands."
                                )
                            if entry.is_dir(follow_symlinks=False):
                                directories.append(child_relative)
                            elif entry.is_file(follow_symlinks=False):
                                files.append(child_relative)
                            else:
                                raise SandboxUnavailableError(
                                    f"Cannot safely hide sensitive special path {child_relative}; "
                                    "remove or replace it before running commands."
                                )
                            continue

                        if (entry.is_dir(follow_symlinks=False)
                                and entry.name.casefold() not in _UNSCANNED_BUILD_OR_DEPENDENCY_DIRECTORIES):
                            pending.append((Path(entry.path), child_relative))
                    except OSError as exc:
                        raise SandboxUnavailableError(
                            f"Cannot inspect workspace path {child_relative}; refusing to run a command."
                        ) from exc
        except OSError as exc:
            raise SandboxUnavailableError(
                f"Cannot inspect workspace directory {relative or '.'}; refusing to run a command."
            ) from exc

    return sorted(directories), sorted(files)


def private_workspace_mount_args(
    root: Path,
    mountpoint: str | Path = "/workspace",
    *,
    allow_subtrees: Iterable[str | Path] = (),
) -> list[str]:
    """Build Bubblewrap mounts that conceal recognized private workspace paths."""
    mountpoint = Path(mountpoint)
    if not mountpoint.is_absolute() or ".." in mountpoint.parts:
        raise ValueError("Workspace mountpoint must be an absolute sandbox path")

    directories, files = private_workspace_paths(root, allow_subtrees=allow_subtrees)
    arguments = [
        argument
        for relative in directories
        for argument in ("--tmpfs", str(mountpoint / relative))
    ]
    arguments.extend(
        argument
        for relative in files
        for argument in ("--ro-bind", "/dev/null", str(mountpoint / relative))
    )
    return arguments
