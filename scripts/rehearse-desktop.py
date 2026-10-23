import argparse
import base64
import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
from dotenv import dotenv_values


def arguments():
    parser = argparse.ArgumentParser(description="Live Linux desktop demo with synthetic code")
    parser.add_argument("--application", type=Path, required=True)
    parser.add_argument("--native-driver", required=True)
    parser.add_argument("--tauri-driver", default="tauri-driver")
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--record", action="store_true")
    return parser.parse_args()


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
    application = options.application.resolve(strict=True)
    output = options.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    private = dotenv_values(options.env_file) if options.env_file else {}
    env = {name: value for name, value in os.environ.items() if name in {
        "PATH", "LANG", "LC_ALL", "DISPLAY", "XAUTHORITY", "DBUS_SESSION_BUS_ADDRESS",
    }}
    for name in ("NEBIUS_API_KEY", "BIFANG_NEBIUS_BASE_URL", "BIFANG_NEBIUS_MODEL"):
        value = private.get(name) or os.environ.get(name)
        if value:
            env[name] = value
    if not env.get("NEBIUS_API_KEY"):
        raise RuntimeError("NEBIUS_API_KEY is required; no credential value is logged")
    if env.get("BIFANG_NEBIUS_BASE_URL", "https://api.tokenfactory.nebius.com/v1").rstrip("/") != "https://api.tokenfactory.nebius.com/v1":
        raise RuntimeError("This live Nebius rehearsal only sends credentials to Token Factory")
    env.setdefault("BIFANG_NEBIUS_MODEL", "nvidia/Nemotron-3-Ultra-550b-a55b")
    recorder = None
    driver = None
    with tempfile.TemporaryDirectory(prefix="bifang-demo-", ignore_cleanup_errors=True) as temporary:
        root = Path(temporary)
        (root / "runtime").mkdir(mode=0o700)
        env.update(HOME=str(root), XDG_CONFIG_HOME=str(root / "config"),
                   XDG_STATE_HOME=str(root / "state"), XDG_CACHE_HOME=str(root / "cache"),
                   XDG_DATA_HOME=str(root / "data"), GDK_BACKEND="x11",
                   XDG_RUNTIME_DIR=str(root / "runtime"),
                   GIO_USE_VFS="local", GTK_USE_PORTAL="0",
                   LIBGL_ALWAYS_SOFTWARE="1", BIFANG_DEFAULT_PROVIDER="nebius",
                   BIFANG_ENABLE_MEMORY="0", BIFANG_BWRAP="0")
        workspace = root / "receipt-demo"
        workspace.mkdir()
        fixture = Path(__file__).resolve().parents[1] / "examples/demo"
        for name in ("receipts.py", "check_receipts.py", ".gitignore"):
            shutil.copyfile(fixture / name, workspace / name)
        for command in (["init", "-q"], ["add", "."], ["-c", "user.name=Bifang Demo", "-c", "user.email=demo@example.invalid", "commit", "-qm", "Baseline"]):
            subprocess.run(["git", *command], cwd=workspace, check=True, capture_output=True)
        checks_before = (workspace / "check_receipts.py").read_bytes()
        baseline = subprocess.run([sys.executable, "-m", "unittest", "-v", "check_receipts"], cwd=workspace, capture_output=True, text=True, check=False)
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
                        (output / name).write_bytes(base64.b64decode(request("/screenshot", method="GET")))

                    request("/window/rect", {"x": 0, "y": 0, "width": 1400, "height": 900})
                    time.sleep(2)
                    execute("localStorage.setItem('bifang-workspace', arguments[0])", json.dumps({"state": {"workspacePath": str(workspace), "activeWorkspacePath": str(workspace)}, "version": 0}))
                    request("/refresh", {})
                    time.sleep(2)
                    if options.record:
                        recorder = subprocess.Popen(["ffmpeg", "-nostdin", "-y", "-f", "x11grab", "-video_size", "1400x900", "-framerate", "20", "-i", env["DISPLAY"], "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(output / "desktop-demo.mp4")], env=env, stdout=recording_log, stderr=recording_log, start_new_session=True)
                        time.sleep(2)
                    prompt = "Run python3 -m unittest -v check_receipts. Fix receipts.py so quoted CSV commas and escaped quotes work, using the standard library. Preserve the return shape and reject wrong field counts. Do not edit check_receipts.py. Use read_file, write_file and run_command; the only approved command is exactly python3 -m unittest -v check_receipts. Rerun checks. Keep the final answer to four concise bullets, without repeating the source code."
                    textarea = request("/element", {"using": "css selector", "value": "textarea"})["element-6066-11e4-a52e-4f735466cecf"]
                    request(f"/element/{textarea}/value", {"text": prompt})
                    click("css selector", "form button[type=submit]")
                    approvals = []
                    started = time.monotonic()
                    while time.monotonic() - started < 180:
                        action = execute("return document.querySelector('dialog[open] pre')?.innerText || null")
                        if action:
                            allowed = action in {"Allow Bifang to write receipts.py?", "Run command?\npython3 -m unittest -v check_receipts"}
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
                    click("xpath", "//button[normalize-space(.)='Apply']")
                    time.sleep(2 if options.record else 0)
                    click("xpath", "//dialog[@open]//button[normalize-space(.)='Apply to repository']")
                    for attempt in range(100):
                        if execute("return document.body.innerText.includes('Changes applied to the original repository.')"):
                            break
                        time.sleep(0.1)
                    else:
                        raise RuntimeError("Apply success notice missing")
                    final = subprocess.run([sys.executable, "-m", "unittest", "-v", "check_receipts"], cwd=workspace, capture_output=True, text=True, check=False)
                    changed = subprocess.check_output(["git", "diff", "--name-only"], cwd=workspace, text=True).splitlines()
                    if final.returncode or changed != ["receipts.py"] or checks_before != (workspace / "check_receipts.py").read_bytes():
                        raise RuntimeError("Final source verification failed")
                    (output / "final-checks.txt").write_text(final.stderr)
                    (output / "change.patch").write_bytes(subprocess.check_output(["git", "diff"], cwd=workspace))
                    screenshot("verified.png")
                    (output / "evidence.json").write_text(json.dumps({"provider": "nebius", "model": env["BIFANG_NEBIUS_MODEL"], "application_sha256": hashlib.sha256(application.read_bytes()).hexdigest(), "interface": "native Tauri WebDriver", "workspace_selection": "preseeded fixture", "approval_mode": "automated exact-action allowlist", "approvals": approvals, "changed_files": changed, "checks_unchanged": True, "baseline_returncode": baseline.returncode, "final_returncode": final.returncode, "continuous_screen_recording": options.record}, indent=2) + "\n")
                    time.sleep(5 if options.record else 0)
                    stop(recorder)
                    if recorder is not None and (recorder.returncode not in (0, 255) or not (output / "desktop-demo.mp4").is_file()):
                        raise RuntimeError("Screen recording failed; inspect recording.log privately")
                    request("", method="DELETE")
                    print("PASS: native UI, approvals, apply, unchanged checks and five passing tests")
            finally:
                stop(recorder)
                stop(driver)


if __name__ == "__main__":
    main()
