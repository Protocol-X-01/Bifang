from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import signal
import subprocess
import tempfile
from pathlib import Path


async def install_fixture(binary: Path, project: Path, environment: dict, plan: dict) -> dict:
    process = await asyncio.create_subprocess_exec(str(binary), "--setup", cwd=project, env=environment,
                                                  start_new_session=True, stdin=asyncio.subprocess.PIPE,
                                                  stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    request = {"version": 1, "workspace": str(project), "sha256": plan["sha256"], "registry": plan["registry"],
               "network": False, "confirmed": True}
    if plan["profile"] != "javascript-npm":
        request.update({"version": 2, "profile": plan["profile"], "allow_builds": plan["allow_builds"]})
    progress = 0
    receipt = None
    size = 0
    try:
        process.stdin.write(json.dumps(request).encode() + b"\n")
        await process.stdin.drain()
        async with asyncio.timeout(20):
            while raw := await process.stdout.readline():
                size += len(raw)
                assert len(raw) <= 65_536 and size <= 8_000_000
                event = json.loads(raw)
                if event["event"] == "output":
                    progress += 1
                else:
                    assert event["event"] == "result" and receipt is None
                    receipt = event["receipt"]
            await process.wait()
        assert process.returncode == 0 and not await process.stderr.read()
        assert receipt and receipt["status"] == "succeeded" and receipt["receipt_saved"]
        assert receipt["plan_sha256"] == plan["sha256"] and receipt["inputs_unchanged"]
        saved = Path(receipt["receipt_path"])
        assert saved.stat().st_mode & 0o777 == 0o600
        assert json.loads(saved.read_text())["plan_sha256"] == plan["sha256"]
        assert (progress > 0 or plan["profile"] == "rust-cargo") and not (project / "HOOK_EXECUTED").exists()
        return {"plan": plan, "receipt": receipt, "progress_frames": progress,
                "wire_bytes": size, "saved_receipt_mode": "0600"}
    finally:
        if process.returncode is None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            await process.wait()


def check(binary: Path, metrics: bool = False, setup: bool = False, languages: bool = False) -> dict:
    passed = []
    setup_result = None
    profile_results = {}
    with tempfile.TemporaryDirectory(prefix="bifang-workbench-check-") as temporary:
        root = Path(temporary)
        project = root / "project"
        plugins = project / ".bifang/plugins"
        plugins.mkdir(parents=True)
        home = root / "home"
        home.mkdir()
        source = plugins / "fixture.py"
        source.write_text('raise RuntimeError("Fixture plugin must not execute during management")\n')
        (plugins / "fixture.plugin.json").write_text(json.dumps({
            "name": "fixture", "version": "1", "description": "Synthetic fixture", "capabilities": ["process"],
        }))
        (project / "package.json").write_text('{"scripts":{"postinstall":"must-not-run"}}')
        (project / ".env").write_text(f"XDG_STATE_HOME={root / 'forbidden-dotenv-state'}\n")
        environment = {key: value for key, value in os.environ.items()
                       if key in {"PATH", "SystemRoot", "WINDIR", "LANG", "LC_ALL", "TEMP", "TMP"}}
        environment.update({"HOME": str(home), "USERPROFILE": str(home),
                            "XDG_STATE_HOME": str(root / "state"), "BIFANG_ENV_FILE": str(project / ".env")})

        def call(action: str, expected: bool = True, **extra) -> dict:
            request = {"version": 1, "action": action, "workspace": str(project), **extra}
            result = subprocess.run([str(binary), "--workbench"],
                                    input=json.dumps(request) + "\n", text=True, capture_output=True,
                                    cwd=project, env=environment, timeout=15, check=False)
            response = json.loads(result.stdout)
            assert response["ok"] is expected
            assert (result.returncode == 0) is expected
            assert len(result.stdout.splitlines()) == 1
            assert not result.stderr
            return response.get("result", {})

        candidate = call("plugins.list")["plugins"][0]
        assert candidate["trusted"] is False
        passed.append("untrusted manifest discovery without code execution")
        reviewed = call("plugins.review", id=candidate["id"])
        assert reviewed["sha256"] == candidate["sha256"]
        assert "must not execute" in reviewed["source"]
        passed.append("exact source review without import")
        call("plugins.trust", expected=False, id=candidate["id"], sha256=candidate["sha256"], confirmed=False)
        passed.append("missing confirmation rejected")
        call("plugins.trust", id=candidate["id"], sha256=reviewed["sha256"], confirmed=True)
        assert call("plugins.list")["plugins"][0]["trusted"] is True
        assert (root / "state/bifang/plugins/trust.json").is_file()
        assert not (root / "forbidden-dotenv-state").exists()
        passed.append("exact-content trust uses explicit state without dotenv")
        source.write_text("changed = True\n")
        assert call("plugins.list")["plugins"][0]["state"] == "changed"
        call("plugins.trust", expected=False, id=candidate["id"], sha256=reviewed["sha256"], confirmed=True)
        passed.append("changed content disables trust and rejects stale fingerprint")
        call("plugins.disable", id=candidate["id"])
        assert call("plugins.list")["plugins"][0]["state"] == "disabled"
        passed.append("disable updates shared trust storage")
        profile = call("toolchains.inspect")["profiles"][0]
        assert profile["bootstrap_argv"] == ["npm", "install", "--ignore-scripts"]
        assert not (project / "node_modules").exists()
        passed.append("language bootstrap remains a non-executing preview")
        call("run", expected=False, command="must-not-run")
        passed.append("unknown operations rejected without command execution")
        if metrics:
            sampled = call("metrics.sample")
            assert sampled["schema"] == 1
            assert sampled["cpu"]["available"] and 0 <= sampled["cpu"]["percent"] <= 100
            assert sampled["memory"]["available"] and sampled["memory"]["total_bytes"] > 0
            assert sampled["disk"]["available"] and sampled["disk"]["total_bytes"] > 0
            assert sampled["gpu"]["available"] is False
            passed.append("actual local CPU, memory and disk metrics without GPU fabrication")
        if setup:
            (project / "package.json").write_text('{"name":"frozen-setup-fixture","version":"1.0.0","scripts":{"postinstall":"touch HOOK_EXECUTED"}}')
            (project / "package-lock.json").write_text('{"lockfileVersion":3,"packages":{"":{"name":"frozen-setup-fixture","version":"1.0.0"}}}')
            plan = call("setup.plan", network=False)
            assert not Path(plan["cache_path"]).exists()
            passed.append("setup plan binds manifest bytes without installing or creating cache")
            setup_result = asyncio.run(install_fixture(binary, project, environment, plan))
            assert not (root / "forbidden-dotenv-state").exists()
            passed.append("actual frozen setup streams progress, suppresses hooks and saves exact-plan receipt without dotenv")
        if languages:
            environment["HOME"] = str(Path.home())
            for key in ("RUSTUP_HOME", "UV_PYTHON_INSTALL_DIR", "XDG_DATA_HOME"):
                if key in os.environ:
                    environment[key] = os.environ[key]
            for profile in ("python-uv", "rust-cargo"):
                project = root / profile
                project.mkdir()
                if profile == "python-uv":
                    (project / "pyproject.toml").write_text('[project]\nname="frozen-python-fixture"\nversion="1.0.0"\nrequires-python=">=3.11,<3.12"\ndependencies=[]\n')
                    (project / "uv.lock").write_text('version=1\nrevision=3\nrequires-python=">=3.11,<3.12"\n[[package]]\nname="frozen-python-fixture"\nversion="1.0.0"\nsource={virtual="."}\n')
                else:
                    (project / "Cargo.toml").write_text('[package]\nname="frozen-rust-fixture"\nversion="1.0.0"\nedition="2021"\nbuild="build.rs"\n')
                    (project / "Cargo.lock").write_text('version=4\n[[package]]\nname="frozen-rust-fixture"\nversion="1.0.0"\n')
                    (project / "src").mkdir()
                    (project / "src/lib.rs").write_text('pub fn answer() -> u32 { 42 }\n')
                    (project / "build.rs").write_text('fn main() { std::fs::write("HOOK_EXECUTED", "bad").unwrap(); }\n')
                plan = call("setup.profile_plan", profile=profile, network=False, allow_builds=False)
                assert plan["scripts"] == "disabled"
                passed.append(f"{profile} read-only manifest/runtime-bound plan")
                profile_results[profile] = asyncio.run(install_fixture(binary, project, environment, plan))
                passed.append(f"{profile} actual frozen no-build setup and exact-plan saved receipt")
    return {"scope": "Frozen helper stdio acceptance, not native window or IPC acceptance",
            "binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(), "checks": passed,
            "setup": setup_result, "profiles": profile_results}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("binary", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--metrics", action="store_true")
    parser.add_argument("--setup", action="store_true")
    parser.add_argument("--languages", action="store_true")
    arguments = parser.parse_args()
    result = check(arguments.binary.resolve(strict=True), arguments.metrics, arguments.setup, arguments.languages)
    arguments.output.write_text(json.dumps(result, indent=2) + "\n")
    print(f"PASS: {len(result['checks'])} frozen helper checks; evidence: {arguments.output}")


if __name__ == "__main__":
    main()
