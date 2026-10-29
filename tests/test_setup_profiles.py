import asyncio
import base64
import csv
import hashlib
import io
import json
import platform
import re
import subprocess
import sys
import tarfile
import threading
import zipfile
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from bifang.package_setup import read_manifest, run_setup, setup_plan
from bifang.setup_profiles import selected_uv


@pytest.fixture
def project(tmp_path, monkeypatch):
    if platform.system() != "Linux" or not Path("/usr/bin/bwrap").is_file():
        pytest.skip("Linux Bubblewrap adapter")
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    root = tmp_path / "project"
    root.mkdir()
    return root


def require_namespaces():
    result = subprocess.run(["/usr/bin/bwrap", "--unshare-all", "--ro-bind", "/", "/", "--", "/usr/bin/true"], capture_output=True, check=False)
    if result.returncode:
        pytest.skip("This system denies Bubblewrap namespaces")


def python_project(root):
    (root / "pyproject.toml").write_text('[project]\nname="python-fixture"\nversion="1.0.0"\nrequires-python=">=3.11,<3.12"\ndependencies=[]\n[build-system]\nrequires=[]\nbuild-backend="hostile_backend"\nbackend-path=["."]\n')
    (root / "hostile_backend.py").write_text('from pathlib import Path\nPath(__file__).with_name("BACKEND_EXECUTED").write_text("bad")\nraise RuntimeError("must not import root backend")\n')
    (root / "uv.lock").write_text('version=1\nrevision=3\nrequires-python=">=3.11,<3.12"\n[[package]]\nname="python-fixture"\nversion="1.0.0"\nsource={editable="."}\n')


def rust_project(root):
    (root / "Cargo.toml").write_text('[package]\nname="rust-fixture"\nversion="1.0.0"\nedition="2021"\nbuild="build.rs"\n')
    (root / "Cargo.lock").write_text('version=4\n[[package]]\nname="rust-fixture"\nversion="1.0.0"\n')
    (root / "src").mkdir()
    (root / "src/lib.rs").write_text('pub fn answer() -> u32 { 42 }\n')
    (root / "build.rs").write_text('fn main() { std::fs::write("BUILD_EXECUTED", "allowed").unwrap(); }\n')


@contextmanager
def registry_server():
    resources, requests = {}, []

    class Handler(BaseHTTPRequestHandler):
        def do_HEAD(self):
            self.do_GET()

        def do_GET(self):
            requests.append(self.path)
            content = resources.get(self.path)
            if content is None:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8" if content.lstrip().startswith(b"<") else "application/json" if content.lstrip().startswith(b"{") else "application/octet-stream")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(content)

        def log_message(self, *args):
            pass

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            yield f"http://127.0.0.1:{server.server_port}", resources, requests
        finally:
            server.shutdown()
            worker.join(timeout=5)


def wheel_fixture(root):
    files = {"tiny_fixture/__init__.py": b"ANSWER = 42\n",
             "tiny_fixture-1.0.0.dist-info/WHEEL": b"Wheel-Version: 1.0\nGenerator: Bifang-test\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
             "tiny_fixture-1.0.0.dist-info/METADATA": b"Metadata-Version: 2.2\nName: tiny-fixture\nVersion: 1.0.0\nRequires-Python: >=3.11\n",
             "fixture_startup.pth": f'import pathlib; pathlib.Path({str(root / "PTH_EXECUTED")!r}).write_text("must-not-run-during-setup")\n'.encode()}
    record = io.StringIO()
    writer = csv.writer(record, lineterminator="\n")
    for name, data in files.items():
        writer.writerow([name, "sha256=" + base64.urlsafe_b64encode(hashlib.sha256(data).digest()).decode().rstrip("="), len(data)])
    writer.writerow(["tiny_fixture-1.0.0.dist-info/RECORD", "", ""])
    files["tiny_fixture-1.0.0.dist-info/RECORD"] = record.getvalue().encode()
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return output.getvalue()


def test_python_plan_never_executes_existing_project_interpreter_or_backend(project):
    python_project(project)
    (project / ".venv/bin").mkdir(parents=True)
    executable = project / ".venv/bin/python"
    executable.write_text('#!/bin/sh\ntouch "' + str(project / "INTERPRETER_EXECUTED") + '"\n')
    executable.chmod(0o700)
    plan = setup_plan(project, profile="python-uv")
    assert plan["version"] == "project-setup-v2" and plan["scripts"] == "disabled"
    assert plan["python_version"].startswith("3.11.")
    assert "--no-build" in plan["argv"] and "--no-install-project" in plan["argv"]
    assert not Path(plan["environment_path"]).exists()
    assert not (project / "INTERPRETER_EXECUTED").exists()
    assert not (project / "BACKEND_EXECUTED").exists()
    enabled = setup_plan(project, profile="python-uv", allow_builds=True)
    assert enabled["sha256"] != plan["sha256"] and enabled["scripts"] == "build-code-enabled"


def test_real_python_sync_creates_fresh_usable_311_environment_without_root_build_hooks(project):
    require_namespaces()
    python_project(project)
    plan = setup_plan(project, profile="python-uv")
    output = []
    result = asyncio.run(run_setup(project, plan["sha256"], profile="python-uv", confirmed=True,
                                   on_output=lambda stream, text: output.append(text)))
    assert result["status"] == "succeeded", "".join(output)
    assert result["inputs_unchanged"] and result["receipt_saved"]
    environment = Path(plan["environment_path"])
    probe = subprocess.run([str(environment / "bin/python"), "-I", "-c", "import sys; assert sys.version_info[:2] == (3,11)"], capture_output=True, check=False)
    assert probe.returncode == 0
    assert str(environment) in (environment / "bin/activate").read_text()
    assert not (project / "BACKEND_EXECUTED").exists()
    second = setup_plan(project, profile="python-uv")
    assert second["environment_path"] != plan["environment_path"]


def test_real_cargo_fetch_does_not_run_build_script_but_explicit_check_can(project):
    require_namespaces()
    rust_project(project)
    plan = setup_plan(project, profile="rust-cargo")
    output = []
    fetched = asyncio.run(run_setup(project, plan["sha256"], profile="rust-cargo", confirmed=True,
                                    on_output=lambda stream, text: output.append(text)))
    assert fetched["status"] == "succeeded", "".join(output)
    assert not (project / "BUILD_EXECUTED").exists()
    build = setup_plan(project, profile="rust-cargo", allow_builds=True)
    assert build["sha256"] != plan["sha256"] and "check" in build["argv"]
    with pytest.raises(ValueError, match="changed"):
        asyncio.run(run_setup(project, plan["sha256"], profile="rust-cargo", allow_builds=True, confirmed=True))
    checked = asyncio.run(run_setup(project, build["sha256"], profile="rust-cargo", allow_builds=True, confirmed=True,
                                    on_output=lambda stream, text: output.append(text)))
    assert checked["status"] == "succeeded", "".join(output)
    assert (project / "BUILD_EXECUTED").read_text() == "allowed"


def test_nested_input_symlinks_cannot_read_outside_the_project(project, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "config.toml").write_text("synthetic-not-a-real-secret")
    (project / ".cargo").symlink_to(outside, target_is_directory=True)
    with pytest.raises(OSError):
        read_manifest(project, ".cargo/config.toml")


@pytest.mark.parametrize("profile", ["python-uv", "rust-cargo"])
def test_profile_input_changes_and_custom_configuration_require_fresh_review(project, profile):
    if profile == "python-uv":
        python_project(project)
        name = "uv.toml"
    else:
        rust_project(project)
        name = ".cargo/config.toml"
        (project / ".cargo").mkdir()
    plan = setup_plan(project, profile=profile)
    (project / name).write_text("unsupported=true")
    with pytest.raises(ValueError):
        asyncio.run(run_setup(project, plan["sha256"], profile=profile, confirmed=True))


def test_real_python_wheel_download_and_cached_reinstall_never_probe_old_or_installed_startup_hooks(project):
    require_namespaces()
    python_project(project)
    (project / "pyproject.toml").write_text((project / "pyproject.toml").read_text().replace("dependencies=[]", 'dependencies=["tiny-fixture==1.0.0"]'))
    wheel = wheel_fixture(project)
    with registry_server() as (base, resources, requests):
        index = base + "/simple"
        resources["/packages/tiny_fixture-1.0.0-py3-none-any.whl"] = wheel
        resources["/simple/tiny-fixture/"] = (f'<a href="/packages/tiny_fixture-1.0.0-py3-none-any.whl#sha256={hashlib.sha256(wheel).hexdigest()}">fixture</a>').encode()
        lock = subprocess.run([str(selected_uv(project)), "lock", "--no-config", "--no-build", "--no-python-downloads", "--python=3.11",
                               f"--default-index={index}", f"--cache-dir={project.parent / 'lock-cache'}"], cwd=project,
                              env={"HOME": str(Path.home()), "PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"}, capture_output=True, text=True, check=False, timeout=20)
        assert lock.returncode == 0, lock.stderr
        (project / ".venv/bin").mkdir(parents=True)
        executable = project / ".venv/bin/python"
        executable.write_text('#!/bin/sh\ntouch "' + str(project / "OLD_INTERPRETER_EXECUTED") + '"\n')
        executable.chmod(0o700)
        before = list(requests)
        offline = setup_plan(project, profile="python-uv", registry=index)
        result = asyncio.run(run_setup(project, offline["sha256"], profile="python-uv", registry=index, confirmed=True))
        assert result["status"] == "failed" and requests == before
        plan = setup_plan(project, profile="python-uv", registry=index, network=True)
        output = []
        result = asyncio.run(run_setup(project, plan["sha256"], profile="python-uv", registry=index, network=True, confirmed=True,
                                       on_output=lambda stream, text: output.append(text)))
        assert result["status"] == "succeeded", "".join(output)
        environment = Path(plan["environment_path"])
        site = environment / "lib/python3.11/site-packages"
        assert (site / "tiny_fixture/__init__.py").read_text() == "ANSWER = 42\n"
        before = list(requests)
        again = setup_plan(project, profile="python-uv", registry=index)
        result = asyncio.run(run_setup(project, again["sha256"], profile="python-uv", registry=index, confirmed=True))
        assert result["status"] == "succeeded" and requests == before
        assert not (project / "PTH_EXECUTED").exists()
        assert not (project / "OLD_INTERPRETER_EXECUTED").exists()
        assert not (project / "BACKEND_EXECUTED").exists()


def test_real_registry_crate_fetch_and_explicit_check_use_private_cache_and_build_permission(project):
    require_namespaces()
    rust_project(project)
    (project / "Cargo.toml").write_text((project / "Cargo.toml").read_text() + '[dependencies]\ntiny-fixture="=0.1.0"\n')
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode="w:gz") as stream:
        files = {"tiny-fixture-0.1.0/Cargo.toml": b'[package]\nname="tiny-fixture"\nversion="0.1.0"\nedition="2021"\nbuild="build.rs"\n',
                 "tiny-fixture-0.1.0/src/lib.rs": b'pub fn answer() -> u32 { 42 }\n',
                 "tiny-fixture-0.1.0/build.rs": b'fn main() { std::fs::write("DEPENDENCY_BUILD_EXECUTED", "allowed").unwrap(); }\n'}
        for name, data in files.items():
            metadata = tarfile.TarInfo(name)
            metadata.size = len(data)
            metadata.mode = 0o644
            stream.addfile(metadata, io.BytesIO(data))
    crate = archive.getvalue()
    checksum = hashlib.sha256(crate).hexdigest()
    (project / "Cargo.lock").write_text('version=4\n[[package]]\nname="rust-fixture"\nversion="1.0.0"\ndependencies=["tiny-fixture"]\n[[package]]\nname="tiny-fixture"\nversion="0.1.0"\nsource="registry+https://github.com/rust-lang/crates.io-index"\nchecksum="' + checksum + '"\n')
    with registry_server() as (index, resources, requests):
        resources["/config.json"] = json.dumps({"dl": index + "/api/v1/crates"}).encode()
        resources["/ti/ny/tiny-fixture"] = json.dumps({"name": "tiny-fixture", "vers": "0.1.0", "deps": [], "cksum": checksum, "features": {}, "yanked": False}).encode() + b"\n"
        resources["/api/v1/crates/tiny-fixture/0.1.0/download"] = crate
        plan = setup_plan(project, profile="rust-cargo", registry=index, network=True)
        output = []
        result = asyncio.run(run_setup(project, plan["sha256"], profile="rust-cargo", registry=index, network=True, confirmed=True,
                                       on_output=lambda stream, text: output.append(text)))
        assert result["status"] == "succeeded", "".join(output)
        assert not (project / "BUILD_EXECUTED").exists()
        cache = Path(plan["cache_path"])
        assert not list(cache.rglob("DEPENDENCY_BUILD_EXECUTED"))
        (cache / "config.toml").write_text('[credential-alias]\nevil=["must-not-run"]\n')
        before = list(requests)
        offline = setup_plan(project, profile="rust-cargo", registry=index)
        result = asyncio.run(run_setup(project, offline["sha256"], profile="rust-cargo", registry=index, confirmed=True))
        assert result["status"] == "succeeded" and requests == before
        approved = setup_plan(project, profile="rust-cargo", registry=index, allow_builds=True)
        output.clear()
        result = asyncio.run(run_setup(project, approved["sha256"], profile="rust-cargo", registry=index, allow_builds=True, confirmed=True,
                                       on_output=lambda stream, text: output.append(text)))
        assert result["status"] == "succeeded", "".join(output)
        assert (project / "BUILD_EXECUTED").exists()
        assert list(cache.rglob("DEPENDENCY_BUILD_EXECUTED"))


@pytest.mark.parametrize("field", ["requires-python", ".python-version"])
def test_python_version_requests_cannot_select_project_executable_paths(project, monkeypatch, field):
    python_project(project)
    if field == ".python-version":
        (project / field).write_text(str(project / "untrusted-python"))
    else:
        (project / "pyproject.toml").write_text((project / "pyproject.toml").read_text().replace(">=3.11,<3.12", str(project / "untrusted-python")))
    monkeypatch.setattr("bifang.setup_profiles.probe", lambda *args: pytest.fail("Untrusted version request reached interpreter probing"))
    with pytest.raises(ValueError):
        setup_plan(project, profile="python-uv")


def test_python_source_build_backend_requires_explicit_build_permission(project):
    require_namespaces()
    python_project(project)
    (project / "pyproject.toml").write_text((project / "pyproject.toml").read_text().replace("dependencies=[]", 'dependencies=["tiny-fixture==1.0.0"]'))
    backend = '''import pathlib, zipfile
def build_wheel(wheel_directory, config_settings=None, metadata_directory=None):
    pathlib.Path("/workspace/PYTHON_BUILD_EXECUTED").write_text("explicitly allowed")
    name = "tiny_fixture-1.0.0-py3-none-any.whl"
    with zipfile.ZipFile(pathlib.Path(wheel_directory) / name, "w") as archive:
        archive.writestr("tiny_fixture/__init__.py", "ANSWER = 73\\n")
        archive.writestr("tiny_fixture-1.0.0.dist-info/METADATA", "Metadata-Version: 2.2\\nName: tiny-fixture\\nVersion: 1.0.0\\n")
        archive.writestr("tiny_fixture-1.0.0.dist-info/WHEEL", "Wheel-Version: 1.0\\nRoot-Is-Purelib: true\\nTag: py3-none-any\\n")
        archive.writestr("tiny_fixture-1.0.0.dist-info/RECORD", "")
    return name
'''
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w:gz") as archive:
        for name, data in {"tiny_fixture-1.0.0/pyproject.toml": b'[build-system]\nrequires=[]\nbuild-backend="fixture_backend"\nbackend-path=["."]\n',
                           "tiny_fixture-1.0.0/fixture_backend.py": backend.encode()}.items():
            entry = tarfile.TarInfo(name)
            entry.size = len(data)
            archive.addfile(entry, io.BytesIO(data))
    source = output.getvalue()
    wheel = wheel_fixture(project)
    with registry_server() as (base, resources, _requests):
        index = base + "/simple"
        resources["/packages/tiny_fixture-1.0.0-py3-none-any.whl"] = wheel
        resources["/simple/tiny-fixture/"] = f'<a href="/packages/tiny_fixture-1.0.0-py3-none-any.whl#sha256={hashlib.sha256(wheel).hexdigest()}">fixture</a>'.encode()
        locked = subprocess.run([str(selected_uv(project)), "lock", "--no-config", "--no-build", "--no-python-downloads", "--python=3.11",
                                 f"--default-index={index}", f"--cache-dir={project.parent / 'lock-cache'}"], cwd=project,
                                env={"HOME": str(Path.home()), "PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"}, capture_output=True, text=True, check=False, timeout=20)
        assert locked.returncode == 0, locked.stderr
        resources["/packages/tiny_fixture-1.0.0.tar.gz"] = source
        lock = (project / "uv.lock").read_text()
        replacement = f'sdist = {{ url = "{base}/packages/tiny_fixture-1.0.0.tar.gz", hash = "sha256:{hashlib.sha256(source).hexdigest()}", size = {len(source)} }}\n'
        updated, count = re.subn(r"wheels = \[.*?\]\n", replacement, lock, flags=re.DOTALL)
        assert count == 1
        (project / "uv.lock").write_text(updated)
        plan = setup_plan(project, profile="python-uv", registry=index, network=True)
        receipt = asyncio.run(run_setup(project, plan["sha256"], profile="python-uv", registry=index, network=True, confirmed=True))
        assert receipt["status"] == "failed" and not (project / "PYTHON_BUILD_EXECUTED").exists()
        allowed = setup_plan(project, profile="python-uv", registry=index, network=True, allow_builds=True)
        log = []
        receipt = asyncio.run(run_setup(project, allowed["sha256"], profile="python-uv", registry=index, network=True, allow_builds=True, confirmed=True,
                                        on_output=lambda stream, text: log.append(text)))
        assert receipt["status"] == "succeeded", "".join(log)
        assert (project / "PYTHON_BUILD_EXECUTED").read_text() == "explicitly allowed"
        assert not (project / "BACKEND_EXECUTED").exists()


@pytest.mark.parametrize("profile", ["python-uv", "rust-cargo"])
def test_cli_profile_review_and_exact_no_build_execution(project, profile):
    require_namespaces()
    if profile == "python-uv":
        python_project(project)
    else:
        rust_project(project)
    command = [sys.executable, "-m", "bifang", "--workspace", str(project), "setup"]
    preview = subprocess.run([*command, "review", "--profile", profile], capture_output=True, text=True, timeout=20, check=False)
    assert preview.returncode == 0, preview.stderr
    plan = json.loads(preview.stdout)
    result = subprocess.run([*command, "run", "--profile", profile, "--sha256", plan["sha256"], "--yes"], capture_output=True, text=True, timeout=20, check=False)
    assert result.returncode == 0, result.stderr
    receipt = json.loads(result.stdout[result.stdout.rfind('{\n  "plan_sha256"'):])
    assert receipt["plan"]["profile"] == profile and receipt["scripts"] == "disabled"
