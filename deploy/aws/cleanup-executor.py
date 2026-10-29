import argparse
import json
import os
import re
import shutil
import stat
import subprocess
from pathlib import Path


def cleanup(scratch, runner=subprocess.run, socket_path=None):
    if (scratch.is_symlink() or not scratch.is_dir() or scratch.stat().st_uid != os.geteuid()
            or scratch.stat().st_mode & 0o077):
        raise ValueError("Use the private executor scratch directory")
    environment = {"PATH": "/usr/bin:/bin", "HOME": "/nonexistent", "DOCKER_HOST": "unix:///var/run/docker.sock",
                   "DOCKER_CONFIG": "/run/bifang-executor/docker"}

    def docker(*arguments):
        result = runner(["/usr/bin/docker", *arguments], env=environment, capture_output=True, text=True, timeout=20, check=True)
        return result.stdout

    identities = docker("ps", "--all", "--quiet", "--no-trunc", "--filter", "label=bifang.executor=1").splitlines()
    for identity in identities:
        if not re.fullmatch(r"[a-f0-9]{64}", identity):
            raise ValueError("Unexpected executor identity; no broad cleanup")
        container = json.loads(docker("inspect", identity))[0]
        if (not re.fullmatch(r"/bifang-check-[a-f0-9]{32}", container["Name"])
                or container["Config"]["Labels"].get("bifang.executor") != "1"):
            raise ValueError("Refuse to remove a container outside the executor namespace")
    for identity in identities:
        docker("rm", "--force", identity)
    snapshots = list(scratch.iterdir())
    for path in snapshots:
        if (not re.fullmatch(r"snapshot-[A-Za-z0-9_-]+", path.name) or path.is_symlink()
                or not path.is_dir() or path.stat().st_uid not in {0, 10001, os.geteuid()}):
            raise ValueError("Refuse unexpected scratch contents")
    for path in snapshots:
        shutil.rmtree(path)
    if socket_path is not None and (socket_path.exists() or socket_path.is_symlink()):
        metadata = socket_path.lstat()
        if not stat.S_ISSOCK(metadata.st_mode) or metadata.st_uid not in {0, 10001}:
            raise ValueError("Refuse to unlink an unexpected IPC path")
        socket_path.unlink()
    return {"owned_containers_removed": len(identities), "private_snapshots_removed": len(snapshots)}


if __name__ == "__main__":
    if os.geteuid() != 0:
        raise RuntimeError("Cleanup requires the operator service")
    parser = argparse.ArgumentParser()
    parser.add_argument("--scratch", required=True, type=Path)
    parser.add_argument("--socket", required=True, type=Path)
    options = parser.parse_args()
    print(json.dumps(cleanup(options.scratch, socket_path=options.socket)))
