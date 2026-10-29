from __future__ import annotations

import json
import platform
import shlex
import shutil
import tempfile
from pathlib import Path

from .policy import Policy
from .sandbox_network import POLICY, SandboxUnavailableError
from .tools.commands import run_command

PROBE = '''import errno,json,os,socket
blocked = {}
for label,family,kind in [
    ("ipv4_tcp",socket.AF_INET,socket.SOCK_STREAM),
    ("ipv4_udp",socket.AF_INET,socket.SOCK_DGRAM),
    ("ipv6_tcp",socket.AF_INET6,socket.SOCK_STREAM),
    ("ipv6_udp",socket.AF_INET6,socket.SOCK_DGRAM),
    ("unix_proxy",socket.AF_UNIX,socket.SOCK_STREAM)]:
    try:
        connection=socket.socket(family,kind)
    except OSError as error:
        blocked[label]=error.errno == errno.EPERM
    else:
        blocked[label]=False
        connection.close()
first,second=socket.socketpair()
first.sendall(b"internal fixture")
internal_pair=second.recv(64)==b"internal fixture"
first.close()
second.close()
status=dict(line.split(":",1) for line in open("/proc/self/status") if ":" in line)
print(json.dumps({"net_namespace":os.readlink("/proc/self/ns/net"),"blocked":blocked,
    "seccomp":status.get("Seccomp", "").strip(),
    "no_new_privileges":status.get("NoNewPrivs", "").strip(),"internal_pair":internal_pair}))
'''


def host_settings() -> dict:
    settings = {}
    for key, name in (("user_namespaces", "/proc/sys/kernel/unprivileged_userns_clone"),
                      ("apparmor_userns_restriction", "/proc/sys/kernel/apparmor_restrict_unprivileged_userns")):
        try:
            value = Path(name).read_text().strip()
            settings[key] = value if value in {"0", "1"} else "unknown"
        except OSError:
            settings[key] = "unavailable"
    return {"system": platform.system(), "architecture": platform.machine(),
            "bubblewrap_available": shutil.which("bwrap") is not None, **settings}


async def inspect_sandbox() -> dict:
    report = {"policy": POLICY, "host": host_settings(), "ready": False,
              "scope": "Actual local command sandbox only; no host policy changes or cloud deployment proof"}
    try:
        parent_namespace = str(Path("/proc/self/ns/net").readlink())
        with tempfile.TemporaryDirectory(prefix="bifang-network-probe-") as directory:
            command = shlex.join(["/usr/bin/python3", "-I", "-c", PROBE])
            result = await run_command(Policy(Path(directory), "trusted"), command, timeout=10)
        if result["returncode"] != 0:
            report["error"] = "Sandbox probe could not complete. Review the scoped Ubuntu/kernel setup; no fallback was attempted."
            return report
        observed = json.loads(result["stdout"])
        isolated = observed["net_namespace"] != parent_namespace
        report["observed"] = {**observed, "namespace_isolated": isolated}
        report["ready"] = (isolated and observed["seccomp"] == "2" and observed["no_new_privileges"] == "1"
                           and observed["internal_pair"] and all(observed["blocked"].values()))
        return report
    except (OSError, ValueError, KeyError, SandboxUnavailableError):
        report["error"] = "Sandbox capabilities unavailable; review supported Linux architecture and scoped host setup. No fallback was attempted."
        return report
