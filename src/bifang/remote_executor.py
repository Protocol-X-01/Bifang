from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import socket
import struct
import tempfile
import uuid
from pathlib import Path, PurePosixPath

RUNTIME = "bifang-runsc"
MAX_BODY = 400000
MAX_OUTPUT = 64000
LAUNCHER = "import os,sys; os.execvpe(sys.argv[1],sys.argv[1:],{'PATH':'/usr/local/bin:/usr/bin:/bin','HOME':'/tmp','PYTHONDONTWRITEBYTECODE':'1','PYTHONPATH':'/workspace'})"


def validate_request(payload):
    if not isinstance(payload, dict) or set(payload) != {"files", "command", "timeout"}:
        raise ValueError("Require only selected source, check arguments and a timeout")
    files, command, timeout = payload["files"], payload["command"], payload["timeout"]
    if not isinstance(files, dict) or not 1 <= len(files) <= 8:
        raise ValueError("Bound the selected snapshot")
    blocked = {".git", ".bifang", ".arca", ".venv", "node_modules", ".ssh", ".aws", ".vercel"}
    for name, content in files.items():
        if not isinstance(name, str) or not isinstance(content, str) or len(content) > 64000:
            raise ValueError("Bound ordinary source files")
        path = PurePosixPath(name)
        if (not name or len(name) > 200 or path.is_absolute() or path.as_posix() != name or name == "."
                or "\\" in name or ":" in name or ".." in path.parts
                or any(ord(character) < 32 or ord(character) == 127 for character in name)
                or any(part in blocked or part.startswith(".env") for part in path.parts)
                or path.name in {"credentials", "id_rsa", "id_ed25519"}
                or path.suffix.lower() in {".pem", ".key", ".p12", ".pfx"}
                or any(other.startswith(name + "/") for other in files)):
            raise ValueError("Select ordinary normalized source paths")
    if len(json.dumps(files, ensure_ascii=False).encode()) > 128000:
        raise ValueError("Selected source exceeds the byte budget")
    if (not isinstance(command, list) or not 1 <= len(command) <= 32
            or any(not isinstance(argument, str) or not argument or any(ord(character) < 32 for character in argument)
                   for argument in command)
            or sum(len(argument.encode()) for argument in command) > 2048
            or type(timeout) is not int or not 1 <= timeout <= 60):
        raise ValueError("Require bounded explicit arguments and timeout")
    return files, command, timeout


def snapshot_hash(files):
    manifest = {path: hashlib.sha256(content.encode()).hexdigest() for path, content in files.items()}
    return hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()


class Executor:
    def __init__(self, image, runtime_binary, runtime_sha256, scratch, *, uid=10001):
        if not re.fullmatch(r"sha256:[a-f0-9]{64}", image) or not re.fullmatch(r"[a-f0-9]{64}", runtime_sha256):
            raise ValueError("Pin the execution image and runtime binary")
        self.image, self.runtime_binary = image, Path(runtime_binary)
        self.runtime_sha256, self.scratch, self.uid = runtime_sha256, Path(scratch), uid
        self.environment = {"PATH": "/usr/bin:/bin", "HOME": "/nonexistent",
                            "DOCKER_HOST": "unix:///var/run/docker.sock", "DOCKER_CONFIG": "/run/bifang-executor/docker"}

    async def control(self, *arguments):
        process = await asyncio.create_subprocess_exec("/usr/bin/docker", *arguments, env=self.environment,
                                                       stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
        try:
            output, _unused = await asyncio.wait_for(process.communicate(), timeout=20)
            if process.returncode or len(output) > MAX_OUTPUT:
                raise RuntimeError("Executor control operation unavailable")
            return output
        finally:
            if process.returncode is None:
                process.kill()
                await process.wait()

    async def verify_runtime(self):
        if self.runtime_binary.is_symlink():
            raise RuntimeError("Use an installed, pinned runtime binary")
        metadata = self.runtime_binary.stat()
        if metadata.st_uid != 0 or metadata.st_mode & 0o022:
            raise RuntimeError("Runtime must be root-owned and not writable by other users")
        for parent in self.runtime_binary.parents:
            metadata = parent.stat()
            if parent.is_symlink() or metadata.st_uid != 0 or metadata.st_mode & 0o022:
                raise RuntimeError("Runtime ancestors must be controlled by the operator")
        if hashlib.sha256(self.runtime_binary.read_bytes()).hexdigest() != self.runtime_sha256:
            raise RuntimeError("Runtime binary changed")
        runtimes = json.loads(await self.control("info", "--format", "{{json .Runtimes}}"))
        runtime = runtimes.get(RUNTIME, {})
        if (runtime.get("path") != str(self.runtime_binary)
                or runtime.get("runtimeArgs") != ["--platform=systrap", "--network=none"]):
            raise RuntimeError("Required isolated runtime is unavailable; no fallback")

    def arguments(self, name, workspace, command):
        return ["create", "--pull", "never", "--name", name, "--label", "bifang.executor=1", "--runtime", RUNTIME,
                "--network", "none", "--read-only", "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
                "--user", str(self.uid) + ":" + str(self.uid), "--memory", "256m", "--memory-swap", "256m",
                "--cpus", "1", "--pids-limit", "128", "--log-driver", "none",
                "--tmpfs", "/tmp:rw,nosuid,noexec,size=16m,mode=1777", "--workdir", "/workspace",
                "--mount", "type=bind,src=" + str(workspace) + ",dst=/workspace,readonly",
                "--entrypoint", "/usr/local/bin/python", self.image, "-I", "-c", LAUNCHER, *command]

    def validate_container(self, container, workspace):
        host = container["HostConfig"]
        mounts = [mount for mount in container["Mounts"] if mount["Type"] == "bind"]
        if (host["Runtime"] != RUNTIME or host["NetworkMode"] != "none" or not host["ReadonlyRootfs"]
                or host["CapDrop"] != ["ALL"] or "no-new-privileges" not in host["SecurityOpt"]
                or host["Memory"] != 256 * 1024 * 1024 or host["MemorySwap"] != 256 * 1024 * 1024
                or host["NanoCpus"] != 1000000000 or host["PidsLimit"] != 128
                or container["Image"] != self.image or container["Config"]["User"] != str(self.uid) + ":" + str(self.uid)
                or len(mounts) != 1 or mounts[0]["Source"] != str(workspace)
                or mounts[0]["Destination"] != "/workspace" or mounts[0]["RW"]):
            raise RuntimeError("Created check container does not match the isolated contract")

    async def run(self, payload):
        files, command, timeout = validate_request(payload)
        if (self.scratch.is_symlink() or not self.scratch.is_dir() or self.scratch.stat().st_mode & 0o077
                or self.scratch.stat().st_uid != os.geteuid()):
            raise RuntimeError("Use a private operator-controlled scratch directory")
        await self.verify_runtime()
        name = "bifang-check-" + uuid.uuid4().hex
        with tempfile.TemporaryDirectory(prefix="snapshot-", dir=self.scratch) as directory:
            workspace = Path(directory)
            for path, content in files.items():
                target = workspace / path
                target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                target.write_bytes(content.encode("utf-8"))
                target.chmod(0o600)
                os.chown(target, self.uid, self.uid)
            for path in sorted(workspace.rglob("*"), reverse=True):
                if path.is_dir():
                    path.chmod(0o700)
                    os.chown(path, self.uid, self.uid)
            os.chown(workspace, self.uid, self.uid)
            process = None
            timed_out, overflow, digest = False, False, hashlib.sha256()
            try:
                await self.control(*self.arguments(name, workspace, command))
                container = json.loads(await self.control("inspect", name))[0]
                self.validate_container(container, workspace)
                process = await asyncio.create_subprocess_exec("/usr/bin/docker", "start", "--attach", name,
                                                               env=self.environment, stdout=asyncio.subprocess.PIPE,
                                                               stderr=asyncio.subprocess.STDOUT)

                async def consume():
                    nonlocal overflow
                    total = 0
                    while True:
                        chunk = await process.stdout.read(8192)
                        if not chunk:
                            break
                        digest.update(chunk[:max(0, MAX_OUTPUT - total)])
                        total += len(chunk)
                        if total > MAX_OUTPUT:
                            overflow = True
                            break
                    if not overflow:
                        await process.wait()

                try:
                    await asyncio.wait_for(consume(), timeout=timeout)
                except asyncio.TimeoutError:
                    timed_out = True
                if timed_out or overflow:
                    exit_code = 124 if timed_out else 125
                else:
                    container = json.loads(await self.control("inspect", name))[0]
                    if container["State"]["Status"] != "exited" or container["State"].get("Error"):
                        raise RuntimeError("Check did not reach a terminal container state")
                    exit_code = container["State"]["ExitCode"]
                return {"candidate_sha256": snapshot_hash(files), "command": command, "exit_code": exit_code,
                        "timed_out": timed_out, "output_sha256": digest.hexdigest()}
            finally:
                if process is not None and process.returncode is None:
                    process.kill()
                    await process.wait()
                await self.control("rm", "--force", name)


class Broker:
    def __init__(self, executor, *, peer_uid=10001):
        self.executor, self.peer_uid = executor, peer_uid
        self.busy = asyncio.Lock()
        self.connections = 0

    async def handle(self, reader, writer):
        counted = False
        try:
            peer = writer.get_extra_info("socket").getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
            _unused_pid, uid, _unused_gid = struct.unpack("3i", peer)
            if uid not in {0, self.peer_uid} or self.connections >= 8:
                return
            self.connections += 1
            counted = True
            line = await asyncio.wait_for(reader.readline(), timeout=5)
            if not line:
                return
            if len(line) > MAX_BODY:
                raise ValueError("Bound the executor request")
            payload = json.loads(line)
            validate_request(payload)
            if self.busy.locked():
                raise RuntimeError("Executor is busy")
            async with self.busy:
                running = asyncio.create_task(self.executor.run(payload))
                disconnected = asyncio.create_task(reader.read(1))
                try:
                    done, _pending = await asyncio.wait({running, disconnected}, return_when=asyncio.FIRST_COMPLETED)
                    if disconnected in done:
                        return
                    result = {"ok": await running}
                finally:
                    for task in (running, disconnected):
                        if not task.done():
                            task.cancel()
                    await asyncio.gather(running, disconnected, return_exceptions=True)
            writer.write(json.dumps(result).encode() + b"\n")
            await writer.drain()
        except (ValueError, RuntimeError, OSError, asyncio.TimeoutError):
            writer.write(b'{"error":"execution_unavailable"}\n')
            try:
                await writer.drain()
            except OSError:
                pass
        finally:
            if counted:
                self.connections -= 1
            writer.close()
            try:
                await writer.wait_closed()
            except OSError:
                pass


class BrokerClient:
    def __init__(self, path, *, server_uid=0):
        self.path, self.server_uid = Path(path), server_uid

    def trusted_peer(self, writer):
        peer = writer.get_extra_info("socket").getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
        if struct.unpack("3i", peer)[1] != self.server_uid:
            raise RuntimeError("Unexpected executor service identity")

    async def verify_peer(self):
        _reader, writer = await asyncio.open_unix_connection(str(self.path))
        try:
            self.trusted_peer(writer)
        finally:
            writer.close()
            await writer.wait_closed()

    async def __call__(self, files, command, timeout):
        payload = {"files": files, "command": command, "timeout": timeout}
        validate_request(payload)
        reader, writer = await asyncio.open_unix_connection(str(self.path), limit=8192)
        try:
            self.trusted_peer(writer)
            writer.write(json.dumps(payload, ensure_ascii=False).encode() + b"\n")
            await writer.drain()
            line = await asyncio.wait_for(reader.readline(), timeout=timeout + 8)
            result = json.loads(line)
            if not isinstance(result, dict) or set(result) != {"ok"} or not isinstance(result["ok"], dict):
                raise RuntimeError("Independent executor unavailable")
            return result["ok"]
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except OSError:
                pass


async def serve(options):
    if os.geteuid() != 0:
        raise RuntimeError("Run the narrow broker as its operator service")
    executor = Executor(options.image, options.runtime_binary, options.runtime_sha256, options.scratch)
    await executor.verify_runtime()
    path = Path(options.socket)
    parent = path.parent.stat()
    if path.parent.is_symlink() or parent.st_uid != 0 or parent.st_mode & 0o022:
        raise RuntimeError("Use an operator-controlled socket directory")
    if path.exists() or path.is_symlink():
        raise RuntimeError("Refuse to replace an existing broker socket")
    server = await asyncio.start_unix_server(Broker(executor).handle, path=str(path), limit=MAX_BODY + 1, backlog=8)
    os.chown(path, 10001, 10001)
    path.chmod(0o600)
    try:
        async with server:
            await server.serve_forever()
    finally:
        path.unlink(missing_ok=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Narrow local Bifang check executor; no public listener")
    parser.add_argument("--image", required=True)
    parser.add_argument("--runtime-binary", required=True)
    parser.add_argument("--runtime-sha256", required=True)
    parser.add_argument("--scratch", required=True)
    parser.add_argument("--socket", required=True)
    asyncio.run(serve(parser.parse_args()))
