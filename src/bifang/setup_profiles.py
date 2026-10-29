from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import tomllib
from pathlib import Path

from packaging.specifiers import SpecifierSet
from packaging.version import Version

PROFILES = {"python-uv", "rust-cargo"}
DEFAULT_INDEXES = {"python-uv": "https://pypi.org/simple", "rust-cargo": "https://index.crates.io"}
INPUTS = {
    "python-uv": ("pyproject.toml", "uv.lock", "uv.toml", ".python-version", "poetry.lock", "pdm.lock"),
    "rust-cargo": ("Cargo.toml", "Cargo.lock", ".cargo/config", ".cargo/config.toml", "rust-toolchain", "rust-toolchain.toml", "build.rs"),
}


def trusted_executable(path: Path) -> Path:
    target = path.resolve(strict=True)
    metadata = target.stat()
    if (not stat.S_ISREG(metadata.st_mode) or metadata.st_uid not in {0, os.getuid()}
            or metadata.st_mode & 0o002 or not os.access(target, os.X_OK)):
        raise ValueError("Select an installed, owner-controlled executable")
    with target.open("rb") as source:
        if source.read(4) != b"\x7fELF":
            raise ValueError("This adapter requires an installed native Linux executable")
    return target


def probe(arguments: list[str], root: Path) -> str:
    directories = []
    for entry in os.environ.get("PATH", "/usr/bin:/bin").split(os.pathsep):
        candidate = Path(entry)
        if candidate.is_absolute() and candidate.is_dir() and not candidate.resolve().is_relative_to(root):
            directories.append(str(candidate))
    environment = {"HOME": str(Path.home()), "PATH": os.pathsep.join(directories), "LANG": "C.UTF-8", "RUSTUP_AUTO_INSTALL": "0"}
    for key in ("RUSTUP_HOME", "UV_PYTHON_INSTALL_DIR", "XDG_DATA_HOME"):
        if key in os.environ and Path(os.environ[key]).is_absolute() and not Path(os.environ[key]).resolve().is_relative_to(root):
            environment[key] = os.environ[key]
    try:
        result = subprocess.run(arguments, cwd="/", env=environment,
                                stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=8, check=False)
    except subprocess.TimeoutExpired as error:
        raise ValueError("Installed tool probe timed out") from error
    if result.returncode or len(result.stdout) > 16384:
        raise ValueError("Required runtime is not installed; install it explicitly and review again")
    return result.stdout.strip()


def selected_uv(root: Path) -> Path:
    selected = shutil.which("uv")
    candidates = (Path("/usr/bin/uv"), Path("/usr/local/bin/uv"), Path.home() / ".local/bin/uv", *([Path(selected)] if selected else []))
    for candidate in candidates:
        if candidate.is_file() and not candidate.resolve().is_relative_to(root):
            return trusted_executable(candidate)
    raise ValueError("Install uv before using the Python adapter")


def next_environment(root: Path) -> int:
    for parent in (root / ".bifang", root / ".bifang/environments"):
        if parent.is_symlink() or (parent.exists() and not parent.is_dir()):
            raise ValueError("Managed environments require real project directories")
    for generation in range(256):
        target = root / ".bifang/environments" / f"python-{generation:04d}"
        if not target.exists() and not target.is_symlink():
            return generation
    raise ValueError("Clear unused managed environments explicitly before creating another")


def python_profile(root: Path, inputs: dict, network: bool, registry: str, builds: bool, generation: int | None) -> dict:
    if inputs["pyproject.toml"] is None or inputs["uv.lock"] is None:
        raise ValueError("Python setup requires pyproject.toml and uv.lock")
    if any(inputs[name] is not None for name in ("uv.toml", "poetry.lock", "pdm.lock")):
        raise ValueError("Custom configuration and other Python lock managers need their own adapter")
    manifest = tomllib.loads(inputs["pyproject.toml"].decode())
    lock = tomllib.loads(inputs["uv.lock"].decode())
    project = manifest.get("project", {})
    if not isinstance(project, dict) or project.get("dynamic") or manifest.get("tool", {}).get("uv"):
        raise ValueError("Use static project metadata without uv source/workspace overrides")
    name = project.get("name")
    if not isinstance(name, str) or not isinstance(project.get("requires-python"), str):
        raise TypeError("Declare project name and requires-python explicitly")
    for package in lock.get("package", []):
        source = package.get("source", {})
        if source in ({"editable": "."}, {"virtual": "."}) and package.get("name") == re.sub(r"[-_.]+", "-", name).lower():
            continue
        if source != {"registry": registry}:
            raise ValueError("Only the explicitly selected index and root project are supported")
        artifacts = ([package["sdist"]] if "sdist" in package else []) + package.get("wheels", [])
        if not artifacts or any(not re.fullmatch(r"sha256:[a-f0-9]{64}", artifact.get("hash", "")) for artifact in artifacts):
            raise ValueError("Python dependency artifacts must be checksum-pinned")
    request = str(SpecifierSet(project["requires-python"]))
    if inputs[".python-version"] is not None:
        pins = [line.strip() for line in inputs[".python-version"].decode().splitlines() if line.strip() and not line.lstrip().startswith("#")]
        if len(pins) != 1:
            raise ValueError("Select one installed Python version")
        request = str(Version(pins[0]))
    uv = selected_uv(root)
    python = trusted_executable(Path(probe([str(uv), "python", "find", "--no-config", "--no-project", "--offline",
                                          "--no-python-downloads", "--resolve-links", "--", request], root)))
    if python.is_relative_to(root):
        raise ValueError("Project interpreters are not trusted runtime probes")
    runtime = json.loads(probe([str(python), "-I", "-S", "-c", "import json,sys; print(json.dumps({'prefix':sys.base_prefix,'version':sys.version.split()[0]}))"], root))
    library = Path(runtime["prefix"]) / "lib"
    if not library.is_absolute() or library == Path("/lib") or not library.is_dir():
        raise ValueError("Unsupported Python runtime layout")
    slot = next_environment(root) if generation is None else generation
    environment = root / ".bifang/environments" / f"python-{slot:04d}"
    return {
        "executable": str(uv), "argv": ["/bifang-tools/uv", "sync", "--locked", "--no-install-project", "--no-sources", "--no-config",
                                        "--no-python-downloads", f"--python={python}", f"--default-index={registry}",
                                        "--cache-dir=/cache", "--link-mode=copy", *([] if builds else ["--no-build"]), *([] if network else ["--offline"])],
        "runtime_mounts": [str(uv), str(python), str(library)],
        "runtime_tools": {str(python): hashlib.sha256(python.read_bytes()).hexdigest()},
        "environment_generation": slot, "environment_path": str(environment), "python_version": runtime["version"],
        "sandbox_env": {"UV_PROJECT_ENVIRONMENT": str(environment), "UV_NO_PROGRESS": "1", "PYTHONNOUSERSITE": "1"},
        "writes": ["selected project, including the fresh environment", str(environment), "private per-project uv cache", "temporary isolated home"],
        "execution": "Dependency build backends may execute; root project is not installed" if builds else "Wheel-only dependencies; no root-project install; fresh environment avoids existing project interpreters",
    }


def rust_profile(root: Path, inputs: dict, network: bool, registry: str, builds: bool) -> dict:
    if inputs["Cargo.toml"] is None or inputs["Cargo.lock"] is None:
        raise ValueError("Rust setup requires Cargo.toml and Cargo.lock")
    if any(inputs[name] is not None for name in (".cargo/config", ".cargo/config.toml")):
        raise ValueError("Custom Cargo execution/credential configuration requires separate support")
    manifest = tomllib.loads(inputs["Cargo.toml"].decode())
    lock = tomllib.loads(inputs["Cargo.lock"].decode())
    if "workspace" in manifest or manifest.get("patch") or manifest.get("replace") or not isinstance(manifest.get("package"), dict):
        raise ValueError("Use a single-root registry-backed Cargo project")
    for package in lock.get("package", []):
        if package.get("source") is None and package.get("name") == manifest["package"].get("name"):
            continue
        if (package.get("source") != "registry+https://github.com/rust-lang/crates.io-index"
                or not re.fullmatch(r"[a-f0-9]{64}", package.get("checksum", ""))):
            raise ValueError("Rust dependencies must be checksum-pinned crates.io packages")
    channel = None
    if inputs["rust-toolchain"] is not None and inputs["rust-toolchain.toml"] is not None:
        raise ValueError("Select one toolchain pin")
    if inputs["rust-toolchain"] is not None:
        channel = inputs["rust-toolchain"].decode().strip()
    if inputs["rust-toolchain.toml"] is not None:
        channel = tomllib.loads(inputs["rust-toolchain.toml"].decode()).get("toolchain", {}).get("channel")
    if channel is not None and (not isinstance(channel, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,99}", channel)):
        raise ValueError("Choose an already-installed named Rust toolchain")
    selected = shutil.which("cargo")
    candidates = [Path("/usr/bin/cargo"), Path.home() / ".cargo/bin/cargo", *([Path(selected)] if selected else [])]
    candidate = next((path for path in candidates if path.is_file() and not path.resolve().is_relative_to(root)), None)
    if candidate is None:
        raise ValueError("Install Cargo or rustup before using the Rust adapter")
    cargo = trusted_executable(candidate)
    if cargo.name == "rustup":
        options = ["--toolchain", channel] if channel else []
        cargo = trusted_executable(Path(probe([str(cargo), "which", *options, "cargo"], root)))
    elif channel:
        raise ValueError("Named Rust toolchains require an installed rustup manager")
    rustc = trusted_executable(cargo.parent / "rustc")
    if cargo.is_relative_to(root) or rustc.is_relative_to(root):
        raise ValueError("Project executables are not installed Rust toolchains")
    library = cargo.parent.parent / "lib"
    if not library.is_dir():
        raise ValueError("Unsupported Rust runtime layout")
    overrides = [] if registry == DEFAULT_INDEXES["rust-cargo"] else [
        '--config=source.crates-io.replace-with="bifang-approved"',
        f'--config=source.bifang-approved.registry={json.dumps("sparse+" + registry.rstrip("/") + "/")}',
    ]
    tools = {str(rustc): hashlib.sha256(rustc.read_bytes()).hexdigest()}
    environment = {"PATH": f"/bifang-tools:{cargo.parent}:/usr/bin:/bin", "RUSTC": str(rustc), "CARGO_HOME": "/tmp/cargo-home",
                   "CARGO_TARGET_DIR": "/cache/target", "CARGO_REGISTRIES_CRATES_IO_PROTOCOL": "sparse"}
    aliases = {}
    if builds:
        compiler = trusted_executable(Path("/usr/bin/cc"))
        if not compiler.is_relative_to("/usr") or any(character.isspace() for character in str(compiler)):
            raise ValueError("Rust build mode requires a system C linker under /usr")
        environment["CARGO_ENCODED_RUSTFLAGS"] = f"-C\x1flinker={compiler}"
        tools[str(compiler)] = hashlib.sha256(compiler.read_bytes()).hexdigest()
        for name in ("ld", "as", "ar"):
            target = trusted_executable(Path("/usr/bin") / name)
            if not target.is_relative_to("/usr"):
                raise ValueError("Use installed system binutils")
            aliases[name] = str(target)
            tools[str(target)] = hashlib.sha256(target.read_bytes()).hexdigest()
    return {"executable": str(cargo), "argv": [str(cargo), "check" if builds else "fetch", "--locked", *overrides, *([] if network else ["--offline"])],
            "runtime_mounts": [str(cargo.parent), str(library)], "runtime_tools": tools, "runtime_aliases": aliases,
            "sandbox_env": environment,
            "writes": ["selected project, including possible build-code side effects", "private per-project Cargo registry/target cache", "temporary isolated home"],
            "execution": "cargo check may execute project/dependency build.rs and procedural macros" if builds else "Fetches locked dependencies without compiling the project or running build scripts"}


def profile_plan(root: Path, *, profile: str, network: bool, registry: str, builds: bool, generation: int | None = None) -> dict:
    from .config import state_home
    from .package_setup import MAX_OUTPUT, TIMEOUT_SECONDS, read_manifest

    if profile not in PROFILES or type(builds) is not bool:
        raise ValueError("Choose a supported profile and explicit build-code setting")
    inputs = {name: read_manifest(root, name) for name in INPUTS[profile]}
    try:
        details = (python_profile(root, inputs, network, registry, builds, generation) if profile == "python-uv"
                   else rust_profile(root, inputs, network, registry, builds))
    except (AttributeError, KeyError, TypeError) as error:
        raise ValueError("Invalid project metadata for this setup profile") from error
    state = state_home().expanduser()
    if not state.is_absolute():
        raise ValueError("Setup state must be absolute")
    plan = {"version": "project-setup-v2", "profile": profile, "workspace": str(root), "network": "host-network" if network else "offline-v1",
            "registry": registry, "allow_builds": builds, "scripts": "build-code-enabled" if builds else "disabled",
            "inputs": {name: hashlib.sha256(content).hexdigest() if content is not None else None for name, content in inputs.items()},
            "cache_path": str(state.resolve() / "setup-cache" / hashlib.sha256(str(root).encode()).hexdigest()[:24] / profile),
            "timeout_seconds": TIMEOUT_SECONDS, "output_limit_bytes": MAX_OUTPUT,
            "isolation": "Linux Bubblewrap; no host fallback; explicitly selected installed runtime mounted read-only",
            "warning": "Review probes installed tools only. Project files are visible; host-network mode reaches local and remote services. Runtime libraries are trusted host software.", **details}
    plan["executable_sha256"] = hashlib.sha256(Path(plan["executable"]).read_bytes()).hexdigest()
    plan["sha256"] = hashlib.sha256(json.dumps(plan, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return plan
