import ast
import asyncio
import hashlib
import json
import os
from pathlib import Path

import pytest

from bifang import remote_executor
from bifang.remote_coding import snapshot_digest
from bifang.remote_executor import Broker, BrokerClient, Executor, snapshot_hash, validate_request


def payload(**changes):
    return {"files": {"source.py": "print('synthetic fixture')\n"}, "command": ["python", "source.py"], "timeout": 1, **changes}


@pytest.mark.parametrize("changes", [
    {"image": "caller-selected-image"}, {"environment": {"KEY": "not accepted"}}, {"mounts": []},
    {"files": {}}, {"files": {"../escape": "no"}}, {"files": {"/etc/passwd": "no"}},
    {"files": {".aws/credentials": "no"}}, {"files": {".env": "no"}}, {"files": {"source.py": "x" * 64001}},
    {"files": {"a": "x", "a/b": "x"}}, {"files": {"a//b": "x"}}, {"files": {"a\\b": "x"}},
    {"files": {"secret.key": "x"}}, {"files": {"id_rsa": "x"}}, {"files": {"a\x00b": "x"}},
    {"command": []}, {"command": ["python", "bad\x00arg"]}, {"command": ["x" * 2049]},
    {"timeout": True}, {"timeout": 61}, {"timeout": 0},
])
def test_broker_revalidates_narrow_contract(changes):
    with pytest.raises(ValueError):
        validate_request(payload(**changes))


def test_broker_hash_and_capabilities_match_control_plane():
    files, command, timeout = validate_request(payload())
    assert snapshot_hash(files) == snapshot_digest(files)
    assert command == ["python", "source.py"] and timeout == 1
    executor = Executor("sha256:" + "a" * 64, "/operator/runsc", "b" * 64, "/operator/scratch")
    arguments = executor.arguments("bifang-check-synthetic", Path("/operator/scratch/snapshot"), command)
    for option in ("--read-only", "--cap-drop", "ALL", "--network", "none", "--runtime", "bifang-runsc",
                   "no-new-privileges", "--memory-swap", "256m", "--pids-limit", "128"):
        assert option in arguments
    assert arguments[arguments.index("--mount") + 1] == "type=bind,src=/operator/scratch/snapshot,dst=/workspace,readonly"
    assert "--privileged" not in arguments and "--env-file" not in arguments
    assert not any("docker.sock" in argument for argument in arguments)
    assert set(executor.environment) == {"PATH", "HOME", "DOCKER_HOST", "DOCKER_CONFIG"}
    assert "-I" in arguments and "os.execvpe" in remote_executor.LAUNCHER


class FixtureExecutor(Executor):
    def __init__(self, scratch, exit_code=0):
        super().__init__("sha256:" + "a" * 64, "/synthetic/runsc", "b" * 64, scratch, uid=os.getuid())
        self.calls, self.workspace, self.exit_code = [], None, exit_code

    async def verify_runtime(self):
        return None

    async def control(self, *arguments):
        self.calls.append(arguments)
        if arguments[0] == "create":
            mount = arguments[arguments.index("--mount") + 1]
            self.workspace = Path(mount.split("src=", 1)[1].split(",dst=", 1)[0])
            return b"synthetic-container"
        if arguments[0] == "inspect":
            return json.dumps([{"HostConfig": {"Runtime": "bifang-runsc", "NetworkMode": "none", "ReadonlyRootfs": True,
                "CapDrop": ["ALL"], "SecurityOpt": ["no-new-privileges"], "Memory": 256 * 1024 * 1024,
                "MemorySwap": 256 * 1024 * 1024, "NanoCpus": 1000000000, "PidsLimit": 128},
                "Image": self.image, "Config": {"User": str(self.uid) + ":" + str(self.uid)},
                "Mounts": [{"Type": "bind", "Source": str(self.workspace), "Destination": "/workspace", "RW": False}],
                "State": {"Status": "exited", "ExitCode": self.exit_code, "Error": ""}}]).encode()
        assert arguments[:2] == ("rm", "--force")
        return b""


class FixtureProcess:
    def __init__(self, output=b"synthetic output\n", eof=True):
        self.stdout = asyncio.StreamReader()
        self.stdout.feed_data(output)
        if eof:
            self.stdout.feed_eof()
        self.returncode, self.killed = None, False

    async def wait(self):
        if self.returncode is None:
            self.returncode = 0
        return self.returncode

    def kill(self):
        self.killed, self.returncode = True, -9


@pytest.mark.parametrize("mode", ["success", "nonzero", "timeout", "overflow"])
def test_executor_lifecycle_limits_and_cleanup_with_synthetic_docker(tmp_path, monkeypatch, mode):
    async def scenario():
        scratch = tmp_path / "scratch"
        scratch.mkdir(mode=0o700)
        executor = FixtureExecutor(scratch, exit_code=2 if mode == "nonzero" else 0)
        output = b"x" * (remote_executor.MAX_OUTPUT + 1) if mode == "overflow" else b"synthetic output\n"
        process = FixtureProcess(output, eof=mode != "timeout")

        async def launch(*arguments, **options):
            assert arguments[:3] == ("/usr/bin/docker", "start", "--attach")
            assert options["env"] == executor.environment
            assert (executor.workspace / "source.py").read_text() == payload()["files"]["source.py"]
            return process

        monkeypatch.setattr(remote_executor.asyncio, "create_subprocess_exec", launch)
        receipt = await executor.run(payload())
        assert receipt["candidate_sha256"] == snapshot_digest(payload()["files"])
        assert receipt["exit_code"] == {"success": 0, "nonzero": 2, "timeout": 124, "overflow": 125}[mode]
        assert receipt["timed_out"] == (mode == "timeout")
        assert receipt["output_sha256"] == hashlib.sha256(output[:remote_executor.MAX_OUTPUT]).hexdigest()
        assert executor.calls[-1][:2] == ("rm", "--force")
        assert not executor.workspace.exists()
        if mode in {"timeout", "overflow"}:
            assert process.killed

    asyncio.run(scenario())


def test_real_unix_transport_returns_receipt_and_closes_on_cancellation(tmp_path):
    async def scenario():
        started, cancelled = asyncio.Event(), asyncio.Event()

        class Handler:
            async def run(self, request):
                if request["command"] == ["synthetic-hang"]:
                    started.set()
                    try:
                        await asyncio.Event().wait()
                    finally:
                        cancelled.set()
                return {"candidate_sha256": snapshot_hash(request["files"]), "command": request["command"],
                        "exit_code": 0, "timed_out": False, "output_sha256": "0" * 64}

        path = tmp_path / "broker.sock"
        broker = Broker(Handler(), peer_uid=os.getuid())
        server = await asyncio.start_unix_server(broker.handle, path=str(path), limit=remote_executor.MAX_BODY + 1)
        async with server:
            client = BrokerClient(path, server_uid=os.getuid())
            result = await client(**payload())
            assert result["candidate_sha256"] == snapshot_digest(payload()["files"])
            task = asyncio.create_task(client(**payload(command=["synthetic-hang"])))
            await started.wait()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            await asyncio.wait_for(cancelled.wait(), timeout=1)

    asyncio.run(scenario())


def test_unix_broker_rejects_extra_capabilities_without_echoing_source(tmp_path):
    async def scenario():
        class Handler:
            async def run(self, request):
                raise AssertionError("Invalid requests must not reach execution")

        path = tmp_path / "broker.sock"
        broker = Broker(Handler(), peer_uid=os.getuid())
        server = await asyncio.start_unix_server(broker.handle, path=str(path), limit=remote_executor.MAX_BODY + 1)
        async with server:
            reader, writer = await asyncio.open_unix_connection(str(path))
            writer.write(json.dumps(payload(environment={"KEY": "private-marker-not-echoed"})).encode() + b"\n")
            await writer.drain()
            response = await reader.readline()
            assert json.loads(response) == {"error": "execution_unavailable"}
            assert b"private-marker" not in response
            writer.close()
            await writer.wait_closed()

    asyncio.run(scenario())


def test_standalone_operator_components_keep_python39_grammar():
    root = Path(__file__).resolve().parents[1]
    for name in ("src/bifang/remote_executor.py", "scripts/verify-remote-executor.py"):
        ast.parse((root / name).read_text(), feature_version=(3, 9))


def test_runtime_installer_is_checksum_pinned_and_does_not_replace_defaults():
    root = Path(__file__).resolve().parents[1]
    content = (root / "deploy/aws/install-executor-runtime.sh").read_text()
    assert "release-20261019.0/gvisor-x86_64.tar.bz2" in content
    assert "sha512sum -c -" in content
    assert "member.isfile() or member.isdir()" in content
    assert "systemctl reload docker" in content
    assert "systemctl restart" not in content
    assert "default-runtime" not in content and "setenforce" not in content
    assert 'test "$active" = 0' in content


def test_client_rejects_wrong_server_identity_before_sending_source(tmp_path):
    async def scenario():
        received = []
        closed = asyncio.Event()

        async def handler(reader, writer):
            received.append(await reader.read())
            writer.close()
            await writer.wait_closed()
            closed.set()

        path = tmp_path / "wrong-peer.sock"
        server = await asyncio.start_unix_server(handler, path=str(path))
        async with server:
            with pytest.raises(RuntimeError, match="identity"):
                await BrokerClient(path, server_uid=os.getuid() + 1)(**payload())
            await asyncio.wait_for(closed.wait(), timeout=1)
            assert received == [b""]

    asyncio.run(scenario())
