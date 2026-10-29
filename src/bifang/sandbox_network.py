from __future__ import annotations

import errno
import platform
import struct
import tempfile
from contextlib import contextmanager

POLICY = "offline-v1"
ARCHITECTURES = {
    "x86_64": (0xC000003E, (41, 42, 46, 307, 308, 425), 44),
    "aarch64": (0xC00000B7, (198, 203, 211, 268, 269, 425), 206),
}
ALLOW = 0x7FFF0000
KILL = 0x80000000
DENY = 0x00050000 | errno.EPERM


class SandboxUnavailableError(RuntimeError):
    pass


def offline_program(machine: str | None = None) -> bytes:
    machine = machine or platform.machine().lower()
    if platform.system() != "Linux" or machine not in ARCHITECTURES:
        raise SandboxUnavailableError("Offline sandbox policy requires supported Linux x86_64 or aarch64; no fallback")
    architecture, denied_calls, sendto = ARCHITECTURES[machine]
    instructions = [(0x20, 0, 0, 4), (0x15, 1, 0, architecture), (0x06, 0, 0, KILL),
                    (0x20, 0, 0, 0), (0x35, 0, 1, 0x40000000), (0x06, 0, 0, DENY)]
    for number in denied_calls:
        instructions.extend([(0x15, 0, 1, number), (0x06, 0, 0, DENY)])
    instructions.extend([(0x15, 0, 5, sendto), (0x20, 0, 0, 48), (0x15, 0, 2, 0),
                         (0x20, 0, 0, 52), (0x15, 1, 0, 0), (0x06, 0, 0, DENY),
                         (0x06, 0, 0, ALLOW)])
    return b"".join(struct.pack("=HBBI", *instruction) for instruction in instructions)


@contextmanager
def offline_filter(enabled: bool = True):
    if not enabled:
        yield None
        return
    program = offline_program()
    with tempfile.TemporaryFile() as stream:
        stream.write(program)
        stream.seek(0)
        yield stream.fileno()


def attach_filter(arguments: list[str], descriptor: int) -> list[str]:
    return [arguments[0], "--seccomp", str(descriptor), "--cap-drop", "ALL", *arguments[1:]]
