from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from pathlib import Path
from typing import BinaryIO

from .package_setup import run_setup
from .workbench import reject_constant, unique_object

MAX_REQUEST = 8192


def parse_request(raw: bytes) -> dict:
    if not raw.endswith(b"\n") or len(raw) > MAX_REQUEST:
        raise ValueError("Expected a bounded setup request")
    request = json.loads(raw, object_pairs_hook=unique_object, parse_constant=reject_constant)
    fields = {"version", "workspace", "sha256", "network", "registry", "confirmed"}
    if isinstance(request, dict) and request.get("version") == 2:
        fields |= {"profile", "allow_builds"}
    if not isinstance(request, dict) or set(request) != fields:
        raise ValueError("Invalid setup fields")
    if (type(request["version"]) is not int or request["version"] not in {1, 2} or request["confirmed"] is not True
            or type(request["network"]) is not bool or not isinstance(request["workspace"], str)
            or not Path(request["workspace"]).is_absolute() or not isinstance(request["sha256"], str)
            or not re.fullmatch(r"[a-f0-9]{64}", request["sha256"]) or not isinstance(request["registry"], str)):
        raise ValueError("Review and approve an exact setup plan")
    if request["version"] == 2 and (not isinstance(request["profile"], str) or request["profile"] not in {"javascript-npm", "python-uv", "rust-cargo"} or type(request["allow_builds"]) is not bool):
        raise ValueError("Choose a supported profile and explicit build permission")
    return request


async def serve(source: BinaryIO, destination: BinaryIO) -> int:
    reader = asyncio.StreamReader(limit=MAX_REQUEST)
    loop = asyncio.get_running_loop()
    transport, _ = await loop.connect_read_pipe(lambda: asyncio.StreamReaderProtocol(reader), source)

    def emit(event: dict):
        destination.write(json.dumps(event, ensure_ascii=True).encode() + b"\n")
        destination.flush()

    work = None
    control = None
    try:
        request = parse_request(await reader.readline())
        work = asyncio.create_task(run_setup(Path(request["workspace"]), request["sha256"],
                                            network=request["network"], registry=request["registry"], confirmed=True,
                                            profile=request.get("profile", "javascript-npm"), allow_builds=request.get("allow_builds", False),
                                            on_output=lambda stream, text: emit({"event": "output", "stream": stream, "text": text})))

        async def cancellation():
            try:
                raw = await reader.readline()
                if raw and (len(raw) > MAX_REQUEST or json.loads(raw, object_pairs_hook=unique_object) != {"cancel": True}):
                    raise ValueError("Invalid setup cancellation")
            finally:
                work.cancel()

        control = asyncio.create_task(cancellation())
        receipt = await work
        emit({"event": "result", "receipt": receipt})
        return 0
    except (OSError, ValueError, TypeError, RuntimeError, RecursionError, asyncio.CancelledError):
        emit({"event": "error", "message": "Setup could not be verified. Review current manifests, options and sandbox availability before retrying."})
        return 1
    finally:
        if work is not None and not work.done():
            work.cancel()
            await asyncio.gather(work, return_exceptions=True)
        if control is not None:
            control.cancel()
            await asyncio.gather(control, return_exceptions=True)
        transport.close()


def main():
    os.environ["BIFANG_NO_DOTENV"] = "1"
    raise SystemExit(asyncio.run(serve(sys.stdin.buffer, sys.stdout.buffer)))


if __name__ == "__main__":
    main()
