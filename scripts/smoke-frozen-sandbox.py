import argparse
import hashlib
import json
import os
import signal
import socket
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import httpx

from bifang.coding_eval import save_report

COMMAND = "printf BIFANG_SANDBOX_PROBE > sandbox-sentinel.txt"


def free_port():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def exercise(executable, use_sandbox, expected_missing_status):
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def respond(self, value):
            body = json.dumps(value).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            self.respond({"data": [{"id": "fixture-model"}]})

        def do_POST(self):
            calls.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            message = ({"role": "assistant", "content": None, "tool_calls": [{"id": "command-1",
                "type": "function", "function": {"name": "run_command", "arguments": json.dumps({"command": COMMAND})}}]}
                if len(calls) == 1 else {"role": "assistant", "content": "Synthetic fixture complete"})
            self.respond({"model": "fixture-model", "choices": [{"message": message,
                "finish_reason": "tool_calls" if len(calls) == 1 else "stop"}]})

        def log_message(self, *args):
            return

    fixture = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = Thread(target=fixture.serve_forever, daemon=True)
    worker.start()
    process = None
    port = free_port()
    try:
        with tempfile.TemporaryDirectory(prefix="bifang-frozen-sandbox-") as temporary:
            root = Path(temporary)
            (root / "empty-path").mkdir()
            environment = {"PATH": str(root / "empty-path"), "LANG": "C.UTF-8",
                "HOME": str(root / "home"), "XDG_STATE_HOME": str(root / "state"),
                "BIFANG_ENV_FILE": str(root / "absent.env"), "BIFANG_SERVER_PORT": str(port),
                "BIFANG_SERVER_HOST": "127.0.0.1", "BIFANG_WORKSPACE_ROOT": str(root),
                "BIFANG_WORKTREE": "0", "BIFANG_BWRAP": "1" if use_sandbox else "0",
                "BIFANG_ENABLE_MEMORY": "0", "BIFANG_ENABLE_CONVERSATION_HISTORY": "0",
                "BIFANG_DEFAULT_PROVIDER": "nebius", "NEBIUS_API_KEY": "synthetic-fixture-key",
                "BIFANG_NEBIUS_BASE_URL": f"http://127.0.0.1:{fixture.server_port}/v1",
                "BIFANG_NEBIUS_MODEL": "fixture-model", "BIFANG_MAX_STEPS": "3"}
            base_url = f"http://127.0.0.1:{port}"
            with (root / "server.log").open("w") as log:
                process = subprocess.Popen([str(executable)], cwd=root, env=environment,
                    stdout=log, stderr=log, start_new_session=True)
                with httpx.Client(base_url=base_url, timeout=10, trust_env=False) as client:
                    deadline = time.monotonic() + 60
                    while True:
                        if process.poll() is not None:
                            raise RuntimeError("Frozen server exited during startup")
                        try:
                            if client.get("/health").status_code == 200:
                                break
                        except httpx.TransportError:
                            pass
                        if time.monotonic() >= deadline:
                            raise RuntimeError("Frozen server startup timeout")
                        time.sleep(0.2)
                    created = client.post("/sessions", json={"workspace": ".", "max_steps": 3})
                    created.raise_for_status()
                    session = created.json()["session_id"]

                    def request_chat():
                        with httpx.Client(base_url=base_url, timeout=20, trust_env=False) as chat:
                            return chat.post(f"/sessions/{session}/chat", json={"prompt": "Run the synthetic sentinel command"})

                    with ThreadPoolExecutor(max_workers=1) as executor:
                        future = executor.submit(request_chat)
                        deadline = time.monotonic() + 15
                        while True:
                            pending = client.get(f"/sessions/{session}/approval").json()
                            if pending.get("approval_id"):
                                if pending.get("action") != "Run command?\n" + COMMAND:
                                    raise RuntimeError("Unexpected action; no approval granted")
                                resolved = client.post(f"/sessions/{session}/approval", json={
                                    "approval_id": pending["approval_id"], "approved": True})
                                resolved.raise_for_status()
                                break
                            if future.done() or time.monotonic() >= deadline:
                                raise RuntimeError("Expected exact-action approval was not observed")
                            time.sleep(0.05)
                        response = future.result(timeout=20)
                    sentinel = root / "sandbox-sentinel.txt"
                    contents_match = sentinel.exists() and sentinel.read_text() == "BIFANG_SANDBOX_PROBE"
                    actionable = (response.status_code == 503 and
                                  "refusing unsandboxed execution" in response.json().get("detail", ""))
                    passed = (response.status_code == expected_missing_status and not sentinel.exists() and len(calls) == 1
                              and (actionable or expected_missing_status == 500)
                              if use_sandbox else response.status_code == 200 and contents_match and len(calls) == 2)
                    row = {"sandbox_requested": use_sandbox, "sandbox_executable_on_path": False,
                        "chat_status": response.status_code, "synthetic_model_requests": len(calls),
                        "sentinel_created": sentinel.exists(), "exact_action_approved": True,
                        "actionable_missing_sandbox_detail": actionable, "passed": passed}
    finally:
        if process and process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=5)
        fixture.shutdown()
        fixture.server_close()
        worker.join(timeout=5)
    with socket.socket() as probe:
        if probe.connect_ex(("127.0.0.1", port)) != 111:
            raise RuntimeError("Frozen test port was not closed")
    row["server_port_closed"] = True
    return row


def main():
    parser = argparse.ArgumentParser(description="Exercise missing sandbox and explicit opt-out through a frozen server API")
    parser.add_argument("--server-executable", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-missing-status", type=int, choices=(500, 503), default=503)
    options = parser.parse_args()
    if options.output.exists():
        raise ValueError("Choose a fresh report path")
    executable = options.server_executable.resolve(strict=True)
    rows = [exercise(executable, enabled, options.expected_missing_status) for enabled in (True, False)]
    report = {"passed": all(row["passed"] for row in rows), "cases": rows,
        "server_sha256": hashlib.sha256(executable.read_bytes()).hexdigest(), "hosted_model_requests": 0,
        "scope": "Known harmless sentinel command, synthetic local HTTP model. Missing executable only, not hostile-code sandbox isolation. Legacy HTTP 500 requires explicit selection; current HTTP 503 must include recovery detail."}
    save_report(options.output, report)
    print(json.dumps(report))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
