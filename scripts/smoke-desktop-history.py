import argparse
import base64
import hashlib
import json
import os
import signal
import socket
import subprocess
import tempfile
import time
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Event, Thread
from unittest.mock import patch

import httpx

from bifang.config import Config
from bifang.context.kv_cache import create_conversation_cache
from bifang.routing import TOKEN_FACTORY_ROLES


@contextmanager
def model_fixture(enabled):
    if not enabled:
        yield None
        return
    calls = []
    release = Event()

    class Handler(BaseHTTPRequestHandler):
        def send_json(self, value):
            body = json.dumps(value).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path != "/v1/models":
                self.send_error(404)
                return
            self.send_json({"data": [{"id": model} for model in TOKEN_FACTORY_ROLES.values()]})

        def do_POST(self):
            if self.path != "/v1/chat/completions":
                self.send_error(404)
                return
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            calls.append(payload["model"])
            if len(calls) == 1:
                release.wait(timeout=15)
            self.send_json({"model": "fixture-reported:" + payload["model"],
                "choices": [{"message": {"role": "assistant", "content": "Native model selection fixture answer."},
                             "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}})

        def log_message(self, format, *args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield {"base_url": f"http://127.0.0.1:{server.server_port}/v1", "calls": calls, "release": release}
    finally:
        release.set()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def main():
    parser = argparse.ArgumentParser(description="Native desktop history test with no model calls")
    parser.add_argument("--application", type=Path, required=True)
    parser.add_argument("--native-driver", required=True)
    parser.add_argument("--tauri-driver", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model-fixture", action="store_true")
    parser.add_argument("--paint-fixture", action="store_true")
    options = parser.parse_args()
    if options.paint_fixture and not options.model_fixture:
        raise ValueError("The paint fixture requires synthetic model-fixture mode")
    if not os.environ.get("DISPLAY"):
        raise RuntimeError("Use a dedicated display such as xvfb-run")
    application = options.application.resolve(strict=True)
    output = options.output.resolve()
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    with socket.socket() as probe:
        if probe.connect_ex(("127.0.0.1", 8000)) == 0:
            raise RuntimeError("Port 8000 is occupied; do not interrupt an existing server")
    with tempfile.TemporaryDirectory(prefix="bifang-history-native-") as temporary, model_fixture(options.model_fixture) as fixture:
        root = Path(temporary)
        workspace = root / "project"
        workspace.mkdir()
        (workspace / "fixture.txt").write_text("Keep this source file unchanged.\n")
        subprocess.run(["git", "init", "-q", str(workspace)], check=True)
        subprocess.run(["git", "add", "."], cwd=workspace, check=True)
        subprocess.run(["git", "-c", "user.name=Bifang Test", "-c", "user.email=test@example.invalid",
                        "commit", "-qm", "Synthetic history fixture"], cwd=workspace, check=True)
        state = root / "state"
        first, second = "1" * 32, "2" * 32
        question = '<img src=x onerror="window.historyInjected=true"> Earlier synthetic question'
        answer = "Earlier verified answer; do not replay tools."
        with patch.dict(os.environ, {"XDG_STATE_HOME": str(state)}):
            cache = create_conversation_cache(Config(), workspace).cache
            for identity in (first, second):
                cache.create_session(identity)
                messages = [
                    {"role": "user", "content": question},
                    {"role": "assistant", "content": None, "tool_calls": [{
                        "id": "historical-command", "type": "function", "function": {
                            "name": "run_command", "arguments": '{"command":"touch never-replay"}'}}]},
                    {"role": "tool", "tool_call_id": "historical-command", "content": "Historical only"},
                    {"role": "assistant", "content": answer},
                ]
                cache.add_turn(identity, question, answer,
                               {"status": "completed", "messages": messages})
            cache.close()
        (root / "runtime").mkdir(mode=0o700)
        environment = {name: value for name, value in os.environ.items() if name in {
            "PATH", "LANG", "LC_ALL", "DISPLAY", "XAUTHORITY", "DBUS_SESSION_BUS_ADDRESS"}}
        environment.update(HOME=str(root), XDG_CONFIG_HOME=str(root / "config"),
                           XDG_STATE_HOME=str(state), XDG_DATA_HOME=str(root / "data"),
                           XDG_CACHE_HOME=str(root / "cache"), XDG_RUNTIME_DIR=str(root / "runtime"),
                           GDK_BACKEND="x11", GIO_USE_VFS="local", GTK_USE_PORTAL="0",
                           LIBGL_ALWAYS_SOFTWARE="1", BIFANG_ENABLE_MEMORY="0",
                           BIFANG_ENABLE_TRACING="0", BIFANG_BWRAP="0")
        if fixture:
            environment.update(NEBIUS_API_KEY="bifang-synthetic-local-fixture-key",
                               BIFANG_NEBIUS_BASE_URL=fixture["base_url"], BIFANG_ROUTING_MODE="pinned")
        with (output / "driver.log").open("w") as log:
            driver = subprocess.Popen([options.tauri_driver, "--native-driver", options.native_driver],
                                      env=environment, stdout=log, stderr=log, start_new_session=True)
            prefix = None
            with httpx.Client(base_url="http://127.0.0.1:4444", timeout=30, trust_env=False) as client:
                try:
                    for attempt in range(150):
                        if driver.poll() is not None:
                            raise RuntimeError("WebDriver exited during startup")
                        try:
                            if client.get("/status").status_code == 200:
                                break
                        except httpx.TransportError:
                            pass
                        time.sleep(0.2)
                    else:
                        raise RuntimeError("WebDriver startup timed out")
                    result = client.post("/session", json={"capabilities": {"alwaysMatch": {
                        "tauri:options": {"application": str(application)}}}})
                    result.raise_for_status()
                    prefix = "/session/" + result.json()["value"]["sessionId"]

                    def request(endpoint, payload=None, method="POST"):
                        response = client.request(method, prefix + endpoint, json=payload)
                        response.raise_for_status()
                        value = response.json().get("value")
                        if isinstance(value, dict) and value.get("error"):
                            raise RuntimeError("WebDriver operation failed")
                        return value

                    def execute(script, *args):
                        return request("/execute/sync", {"script": script, "args": list(args)})

                    def click(selector):
                        element = request("/element", {"using": "css selector", "value": selector})
                        request("/element/" + element["element-6066-11e4-a52e-4f735466cecf"] + "/click", {})

                    def click_text(label, dialog=False):
                        selector = ("//dialog[@open]" if dialog else "") + "//button[normalize-space(.)='" + label + "']"
                        element = request("/element", {"using": "xpath", "value": selector})
                        request("/element/" + element["element-6066-11e4-a52e-4f735466cecf"] + "/click", {})

                    def wait_health(running):
                        for attempt in range(100):
                            try:
                                healthy = httpx.get("http://127.0.0.1:8000/health", timeout=1,
                                                    trust_env=False).status_code == 200
                            except httpx.TransportError:
                                healthy = False
                            if healthy == running:
                                return
                            time.sleep(0.2)
                        raise RuntimeError("Server health did not match the requested lifecycle state")

                    def wait_for(condition, message):
                        for attempt in range(150):
                            if execute("return " + condition):
                                return
                            time.sleep(0.2)
                        raise RuntimeError(message)

                    def saved():
                        return execute("return JSON.parse(localStorage.getItem('bifang-session') || '{}').state")

                    def screenshot(name):
                        (output / name).write_bytes(base64.b64decode(request("/screenshot", method="GET")))

                    request("/window/rect", {"x": 0, "y": 0, "width": 1400, "height": 900})
                    wait_for("!!document.querySelector('textarea')", "Application did not render")
                    wait_health(True)
                    click_text("Open by path…")
                    wait_for("!!document.querySelector('input[name=workspace-path]')", "Path dialog did not open")
                    path = request("/element", {"using": "css selector", "value": "input[name=workspace-path]"})
                    request("/element/" + path["element-6066-11e4-a52e-4f735466cecf"] + "/value", {"text": str(workspace)})
                    click_text("Open workspace", dialog=True)
                    wait_for("!document.querySelector('dialog[open] input[name=workspace-path]')", "Workspace selection failed")
                    if fixture:
                        wait_for("!!document.querySelector('#model-selection option[value=auto]:not(:disabled)')", "Fixture catalog did not reach native picker")
                        expected = [TOKEN_FACTORY_ROLES["balanced"], TOKEN_FACTORY_ROLES["fast"], TOKEN_FACTORY_ROLES["reasoning"]]
                        for index, selection in enumerate(("auto", "model:" + TOKEN_FACTORY_ROLES["fast"], "configured")):
                            execute("const element = document.querySelector('#model-selection'); element.value=arguments[0]; element.dispatchEvent(new Event('change', {bubbles:true}));", selection)
                            field = request("/element", {"using": "css selector", "value": "textarea"})
                            request("/element/" + field["element-6066-11e4-a52e-4f735466cecf"] + "/value", {"text": f"hello {index}"})
                            click('textarea + button[type="submit"]')
                            if index == 0:
                                wait_for("document.querySelector('#model-selection').disabled", "Model picker was not disabled while busy")
                                fixture["release"].set()
                            wait_for(f"document.querySelectorAll('details').length === {index + 1}", "Model response/receipt did not reach native UI")
                            wait_for("!document.querySelector('#model-selection').disabled", "Model picker stayed disabled after response")
                        if fixture["calls"] != expected:
                            raise RuntimeError("Native selection did not reach the expected provider models")
                        actual = saved()
                        receipts = [message["routing"][0] for message in actual["messages"] if message["role"] == "assistant"]
                        if [receipt["requested_model"] for receipt in receipts] != expected or any(
                            receipt["reported_model"] != "fixture-reported:" + receipt["requested_model"] for receipt in receipts):
                            raise RuntimeError("Native receipts conflated requested and reported model identities")
                        execute("document.querySelectorAll('details').forEach(element => element.open=true)")
                        screenshot("model-selection-receipts.png")
                        execute("window.originalChatFetch=window.fetch; window.fetch=(input, options)=>String(input).endsWith('/chat') ? Promise.resolve(new Response(JSON.stringify({detail:'Bubblewrap unavailable; refusing unsandboxed execution. Install in a supported isolated environment.'}),{status:503,headers:{'Content-Type':'application/json'}})) : window.originalChatFetch(input, options)")
                        field = request("/element", {"using": "css selector", "value": "textarea"})
                        request("/element/" + field["element-6066-11e4-a52e-4f735466cecf"] + "/value", {"text": "Synthetic missing-sandbox UI fixture"})
                        click('textarea + button[type="submit"]')
                        wait_for("document.body.innerText.includes('Bubblewrap unavailable; refusing unsandboxed execution.')", "Structured sandbox recovery detail was not visible")
                        wait_for("!document.querySelector('#model-selection').disabled", "Sandbox error left UI busy")
                        if '{"detail"' in saved()["messages"][-1]["content"]:
                            raise RuntimeError("Sandbox recovery rendered a raw JSON wrapper")
                        screenshot("sandbox-recovery-message.png")
                        execute("window.fetch=window.originalChatFetch; delete window.originalChatFetch")
                        execute("window.originalModelFetch=window.fetch; window.fetch=(input, options)=>String(input).endsWith('/models') ? Promise.resolve(new Response('',{status:503})) : window.originalModelFetch(input, options)")
                        click_text("Refresh models")
                        wait_for("[...document.querySelectorAll('[role=status]')].some(element=>element.textContent.includes('Catalog unavailable'))", "Catalog failure was not visible")
                        if not execute("return document.querySelector('#model-selection option[value=auto]').disabled"):
                            raise RuntimeError("Failed catalog left automatic mode deceptively available")
                        screenshot("model-catalog-failure.png")
                        execute("window.fetch=window.originalModelFetch; delete window.originalModelFetch")
                        click_text("Refresh models")
                        wait_for("!!document.querySelector('#model-selection option[value=auto]:not(:disabled)')", "Catalog did not recover")
                    if options.paint_fixture:
                        with httpx.Client(base_url="http://127.0.0.1:8000", trust_env=False) as api:
                            active = next(row for row in api.get("/sessions").json()
                                          if row["session_id"] == saved()["sessionId"])
                        disposable = Path(active["workspace"]).resolve()
                        if not disposable.is_relative_to(root):
                            raise RuntimeError("Paint fixture workspace escaped the disposable test root")
                        original = (workspace / "fixture.txt").read_bytes()
                        changed = original + b"Synthetic paint-check edit.\n"
                        (disposable / "fixture.txt").write_bytes(changed)
                        wait_for("[...document.querySelectorAll('button')].some(button=>button.textContent.trim()==='Apply'&&!button.disabled)", "Synthetic patch did not reach the diff panel")
                        click_text("Apply")
                        wait_for("!!document.querySelector('dialog[open] #apply-title')", "Apply confirmation did not open")
                        screenshot("apply-confirmation-open.png")
                        click_text("Cancel", dialog=True)
                        wait_for("!document.querySelector('dialog[open]')", "Cancel did not close confirmation")
                        screenshot("apply-cancel-immediate.png")
                        request("/execute/async", {"script": "const done=arguments[arguments.length-1]; requestAnimationFrame(()=>requestAnimationFrame(()=>setTimeout(()=>done(true),100)));", "args": []})
                        screenshot("apply-cancel-settled.png")
                        if (workspace / "fixture.txt").read_bytes() != original:
                            raise RuntimeError("Cancel unexpectedly applied the patch")
                        click_text("Apply")
                        click_text("Apply to repository", dialog=True)
                        wait_for("document.body.innerText.includes('Changes applied to the original repository.')&&!document.querySelector('dialog[open]')", "Apply result did not close confirmation")
                        if (workspace / "fixture.txt").read_bytes() != changed:
                            raise RuntimeError("Synthetic apply did not reach the original fixture")
                        screenshot("apply-success-immediate.png")
                        request("/execute/async", {"script": "const done=arguments[arguments.length-1]; requestAnimationFrame(()=>requestAnimationFrame(()=>setTimeout(()=>done(true),100)));", "args": []})
                        screenshot("apply-success-settled.png")
                        (workspace / "fixture.txt").write_bytes(original)
                        (disposable / "fixture.txt").write_bytes(original)
                    click('button[aria-label="Saved conversations"]')
                    wait_for("!!document.querySelector('button[aria-label=\"Resume conversation 11111111\"]')", "Saved history missing")
                    screenshot("history-picker.png")
                    click('button[aria-label="Resume conversation 11111111"]')
                    wait_for("[...document.querySelectorAll('[role=status]')].some(e => e.textContent.includes('History restored'))", "History not restored")
                    before = saved()
                    if [message["content"] for message in before["messages"]] != [question, answer]:
                        raise RuntimeError("Restored messages differ from durable history")
                    if execute("return !!window.historyInjected"):
                        raise RuntimeError("Historical text was executed as markup")
                    screenshot("history-restored.png")
                    click('button[aria-label="Saved conversations"]')
                    wait_for("!!document.querySelector('button[aria-label=\"Resume conversation 22222222\"]')", "Second history missing")
                    execute("window.originalHistoryFetch = window.fetch; window.fetch = (input, options) => String(input).endsWith('/history') ? Promise.resolve(new Response('', {status:503})) : window.originalHistoryFetch(input, options)")
                    click('button[aria-label="Resume conversation 22222222"]')
                    wait_for("[...document.querySelectorAll('[role=alert]')].some(e => e.textContent.includes('503'))", "Restore failure was not visible")
                    if saved() != before:
                        raise RuntimeError("Failed restore changed the active conversation")
                    execute("window.fetch = window.originalHistoryFetch; delete window.originalHistoryFetch")
                    with httpx.Client(base_url="http://127.0.0.1:8000", trust_env=False) as api:
                        active = api.get("/sessions").json()
                        if len(active) != 1 or active[0]["session_id"] != before["sessionId"]:
                            raise RuntimeError("Failed resume leaked a candidate session")
                    screenshot("history-failure-preserved.png")
                    click_text("Close", dialog=True)
                    click_text("Stop")
                    wait_for("document.body.innerText.includes('Stopped') || document.body.innerText.includes('stopped')", "Server did not stop")
                    wait_health(False)
                    click_text("Start")
                    wait_for("document.body.innerText.includes('Running') || document.body.innerText.includes('running')", "Server did not restart")
                    wait_health(True)
                    with httpx.Client(base_url="http://127.0.0.1:8000", trust_env=False) as api:
                        if api.get("/sessions").json():
                            raise RuntimeError("Server retained in-memory sessions; restart was not verified")
                    click('button[aria-label="Saved conversations"]')
                    wait_for("!!document.querySelector('button[aria-label=\"Resume conversation 11111111\"]')", "History missing after process restart")
                    click('button[aria-label="Resume conversation 11111111"]')
                    wait_for("!document.querySelector('dialog[open]')", "Resume after restart failed")
                    if [message["content"] for message in saved()["messages"]] != [question, answer]:
                        raise RuntimeError("Durable conversation did not survive server restart")
                    if list(root.rglob("never-replay")):
                        raise RuntimeError("Historical command was replayed")
                    if (workspace / "fixture.txt").read_text() != "Keep this source file unchanged.\n":
                        raise RuntimeError("Source fixture was modified")
                    screenshot("history-after-restart.png")
                    report = {"status": "passed", "application_sha256": hashlib.sha256(application.read_bytes()).hexdigest(),
                              "interface": "native Tauri WebDriver", "model_requests": 0,
                              "history_fixture": "preseeded synthetic SQLite completed turns",
                              "history_picker_verified": True, "restored_messages_verified": True,
                              "historical_markup_not_executed": True,
                              "http_503_fault_injection_preserved_current_session": True,
                              "failed_candidate_session_cleaned_up": True,
                              "server_process_restart_resume_verified": True,
                              "historical_commands_not_replayed": True, "source_unchanged": True}
                    if fixture:
                        report.update(hosted_model_requests=0, model_fixture_requests=len(fixture["calls"]),
                            provider_fixture="local synthetic OpenAI-compatible HTTP service, not hosted inference",
                            native_auto_explicit_configured_selection_verified=True,
                            native_requested_reported_receipts_verified=True,
                            native_busy_model_change_disabled=True,
                            native_catalog_failure_recovery_verified=True)
                        report.update(native_structured_sandbox_error_formatting_verified=True,
                                      sandbox_error_source="Injected HTTP 503 response, not an actual namespace failure")
                    if options.paint_fixture:
                        report.update(paint_fixture="Locally authored file edit, no hosted model call",
                            actual_apply_cancel_and_success_verified=True,
                            closed_dialog_frame_wait="Two animation frames plus 100 ms",
                            final_paint_images_require_visual_review=True)
                    (output / "evidence.json").write_text(json.dumps(report, indent=2) + "\n")
                finally:
                    if prefix:
                        try:
                            if not (output / "evidence.json").exists():
                                screenshot("failure.png")
                            request("/execute/async", {"script": "const done = arguments[arguments.length - 1]; window.__TAURI_INTERNALS__.invoke('stop_bifang_server').then(() => done(true), () => done(false));", "args": []})
                            client.delete(prefix)
                        except httpx.TransportError:
                            pass
                    if driver.poll() is None:
                        os.killpg(driver.pid, signal.SIGTERM)
                        driver.wait(timeout=10)
    print("Native history picker, failure recovery and restart resume passed without hosted inference.")


if __name__ == "__main__":
    main()
