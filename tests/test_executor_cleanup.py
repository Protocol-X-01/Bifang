import importlib.util
import json
import subprocess
from pathlib import Path

import pytest


def cleaner():
    path = Path(__file__).resolve().parents[1] / "deploy/aws/cleanup-executor.py"
    specification = importlib.util.spec_from_file_location("executor_cleanup_fixture", path)
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module.cleanup


def test_cleanup_removes_only_labelled_owned_containers_and_private_snapshots(tmp_path):
    scratch = tmp_path / "scratch"
    scratch.mkdir(mode=0o700)
    snapshot = scratch / "snapshot-fixture"
    snapshot.mkdir()
    (snapshot / "source.py").write_text("synthetic")
    calls = []

    def runner(arguments, **options):
        calls.append(arguments)
        assert options["env"]["DOCKER_HOST"] == "unix:///var/run/docker.sock"
        if arguments[1] == "ps":
            output = "a" * 64 + "\n"
        elif arguments[1] == "inspect":
            output = json.dumps([{"Name": "/bifang-check-" + "b" * 32, "Config": {"Labels": {"bifang.executor": "1"}}}])
        else:
            assert arguments[1:] == ["rm", "--force", "a" * 64]
            output = ""
        return subprocess.CompletedProcess(arguments, 0, output, "")

    assert cleaner()(scratch, runner) == {"owned_containers_removed": 1, "private_snapshots_removed": 1}
    assert not list(scratch.iterdir()) and calls[-1][1] == "rm"


def test_cleanup_refuses_wrong_namespace_and_unexpected_scratch(tmp_path):
    scratch = tmp_path / "scratch"
    scratch.mkdir(mode=0o700)

    def wrong(arguments, **options):
        if arguments[1] == "ps":
            output = "a" * 64
        elif arguments[1] == "inspect":
            output = json.dumps([{"Name": "/unrelated-service", "Config": {"Labels": {"bifang.executor": "1"}}}])
        else:
            pytest.fail("Must not remove an unrelated container")
        return subprocess.CompletedProcess(arguments, 0, output, "")

    with pytest.raises(ValueError, match="namespace"):
        cleaner()(scratch, wrong)
    (scratch / "unrelated").mkdir()
    with pytest.raises(ValueError, match="scratch"):
        cleaner()(scratch, lambda arguments, **options: subprocess.CompletedProcess(arguments, 0, "", ""))
    assert (scratch / "unrelated").exists()


def test_broker_installer_keeps_ipc_private_and_no_host_credentials():
    path = Path(__file__).resolve().parents[1] / "deploy/aws/install-executor-broker.sh"
    subprocess.run(["bash", "-n", str(path)], capture_output=True, check=True)
    content = path.read_text()
    for required in ("RuntimeDirectoryMode=0750", "RuntimeDirectoryPreserve=yes", "Group=bifang-clients", "ProtectSystem=strict", "ProtectHome=yes",
                     "RestrictAddressFamilies=AF_UNIX", "ExecStopPost=", "InaccessiblePaths=-/run/bifang"):
        assert required in content
    assert "service.env" not in content and "setenforce" not in content


def test_cleanup_never_unlinks_a_regular_file_at_the_socket_path(tmp_path):
    scratch = tmp_path / "scratch"
    scratch.mkdir(mode=0o700)
    unexpected = tmp_path / "check.sock"
    unexpected.write_text("preserve operator data")
    with pytest.raises(ValueError, match="IPC"):
        cleaner()(scratch, lambda arguments, **options: subprocess.CompletedProcess(arguments, 0, "", ""),
                  socket_path=unexpected)
    assert unexpected.read_text() == "preserve operator data"
