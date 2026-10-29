import json
import os
import queue
import subprocess
import sys
import threading
from contextlib import contextmanager
from pathlib import Path

import httpx


@contextmanager
def desktop_instance():
    environment = dict(os.environ, BIFANG_NO_DOTENV="1", BIFANG_DESKTOP_BOOTSTRAP="1")
    binary = os.environ.get("BIFANG_TEST_SIDECAR")
    command = [binary] if binary else [sys.executable, "-c", "from bifang.server import main; main()"]
    process = subprocess.Popen(
        command,
        env=environment, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
    )
    try:
        lines = queue.Queue(maxsize=1)
        reader = threading.Thread(target=lambda: lines.put(process.stdout.readline(2049)), daemon=True)
        reader.start()
        line = lines.get(timeout=30)
        assert line.startswith(b"BIFANG_DESKTOP_READY "), "Missing desktop readiness"
        connection = json.loads(line.removeprefix(b"BIFANG_DESKTOP_READY "))
        assert connection["version"] == 1
        assert connection["origin"].startswith("http://127.0.0.1:")
        yield connection
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        process.stdout.close()


def test_independent_instances_require_their_own_keys():
    with desktop_instance() as first, desktop_instance() as second:
        assert first["origin"] != second["origin"]
        assert first["api_key"] != second["api_key"]
        for connection, other in [(first, second), (second, first)]:
            with httpx.Client(base_url=connection["origin"], trust_env=False) as client:
                assert client.get("/health").status_code == 200
                assert client.get("/sessions").status_code == 401
                assert client.get("/sessions", headers={"X-API-Key": other["api_key"]}).status_code == 401
                response = client.get("/sessions/missing", headers={"X-API-Key": connection["api_key"]})
                assert response.status_code == 404
                assert response.json() == {"detail": "Session not found"}
                preflight = client.options("/sessions", headers={
                    "Origin": "tauri://localhost", "Access-Control-Request-Method": "POST",
                    "Access-Control-Request-Headers": "X-API-Key,Content-Type",
                })
                assert preflight.status_code == 200
                assert preflight.headers["access-control-allow-origin"] == "tauri://localhost"
                rejected = client.options("/sessions", headers={
                    "Origin": "https://untrusted.example", "Access-Control-Request-Method": "POST",
                })
                assert rejected.status_code == 400
                assert "access-control-allow-origin" not in rejected.headers


def test_desktop_fresh_project_reviewed_apply(tmp_path, monkeypatch):
    source = tmp_path / "project"
    source.mkdir()
    state = tmp_path / "state"
    monkeypatch.setenv("BIFANG_WORKSPACE_ROOT", str(source))
    monkeypatch.setenv("XDG_STATE_HOME", str(state))
    monkeypatch.setenv("BIFANG_WORKTREE", "1")
    monkeypatch.setenv("BIFANG_ENABLE_MEMORY", "0")
    monkeypatch.setenv("BIFANG_ENABLE_CONVERSATION_HISTORY", "0")
    monkeypatch.setenv("BIFANG_ENABLE_TRACING", "0")
    monkeypatch.setenv("NEBIUS_API_KEY", "synthetic-no-inference-fixture")
    monkeypatch.setenv("BIFANG_DEFAULT_PROVIDER", "nebius")
    monkeypatch.setenv("BIFANG_ROUTING_MODE", "pinned")
    with desktop_instance() as connection, httpx.Client(
        base_url=connection["origin"], trust_env=False, timeout=15,
        headers={"X-API-Key": connection["api_key"]},
    ) as client:
        created = client.post("/sessions", json={"workspace": "."})
        assert created.status_code == 200, created.text
        session = created.json()
        draft = Path(session["workspace"])
        assert draft != source and draft.is_relative_to(state / "bifang" / "boxes")
        route = f"/sessions/{session['session_id']}"
        try:
            (draft / "hello.py").write_text("value = 42\n")
            reviewed = client.get(route + "/diff").json()
            assert "+value = 42" in reviewed["diff"]
            assert not (source / "hello.py").exists()
            assert client.post(route + "/apply").status_code == 422
            (draft / "hello.py").write_text("value = 43\n")
            assert client.post(route + "/apply", json={"patch_sha256": reviewed["patch_sha256"]}).status_code == 409
            assert not (source / "hello.py").exists()
            reviewed = client.get(route + "/diff").json()
            applied = client.post(route + "/apply", json={"patch_sha256": reviewed["patch_sha256"]})
            assert applied.status_code == 200 and applied.json()["applied"]
            assert (source / "hello.py").read_text() == "value = 43\n"
            assert not (source / ".git").exists()
        finally:
            assert client.delete(route).status_code == 200
        assert not draft.exists()
