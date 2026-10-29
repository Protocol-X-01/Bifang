import asyncio
import json
import os
import shlex
import socket
import struct
import subprocess

import pytest

from bifang.policy import Policy
from bifang.sandbox_diagnostics import inspect_sandbox
from bifang.sandbox_network import (
    ALLOW,
    ARCHITECTURES,
    DENY,
    KILL,
    SandboxUnavailableError,
    offline_program,
)
from bifang.tools.commands import bwrap_argv, run_command


def evaluate(program, architecture, syscall, destination=0):
    instructions = list(struct.iter_unpack("=HBBI", program))
    data = {0: syscall, 4: architecture, 48: destination & 0xFFFFFFFF, 52: destination >> 32}
    cursor, accumulator = 0, 0
    for _ in range(len(instructions) + 1):
        opcode, when_true, when_false, value = instructions[cursor]
        cursor += 1
        if opcode == 0x20:
            accumulator = data[value]
        elif opcode == 0x15:
            cursor += when_true if accumulator == value else when_false
        elif opcode == 0x35:
            cursor += when_true if accumulator >= value else when_false
        elif opcode == 0x06:
            return value
        else:
            raise AssertionError("Unexpected BPF opcode")
    raise AssertionError("Filter did not terminate")


@pytest.mark.parametrize("machine", ["x86_64", "aarch64"])
def test_native_and_compatibility_abi_filter_branches(machine):
    program = offline_program(machine)
    architecture, blocked, sendto = ARCHITECTURES[machine]
    for syscall in blocked:
        assert evaluate(program, architecture, syscall) == DENY
    assert evaluate(program, architecture, 0x40000000 | 41) == DENY
    assert evaluate(program, 0x40000003, 102) == KILL
    assert evaluate(program, architecture, sendto, 1) == DENY
    assert evaluate(program, architecture, sendto, 1 << 32) == DENY
    assert evaluate(program, architecture, sendto, 0) == ALLOW
    assert evaluate(program, architecture, 0) == ALLOW
    assert evaluate(program, architecture, 53 if machine == "x86_64" else 199) == ALLOW


def test_unsupported_architecture_does_not_get_weaker_policy():
    with pytest.raises(SandboxUnavailableError, match="no fallback"):
        offline_program("unsupported-fixture")


def test_command_layout_never_shares_host_network(tmp_path):
    arguments = bwrap_argv(tmp_path, "true")
    assert "--unshare-all" in arguments and "--share-net" not in arguments
    assert "--clearenv" in arguments and "--new-session" in arguments
    assert "/run" not in arguments and "/var/run" not in arguments


@pytest.mark.skipif(os.getenv("BIFANG_TEST_REAL_BWRAP") != "1", reason="Explicit real Bubblewrap execution opt-in")
def test_actual_host_diagnostics_no_changes_and_no_external_packets(tmp_path):
    result = asyncio.run(inspect_sandbox())
    assert result["ready"], result
    assert result["observed"]["namespace_isolated"]
    assert all(result["observed"]["blocked"].values())
    assert result["observed"]["internal_pair"]


@pytest.mark.skipif(os.getenv("BIFANG_TEST_REAL_BWRAP") != "1", reason="Explicit real Bubblewrap execution opt-in")
def test_actual_workspace_unix_proxy_cannot_bypass_network_policy(tmp_path):
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    path = tmp_path / "fixture-proxy.sock"
    listener.bind(str(path))
    listener.settimeout(0.2)
    control = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    control.sendto(b"host control", str(path))
    assert listener.recv(64) == b"host control"
    control.close()
    baseline_code = 'import socket; connection=socket.socket(socket.AF_UNIX,socket.SOCK_DGRAM); connection.sendto(b"namespace control", "/workspace/fixture-proxy.sock")'
    baseline = subprocess.run(bwrap_argv(tmp_path, shlex.join(["/usr/bin/python3", "-I", "-c", baseline_code])),
                              env={"PATH": "/usr/bin:/bin"}, stdin=subprocess.DEVNULL,
                              capture_output=True, timeout=5, check=False)
    assert baseline.returncode == 0, baseline.stderr.decode(errors="replace")
    assert listener.recv(64) == b"namespace control"
    _, calls, _ = ARCHITECTURES[os.uname().machine]
    code = f'''import asyncio,ctypes,errno,json,socket,subprocess
blocked=[]
for family,kind in [(socket.AF_INET,socket.SOCK_STREAM),(socket.AF_INET,socket.SOCK_DGRAM),
                    (socket.AF_INET6,socket.SOCK_STREAM),(socket.AF_INET6,socket.SOCK_DGRAM),
                    (socket.AF_UNIX,socket.SOCK_DGRAM)]:
    try:
        connection=socket.socket(family,kind)
    except OSError as error:
        assert error.errno==errno.EPERM
        blocked.append(True)
    else:
        connection.close()
        raise AssertionError("Socket creation allowed")
first,second=socket.socketpair(socket.AF_UNIX,socket.SOCK_DGRAM)
for operation in [lambda:first.sendto(b"bypass", "/workspace/fixture-proxy.sock"),
                  lambda:first.connect("/workspace/fixture-proxy.sock"),
                  lambda:first.sendmsg([b"bypass"], [], 0, "/workspace/fixture-proxy.sock")]:
    try:
        operation()
    except OSError as error:
        assert error.errno==errno.EPERM
    else:
        raise AssertionError("Explicit destination allowed")
first.send(b"internal")
assert second.recv(64)==b"internal"
first.close()
second.close()
libc=ctypes.CDLL(None,use_errno=True)
for number in {list(calls)!r}:
    assert libc.syscall(number,0,0,0,0,0,0)==-1
    assert ctypes.get_errno()==errno.EPERM
asyncio.run(asyncio.sleep(0))
child=subprocess.run(["/usr/bin/python3","-I","-c","import socket; socket.socket()"],capture_output=True)
assert child.returncode!=0 and b"PermissionError" in child.stderr
print(json.dumps({{"blocked_families":len(blocked),"descendant_blocked":True,"internal_ipc":True}}))
'''
    try:
        result = asyncio.run(run_command(Policy(tmp_path, "trusted"), shlex.join(["/usr/bin/python3", "-I", "-c", code])))
        assert result["returncode"] == 0, result
        assert json.loads(result["stdout"]) == {"blocked_families": 5, "descendant_blocked": True, "internal_ipc": True}
        with pytest.raises(TimeoutError):
            listener.recv(64)
    finally:
        listener.close()
        path.unlink(missing_ok=True)


def test_diagnostics_fail_closed_when_host_cannot_create_sandbox(monkeypatch):
    async def unavailable(*args, **kwargs):
        raise SandboxUnavailableError("Synthetic unsupported host")

    monkeypatch.setattr("bifang.sandbox_diagnostics.run_command", unavailable)
    result = asyncio.run(inspect_sandbox())
    assert not result["ready"] and "No fallback" in result["error"]
