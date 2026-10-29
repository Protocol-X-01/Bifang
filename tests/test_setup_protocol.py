import asyncio
import json
import os
import platform
import subprocess
import sys
from pathlib import Path

import pytest

from bifang.package_setup import setup_plan
from bifang.setup_protocol import parse_request
from bifang.workbench import dispatch


@pytest.fixture
def protocol_project(tmp_path, monkeypatch):
    if platform.system() != "Linux" or not Path("/usr/bin/npm").is_file():
        pytest.skip("Linux system npm adapter")
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    root = tmp_path / "project"
    root.mkdir()
    (root / "package.json").write_text('{"name":"protocol-fixture","version":"1.0.0","scripts":{"postinstall":"touch HOOK_EXECUTED"}}')
    (root / "package-lock.json").write_text('{"lockfileVersion":3,"packages":{"":{"name":"protocol-fixture","version":"1.0.0"}}}')
    return root


def input_request(root):
    plan = setup_plan(root)
    return {"version": 1, "workspace": str(root), "sha256": plan["sha256"], "network": False,
            "registry": plan["registry"], "confirmed": True}


def test_protocol_schema_requires_exact_human_confirmation_and_no_arbitrary_command(protocol_project):
    request = input_request(protocol_project)
    assert parse_request(json.dumps(request).encode() + b"\n") == request
    for extra in [{"confirmed": False}, {"command": "arbitrary"}, {"version": True}, {"network": "yes"}, {"sha256": "bad"}]:
        with pytest.raises(ValueError):
            parse_request(json.dumps({**request, **extra}).encode() + b"\n")
    with pytest.raises(ValueError):
        parse_request(b'{"version":1,"version":1}\n')
    with pytest.raises(ValueError):
        parse_request(b"x" * 8193 + b"\n")


def test_read_only_plan_bridge_does_not_create_cache_or_run_scripts(protocol_project):
    result = dispatch({"version": 1, "action": "setup.plan", "workspace": str(protocol_project), "network": False})
    assert result == setup_plan(protocol_project)
    assert not Path(result["cache_path"]).exists()
    assert not (protocol_project / "HOOK_EXECUTED").exists()


@pytest.mark.parametrize("profile", ["python-uv", "rust-cargo"])
def test_v2_protocol_requires_explicit_profile_and_boolean_build_permission(protocol_project, profile):
    request = {**input_request(protocol_project), "version": 2, "profile": profile, "allow_builds": False}
    assert parse_request(json.dumps(request).encode() + b"\n") == request
    for replacement in [{"allow_builds": "yes"}, {"profile": "arbitrary-command"}, {"profile": []}, {"version": 1}]:
        with pytest.raises(ValueError):
            parse_request(json.dumps({**request, **replacement}).encode() + b"\n")


@pytest.mark.parametrize("action", ["success", "cancel", "disconnect", "stale"])
def test_actual_helper_stream_lifecycle_and_parent_disconnect(protocol_project, monkeypatch, action):
    if not Path("/usr/bin/bwrap").is_file():
        pytest.skip("Actual Bubblewrap required")
    probe = subprocess.run(["/usr/bin/bwrap", "--unshare-all", "--ro-bind", "/", "/", "--", "/usr/bin/true"], capture_output=True, check=False)
    if probe.returncode:
        pytest.skip("Bubblewrap namespaces unavailable")
    request = input_request(protocol_project)
    if action == "stale":
        (protocol_project / "package.json").write_text('{}')
    environment = {"PATH": "/usr/bin:/bin", "HOME": str(protocol_project.parent),
                   "XDG_STATE_HOME": os.environ["XDG_STATE_HOME"], "BIFANG_NO_DOTENV": "1",
                   "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")}
    code = "from bifang.setup_protocol import main; main()"
    if action in ("cancel", "disconnect"):
        code = ("import bifang.package_setup as setup; original=setup.sandbox_argv; "
                "setup.sandbox_argv=lambda plan: original(plan)[:original(plan).index('--')+1]+"
                "['/usr/bin/python3','-c',\"import time; print('READY',flush=True); time.sleep(20)\"]; " + code)

    async def scenario():
        process = await asyncio.create_subprocess_exec(sys.executable, "-c", code, env=environment,
                                                      stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                                                      stderr=asyncio.subprocess.PIPE)
        events = []
        try:
            process.stdin.write(json.dumps(request).encode() + b"\n")
            await process.stdin.drain()
            while True:
                raw = await asyncio.wait_for(process.stdout.readline(), 8)
                if not raw:
                    break
                event = json.loads(raw)
                events.append(event)
                if action in ("cancel", "disconnect") and event["event"] == "output" and "READY" in event["text"]:
                    if action == "cancel":
                        process.stdin.write(b'{"cancel":true}\n')
                        await process.stdin.drain()
                    else:
                        process.stdin.close()
            await asyncio.wait_for(process.wait(), 5)
            if action == "stale":
                assert process.returncode == 1 and events[-1]["event"] == "error"
            else:
                assert process.returncode == 0
                result = events[-1]["receipt"]
                assert result["plan_sha256"] == request["sha256"] and result["receipt_saved"]
                assert result["status"] == ("succeeded" if action == "success" else "cancelled")
            assert not (protocol_project / "HOOK_EXECUTED").exists()
        finally:
            if process.returncode is None:
                process.kill()
                await process.wait()

    asyncio.run(scenario())
