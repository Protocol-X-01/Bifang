import importlib.util
import json
from pathlib import Path

import pytest

specification = importlib.util.spec_from_file_location(
    "desktop_rehearsal", Path(__file__).resolve().parents[1] / "scripts/rehearse-desktop.py")
rehearsal = importlib.util.module_from_spec(specification)
specification.loader.exec_module(rehearsal)


@pytest.fixture
def token_file(tmp_path):
    path = tmp_path / "judge.json"
    path.write_text(json.dumps({"judge_token": "synthetic-judge-only-token-" * 3}))
    return path


def test_relay_uses_only_judge_credentials_not_inherited_provider_key(token_file, monkeypatch):
    monkeypatch.setenv("NEBIUS_API_KEY", "synthetic-provider-must-not-transfer")
    environment = rehearsal.provider_environment(None, "https://relay.example/v1/", token_file)
    assert environment["NEBIUS_API_KEY"] == json.loads(token_file.read_text())["judge_token"]
    assert environment["BIFANG_NEBIUS_BASE_URL"] == "https://relay.example/v1"
    assert "synthetic-provider-must-not-transfer" not in str(environment)


@pytest.mark.parametrize("url", ["http://relay.example", "https://user:pass@relay.example",
                                 "https://relay.example?q=1", "https://relay.example/#fragment",
                                 "https://relay.example:8443", "https://relay.example/other"])
def test_relay_rejects_unsafe_or_ambiguous_urls(token_file, url):
    with pytest.raises(ValueError, match="HTTPS relay"):
        rehearsal.provider_environment(None, url, token_file)


def test_relay_requires_separate_token_file_and_refuses_provider_env_file(token_file, tmp_path):
    for arguments in [(None, "https://relay.example", None),
                      (None, None, token_file),
                      (tmp_path / "private.env", "https://relay.example", token_file)]:
        with pytest.raises(ValueError, match="both relay URL"):
            rehearsal.provider_environment(*arguments)


def test_missing_sandbox_never_executes_fixture(tmp_path, monkeypatch):
    monkeypatch.setattr(rehearsal.shutil, "which", lambda name: None)
    monkeypatch.setattr(rehearsal.subprocess, "run", lambda *args, **kwargs: pytest.fail("Executed without sandbox"))
    with pytest.raises(RuntimeError, match="refusing unsandboxed"):
        rehearsal.check_fixture(tmp_path)


def test_fixture_checks_use_readonly_workspace_and_clean_environment(tmp_path, monkeypatch):
    monkeypatch.setattr(rehearsal.shutil, "which", lambda name: "/usr/bin/bwrap")
    calls = []
    monkeypatch.setattr(rehearsal.subprocess, "run", lambda command, **kwargs: calls.append((command, kwargs)))
    rehearsal.check_fixture(tmp_path)
    command, options = calls[0]
    assert command[0] == "bwrap"
    assert "--unshare-all" in command and "--share-net" not in command
    assert "--clearenv" in command
    assert command[command.index(str(tmp_path)) - 1] == "--ro-bind"
    assert options["env"] == {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"}
    assert options["timeout"] == 30
