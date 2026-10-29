from __future__ import annotations

import shutil
from pathlib import Path

MARKERS = frozenset({"pyproject.toml", "uv.lock", "package.json", "package-lock.json",
                     "pnpm-lock.yaml", "yarn.lock", "bun.lock", "bun.lockb", "Cargo.toml", "Cargo.lock"})


def inspect_toolchains(root: Path) -> dict:
    root = root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("Select a project directory")
    manifests = {name for name in MARKERS if not (root / name).is_symlink() and (root / name).is_file()}
    profiles = []

    def profile(identity, label, manager, names, command, executes_dependency_code):
        profiles.append({
            "id": identity, "label": label, "manager": manager,
            "available": shutil.which(manager) is not None,
            "manifests": sorted(manifests.intersection(names)),
            "bootstrap_argv": command,
            "network_required": True,
            "may_execute_dependency_code": executes_dependency_code,
            "writes": ["project environment or lockfile", "package-manager cache"],
            "automatic_install": False,
        })

    if "pyproject.toml" in manifests:
        command = ["uv", "sync"] + (["--locked"] if "uv.lock" in manifests else [])
        profile("python-uv", "Python", "uv", {"pyproject.toml", "uv.lock"}, command, True)
    if "package.json" in manifests:
        foreign_locks = manifests.intersection({"pnpm-lock.yaml", "yarn.lock", "bun.lock", "bun.lockb"})
        command = [] if foreign_locks else ["npm", "ci" if "package-lock.json" in manifests else "install", "--ignore-scripts"]
        profile("javascript-npm", "JavaScript / TypeScript", "npm",
                {"package.json", "package-lock.json", *foreign_locks}, command, False)
        profiles[-1]["manager_selection_required"] = bool(foreign_locks)
    if "Cargo.toml" in manifests:
        command = ["cargo", "fetch"] + (["--locked"] if "Cargo.lock" in manifests else [])
        profile("rust-cargo", "Rust", "cargo", {"Cargo.toml", "Cargo.lock"}, command, False)
    return {"scope": "Read-only root manifest detection and bootstrap preview; no package installation or version probing",
            "profiles": profiles, "automatic_install": False}
