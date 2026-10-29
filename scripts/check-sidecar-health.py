from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import signal
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("binary", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    arguments = parser.parse_args()
    binary = arguments.binary.resolve(strict=True)
    with binary.open("rb") as source:
        digest = hashlib.file_digest(source, "sha256").hexdigest()
    with tempfile.TemporaryDirectory(prefix="bifang-baseline-health-") as temporary:
        root = Path(temporary)
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        environment = {"HOME": str(root), "PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "XDG_STATE_HOME": str(root / "state"),
                       "BIFANG_NO_DOTENV": "1", "BIFANG_SERVER_HOST": "127.0.0.1", "BIFANG_SERVER_PORT": str(port)}
        with (root / "server.log").open("w") as log:
            process = subprocess.Popen([str(binary)], cwd=root, env=environment, stdout=log, stderr=log, start_new_session=True)
            try:
                deadline = time.monotonic() + 45
                opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                while True:
                    if process.poll() is not None:
                        raise RuntimeError("Release sidecar exited before health readiness")
                    try:
                        with opener.open(f"http://127.0.0.1:{port}/health", timeout=2) as response:
                            assert response.status == 200
                            assert json.loads(response.read()) == {"status": "ok", "service": "bifang"}
                        break
                    except (OSError, urllib.error.URLError):
                        if time.monotonic() > deadline:
                            raise RuntimeError("Release API health deadline exceeded") from None
                        time.sleep(0.2)
            finally:
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=5)
        with socket.socket() as listener:
            closed = listener.connect_ex(("127.0.0.1", port)) != 0
        assert closed
    arguments.output.write_text(json.dumps({"scope": "Selected sidecar API on the current host, not GUI or clean installation",
        "host_system": platform.system(), "host_machine": platform.machine(),
        "binary_sha256": digest, "api_health": True, "owned_port_closed": closed,
        "performed_http_requests": ["GET /health"], "private_configuration_used": False}, indent=2) + "\n")
    print("PASS: selected sidecar API health and owned-process/port cleanup")


if __name__ == "__main__":
    main()
