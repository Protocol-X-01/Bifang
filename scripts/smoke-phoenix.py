import argparse
import asyncio
import hashlib
import json
import os
import secrets
import signal
import socket
import subprocess
import tempfile
import time
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.metadata import version
from pathlib import Path
from threading import Thread
from unittest.mock import patch

import httpx
from dotenv import dotenv_values

from bifang.agent import Agent
from bifang.config import Config
from bifang.providers.types import ProviderConfig
from bifang.workspace import Workspace


def free_port():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


async def exercise(endpoint, root, live_key=None):
    marker = "BIFANG-SYNTHETIC-PRIVATE-RECEIPT-7329"
    (root / "fixture.txt").write_text(marker)
    providers = ({"nebius": ProviderConfig(
        name="nebius", api_key=live_key, base_url="https://api.tokenfactory.nebius.com/v1",
        default_model="nvidia/Nemotron-3-Ultra-550b-a55b")} if live_key else {})
    agent = Agent(Config(providers=providers, mode="observe", max_steps=3, enable_memory=False,
                         enable_conversation_history=False, enable_tracing=True,
                         tracing_endpoint=endpoint), Workspace(root, root))
    calls = 0

    async def no_services():
        return

    async def completion(messages, **kwargs):
        nonlocal calls
        calls += 1
        if calls > 3:
            raise RuntimeError("Exceeded smoke-test request limit")
        if live_key:
            kwargs["tools"] = [tool for tool in kwargs["tools"]
                               if tool["function"]["name"] == "read_file"]
            return await agent.provider.provider_manager.complete(
                messages, provider="nebius", model="nvidia/Nemotron-3-Ultra-550b-a55b",
                max_tokens=256, **kwargs)
        if calls == 1:
            return {"role": "assistant", "content": None, "tool_calls": [{
                "id": "read-1", "type": "function", "function": {
                    "name": "read_file", "arguments": '{"path":"fixture.txt"}'}}]}
        return {"role": "assistant", "content": marker, "model": "synthetic-test-model",
                "provider": "synthetic", "usage": {"prompt_tokens": 10, "completion_tokens": 5}}

    tools_seen = []

    def allow_read_only(name, args):
        if name != "read_file" or args.get("path") != "fixture.txt":
            raise RuntimeError("Unexpected smoke-test tool action")
        tools_seen.append(name)

    agent.on_tool = allow_read_only
    agent._ensure_services_started = no_services
    agent.provider.complete = completion
    try:
        result = await agent.ask("Use read_file to inspect fixture.txt. Return ONLY its exact "
                                 "contents without explanation or formatting.")
        if result.strip() != marker or tools_seen != ["read_file"]:
            raise RuntimeError("Model/tool cycle did not meet exact smoke-test expectations")
        with agent.tracer.span("agent.request", attributes={"openinference.span.kind": "AGENT"}):
            try:
                with agent.tracer.span("llm.complete", attributes={"openinference.span.kind": "LLM"}):
                    raise ValueError("SYNTHETIC-PRIVATE-EXCEPTION")
            except ValueError:
                pass
        agent.tracer.shutdown()
    finally:
        await agent.close()
    return calls, marker


def exercise_frozen(executable, endpoint, root, collector_key):
    marker = "BIFANG-SYNTHETIC-PRIVATE-RECEIPT-7329"
    (root / "fixture.txt").write_text(marker)
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def send_json(self, status, value):
            body = json.dumps(value).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path != "/v1/models":
                self.send_error(404)
                return
            self.send_json(200, {"data": [{"id": "fixture-model"}]})

        def do_POST(self):
            if self.path != "/v1/chat/completions":
                self.send_error(404)
                return
            request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            calls.append(request)
            if len(calls) == 1:
                message = {"role": "assistant", "content": None, "tool_calls": [{
                    "id": "fixture-read", "type": "function", "function": {
                        "name": "read_file", "arguments": '{"path":"fixture.txt"}'}}]}
            elif len(calls) == 2 and request["messages"][-1]["role"] == "tool" and marker in request["messages"][-1]["content"]:
                message = {"role": "assistant", "content": marker}
            else:
                self.send_json(500, {"error": {"message": "SYNTHETIC-PRIVATE-EXCEPTION"}})
                return
            self.send_json(200, {"model": "fixture-reported-model", "choices": [{"message": message,
                "finish_reason": "tool_calls" if len(calls) == 1 else "stop"}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}})

        def log_message(self, *args):
            return

    fixture = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = Thread(target=fixture.serve_forever, daemon=True)
    worker.start()
    port = free_port()
    environment = {name: value for name, value in os.environ.items()
                   if name in {"PATH", "LANG", "LC_ALL"}}
    environment.update(HOME=str(root / "home"), XDG_STATE_HOME=str(root / "state"),
        BIFANG_ENV_FILE=str(root / "absent.env"), BIFANG_SERVER_HOST="127.0.0.1",
        BIFANG_SERVER_PORT=str(port), BIFANG_WORKSPACE_ROOT=str(root),
        BIFANG_DEFAULT_PROVIDER="nebius", NEBIUS_API_KEY="synthetic-fixture-key",
        BIFANG_NEBIUS_BASE_URL=f"http://127.0.0.1:{fixture.server_port}/v1",
        BIFANG_NEBIUS_MODEL="fixture-model", BIFANG_WORKTREE="0", BIFANG_BWRAP="0",
        BIFANG_ENABLE_MEMORY="0", BIFANG_ENABLE_CONVERSATION_HISTORY="0",
        BIFANG_ENABLE_TRACING="1", BIFANG_TRACING_ENDPOINT=endpoint,
        PHOENIX_API_KEY=collector_key, PHOENIX_PROJECT_NAME="bifang-smoke", BIFANG_MAX_STEPS="3")
    process = None
    try:
        with (root / "frozen-server.log").open("w") as log:
            process = subprocess.Popen([str(executable)], cwd=root, env=environment,
                                       stdout=log, stderr=log, start_new_session=True)
            with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=60, trust_env=False) as client:
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
                        raise RuntimeError("Frozen server did not become ready")
                    time.sleep(0.2)
                created = client.post("/sessions", json={"workspace": ".", "max_steps": 3})
                created.raise_for_status()
                session = created.json()["session_id"]
                result = client.post(f"/sessions/{session}/chat", json={"prompt": "Use read_file to inspect fixture.txt"})
                result.raise_for_status()
                if result.json()["response"] != marker or len(calls) != 2:
                    raise RuntimeError("Frozen model/file/model cycle failed")
                error = client.post(f"/sessions/{session}/chat", json={"prompt": "Synthetic failure"})
                if error.status_code != 500 or len(calls) != 3:
                    raise RuntimeError("Expected frozen provider failure was not observed")
                with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=60, trust_env=False) as cleanup:
                    deleted = cleanup.delete(f"/sessions/{session}")
                    deleted.raise_for_status()
    finally:
        if process and process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=5)
        fixture.shutdown()
        fixture.server_close()
        worker.join(timeout=5)
    with socket.socket() as probe:
        if probe.connect_ex(("127.0.0.1", port)) == 0:
            raise RuntimeError("Frozen server port remained open after cleanup")
    return len(calls), marker


def main():
    parser = argparse.ArgumentParser(description="Real, authenticated Phoenix collector smoke test")
    parser.add_argument("--phoenix-executable", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--live-env-file", type=Path)
    parser.add_argument("--server-executable", type=Path)
    options = parser.parse_args()
    if options.live_env_file and options.server_executable:
        raise ValueError("Frozen rehearsal uses synthetic responses only; do not combine with live credentials")
    if options.output.exists():
        raise RuntimeError("Output exists; choose a fresh report path")
    executable = options.phoenix_executable.resolve(strict=True)
    live_key = None
    if options.live_env_file:
        live_key = dotenv_values(options.live_env_file).get("NEBIUS_API_KEY")
        if not live_key:
            raise RuntimeError("The selected private file has no Token Factory key")
    admin_key, server_key = "a1" + secrets.token_urlsafe(36), "a1" + secrets.token_urlsafe(36)
    port, grpc_port = free_port(), free_port()
    while port == grpc_port:
        grpc_port = free_port()
    base_url = f"http://127.0.0.1:{port}"
    with tempfile.TemporaryDirectory(prefix="bifang-phoenix-") as temporary:
        root = Path(temporary)
        home, project = root / "home", root / "project"
        home.mkdir(mode=0o700)
        project.mkdir(mode=0o700)
        environment = {name: value for name, value in os.environ.items()
                       if name in {"PATH", "LANG", "LC_ALL"}}
        environment.update(HOME=str(home), PHOENIX_HOST="127.0.0.1", PHOENIX_PORT=str(port),
                           PHOENIX_GRPC_PORT=str(grpc_port), PHOENIX_TELEMETRY_ENABLED="false",
                           PHOENIX_WORKING_DIR=str(home / "phoenix"), PHOENIX_ENABLE_AUTH="true",
                           PHOENIX_SECRET=server_key, PHOENIX_ADMIN_SECRET=admin_key,
                           PHOENIX_DEFAULT_ADMIN_INITIAL_PASSWORD="a1" + secrets.token_urlsafe(36))
        collector_version = subprocess.run(
            [str(executable.parent / "python"), "-c",
             "from importlib.metadata import version; print(version('arize-phoenix'))"],
            env=environment, capture_output=True, text=True, check=True).stdout.strip()
        log_path = root / "service.log"
        with log_path.open("w") as log:
            process = subprocess.Popen([str(executable), "serve"], env=environment,
                                       stdout=log, stderr=log, start_new_session=True)
            try:
                with httpx.Client(base_url=base_url, timeout=10, trust_env=False,
                                  headers={"Authorization": f"Bearer {admin_key}"}) as client:
                    deadline = time.monotonic() + 120
                    while True:
                        if process.poll() is not None:
                            raise RuntimeError("Phoenix exited during startup; inspect local setup")
                        try:
                            ready = client.get("/v1/projects")
                            if ready.status_code == 200:
                                break
                        except httpx.TransportError:
                            pass
                        if time.monotonic() >= deadline:
                            raise RuntimeError("Phoenix did not become ready within 120 seconds")
                        time.sleep(0.5)
                    unauthenticated = httpx.get(base_url + "/v1/projects", trust_env=False).status_code
                    wrong_key = client.get("/v1/projects", headers={"Authorization": "Bearer invalid"}).status_code
                    if unauthenticated not in (401, 403) or wrong_key not in (401, 403):
                        raise RuntimeError("Phoenix API authentication was not enforced")
                    grpc_check = subprocess.run([
                        str(executable.parent / "python"), "-c",
                        ("import grpc, sys\n"
                        "from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest\n"
                        "from opentelemetry.proto.collector.trace.v1.trace_service_pb2_grpc import TraceServiceStub\n"
                        "with grpc.insecure_channel('127.0.0.1:' + sys.argv[1]) as channel:\n"
                        "    try:\n"
                        "        TraceServiceStub(channel).Export(ExportTraceServiceRequest(), timeout=5)\n"
                        "    except grpc.RpcError as error:\n"
                        "        print(error.code().name)\n"
                        "    else:\n"
                        "        print('UNEXPECTED-SUCCESS')\n"), str(grpc_port),
                    ], capture_output=True, text=True, check=True, env=environment)
                    grpc_status = grpc_check.stdout.strip()
                    if grpc_status != "UNAUTHENTICATED":
                        raise RuntimeError("Phoenix gRPC authentication was not enforced")
                    ui = client.get("/")
                    if ui.status_code != 200 or "text/html" not in ui.headers.get("content-type", ""):
                        raise RuntimeError("Phoenix UI document is unavailable")
                    if options.server_executable:
                        calls, marker = exercise_frozen(options.server_executable.resolve(strict=True),
                                                       base_url + "/v1/traces", project, admin_key)
                    else:
                        with patch.dict(os.environ, {"PHOENIX_API_KEY": admin_key,
                                                     "PHOENIX_PROJECT_NAME": "bifang-smoke"}):
                            calls, marker = asyncio.run(exercise(base_url + "/v1/traces", project, live_key))
                    deadline = time.monotonic() + 30
                    while True:
                        response = client.get("/v1/projects/bifang-smoke/spans", params={"limit": 100})
                        spans = response.json().get("data", []) if response.status_code == 200 else []
                        roots = [span for span in spans if span["name"] == "agent.request"]
                        if len(roots) == 2 and len(spans) >= 6:
                            break
                        if time.monotonic() >= deadline:
                            raise RuntimeError("Complete trace tree not retrievable from actual Phoenix")
                        time.sleep(0.5)
                    serialized = json.dumps(spans)
                    for forbidden in (marker, "SYNTHETIC-PRIVATE-EXCEPTION", admin_key,
                                      "Use read_file to inspect", "fixture.txt", "synthetic-fixture-key"):
                        if forbidden in serialized:
                            raise RuntimeError("Private smoke-test content appeared in collected spans")
                    if live_key and live_key in serialized:
                        raise RuntimeError("Credential appeared in collected spans")
                    identities = {span["context"]["span_id"]: span for span in spans}
                    for span in spans:
                        if span["parent_id"]:
                            parent = identities[span["parent_id"]]
                            if span["context"]["trace_id"] != parent["context"]["trace_id"]:
                                raise RuntimeError("Phoenix trace parent/child identity mismatch")
                    if not any(span["status_code"] == "ERROR" for span in spans):
                        raise RuntimeError("Expected sanitized synthetic error span was not stored")
                    report = {"status": "passed", "collector": "real Phoenix service",
                              "phoenix_version": collector_version,
                              "otel_sdk_version": version("opentelemetry-sdk"),
                              "model_mode": "live Token Factory Ultra" if live_key else "synthetic responses",
                              "model_requests": calls, "spans_retrieved": len(spans),
                              "span_names": dict(Counter(span["name"] for span in spans)),
                              "span_kinds": dict(Counter(span["span_kind"] for span in spans)),
                              "parent_relationships_verified": True,
                              "synthetic_content_and_supplied_credentials_absent": True,
                              "missing_key_status": unauthenticated, "wrong_key_status": wrong_key,
                              "grpc_missing_key_status": grpc_status,
                              "ui_document_status": ui.status_code,
                              "rendered_ui_verified": False,
                              "grpc_listener": "Phoenix wildcard default; authentication enabled",
                              "automated_evaluations_verified": False}
                    if options.server_executable:
                        report.update(runtime="frozen server",
                            server_sha256=hashlib.sha256(options.server_executable.read_bytes()).hexdigest(),
                            model_mode="local synthetic HTTP provider", hosted_model_requests=0,
                            frozen_server_port_closed=True)
            finally:
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGTERM)
                    try:
                        process.wait(timeout=20)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGKILL)
                        process.wait(timeout=5)
        with open(options.output, "x", opener=lambda name, flags: os.open(name, flags, 0o600)) as result:
            json.dump(report, result, indent=2, allow_nan=False)
            result.write("\n")
    print("Phoenix collector smoke passed; sanitized report written, temporary service stopped.")


if __name__ == "__main__":
    main()
