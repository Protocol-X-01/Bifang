import asyncio
import base64
import hashlib
import io
import json
import platform
import subprocess
import sys
import tarfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from bifang.package_setup import display_output, run_setup, sandbox_argv, setup_plan


@pytest.fixture
def npm_project(tmp_path, monkeypatch):
    if platform.system() != "Linux" or not Path("/usr/bin/npm").is_file():
        pytest.skip("This adapter targets the Linux system npm installation")
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    package = {"name": "bifang-setup-fixture", "version": "1.0.0", "scripts": {
        "postinstall": "node -e \"require('fs').writeFileSync('HOOK_EXECUTED', 'bad')\""}}
    (tmp_path / "package.json").write_text(json.dumps(package))
    (tmp_path / "package-lock.json").write_text(json.dumps({
        "name": package["name"], "version": package["version"], "lockfileVersion": 3,
        "requires": True, "packages": {"": {"name": package["name"], "version": package["version"]}}}))
    return tmp_path


def require_sandbox():
    if platform.system() != "Linux" or not Path("/usr/bin/bwrap").is_file():
        pytest.skip("Actual Linux Bubblewrap is required")
    probe = subprocess.run(["/usr/bin/bwrap", "--unshare-all", "--ro-bind", "/", "/", "--", "/usr/bin/true"], capture_output=True, check=False)
    if probe.returncode:
        pytest.skip("Current system does not permit Bubblewrap namespaces")


def fixture_workload(monkeypatch, script):
    original = sandbox_argv

    def arguments(plan):
        command = original(plan)
        return command[:command.index("--") + 1] + ["/usr/bin/python3", "-c", script]

    monkeypatch.setattr("bifang.package_setup.sandbox_argv", arguments)


def test_plan_binds_bytes_paths_network_and_exact_command_without_running_hooks(npm_project):
    plan = setup_plan(npm_project)
    assert plan == setup_plan(npm_project)
    assert plan["network"] == "offline-v1"
    assert "--ignore-scripts" in plan["argv"] and "--offline" in plan["argv"]
    online = setup_plan(npm_project, network=True)
    assert online["sha256"] != plan["sha256"]
    assert "--share-net" in sandbox_argv(online)
    assert "--share-net" not in sandbox_argv(plan)
    assert not (npm_project / "HOOK_EXECUTED").exists()
    (npm_project / "package.json").write_text('{"name":"changed"}')
    assert setup_plan(npm_project)["sha256"] != plan["sha256"]


@pytest.mark.parametrize("filename", [".npmrc", "npm-shrinkwrap.json", "pnpm-lock.yaml", "yarn.lock", "bun.lock"])
def test_foreign_managers_and_custom_configuration_are_not_silently_substituted(npm_project, filename):
    (npm_project / filename).write_text("fixture")
    with pytest.raises(ValueError, match="separate setup support"):
        setup_plan(npm_project)


def test_symlinks_and_nonregular_manifests_fail_without_reading_target(npm_project, tmp_path):
    source = npm_project / "package-lock.json"
    source.unlink()
    source.symlink_to(tmp_path / "not-present")
    with pytest.raises(OSError):
        setup_plan(npm_project)


def test_rejects_stale_or_unconfirmed_plan_before_starting_any_process(npm_project, monkeypatch):
    plan = setup_plan(npm_project)

    async def forbidden(*args, **kwargs):
        pytest.fail("Unapproved setup must not spawn")

    monkeypatch.setattr("bifang.package_setup.asyncio.create_subprocess_exec", forbidden)
    with pytest.raises(PermissionError):
        asyncio.run(run_setup(npm_project, plan["sha256"]))
    with pytest.raises(ValueError, match="changed"):
        asyncio.run(run_setup(npm_project, plan["sha256"], network=True, confirmed=True))
    (npm_project / "package-lock.json").write_text('{}')
    with pytest.raises(ValueError):
        asyncio.run(run_setup(npm_project, plan["sha256"], confirmed=True))


def test_real_offline_npm_setup_suppresses_hooks_and_preserves_manifest_bytes(npm_project, monkeypatch):
    require_sandbox()
    monkeypatch.setenv("BIFANG_SYNTHETIC_PRIVATE", "must-not-reach-child")
    before = {name: (npm_project / name).read_bytes() for name in ("package.json", "package-lock.json")}
    output = []
    receipt = asyncio.run(run_setup(npm_project, setup_plan(npm_project)["sha256"], confirmed=True,
                                   on_output=lambda stream, value: output.append(value)))
    assert receipt["status"] == "succeeded", (receipt, output)
    assert receipt["returncode"] == 0 and receipt["scripts"] == "disabled"
    assert receipt["output_bytes"] > 0
    saved = Path(receipt["receipt_path"])
    assert saved.stat().st_mode & 0o777 == 0o600
    assert json.loads(saved.read_text())["plan_sha256"] == receipt["plan_sha256"]
    assert not (npm_project / "HOOK_EXECUTED").exists()
    assert {name: (npm_project / name).read_bytes() for name in before} == before


def test_real_npm_installs_integrity_pinned_dependency_without_root_or_dependency_hooks(npm_project):
    require_sandbox()
    artifact = npm_project / "fixture.tgz"
    dependency = {"name": "fixture-dependency", "version": "1.0.0", "scripts": {
        "install": "node -e \"require('fs').writeFileSync('/workspace/DEPENDENCY_HOOK', 'bad')\""}}
    with tarfile.open(artifact, "w:gz") as archive:
        for name, content in {"package/package.json": json.dumps(dependency).encode(), "package/index.js": b"module.exports = 42;\n"}.items():
            metadata = tarfile.TarInfo(name)
            metadata.size = len(content)
            archive.addfile(metadata, io.BytesIO(content))
    package = json.loads((npm_project / "package.json").read_text())
    package["dependencies"] = {"fixture-dependency": "file:fixture.tgz"}
    (npm_project / "package.json").write_text(json.dumps(package))
    lock = json.loads((npm_project / "package-lock.json").read_text())
    lock["packages"][""]["dependencies"] = package["dependencies"]
    lock["packages"]["node_modules/fixture-dependency"] = {
        "version": "1.0.0", "resolved": "file:fixture.tgz", "hasInstallScript": True,
        "integrity": "sha512-" + base64.b64encode(hashlib.sha512(artifact.read_bytes()).digest()).decode()}
    (npm_project / "package-lock.json").write_text(json.dumps(lock))
    receipt = asyncio.run(run_setup(npm_project, setup_plan(npm_project)["sha256"], confirmed=True))
    assert receipt["status"] == "succeeded"
    assert (npm_project / "node_modules/fixture-dependency/index.js").read_text() == "module.exports = 42;\n"
    assert not (npm_project / "HOOK_EXECUTED").exists()
    assert not (npm_project / "DEPENDENCY_HOOK").exists()


def test_cancel_stops_workload_and_concurrent_setup_is_rejected(npm_project, monkeypatch):
    require_sandbox()
    fixture_workload(monkeypatch, "import subprocess,time; subprocess.Popen(['/usr/bin/python3','-c',\"import time; time.sleep(1); open('/workspace/DESCENDANT_WRITE','w').write('bad')\"]); print('ready', flush=True); time.sleep(20); open('/workspace/LATE_WRITE','w').write('bad')")

    async def scenario():
        ready = asyncio.Event()
        fingerprint = setup_plan(npm_project)["sha256"]
        operation = asyncio.create_task(run_setup(npm_project, fingerprint, confirmed=True,
                                                  on_output=lambda stream, text: ready.set()))
        await asyncio.wait_for(ready.wait(), 5)
        with pytest.raises(RuntimeError, match="Another setup"):
            await run_setup(npm_project, fingerprint, confirmed=True)
        operation.cancel()
        receipt = await asyncio.wait_for(operation, 5)
        assert receipt["status"] == "cancelled" and receipt["returncode"] != 0
        assert receipt["receipt_saved"]
        await asyncio.sleep(1.1)
        assert not (npm_project / "LATE_WRITE").exists()
        assert not (npm_project / "DESCENDANT_WRITE").exists()

    asyncio.run(scenario())


@pytest.mark.parametrize("outcome", ["timed_out", "output_limit", "inputs_changed"])
def test_bounded_lifecycle_and_changed_inputs_receipts(npm_project, monkeypatch, outcome):
    require_sandbox()
    if outcome == "timed_out":
        monkeypatch.setattr("bifang.package_setup.TIMEOUT_SECONDS", 1)
        script = "import time; time.sleep(20)"
    elif outcome == "output_limit":
        monkeypatch.setattr("bifang.package_setup.MAX_OUTPUT", 100)
        script = "print('x' * 10000)"
    else:
        script = "open('/workspace/package.json','w').write('{}')"
    fixture_workload(monkeypatch, script)
    receipt = asyncio.run(run_setup(npm_project, setup_plan(npm_project)["sha256"], confirmed=True))
    assert receipt["status"] == outcome
    assert receipt["receipt_saved"]


def test_environment_is_not_forwarded_and_terminal_control_output_is_literal(npm_project, monkeypatch):
    require_sandbox()
    monkeypatch.setenv("BIFANG_SYNTHETIC_PRIVATE", "must-not-be-forwarded")
    fixture_workload(monkeypatch, "import os; print(os.environ.get('BIFANG_SYNTHETIC_PRIVATE', 'absent')); print('\\x1b]52;c;fixture\\x07')")
    output = []
    receipt = asyncio.run(run_setup(npm_project, setup_plan(npm_project)["sha256"], confirmed=True,
                                   on_output=lambda stream, text: output.append(text)))
    assert receipt["status"] == "succeeded"
    assert "absent" in "".join(output) and "must-not-be-forwarded" not in "".join(output)
    assert "\x1b" not in "".join(output) and "\x07" not in "".join(output)
    assert display_output("\x1b[2J") == "\\u001b[2J"


def test_network_requires_opt_in_and_downloads_only_after_online_plan_approval(npm_project):
    require_sandbox()
    artifact = io.BytesIO()
    with tarfile.open(fileobj=artifact, mode="w:gz") as archive:
        for name, data in {"package/package.json": b'{"name":"network-fixture","version":"1.0.0"}',
                           "package/index.js": b"module.exports = 73;\n"}.items():
            metadata = tarfile.TarInfo(name)
            metadata.size = len(data)
            archive.addfile(metadata, io.BytesIO(data))
    content = artifact.getvalue()
    hits = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            hits.append(self.path)
            if self.path != "/network-fixture/-/fixture.tgz":
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        def log_message(self, *args):
            pass

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            registry = f"http://127.0.0.1:{server.server_port}"
            url = registry + "/network-fixture/-/fixture.tgz"
            package = json.loads((npm_project / "package.json").read_text())
            package["dependencies"] = {"network-fixture": "1.0.0"}
            (npm_project / "package.json").write_text(json.dumps(package))
            lock = json.loads((npm_project / "package-lock.json").read_text())
            lock["packages"][""]["dependencies"] = package["dependencies"]
            lock["packages"]["node_modules/network-fixture"] = {
                "version": "1.0.0", "resolved": url,
                "integrity": "sha512-" + base64.b64encode(hashlib.sha512(content).digest()).decode()}
            (npm_project / "package-lock.json").write_text(json.dumps(lock))
            offline = asyncio.run(run_setup(npm_project, setup_plan(npm_project, registry=registry)["sha256"], registry=registry, confirmed=True))
            assert offline["status"] == "failed" and hits == []
            plan = setup_plan(npm_project, network=True, registry=registry)
            output = []
            online = asyncio.run(run_setup(npm_project, plan["sha256"], network=True, registry=registry, confirmed=True,
                                          on_output=lambda stream, value: output.append(value)))
            assert online["status"] == "succeeded" and hits == ["/network-fixture/-/fixture.tgz"], "".join(output)
            assert (npm_project / "node_modules/network-fixture/index.js").read_text() == "module.exports = 73;\n"
            cached = asyncio.run(run_setup(npm_project, setup_plan(npm_project, registry=registry)["sha256"], registry=registry, confirmed=True))
            assert cached["status"] == "succeeded" and hits == ["/network-fixture/-/fixture.tgz"]
        finally:
            server.shutdown()
            worker.join(timeout=5)


def test_cli_review_default_deny_and_exact_approved_install(npm_project):
    require_sandbox()
    command = [sys.executable, "-m", "bifang", "--workspace", str(npm_project), "setup"]
    review = subprocess.run([*command, "review"], capture_output=True, text=True, check=False, timeout=10)
    assert review.returncode == 0, review.stderr
    fingerprint = json.loads(review.stdout)["sha256"]
    denied = subprocess.run([*command, "run", "--sha256", fingerprint], input="\n", capture_output=True,
                            text=True, check=False, timeout=10)
    assert denied.returncode == 0 and "no process started" in denied.stdout
    assert not (npm_project / "state/bifang/setup-receipts").exists()
    allowed = subprocess.run([*command, "run", "--sha256", fingerprint, "--yes"], capture_output=True,
                             text=True, check=False, timeout=10)
    assert allowed.returncode == 0, allowed.stderr
    receipt = json.loads(allowed.stdout[allowed.stdout.rfind('{\n  "plan_sha256"'):])
    assert receipt["status"] == "succeeded" and receipt["receipt_saved"]
    assert receipt["plan"]["inputs"] == setup_plan(npm_project)["inputs"]
    assert not (npm_project / "HOOK_EXECUTED").exists()


@pytest.mark.parametrize("registry", ["http://registry.example", "https://user:synthetic@example.com", "https://example.com?token=synthetic", "https://example.com#fragment", "https://example.com:99999", "https://example.com/\x00"])
def test_registry_inputs_reject_credentials_unsafe_transport_and_ambiguous_urls(npm_project, registry):
    with pytest.raises(ValueError):
        setup_plan(npm_project, registry=registry)


def test_no_host_fallback_when_sandbox_is_not_supported(npm_project, monkeypatch):
    fingerprint = setup_plan(npm_project)["sha256"]
    monkeypatch.setattr("bifang.package_setup.platform.system", lambda: "Windows")
    with pytest.raises(RuntimeError, match="no unsandboxed"):
        asyncio.run(run_setup(npm_project, fingerprint, confirmed=True))


def test_start_and_output_failures_are_recorded_without_raw_diagnostics(npm_project, monkeypatch):
    async def cannot_start(*args, **kwargs):
        raise OSError("synthetic-private-diagnostic")

    monkeypatch.setattr("bifang.package_setup.asyncio.create_subprocess_exec", cannot_start)
    receipt = asyncio.run(run_setup(npm_project, setup_plan(npm_project)["sha256"], confirmed=True))
    assert receipt["status"] == "start_failed" and receipt["receipt_saved"]
    assert "synthetic-private-diagnostic" not in Path(receipt["receipt_path"]).read_text()


def test_output_consumer_failure_stops_real_workload_and_retains_exit_receipt(npm_project, monkeypatch):
    require_sandbox()
    fixture_workload(monkeypatch, "import time; print('ready', flush=True); time.sleep(20)")

    def cannot_display(*args):
        raise RuntimeError("synthetic display failure")

    receipt = asyncio.run(run_setup(npm_project, setup_plan(npm_project)["sha256"], confirmed=True, on_output=cannot_display))
    assert receipt["status"] == "output_error" and receipt["receipt_saved"]


def test_cache_symlink_is_refused_without_touching_its_target(npm_project):
    plan = setup_plan(npm_project)
    cache = Path(plan["cache_path"])
    cache.parent.mkdir(parents=True)
    outside = npm_project / "unrelated-directory"
    outside.mkdir()
    cache.symlink_to(outside, target_is_directory=True)
    receipt = asyncio.run(run_setup(npm_project, plan["sha256"], confirmed=True))
    assert receipt["status"] == "start_failed"
    assert list(outside.iterdir()) == []


def test_receipt_save_failure_does_not_falsely_claim_persistence(npm_project, monkeypatch):
    require_sandbox()

    def cannot_save(*args):
        raise PermissionError("synthetic unwritable state")

    monkeypatch.setattr("bifang.package_setup.retain_receipt", cannot_save)
    receipt = asyncio.run(run_setup(npm_project, setup_plan(npm_project)["sha256"], confirmed=True))
    assert receipt["status"] == "succeeded" and not receipt["receipt_saved"]
    assert receipt["receipt_path"] is None
