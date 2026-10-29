import argparse
import json
import os
import secrets
import shlex
import subprocess
import time

import httpx


def main():
    parser = argparse.ArgumentParser(description="Verify a built Bifang API image without provider keys")
    parser.add_argument("--image", default="bifang:validation")
    parser.add_argument("--docker-command", default="docker")
    parser.add_argument("--port", type=int, default=18081)
    options = parser.parse_args()
    command = shlex.split(options.docker_command)
    container = "bifang-smoke-" + secrets.token_hex(6)
    env = dict(os.environ)
    env["BIFANG_SERVER_API_KEY"] = secrets.token_urlsafe(32)

    def docker(*args, check=True, private_env=None):
        return subprocess.run([*command, *args], env=private_env, capture_output=True,
                              text=True, check=check, timeout=60)

    missing_key = docker("run", "--rm", options.image, check=False)
    if missing_key.returncode == 0 or "BIFANG_SERVER_API_KEY is required" not in missing_key.stderr:
        raise RuntimeError("Container did not reject non-loopback startup without a key")
    try:
        docker("run", "-d", "--name", container, "-p", f"127.0.0.1:{options.port}:8000",
               "-e", "BIFANG_SERVER_API_KEY", options.image, private_env=env)
        identity = docker("exec", container, "python", "-c",
                          "import json,os; print(json.dumps({'uid':os.getuid(), 'workspace_writable':os.access('/workspace',os.W_OK), 'code_writable':os.access('/app',os.W_OK)}))")
        permissions = json.loads(identity.stdout)
        if permissions["uid"] == 0 or not permissions["workspace_writable"] or permissions["code_writable"]:
            raise RuntimeError("Runtime permissions do not match the non-root deployment policy")
        with httpx.Client(base_url=f"http://127.0.0.1:{options.port}", trust_env=False) as client:
            for attempt in range(100):
                try:
                    if client.get("/health").status_code == 200:
                        break
                except httpx.TransportError:
                    pass
                time.sleep(0.2)
            else:
                raise RuntimeError("Container health check did not become ready")
            payload = {"workspace": ".", "max_steps": 1}
            if client.post("/sessions", json=payload).status_code != 401:
                raise RuntimeError("Unauthenticated session creation was not denied")
            if client.post("/sessions", json=payload, headers={"X-API-Key": "wrong-key"}).status_code != 401:
                raise RuntimeError("Wrong-key session creation was not denied")
            headers = {"X-API-Key": env["BIFANG_SERVER_API_KEY"]}
            if client.post("/sessions", json={"workspace": "/app"}, headers=headers).status_code != 400:
                raise RuntimeError("Absolute workspace selection was not denied")
            if client.post("/sessions", json={"workspace": ".."}, headers=headers).status_code != 403:
                raise RuntimeError("Workspace-root escape was not denied")
            created = client.post("/sessions", json=payload, headers=headers)
            if created.status_code != 200:
                raise RuntimeError("Authenticated session creation failed")
            session = created.json()["session_id"]
            diff = client.get(f"/sessions/{session}/diff", headers=headers)
            if diff.status_code != 200 or diff.json()["diff"]:
                raise RuntimeError("New container workspace diff is not empty")
            if client.delete(f"/sessions/{session}", headers=headers).status_code != 200:
                raise RuntimeError("Authenticated session cleanup failed")
        print(json.dumps({"image": options.image, "runtime": permissions,
                          "missing_startup_key_rejected": True, "health": 200,
                          "missing_and_wrong_request_keys": 401,
                          "absolute_and_escaping_workspaces": "denied",
                          "authenticated_session_lifecycle": "passed",
                          "provider_inference_tested": False}, indent=2))
    finally:
        docker("rm", "-f", container, check=False)


if __name__ == "__main__":
    main()
