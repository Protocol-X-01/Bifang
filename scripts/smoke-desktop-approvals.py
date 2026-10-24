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
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Event, Thread

import httpx

from bifang.model_ids import TOKEN_FACTORY_ROLES


def main():
    parser = argparse.ArgumentParser(description="Native approval levels with synthetic loopback model responses")
    parser.add_argument("--application", type=Path, required=True)
    parser.add_argument("--native-driver", required=True)
    parser.add_argument("--tauri-driver", required=True)
    parser.add_argument("--output", type=Path, required=True)
    options = parser.parse_args()
    if not os.environ.get("DISPLAY"):
        raise RuntimeError("Use a dedicated display such as xvfb-run")
    application = options.application.resolve(strict=True)
    output = options.output.resolve()
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    for port in (8000, 4444):
        with socket.socket() as probe:
            if probe.connect_ex(("127.0.0.1", port)) == 0:
                raise RuntimeError("Native test port already occupied")
    requests = []
    pause_started, pause_release = Event(), Event()

    class Handler(BaseHTTPRequestHandler):
        def respond(self, body):
            encoded = json.dumps(body).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def do_GET(self):
            self.respond({"data": [{"id": value} for value in TOKEN_FACTORY_ROLES.values()]})

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append(body)
            prompt = next(message["content"] for message in reversed(body["messages"]) if message["role"] == "user")
            if body["messages"][-1]["role"] == "tool":
                message = {"role": "assistant", "content": "Synthetic approval fixture complete."}
            else:
                level = prompt.split()[0]
                if level not in {"manual", "auto", "full", "pause"}:
                    raise RuntimeError("Unexpected fixture prompt")
                if level == "pause":
                    pause_started.set()
                    if not pause_release.wait(timeout=45):
                        raise RuntimeError("Native pause fixture was not released")
                calls = [{"id": level + "-write", "type": "function", "function": {
                    "name": "write_file", "arguments": json.dumps({"path": level + ".py", "content": "fixture = True\n"})}}]
                if level == "full":
                    calls.extend({"id": identity, "type": "function", "function": {
                        "name": "run_command", "arguments": json.dumps({"command": command})}}
                        for identity, command in (("full-command", "printf BIFANG_APPROVAL_FIXTURE > command-result.txt"),
                                                  ("blocked-command", "sudo id")))
                message = {"role": "assistant", "content": None, "tool_calls": calls}
            self.respond({"model": body["model"], "choices": [{"message": message,
                "finish_reason": "tool_calls" if message.get("tool_calls") else "stop"}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}})

        def log_message(self, *args):
            return

    fixture = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    fixture_thread = Thread(target=fixture.serve_forever, daemon=True)
    fixture_thread.start()
    driver = None
    report = None
    try:
        with tempfile.TemporaryDirectory(prefix="bifang-approval-native-") as temporary:
            root = Path(temporary)
            workspace = root / "project"
            workspace.mkdir()
            (workspace / "baseline.py").write_text("baseline = True\n")
            subprocess.run(["git", "init", "-q", str(workspace)], check=True)
            subprocess.run(["git", "add", "."], cwd=workspace, check=True)
            subprocess.run(["git", "-c", "user.name=Bifang Fixture", "-c", "user.email=test@example.invalid",
                            "commit", "-qm", "Approval fixture"], cwd=workspace, check=True)
            runtime = root / "runtime"
            runtime.mkdir(mode=0o700)
            environment = {name: value for name, value in os.environ.items() if name in {
                "PATH", "LANG", "LC_ALL", "DISPLAY", "XAUTHORITY", "DBUS_SESSION_BUS_ADDRESS"}}
            environment.update(HOME=str(root), XDG_CONFIG_HOME=str(root / "config"),
                XDG_STATE_HOME=str(root / "state"), XDG_DATA_HOME=str(root / "data"),
                XDG_CACHE_HOME=str(root / "cache"), XDG_RUNTIME_DIR=str(runtime),
                GDK_BACKEND="x11", GIO_USE_VFS="local", GTK_USE_PORTAL="0", LIBGL_ALWAYS_SOFTWARE="1",
                BIFANG_ENABLE_MEMORY="0", BIFANG_ENABLE_TRACING="0", BIFANG_BWRAP="1",
                BIFANG_ENV_FILE=str(root / "absent.env"), BIFANG_APPROVAL_MODE="full",
                NEBIUS_API_KEY="synthetic-local-fixture-key", BIFANG_DEFAULT_PROVIDER="nebius",
                BIFANG_NEBIUS_BASE_URL=f"http://127.0.0.1:{fixture.server_port}/v1",
                BIFANG_NEBIUS_MODEL=TOKEN_FACTORY_ROLES["fast"], BIFANG_ROUTING_MODE="pinned")
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
                            raise RuntimeError("WebDriver startup timeout")
                        created = client.post("/session", json={"capabilities": {"alwaysMatch": {
                            "tauri:options": {"application": str(application)}, "unhandledPromptBehavior": "ignore"}}})
                        created.raise_for_status()
                        prefix = "/session/" + created.json()["value"]["sessionId"]

                        def request(endpoint, payload=None, method="POST"):
                            response = client.request(method, prefix + endpoint, json=payload)
                            response.raise_for_status()
                            value = response.json().get("value")
                            if isinstance(value, dict) and value.get("error"):
                                raise RuntimeError("Native WebDriver operation failed")
                            return value

                        def execute(script, *arguments):
                            return request("/execute/sync", {"script": script, "args": list(arguments)})

                        def wait_for(expression, message):
                            for attempt in range(200):
                                if execute("return " + expression):
                                    return
                                time.sleep(0.1)
                            raise RuntimeError(message)

                        def click(label, dialog=False):
                            selector = ("//dialog[@open]" if dialog else "") + "//button[normalize-space(.)='" + label + "' or @aria-label='" + label + "']"
                            element = request("/element", {"using": "xpath", "value": selector})
                            request("/element/" + element["element-6066-11e4-a52e-4f735466cecf"] + "/click", {})

                        def type_into(selector, text):
                            element = request("/element", {"using": "css selector", "value": selector})
                            request("/element/" + element["element-6066-11e4-a52e-4f735466cecf"] + "/value", {"text": text})

                        def screenshot(name):
                            request("/execute/async", {"script": "const done=arguments[arguments.length-1]; requestAnimationFrame(()=>requestAnimationFrame(()=>setTimeout(()=>done(true),100)));", "args": []})
                            (output / name).write_bytes(base64.b64decode(request("/screenshot", method="GET")))

                        def choose(mode):
                            execute("const field=document.querySelector('#approval-mode');field.value=arguments[0];field.dispatchEvent(new Event('change',{bubbles:true}));", mode)

                        def submit(level):
                            type_into("textarea", level + " fixture")
                            element = request("/element", {"using": "css selector", "value": "textarea + button[type=submit]"})
                            request("/element/" + element["element-6066-11e4-a52e-4f735466cecf"] + "/click", {})

                        def finish(expected_count):
                            wait_for(f"document.querySelectorAll('details').length === {expected_count} && !document.querySelector('#approval-mode').disabled",
                                     "Native fixture turn did not complete")
                            if execute("return document.body.innerText.includes('Error:')"):
                                raise RuntimeError("Native fixture displayed an error")

                        request("/window/rect", {"x": 0, "y": 0, "width": 1400, "height": 900})
                        wait_for("!!document.querySelector('#approval-mode')", "Approval picker not rendered")
                        if execute("return document.querySelector('#approval-mode').value") != "manual":
                            raise RuntimeError("Initial native approval mode was not manual")
                        click("Open by path…")
                        type_into("input[name=workspace-path]", str(workspace))
                        click("Open workspace", dialog=True)
                        wait_for("!document.querySelector('dialog[open]')", "Native workspace selection failed")
                        submit("manual")
                        wait_for("!!document.querySelector('dialog[open] #approval-title')", "Manual edit approval missing")
                        if execute("return document.querySelector('dialog[open] pre').innerText") != "Allow Bifang to write manual.py?":
                            raise RuntimeError("Unexpected native action; no approval given")
                        screenshot("manual-approval.png")
                        click("Allow once", dialog=True)
                        finish(1)
                        session_id = execute("return JSON.parse(localStorage.getItem('bifang-session')).state.sessionId")
                        with httpx.Client(base_url="http://127.0.0.1:8000", trust_env=False) as api:
                            current = api.get(f"/sessions/{session_id}").json()
                            disposable = Path(current["workspace"]).resolve()
                            if not disposable.is_relative_to(root) or disposable == workspace or current["approval_mode"] != "manual":
                                raise RuntimeError("Native session is not a manual disposable worktree")
                            choose("auto")
                            submit("auto")
                            finish(2)
                            if not (disposable / "auto.py").exists() or api.get(f"/sessions/{session_id}").json()["approval_mode"] != "auto":
                                raise RuntimeError("Automatic edit did not reach the isolated worktree")
                            screenshot("auto-edit-complete.png")
                            choose("full")
                            wait_for("!!document.querySelector('dialog[open] #full-approval-title')", "Full approval opt-in missing")
                            click("Keep current mode", dialog=True)
                            if execute("return document.querySelector('#approval-mode').value") != "auto":
                                raise RuntimeError("Cancelling full approval changed the selected level")
                            choose("full")
                            screenshot("full-confirmation.png")
                            click("Enable full approval", dialog=True)
                            submit("full")
                            finish(3)
                            if (disposable / "command-result.txt").read_text() != "BIFANG_APPROVAL_FIXTURE":
                                raise RuntimeError("Full-mode sandboxed command did not finish")
                            results = [message["content"] for message in requests[-1]["messages"] if message["role"] == "tool"]
                            if not any("DENIED: blocked: privilege escalation" in value for value in results):
                                raise RuntimeError("Full mode did not preserve blocked-command policy")
                            screenshot("full-turn-complete.png")
                            submit("pause")
                            if not pause_started.wait(timeout=10):
                                raise RuntimeError("Controlled model pause did not start")
                            wait_for("[...document.querySelectorAll('button')].some(button=>button.textContent==='Pause auto approvals')",
                                     "Native pause control missing")
                            click("Pause auto approvals")
                            wait_for("document.querySelector('#approval-mode').value === 'manual'", "Pause did not restore manual UI")
                            if api.get(f"/sessions/{session_id}").json()["approval_mode"] != "manual":
                                raise RuntimeError("Pause did not narrow the server's approval mode")
                            pause_release.set()
                            wait_for("!!document.querySelector('dialog[open] #approval-title')", "Post-pause tool did not request review")
                            if execute("return document.querySelector('dialog[open] pre').innerText") != "Allow Bifang to write pause.py?":
                                raise RuntimeError("Unexpected action after pause; no approval given")
                            screenshot("paused-manual-review.png")
                            click("Deny", dialog=True)
                            finish(4)
                            if (disposable / "pause.py").exists():
                                raise RuntimeError("Denied post-pause edit was executed")
                            audit = [json.loads(line) for path in (disposable / ".bifang/sessions").glob("*.jsonl")
                                     for line in path.read_text().splitlines()]
                            decisions = [row for row in audit if row["event"] == "tool_approval"]
                            sources = [row["source"] for row in decisions]
                            if sources != ["manual", "auto_workspace_edit", "full", "full", "manual"]:
                                raise RuntimeError("Native audit does not match the exercised approval levels")
                            if decisions[-1]["approved"] is not False:
                                raise RuntimeError("Denied approval was not recorded")
                            for name in ("manual.py", "auto.py", "full.py", "command-result.txt", "pause.py"):
                                if (workspace / name).exists():
                                    raise RuntimeError("Unapplied edit reached the original checkout")
                        choose("full")
                        click("Enable full approval", dialog=True)
                        click("New chat")
                        alert = client.post(prefix + "/alert/accept", json={})
                        if alert.status_code not in (200, 404):
                            alert.raise_for_status()
                        wait_for("document.querySelector('#approval-mode').value === 'manual'", "New chat did not reset approval mode")
                        choose("full")
                        click("Enable full approval", dialog=True)
                        request("/refresh", {})
                        wait_for("!!document.querySelector('#approval-mode') && document.querySelector('#approval-mode').value === 'manual'",
                                 "Reload did not reset approval mode")
                        screenshot("manual-after-reset.png")
                        report = {"status": "passed", "interface": "native Tauri WebDriver",
                            "application_sha256": hashlib.sha256(application.read_bytes()).hexdigest(),
                            "sidecar_sha256": hashlib.sha256(application.with_name("bifang-server").read_bytes()).hexdigest(),
                            "synthetic_model_requests": len(requests), "hosted_model_requests": 0,
                            "manual_edit_approval_verified": True, "auto_isolated_edit_verified": True,
                            "full_optin_cancel_and_confirm_verified": True, "full_write_and_command_verified": True,
                            "command_sandbox_requested": True, "blocked_command_still_denied": True,
                            "native_pause_narrows_server_mode_verified": True, "post_pause_denial_enforced": True,
                            "approval_decision_sources": sources, "original_checkout_unchanged": True,
                            "new_chat_and_reload_reset_verified": True, "published": False,
                            "scope": "Harmless synthetic fixture on development host; no live inference, fresh OS installation or hostile-code isolation claim"}
                    finally:
                        pause_release.set()
                        if prefix:
                            if report is None:
                                screenshot("failure.png")
                            request("/execute/async", {"script": "const done=arguments[arguments.length-1];window.__TAURI_INTERNALS__.invoke('stop_bifang_server').then(()=>done(true),()=>done(false));", "args": []})
                            client.delete(prefix)
    finally:
        pause_release.set()
        if driver and driver.poll() is None:
            os.killpg(driver.pid, signal.SIGTERM)
            driver.wait(timeout=10)
        fixture.shutdown()
        fixture.server_close()
        fixture_thread.join(timeout=5)
    for port in (8000, 4444, fixture.server_port):
        with socket.socket() as probe:
            if probe.connect_ex(("127.0.0.1", port)) == 0:
                raise RuntimeError("Native fixture service port remained open")
    report["test_ports_closed"] = True
    descriptor = os.open(output / "evidence.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as stream:
        json.dump(report, stream, indent=2)
        stream.write("\n")
    print("Native approval levels, sandboxed command, pause and reset checks passed.")


if __name__ == "__main__":
    main()
