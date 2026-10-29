import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from bifang import workbench
from bifang.plugins.catalog import PluginCatalog, plugin_directories
from bifang.workbench import MAX_REQUEST_BYTES, dispatch, serve_once


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    directory = tmp_path / "project"
    directory.mkdir()
    plugins = directory / ".bifang/plugins"
    plugins.mkdir(parents=True)
    (plugins / "fixture.plugin.json").write_text(json.dumps({
        "name": "fixture", "version": "1", "description": "Fixture", "capabilities": ["process"],
    }))
    (plugins / "fixture.py").write_text('raise RuntimeError("must never execute during review")\n')
    return directory


def request(project, action, **extra):
    return {"version": 1, "workspace": str(project), "action": action, **extra}


def test_review_trust_and_disable_share_catalog_without_executing_plugin(project):
    candidate = dispatch(request(project, "plugins.list"))["plugins"][0]
    reviewed = dispatch(request(project, "plugins.review", id=candidate["id"]))
    assert "must never execute" in reviewed["source"]
    assert candidate["sha256"] == reviewed["sha256"]
    assert not candidate["trusted"]
    dispatch(request(project, "plugins.trust", id=candidate["id"], sha256=reviewed["sha256"], confirmed=True))
    catalog = PluginCatalog(plugin_directories(project))
    assert catalog.list()["plugins"][0]["trusted"]
    dispatch(request(project, "plugins.disable", id=candidate["id"]))
    assert not catalog.list()["plugins"][0]["trusted"]


def test_changed_plugin_and_missing_confirmation_cannot_be_trusted(project):
    candidate = dispatch(request(project, "plugins.list"))["plugins"][0]
    for confirmed in (False, 1, "true", None):
        with pytest.raises(ValueError):
            dispatch(request(project, "plugins.trust", id=candidate["id"], sha256=candidate["sha256"], confirmed=confirmed))
    (project / ".bifang/plugins/fixture.py").write_text("changed = True\n")
    with pytest.raises(ValueError):
        dispatch(request(project, "plugins.trust", id=candidate["id"], sha256=candidate["sha256"], confirmed=True))


def test_toolchains_are_read_only(project):
    manifest = project / "package.json"
    manifest.write_text('{"scripts":{"postinstall":"must-not-run"}}')
    before = manifest.read_bytes()
    result = dispatch(request(project, "toolchains.inspect"))
    assert result["profiles"][0]["bootstrap_argv"] == ["npm", "install", "--ignore-scripts"]
    assert manifest.read_bytes() == before
    assert not (project / "node_modules").exists()


@pytest.mark.parametrize("change", [
    {"version": True}, {"version": 2}, {"workspace": "."}, {"workspace": None},
    {"workspace": "/bifang-nonexistent-fixture"}, {"action": "run"}, {"action": []},
    {"command": "whoami"}, {"confirmed": True},
])
def test_protocol_rejects_unexpected_or_malformed_fields(project, change):
    with pytest.raises((ValueError, OSError)):
        dispatch({**request(project, "plugins.list"), **change})


@pytest.mark.parametrize("raw", [b"", b"{}", b"[]\n", b"not json\n", b"\xff\n",
                                    b'{"version":1,"version":1}\n', b'{"version":NaN}\n',
                                    b"x" * MAX_REQUEST_BYTES + b"\n", b"[" * 2000 + b"\n"])
def test_framing_errors_have_one_redacted_response(raw):
    output = io.BytesIO()
    assert serve_once(io.BytesIO(raw), output) == 1
    response = json.loads(output.getvalue())
    assert response["ok"] is False
    assert "Traceback" not in output.getvalue().decode()
    assert len(output.getvalue().splitlines()) == 1


def test_sidecar_dispatch_exits_without_starting_http_or_loading_dotenv(project):
    repository = Path(__file__).resolve().parents[1]
    dotenv_target = project / "dotenv-must-not-be-loaded"
    dotenv = project / ".env"
    dotenv.write_text(f"XDG_STATE_HOME={dotenv_target}\n")
    environment = {key: os.environ[key] for key in ("PATH", "HOME", "XDG_STATE_HOME") if key in os.environ}
    environment.update({"PYTHONPATH": str(repository / "src"), "BIFANG_ENV_FILE": str(dotenv)})
    result = subprocess.run(
        [sys.executable, str(repository / "scripts/bifang-server-entry.py"), "--workbench"],
        input=json.dumps(request(project, "plugins.list")) + "\n", text=True,
        capture_output=True, cwd=project, env=environment, timeout=10, check=False,
    )
    assert result.returncode == 0
    assert result.stderr == ""
    assert len(result.stdout.splitlines()) == 1
    assert json.loads(result.stdout)["ok"] is True
    assert not dotenv_target.exists()
    candidate = json.loads(result.stdout)["result"]["plugins"][0]
    trusted = subprocess.run(
        [sys.executable, str(repository / "scripts/bifang-server-entry.py"), "--workbench"],
        input=json.dumps(request(project, "plugins.trust", id=candidate["id"], sha256=candidate["sha256"], confirmed=True)) + "\n",
        text=True, capture_output=True, cwd=project, env=environment, timeout=10, check=False,
    )
    assert trusted.returncode == 0
    assert not dotenv_target.exists()
    assert (Path(environment["XDG_STATE_HOME"]) / "bifang/plugins/trust.json").is_file()


def test_oversized_response_is_redacted(project, monkeypatch):
    monkeypatch.setattr(workbench, "dispatch", lambda _: {"source": "x" * 2_000_000})
    output = io.BytesIO()
    assert serve_once(io.BytesIO(b"{}\n"), output) == 1
    assert json.loads(output.getvalue())["ok"] is False
    assert len(output.getvalue()) < 200


def test_unknown_sidecar_arguments_do_not_fall_through_to_server(project):
    repository = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, str(repository / "scripts/bifang-server-entry.py"), "--workbench", "unexpected"],
        capture_output=True, text=True, timeout=5, check=False, cwd=project,
    )
    assert result.returncode != 0
    assert not result.stdout
    assert result.stderr.strip() == "Unsupported sidecar arguments"
