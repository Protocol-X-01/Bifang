import argparse
import base64
import hashlib
import json
import os
import shutil
import signal
import socket
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from dotenv import dotenv_values


def arguments():
    parser = argparse.ArgumentParser(description="Live Linux desktop demo with synthetic code")
    parser.add_argument("--application", type=Path, required=True)
    parser.add_argument("--native-driver", required=True)
    parser.add_argument("--tauri-driver", default="tauri-driver")
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--relay-url")
    parser.add_argument("--judge-token-file", type=Path)
    parser.add_argument("--no-command-sandbox", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--record", action="store_true")
    parser.add_argument("--preselect-workspace", action="store_true")
    return parser.parse_args()


def provider_environment(env_file=None, relay_url=None, judge_token_file=None):
    if relay_url or judge_token_file:
        if not relay_url or not judge_token_file or env_file:
            raise ValueError("Relay verification requires both relay URL and judge-token file, without --env-file")
        parsed = urlsplit(relay_url)
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
                or parsed.port not in (None, 443) or parsed.query or parsed.fragment
                or parsed.path.rstrip("/") not in ("", "/v1")):
            raise ValueError("Use an HTTPS relay origin or /v1 URL without credentials, query or fragment")
        private = json.loads(judge_token_file.read_text())
        token = private.get("judge_token")
        if not isinstance(token, str) or len(token) < 32 or any(character.isspace() for character in token):
            raise ValueError("Expected a private JSON file with a strong judge_token")
        return {"NEBIUS_API_KEY": token,
                "BIFANG_NEBIUS_BASE_URL": f"https://{parsed.netloc}/v1",
                "BIFANG_NEBIUS_MODEL": "nvidia/Nemotron-3-Ultra-550b-a55b"}
    private = dotenv_values(env_file) if env_file else {}
    environment = {name: value for name in
                   ("NEBIUS_API_KEY", "BIFANG_NEBIUS_BASE_URL", "BIFANG_NEBIUS_MODEL")
                   if (value := private.get(name) or os.environ.get(name))}
    if not environment.get("NEBIUS_API_KEY"):
        raise ValueError("NEBIUS_API_KEY is required; no credential value is logged")
    if environment.get("BIFANG_NEBIUS_BASE_URL", "https://api.tokenfactory.nebius.com/v1").rstrip("/") != "https://api.tokenfactory.nebius.com/v1":
        raise ValueError("Direct rehearsal only sends provider credentials to Token Factory")
    environment.setdefault("BIFANG_NEBIUS_MODEL", "nvidia/Nemotron-3-Ultra-550b-a55b")
    return environment


def check_fixture(workspace, sandbox=True):
    command = ["/usr/bin/python3", "-I", "-B", "-c",
               "import sys,unittest;sys.path.insert(0,'.');unittest.main(module='check_receipts',verbosity=2)"]
    if sandbox:
        if not shutil.which("bwrap"):
            raise RuntimeError("Bubblewrap is required; refusing unsandboxed fixture checks")
        command = ["bwrap", "--unshare-all", "--die-with-parent", "--new-session",
                   "--clearenv", "--ro-bind", "/usr", "/usr"] + [
            argument for directory in ("/lib", "/lib64") if Path(directory).exists()
            for argument in ("--ro-bind", directory, directory)] + [
            "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp",
            "--ro-bind", str(workspace), "/work", "--chdir", "/work", *command]
    return subprocess.run(command, cwd=workspace, capture_output=True, text=True, check=False,
                          timeout=30, env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"})


def stop(process):
    if process is not None and process.poll() is None:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)


def main():
    options = arguments()
    if not os.environ.get("DISPLAY"):
        raise RuntimeError("Use a dedicated X display, for example xvfb-run")
    for port in (8000, 4444):
        with socket.socket() as probe:
            if probe.connect_ex(("127.0.0.1", port)) == 0:
                raise RuntimeError("A rehearsal port is occupied; do not interrupt an existing service")
    application = options.application.resolve(strict=True)
    output = options.output.resolve()
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    env = {name: value for name, value in os.environ.items() if name in {
        "PATH", "LANG", "LC_ALL", "DISPLAY", "XAUTHORITY", "DBUS_SESSION_BUS_ADDRESS",
    }}
    env.update(provider_environment(options.env_file, options.relay_url, options.judge_token_file))
    recorder = None
    driver = None
    prefix = None
    with tempfile.TemporaryDirectory(prefix="bifang-demo-", ignore_cleanup_errors=True) as temporary:
        root = Path(temporary)
        (root / "runtime").mkdir(mode=0o700)
        env.update(HOME=str(root), XDG_CONFIG_HOME=str(root / "config"),
                   XDG_STATE_HOME=str(root / "state"), XDG_CACHE_HOME=str(root / "cache"),
                   XDG_DATA_HOME=str(root / "data"), GDK_BACKEND="x11",
                   XDG_RUNTIME_DIR=str(root / "runtime"),
                   GIO_USE_VFS="local", GTK_USE_PORTAL="0",
                   LIBGL_ALWAYS_SOFTWARE="1", BIFANG_DEFAULT_PROVIDER="nebius",
                   BIFANG_ENABLE_MEMORY="0", BIFANG_BWRAP="0" if options.no_command_sandbox else "1",
                   BIFANG_MAX_STEPS="8")
        workspace = root / "receipt-demo"
        workspace.mkdir()
        fixture = Path(__file__).resolve().parents[1] / "examples/demo"
        for name in ("receipts.py", "check_receipts.py", ".gitignore"):
            shutil.copyfile(fixture / name, workspace / name)
        for command in (["init", "-q"], ["add", "."], ["-c", "user.name=Bifang Demo", "-c", "user.email=demo@example.invalid", "commit", "-qm", "Baseline"]):
            subprocess.run(["git", *command], cwd=workspace, check=True, capture_output=True)
        checks_before = (workspace / "check_receipts.py").read_bytes()
        baseline = check_fixture(workspace, sandbox=not options.no_command_sandbox)
        if "Ran 5 tests" not in baseline.stderr:
            raise RuntimeError("Fixture baseline did not execute five checks; inspect sandbox availability")
        if baseline.returncode == 0:
            raise RuntimeError("Demo baseline unexpectedly passes")
        (output / "baseline.txt").write_text(baseline.stderr)
        with (output / "driver.log").open("w") as log, (output / "recording.log").open("w") as recording_log:
            try:
                driver = subprocess.Popen([options.tauri_driver, "--native-driver", options.native_driver], env=env, stdout=log, stderr=log, start_new_session=True)
                with httpx.Client(base_url="http://127.0.0.1:4444", timeout=60, trust_env=False) as client:
                    for attempt in range(100):
                        if driver.poll() is not None:
                            raise RuntimeError("WebDriver exited")
                        try:
                            if client.get("/status").is_success:
                                break
                        except httpx.ConnectError:
                            pass
                        time.sleep(0.2)
                    else:
                        raise RuntimeError("WebDriver did not become ready")
                    response = client.post("/session", json={"capabilities": {"alwaysMatch": {"tauri:options": {"application": str(application)}}}})
                    response.raise_for_status()
                    prefix = "/session/" + response.json()["value"]["sessionId"]

                    def request(endpoint, payload=None, method="POST"):
                        response = client.request(method, prefix + endpoint, json=payload)
                        response.raise_for_status()
                        result = response.json().get("value")
                        if isinstance(result, dict) and result.get("error"):
                            raise RuntimeError("WebDriver operation failed")
                        return result

                    def execute(script, *args):
                        return request("/execute/sync", {"script": script, "args": list(args)})

                    def click(using, value):
                        element = request("/element", {"using": using, "value": value})["element-6066-11e4-a52e-4f735466cecf"]
                        request(f"/element/{element}/click", {})

                    def screenshot(name):
                        painted = request("/execute/async", {
                            "script": "const done=arguments[arguments.length-1]; requestAnimationFrame(()=>requestAnimationFrame(()=>setTimeout(()=>done(true),100)));",
                            "args": []})
                        if painted is not True:
                            raise RuntimeError("Native screenshot frame barrier failed")
                        (output / name).write_bytes(base64.b64decode(request("/screenshot", method="GET")))

                    request("/window/rect", {"x": 0, "y": 0, "width": 1400, "height": 900})
                    time.sleep(2)
                    if options.preselect_workspace:
                        execute("localStorage.setItem('bifang-workspace', arguments[0])", json.dumps({"state": {"workspacePath": str(workspace), "activeWorkspacePath": str(workspace)}, "version": 0}))
                        request("/refresh", {})
                    else:
                        click("xpath", "//button[normalize-space(.)='Open by path…']")
                        path_input = request("/element", {"using": "css selector", "value": "input[name=workspace-path]"})["element-6066-11e4-a52e-4f735466cecf"]
                        for invalid, expected in [(".", "absolute"), (str(workspace / "receipts.py"), "not a file"), (str(workspace / "missing-directory"), "does not exist")]:
                            request(f"/element/{path_input}/clear", {})
                            request(f"/element/{path_input}/value", {"text": invalid})
                            click("xpath", "//dialog[@open]//button[normalize-space(.)='Open workspace']")
                            for attempt in range(100):
                                error = execute("return document.querySelector('[role=alert]')?.innerText || ''")
                                if expected in error:
                                    break
                                time.sleep(0.05)
                            else:
                                raise RuntimeError("Invalid workspace path was not visibly rejected")
                            state = execute("return JSON.parse(localStorage.getItem('bifang-workspace') || '{}')")
                            if state.get("state", {}).get("workspacePath"):
                                raise RuntimeError("Invalid path changed the selected workspace")
                        screenshot("workspace-validation.png")
                        request(f"/element/{path_input}/clear", {})
                        request(f"/element/{path_input}/value", {"text": str(workspace)})
                        click("xpath", "//dialog[@open]//button[normalize-space(.)='Open workspace']")
                        for attempt in range(100):
                            state = execute("return JSON.parse(localStorage.getItem('bifang-workspace') || '{}')")
                            if state.get("state", {}).get("workspacePath") == str(workspace):
                                break
                            time.sleep(0.1)
                        else:
                            raise RuntimeError("Workspace selection through the path dialog failed")
                    time.sleep(2)
                    if options.record:
                        recorder = subprocess.Popen(["ffmpeg", "-nostdin", "-y", "-f", "x11grab", "-video_size", "1400x900", "-framerate", "20", "-i", env["DISPLAY"], "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(output / "desktop-demo.mp4")], env=env, stdout=recording_log, stderr=recording_log, start_new_session=True)
                        time.sleep(2)
                    prompt = "Run python3 -m unittest -v check_receipts. Fix receipts.py so quoted CSV commas and escaped quotes work, using the standard library. Preserve the return shape and reject wrong field counts. Do not edit check_receipts.py. Use read_file, write_file and run_command; the only approved command is exactly python3 -m unittest -v check_receipts. Rerun checks. Keep the final answer to four concise bullets, without repeating the source code."
                    textarea = request("/element", {"using": "css selector", "value": "textarea"})["element-6066-11e4-a52e-4f735466cecf"]
                    request(f"/element/{textarea}/value", {"text": prompt})
                    click("xpath", "//form[.//textarea]//button[@type='submit']")
                    approvals = []
                    started = time.monotonic()
                    while time.monotonic() - started < 180:
                        action = execute("return document.querySelector('dialog[open] pre')?.innerText || null")
                        if action:
                            allowed_actions = {"Allow Bifang to write receipts.py?", "Run command?\npython3 -m unittest -v check_receipts"}
                            active_workspace = execute("return JSON.parse(localStorage.getItem('bifang-workspace') || '{}').state?.activeWorkspacePath || null")
                            if active_workspace:
                                active_path = Path(active_workspace).resolve()
                                if active_path.is_relative_to(root / "state" / "bifang" / "boxes"):
                                    allowed_actions.add(f"Allow Bifang to write {active_path / 'receipts.py'}?")
                            allowed = action in allowed_actions
                            approvals.append({"action": action, "approved": allowed})
                            screenshot("approval.png")
                            time.sleep(1.5 if options.record else 0)
                            choice = "Allow once" if allowed else "Deny"
                            click("xpath", "//dialog[@open]//button[normalize-space(.)='" + choice + "']")
                            if not allowed:
                                raise RuntimeError("Unexpected action denied; rehearsal stopped")
                        state = execute("return JSON.parse(localStorage.getItem('bifang-session') || '{}')")
                        messages = state.get("state", {}).get("messages", [])
                        if messages and messages[-1]["role"] == "assistant":
                            if messages[-1]["content"].startswith("Error:"):
                                raise RuntimeError("Assistant reported an error")
                            break
                        time.sleep(0.2)
                    else:
                        raise RuntimeError("Live task timed out")
                    time.sleep(3 if options.record else 2)
                    click("xpath", "//details[.//summary[contains(., 'Model receipts')]]/summary")
                    execute("document.querySelector('details[open] li')?.scrollIntoView({block:'center'});")
                    if not execute("return [...document.querySelectorAll('details[open] li')].some(item=>item.innerText.includes('nebius')&&item.innerText.includes('Requested:')&&item.innerText.includes('Server reported:'))"):
                        raise RuntimeError("Rendered provider/model receipts are missing")
                    screenshot("model-receipts.png")
                    time.sleep(3 if options.record else 0)
                    click("xpath", "//details[.//summary[contains(., 'Model receipts')]]/summary")
                    click("xpath", "//button[normalize-space(.)='Apply']")
                    time.sleep(2 if options.record else 0)
                    click("xpath", "//dialog[@open]//button[normalize-space(.)='Apply to repository']")
                    for attempt in range(100):
                        if execute("return document.body.innerText.includes('Changes applied to the original repository.')"):
                            break
                        time.sleep(0.1)
                    else:
                        raise RuntimeError("Apply success notice missing")
                    final = check_fixture(workspace, sandbox=not options.no_command_sandbox)
                    changed = subprocess.check_output(["git", "diff", "--name-only"], cwd=workspace, text=True).splitlines()
                    if final.returncode or changed != ["receipts.py"] or checks_before != (workspace / "check_receipts.py").read_bytes():
                        raise RuntimeError("Final source verification failed")
                    (output / "final-checks.txt").write_text(final.stderr)
                    (output / "change.patch").write_bytes(subprocess.check_output(["git", "diff"], cwd=workspace))
                    screenshot("verified.png")
                    receipts = messages[-1].get("routing", [])
                    if not receipts:
                        raise RuntimeError("Live model receipts are missing")
                    evidence = {"provider": "nebius", "requested_model": env["BIFANG_NEBIUS_MODEL"],
                                "inference_endpoint": env.get("BIFANG_NEBIUS_BASE_URL"),
                                "credential_type": "judge_only" if options.relay_url else "provider",
                                "command_sandbox_enabled": not options.no_command_sandbox,
                                "independent_checks_sandbox_enabled": not options.no_command_sandbox,
                                "routing_receipts": receipts,
                                "application_sha256": hashlib.sha256(application.read_bytes()).hexdigest(),
                                "sidecar_sha256": hashlib.sha256(application.with_name("bifang-server").read_bytes()).hexdigest(),
                                "interface": "native Tauri WebDriver",
                                "workspace_selection": "preseeded fixture" if options.preselect_workspace else "in-app path dialog",
                                "invalid_workspace_paths_rejected": [] if options.preselect_workspace else ["relative", "file", "nonexistent"],
                                "approval_mode": "automated exact-action allowlist", "approvals": approvals,
                                "changed_files": changed, "checks_unchanged": True,
                                "baseline_returncode": baseline.returncode, "final_returncode": final.returncode,
                                "continuous_screen_recording": options.record,
                                "rendered_provider_model_receipts_verified": True,
                                "screenshot_frame_barrier": "Two animation frames plus 100 ms"}
                    encoded = json.dumps(evidence, indent=2) + "\n"
                    if env["NEBIUS_API_KEY"] in encoded:
                        raise RuntimeError("Credential screen failed; evidence not saved")
                    (output / "evidence.json").write_text(encoded)
                    time.sleep(5 if options.record else 0)
                    stop(recorder)
                    if recorder is not None and (recorder.returncode not in (0, 255) or not (output / "desktop-demo.mp4").is_file()):
                        raise RuntimeError("Screen recording failed; inspect recording.log privately")
                    stopped = request("/execute/async", {
                        "script": "const done=arguments[arguments.length-1]; window.__TAURI_INTERNALS__.invoke('stop_bifang_server').then(()=>done(true),()=>done(false));",
                        "args": []})
                    if stopped is not True:
                        raise RuntimeError("Native sidecar shutdown failed")
                    for attempt in range(50):
                        with socket.socket() as probe:
                            if probe.connect_ex(("127.0.0.1", 8000)) == 111:
                                break
                        time.sleep(0.1)
                    else:
                        raise RuntimeError("Rehearsal sidecar stayed alive after Stop")
                    request("", method="DELETE")
                    print("PASS: native UI, approvals, apply, unchanged checks and five passing tests")
            finally:
                stop(recorder)
                if prefix:
                    try:
                        with httpx.Client(base_url="http://127.0.0.1:4444", timeout=10, trust_env=False) as cleanup:
                            cleanup.post(prefix + "/execute/async", json={
                                "script": "const done=arguments[arguments.length-1]; window.__TAURI_INTERNALS__.invoke('stop_bifang_server').then(()=>done(true),()=>done(false));",
                                "args": []})
                    except httpx.HTTPError:
                        pass
                stop(driver)


if __name__ == "__main__":
    main()
