import importlib.util
import json
import subprocess
from pathlib import Path

import pytest


def fetcher():
    path = Path(__file__).resolve().parents[1] / "deploy/aws/fetch-runtime-env.py"
    specification = importlib.util.spec_from_file_location("runtime_fetch_fixture", path)
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module.fetch_environment


def runner(values, failures=None):
    def invoke(arguments, **options):
        assert "--with-decryption" in arguments and options["capture_output"]
        name = arguments[arguments.index("--name") + 1].rsplit("/", 1)[1]
        if name in (failures or {}):
            return subprocess.CompletedProcess(arguments, 1, "", failures[name])
        if name not in values:
            return subprocess.CompletedProcess(arguments, 1, "", "An error occurred (ParameterNotFound)")
        return subprocess.CompletedProcess(arguments, 0, json.dumps({"Parameter": {"Value": values[name]}}), "")
    return invoke


def test_runtime_fetch_is_private_and_does_not_print_values(tmp_path, capsys):
    directory = tmp_path / "runtime"
    directory.mkdir(mode=0o700)
    destination = directory / "service.env"
    values = {"nebius_api_key": "synthetic-credential-do-not-print", "client_registry": "[]"}
    assert fetcher()(destination, runner(values)) == 1
    assert destination.stat().st_mode & 0o077 == 0
    assert "NEBIUS_API_KEY=synthetic-credential-do-not-print\n" in destination.read_text()
    assert capsys.readouterr().out == ""
    assert list(directory.iterdir()) == [destination]


def test_runtime_failure_preserves_existing_file_without_echo(tmp_path):
    directory = tmp_path / "runtime"
    directory.mkdir(mode=0o700)
    destination = directory / "service.env"
    destination.write_text("preserve existing configuration")
    with pytest.raises(RuntimeError, match="Runtime parameter unavailable") as error:
        fetcher()(destination, runner({}, {"nebius_api_key": "(AccessDeniedException) private-message"}))
    assert "private-message" not in str(error.value)
    assert destination.read_text() == "preserve existing configuration"


def test_optional_provider_access_failure_is_not_silently_ignored(tmp_path):
    directory = tmp_path / "runtime"
    directory.mkdir(mode=0o700)
    values = {"nebius_api_key": "synthetic-credential", "client_registry": "[]"}
    with pytest.raises(RuntimeError):
        fetcher()(directory / "service.env", runner(values, {"nvidia_api_key": "(AccessDeniedException)"}))
    assert list(directory.iterdir()) == []


@pytest.mark.parametrize("value", ["", "first\nsecond", "first\rsecond", "first\x00second"])
def test_invalid_secret_values_never_create_a_runtime_file(tmp_path, value):
    directory = tmp_path / "runtime"
    directory.mkdir(mode=0o700)
    with pytest.raises(ValueError):
        fetcher()(directory / "service.env", runner({"nebius_api_key": value, "client_registry": "[]"}))
    assert list(directory.iterdir()) == []


def test_install_script_is_valid_and_keeps_service_private():
    path = Path(__file__).resolve().parents[1] / "deploy/aws/install-service.sh"
    subprocess.run(["bash", "-n", str(path)], check=True, capture_output=True)
    content = path.read_text()
    for required in ("127.0.0.1:8125:8125", "--read-only", "--cap-drop ALL", "no-new-privileges",
                     "RequiresMountsFor=/var/lib/bifang-state/jobs", "bifang-wait-service-ready.py"):
        assert required in content
    assert "--privileged" not in content and "--network host" not in content
