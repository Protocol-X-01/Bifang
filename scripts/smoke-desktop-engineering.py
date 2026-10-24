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
    parser = argparse.ArgumentParser(description="Native isolated engineering with synthetic loopback model responses")
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
            if any(message.get("role") == "user" and message.get("content") == "Initialize synthetic fixture session" for message in body["messages"]):
                self.respond({"model": body["model"], "choices": [{"message": {
                    "role": "assistant", "content": "Fixture session ready."}, "finish_reason": "stop"}]})
                return
            if body.get("stream"):
                encoded = ('data: ' + json.dumps({"choices": [{"delta": {"content": "Fixture session ready."}, "finish_reason": None}]}) + '\n\ndata: [DONE]\n\n').encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)
                return
            tools = [message for message in body["messages"] if message["role"] == "tool"]
            if not tools:
                name, arguments = "read_file", {"path": "solution.py"}
            elif len(tools) == 1:
                name, arguments = "write_file", {"path": "solution.py", "content": "value = 2\n"}
            else:
                name, arguments = None, None
            message = {"role": "assistant", "content": "All tests passed. (Deliberately unsupported fixture claim.)"}
            if name:
                message = {"role": "assistant", "content": None, "tool_calls": [{
                    "id": "fixture-" + str(len(tools)), "type": "function",
                    "function": {"name": name, "arguments": json.dumps(arguments)}}]}
            self.respond({"model": body["model"], "choices": [{"message": message,
                "finish_reason": "tool_calls" if name else "stop"}],
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
            (workspace / "solution.py").write_text("value = 1\n")
            (workspace / "check.py").write_text("from solution import value\nassert value == 2\n")
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
                with httpx.Client(base_url="http://127.0.0.1:4444", timeout=90, trust_env=False) as client:
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
                            wait_for("(()=>{const button=document.evaluate(" + json.dumps(selector) + ",document,null,XPathResult.FIRST_ORDERED_NODE_TYPE,null).singleNodeValue;return button && !button.disabled;})()",
                                     "Native button did not become actionable: " + label)
                            element = request("/element", {"using": "xpath", "value": selector})
                            request("/element/" + element["element-6066-11e4-a52e-4f735466cecf"] + "/click", {})

                        def type_into(selector, text):
                            element = request("/element", {"using": "css selector", "value": selector})
                            request("/element/" + element["element-6066-11e4-a52e-4f735466cecf"] + "/clear", {})
                            request("/element/" + element["element-6066-11e4-a52e-4f735466cecf"] + "/value", {"text": text.replace("\n", "\ue007")})
                            if execute("return document.querySelector(arguments[0]).value", selector) != text:
                                raise RuntimeError("WebDriver did not enter the exact requested field value")

                        def screenshot(name):
                            request("/execute/async", {"script": "const done=arguments[arguments.length-1]; requestAnimationFrame(()=>requestAnimationFrame(()=>setTimeout(()=>done(true),100)));", "args": []})
                            (output / name).write_bytes(base64.b64decode(request("/screenshot", method="GET")))

                        def status(expected):
                            wait_for("document.body.innerText.includes(" + json.dumps("Isolated engineering · " + expected) + ")",
                                     "Engineering status did not reach " + expected)

                        def disabled(label):
                            return execute("return [...document.querySelectorAll('button')].find(button=>button.textContent.trim()===arguments[0]).disabled", label)

                        def prepare():
                            click("Prepare candidate")
                            click("Confirm candidate action", dialog=True)
                            wait_for("!!document.querySelector('dialog[open] #candidate-write-title')", "Candidate write approval missing")

                        def check():
                            click("Run independent check")
                            if execute("return document.querySelector('dialog[open] pre').innerText") != '["/usr/bin/python3", "-B", "check.py"]':
                                raise RuntimeError("Check confirmation differs from owner-selected arguments")
                            click("Confirm candidate action", dialog=True)

                        request("/window/rect", {"x": 0, "y": 0, "width": 1600, "height": 1200})
                        wait_for("!!document.querySelector('#approval-mode')", "Approval picker not rendered")
                        if execute("return document.querySelector('#approval-mode').value") != "manual":
                            raise RuntimeError("Initial native approval mode was not manual")
                        click("Open by path…")
                        type_into("input[name=workspace-path]", str(workspace))
                        click("Open workspace", dialog=True)
                        wait_for("!document.querySelector('dialog[open]')", "Native workspace selection failed")
                        type_into('textarea[placeholder="Ask Bifang..."]', "Initialize synthetic fixture session")
                        element = request("/element", {"using": "css selector", "value": 'textarea[placeholder="Ask Bifang..."] + button[type=submit]'})
                        request("/element/" + element["element-6066-11e4-a52e-4f735466cecf"] + "/click", {})
                        wait_for("document.body.innerText.includes('Fixture session ready.') && !document.querySelector('#approval-mode').disabled", "Session initialization did not complete")
                        session_id = execute("return JSON.parse(localStorage.getItem('bifang-session')).state.sessionId")
                        print("Native session initialized with synthetic inference", flush=True)
                        with httpx.Client(base_url="http://127.0.0.1:8000", trust_env=False) as api:
                            current = api.get(f"/sessions/{session_id}").json()
                            disposable = Path(current["workspace"]).resolve()
                            if not disposable.is_relative_to(root) or disposable == workspace:
                                raise RuntimeError("Session is not an isolated disposable worktree")
                            summary = request("/element", {"using": "xpath", "value": "//summary[contains(.,'Isolated engineering')]"})
                            request("/element/" + summary["element-6066-11e4-a52e-4f735466cecf"] + "/click", {})
                            type_into('textarea[aria-label="Candidate source paths"]', "solution.py\ncheck.py")
                            type_into('textarea[aria-label="Candidate editable paths"]', "solution.py")
                            type_into('textarea[aria-label="Engineering brief"]', "Change solution.py value to two.")
                            type_into('textarea[aria-label="Candidate check arguments"]', '["/usr/bin/python3", "-B", "check.py"]')
                            before = len(requests)
                            click("Prepare candidate")
                            click("Not now", dialog=True)
                            time.sleep(0.3)
                            if len(requests) != before:
                                raise RuntimeError("Cancelled inference confirmation used a model request")
                            prepare()
                            screenshot("candidate-write-denial.png")
                            click("Deny candidate write", dialog=True)
                            status("ready")
                            check()
                            status("check_failed")
                            failed = api.get(f"/sessions/{session_id}/candidate").json()
                            if failed["receipt"]["returncode"] != 1 or failed["receipt"]["passed"] or not disabled("Stage reviewed candidate"):
                                raise RuntimeError("Unsupported model claim bypassed actual failed-check gate")
                            screenshot("independent-check-failed.png")
                            print("Native denial and actual failing independent check verified", flush=True)
                            prepare()
                            screenshot("candidate-write-approval.png")
                            click("Approve candidate write", dialog=True)
                            status("ready")
                            check()
                            status("verified")
                            verified = api.get(f"/sessions/{session_id}/candidate").json()
                            if not verified["receipt"]["passed"] or verified["receipt"]["returncode"] != 0:
                                raise RuntimeError("Exact independent check did not pass")
                            if not disabled("Stage reviewed candidate"):
                                raise RuntimeError("Stage allowed before patch review")
                            click("Review candidate patch")
                            wait_for("[...document.querySelectorAll('pre')].some(node=>node.innerText.includes('+value = 2'))", "Candidate patch not rendered")
                            wait_for("![...document.querySelectorAll('button')].find(button=>button.textContent==='Stage reviewed candidate').disabled", "Reviewed stage remained disabled")
                            screenshot("verified-patch-reviewed.png")
                            click("Stage reviewed candidate")
                            click("Confirm candidate action", dialog=True)
                            status("staged")
                            wait_for("document.body.innerText.includes('Executed check: exit 0')", "Stage lost passing receipt")
                            if (workspace / "solution.py").read_text() != "value = 1\n" or (disposable / "solution.py").read_text() != "value = 2\n":
                                raise RuntimeError("Stage did not preserve original/apply boundary")
                            screenshot("candidate-staged.png")
                            print("Native reviewed staging and original boundary verified", flush=True)
                            click("Apply")
                            wait_for("!!document.querySelector('dialog[open] #apply-title')", "Original Apply confirmation did not open")
                            click("Apply to repository", dialog=True)
                            wait_for("document.body.innerText.includes('Changes applied to the original repository.')", "Separate original Apply did not complete")
                            if (workspace / "solution.py").read_text() != "value = 2\n":
                                raise RuntimeError("Original Apply did not copy the verified change")
                            screenshot("original-apply-complete.png")
                        report = {"status": "passed", "interface": "installed native Tauri WebDriver",
                            "application_sha256": hashlib.sha256(application.read_bytes()).hexdigest(),
                            "sidecar_sha256": hashlib.sha256(application.with_name("bifang-server").read_bytes()).hexdigest(),
                            "synthetic_model_requests": len(requests), "hosted_model_requests": 0,
                            "cancelled_budget_confirmation_no_inference": True,
                            "manual_write_denial_enforced": True, "unsupported_model_claim_not_verification": True,
                            "failed_check_exit": 1, "passed_check_exit": 0,
                            "patch_review_required_before_stage": True, "stage_receipt_retained": True,
                            "original_unchanged_before_separate_apply": True, "separate_original_apply_verified": True,
                            "real_bubblewrap_check": True, "published": False,
                            "scope": "Harmless synthetic inference, independent executed check, installed native UI; no live inference or hostile-code isolation claim"}
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
    print("Installed native engineering approval, independent check, staging and separate Apply passed.")


if __name__ == "__main__":
    main()
