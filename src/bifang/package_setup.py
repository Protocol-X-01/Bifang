from __future__ import annotations

import asyncio
import codecs
import hashlib
import json
import os
import platform
import re
import signal
import stat
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

from .sandbox_network import SandboxUnavailableError, attach_filter, offline_filter

MAX_MANIFEST = 8_000_000
MAX_OUTPUT = 1_000_000
TIMEOUT_SECONDS = 300
VERSION = "npm-locked-v1"
DEFAULT_REGISTRY = "https://registry.npmjs.org"


class OutputLimitError(RuntimeError):
    pass


class OutputConsumerError(RuntimeError):
    pass


def display_output(value: str) -> str:
    return "".join(character if character.isprintable() or character in "\n\t"
                   else f"\\u{ord(character):04x}" for character in value)


def private_directory(path: Path) -> int:
    descriptor = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY)
    try:
        for component in path.parts[1:]:
            try:
                os.mkdir(component, mode=0o700, dir_fd=descriptor)
            except FileExistsError:
                pass
            child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        metadata = os.fstat(descriptor)
        if metadata.st_uid != os.getuid() or metadata.st_mode & 0o077:
            raise PermissionError("Setup storage must be owner-only")
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def retain_receipt(report: dict) -> str:
    from .config import state_home

    directory = state_home().resolve() / "setup-receipts"
    parent = private_directory(directory)
    target = directory / f"{uuid.uuid4().hex}.json"
    try:
        descriptor = os.open(target.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent)
    finally:
        os.close(parent)
    with os.fdopen(descriptor, "w") as stream:
        json.dump(report, stream, sort_keys=True)
        stream.flush()
        os.fsync(stream.fileno())
    return str(target)


def read_manifest(root: Path, name: str) -> bytes | None:
    parts = PurePosixPath(name).parts
    if not parts or PurePosixPath(name).is_absolute() or ".." in parts or "\\" in name:
        raise ValueError("Choose a relative setup input")
    descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        try:
            for component in parts[:-1]:
                child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
                os.close(descriptor)
                descriptor = child
            source = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=descriptor)
        except FileNotFoundError:
            return None
        with os.fdopen(source, "rb") as stream:
            metadata = os.fstat(stream.fileno())
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > MAX_MANIFEST:
                raise ValueError("Setup inputs must be regular files below 8 MB")
            content = stream.read(MAX_MANIFEST + 1)
            if len(content) > MAX_MANIFEST:
                raise ValueError("Setup input exceeded its size limit")
            return content
    finally:
        os.close(descriptor)


def setup_plan(workspace: Path, *, network: bool = False, registry: str | None = None,
               profile: str = "javascript-npm", allow_builds: bool = False, _generation: int | None = None) -> dict:
    from .config import state_home

    if profile not in {"javascript-npm", "python-uv", "rust-cargo"} or type(allow_builds) is not bool:
        raise ValueError("Choose a supported setup profile and explicit build setting")
    if registry is None:
        from .setup_profiles import DEFAULT_INDEXES
        registry = DEFAULT_REGISTRY if profile == "javascript-npm" else DEFAULT_INDEXES[profile]
    if type(network) is not bool:
        raise ValueError("Choose offline or explicitly approved network access")
    if not isinstance(registry, str) or len(registry) > 2048 or any(character.isspace() or not character.isprintable() for character in registry):
        raise ValueError("Choose a credential-free registry URL")
    endpoint = urlsplit(registry)
    if (not endpoint.hostname or endpoint.username is not None or endpoint.password is not None
            or endpoint.query or endpoint.fragment or "\\" in registry
            or (endpoint.port is not None and not 1 <= endpoint.port <= 65535)
            or (endpoint.scheme != "https" and not (endpoint.scheme == "http" and endpoint.hostname in {"127.0.0.1", "localhost", "::1"}))):
        raise ValueError("Use a credential-free HTTPS registry, or a loopback HTTP registry")
    registry = registry.rstrip("/")
    root = workspace.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("Select a project directory")
    if profile != "javascript-npm":
        from .setup_profiles import profile_plan
        return profile_plan(root, profile=profile, network=network, registry=registry, builds=allow_builds, generation=_generation)
    if allow_builds:
        raise ValueError("The npm adapter keeps lifecycle hooks disabled")
    names = ("package.json", "package-lock.json", "npm-shrinkwrap.json", ".npmrc",
             "pnpm-lock.yaml", "yarn.lock", "bun.lock", "bun.lockb")
    inputs = {name: read_manifest(root, name) for name in names}
    if inputs["package.json"] is None or inputs["package-lock.json"] is None:
        raise ValueError("Locked npm setup requires package.json and package-lock.json")
    if any(inputs[name] is not None for name in names[2:]):
        raise ValueError("Custom npm configuration, shrinkwrap and other lock managers need separate setup support")
    package = json.loads(inputs["package.json"])
    lock = json.loads(inputs["package-lock.json"])
    if not isinstance(package, dict) or not isinstance(lock, dict):
        raise TypeError("Package manifests must be objects")
    manager = package.get("packageManager", "npm")
    if not isinstance(manager, str) or manager.split("@", 1)[0] != "npm" or package.get("workspaces"):
        raise ValueError("Choose a single-root npm project; other managers and monorepos need their own adapter")
    if lock.get("lockfileVersion") not in (2, 3):
        raise ValueError("Use an npm lockfile version 2 or 3")
    packages = lock.get("packages")
    if not isinstance(packages, dict):
        raise TypeError("The lockfile must describe exact packages")
    for name, entry in packages.items():
        if not isinstance(entry, dict):
            raise TypeError("Lockfile package entries must be objects")
        if name and (entry.get("link") or not isinstance(entry.get("integrity"), str)
                     or not re.fullmatch(r"sha512-[A-Za-z0-9+/]+={0,2}", entry["integrity"])):
            raise ValueError("Setup requires integrity-pinned packages; links and unpinned artifacts need separate review")
    executable = Path("/usr/bin/npm").resolve(strict=True)
    if not executable.is_relative_to("/usr") or not executable.is_file():
        raise ValueError("Setup requires the system npm installation under /usr")
    state = state_home().expanduser()
    if not state.is_absolute():
        raise ValueError("Setup state must use an absolute directory")
    cache = state.resolve() / "setup-cache" / hashlib.sha256(str(root).encode()).hexdigest()[:24] / "npm"
    plan = {
        "version": VERSION, "workspace": str(root), "profile": "javascript-npm",
        "argv": ["/usr/bin/npm", "ci", "--ignore-scripts", "--no-audit", "--no-fund",
                 f"--registry={registry}", "--cache=/cache", "--userconfig=/tmp/npm-user-config", "--globalconfig=/tmp/npm-global-config", *([] if network else ["--offline"])],
        "inputs": {name: hashlib.sha256(content).hexdigest() if content is not None else None
                   for name, content in inputs.items()},
        "executable": str(executable), "executable_sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
        "network": "host-network" if network else "offline-v1",
        "registry": registry,
        "cache_path": str(cache),
        "scripts": "disabled", "timeout_seconds": TIMEOUT_SECONDS, "output_limit_bytes": MAX_OUTPUT,
        "writes": ["selected project, including replacement of node_modules", "private per-project npm cache", "temporary isolated home"],
        "isolation": "Linux Bubblewrap; no host fallback; host network only with separate consent",
        "warning": "Downloads are not a package safety audit. Host-network mode can reach local and remote services. Project files are visible inside the sandbox.",
    }
    plan["sha256"] = hashlib.sha256(json.dumps(plan, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return plan


def sandbox_argv(plan: dict, executable: str = "/usr/bin/bwrap") -> list[str]:
    arguments = [executable, "--die-with-parent", "--unshare-all", "--new-session", "--clearenv", "--cap-drop", "ALL"]
    if plan["network"] == "host-network":
        arguments.append("--share-net")
    for source in ("/usr", "/bin", "/lib", "/lib64"):
        if Path(source).exists():
            arguments.extend(["--ro-bind", source, source])
    arguments.extend(["--dir", "/etc"])
    for source in ("/etc/resolv.conf", "/etc/hosts", "/etc/nsswitch.conf", "/etc/ssl/certs"):
        if Path(source).exists():
            arguments.extend(["--ro-bind", source, source])
    arguments.extend(["--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp",
                      "--bind", plan["workspace"], "/workspace", "--chdir", "/workspace",
                      "--bind", plan["cache_path"], "/cache",
                      "--setenv", "PATH", "/usr/bin:/bin", "--setenv", "HOME", "/tmp",
                      "--setenv", "LANG", "C.UTF-8",
                      "--setenv", "npm_config_update_notifier", "false"])
    if plan["profile"] != "javascript-npm":
        arguments.extend(["--dir", "/bifang-tools"])
        arguments.extend(["--bind", plan["workspace"], plan["workspace"], "--chdir", plan["workspace"]])
        for source in plan["runtime_mounts"]:
            if not Path(source).is_relative_to("/usr"):
                arguments.extend(["--ro-bind", source, source])
        if plan["profile"] == "python-uv":
            arguments.extend(["--ro-bind", plan["executable"], "/bifang-tools/uv"])
        else:
            arguments.extend(["--dir", "/tmp/cargo-home", "--bind", str(Path(plan["cache_path"]) / "registry"), "/tmp/cargo-home/registry"])
            for name, source in plan["runtime_aliases"].items():
                arguments.extend(["--ro-bind", source, f"/bifang-tools/{name}"])
        for key, value in plan["sandbox_env"].items():
            arguments.extend(["--setenv", key, value])
    arguments.extend(["--", *plan["argv"]])
    return arguments


async def run_setup(workspace: Path, fingerprint: str, *, network: bool = False, confirmed: bool = False,
                    registry: str | None = None, profile: str = "javascript-npm", allow_builds: bool = False,
                    on_output: Callable[[str, str], None] | None = None) -> dict:
    if confirmed is not True:
        raise PermissionError("Review and explicitly approve the exact setup plan first")
    if platform.system() != "Linux" or not Path("/usr/bin/bwrap").is_file():
        raise SandboxUnavailableError("Linux Bubblewrap is required; no unsandboxed setup fallback")
    import fcntl

    descriptor = os.open(workspace.resolve(strict=True), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError("Another setup operation is active for this project") from error
        report = await _run_setup(workspace, fingerprint, network=network, registry=registry, profile=profile, allow_builds=allow_builds, on_output=on_output)
        try:
            report["receipt_path"] = retain_receipt(report)
            report["receipt_saved"] = True
        except (OSError, ValueError):
            report["receipt_path"] = None
            report["receipt_saved"] = False
        return report
    finally:
        os.close(descriptor)


async def _run_setup(workspace: Path, fingerprint: str, *, network: bool,
                     registry: str | None, profile: str, allow_builds: bool,
                     on_output: Callable[[str, str], None] | None) -> dict:
    plan = setup_plan(workspace, network=network, registry=registry, profile=profile, allow_builds=allow_builds)
    if not isinstance(fingerprint, str) or fingerprint != plan["sha256"]:
        raise ValueError("Setup inputs or options changed; review a fresh plan")
    started = datetime.now(UTC).isoformat()
    clock = time.monotonic()
    output_size = 0
    digest = hashlib.sha256()
    process = None
    stopped = False
    status = "failed"

    async def drain(stream, label):
        nonlocal output_size
        decoder = codecs.getincrementaldecoder("utf-8")("replace")

        def emit(value):
            if on_output and value:
                try:
                    on_output(label, display_output(value))
                except Exception as error:
                    raise OutputConsumerError("Setup output could not be displayed") from error

        while content := await stream.read(4096):
            output_size += len(content)
            digest.update(label.encode() + b"\0" + content)
            if output_size > MAX_OUTPUT:
                raise OutputLimitError("Setup output exceeded its limit")
            emit(decoder.decode(content))
        emit(decoder.decode(b"", final=True))

    async def stop():
        nonlocal stopped
        if process is not None and not stopped:
            stopped = True
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            await process.wait()

    try:
        os.close(private_directory(Path(plan["cache_path"])))
        if profile == "rust-cargo":
            os.close(private_directory(Path(plan["cache_path"]) / "registry"))
        if profile == "python-uv":
            environment = Path(plan["environment_path"])
            parent = private_directory(environment.parent)
            try:
                os.mkdir(environment.name, mode=0o700, dir_fd=parent)
            finally:
                os.close(parent)
        with offline_filter(not network) as descriptor:
            arguments = sandbox_argv(plan)
            if descriptor is not None:
                arguments = attach_filter(arguments, descriptor)
            process = await asyncio.create_subprocess_exec(
                *arguments, cwd="/", env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"},
                pass_fds=(descriptor,) if descriptor is not None else (),
                stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE, start_new_session=True,
            )
        tasks = [asyncio.create_task(drain(process.stdout, "stdout")),
                 asyncio.create_task(drain(process.stderr, "stderr")), asyncio.create_task(process.wait())]
        try:
            await asyncio.wait_for(asyncio.gather(*tasks), plan["timeout_seconds"])
            status = "succeeded" if process.returncode == 0 else "failed"
        finally:
            await stop()
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
    except TimeoutError:
        status = "timed_out"
    except asyncio.CancelledError:
        status = "cancelled"
    except OutputLimitError:
        status = "output_limit"
    except OutputConsumerError:
        status = "output_error"
    except OSError:
        status = "start_failed"
    finally:
        await stop()
    try:
        unchanged = setup_plan(workspace, network=network, registry=registry, profile=profile, allow_builds=allow_builds,
                               _generation=plan.get("environment_generation"))["sha256"] == plan["sha256"]
    except (OSError, ValueError, TypeError):
        unchanged = False
    if status == "succeeded" and not unchanged:
        status = "inputs_changed"
    return {"plan_sha256": plan["sha256"], "plan": plan, "workspace": plan["workspace"], "argv": plan["argv"],
            "network": plan["network"], "scripts": plan["scripts"], "status": status,
            "returncode": process.returncode if process else None, "started_at": started,
            "elapsed_seconds": round(time.monotonic() - clock, 3), "output_bytes": output_size,
            "output_sha256": digest.hexdigest(), "inputs_unchanged": unchanged,
            "rollback": "not performed; inspect project after failure or cancellation"}
