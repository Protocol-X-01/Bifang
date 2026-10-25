import argparse
import asyncio
import hashlib
import importlib.util
import json
import os
import tempfile
from pathlib import Path


async def verify(options):
    if os.geteuid() != 0:
        raise RuntimeError("Use the isolated host's operator account")
    specification = importlib.util.spec_from_file_location("bifang_executor_proof", options.module)
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    configuration = json.loads(Path(options.configuration).read_text())
    executor = module.Executor(**configuration)
    await executor.verify_runtime()
    assert not await executor.control("ps", "--all", "--quiet", "--filter", "label=bifang.executor=1")
    baseline = "def valid(index, items):\n    return 0 <= index <= len(items)\n"
    corrected = "def valid(index, items):\n    return 0 <= index < len(items)\n"
    tests = """import unittest
from bounds import valid
class BoundaryTests(unittest.TestCase):
    def test_boundary(self):
        self.assertFalse(valid(1, [0]))
        self.assertFalse(valid(-1, [0]))
        self.assertTrue(valid(0, [0]))
"""
    command = ["python", "-B", "-m", "unittest", "discover", "-v"]
    before = await executor.run({"files": {"bounds.py": baseline, "test_bounds.py": tests}, "command": command, "timeout": 30})
    assert before["exit_code"] == 1 and not before["timed_out"]
    after = await executor.run({"files": {"bounds.py": corrected, "test_bounds.py": tests}, "command": command, "timeout": 30})
    assert after["exit_code"] == 0 and not after["timed_out"]
    probe = """import os, socket
from pathlib import Path
assert os.getuid() == 10001
assert not any(name.startswith(('AWS_', 'NEBIUS_', 'NVIDIA_', 'LANGSMITH_', 'TAVILY_')) for name in os.environ)
for name in ('/var/lib/bifang/review-jobs.sqlite3', '/run/bifang/service.env', '/var/run/docker.sock', '/opt/bifang/gvisor/executor-config.json'):
    assert not Path(name).exists(), name
try:
    Path('/workspace/probe.py').write_text('must not modify source')
except OSError:
    pass
else:
    raise AssertionError('Source snapshot is writable')
for address in ('1.1.1.1', '169.254.169.254'):
    try:
        connection = socket.create_connection((address, 80), timeout=0.5)
    except OSError:
        pass
    else:
        connection.close()
        raise AssertionError('Outbound network unexpectedly available')
print('selected-boundaries-passed')
"""
    boundary = await executor.run({"files": {"probe.py": probe}, "command": ["python", "-B", "probe.py"], "timeout": 30})
    assert boundary["exit_code"] == 0 and boundary["output_sha256"] == hashlib.sha256(b"selected-boundaries-passed\n").hexdigest()
    timed = await executor.run({"files": {"hang.py": "import time\ntime.sleep(30)\n"},
                                "command": ["python", "-B", "hang.py"], "timeout": 1})
    assert timed["timed_out"] and timed["exit_code"] == 124
    flooded = await executor.run({"files": {"flood.py": "import sys\nsys.stdout.write('x' * 200000)\nsys.stdout.flush()\n"},
                                  "command": ["python", "-B", "flood.py"], "timeout": 30})
    assert flooded["exit_code"] == 125 and not flooded["timed_out"]
    missing = module.Executor(**{**configuration, "runtime_binary": "/opt/bifang/gvisor/not-installed/runsc"})
    try:
        await missing.run({"files": {"empty.py": "pass\n"}, "command": ["python", "empty.py"], "timeout": 1})
    except OSError:
        pass
    else:
        raise AssertionError("Missing runtime did not fail closed")
    with tempfile.TemporaryDirectory(prefix="bifang-broker-proof-") as directory:
        path = Path(directory) / "broker.sock"
        broker = module.Broker(executor)
        server = await asyncio.start_unix_server(broker.handle, path=str(path), limit=module.MAX_BODY + 1)
        async with server:
            client = module.BrokerClient(path)
            through_socket = await client({"ok.py": "print('unix-transport-passed')\n"}, ["python", "-B", "ok.py"], 30)
            assert through_socket["exit_code"] == 0
            assert through_socket["output_sha256"] == hashlib.sha256(b"unix-transport-passed\n").hexdigest()
            task = asyncio.create_task(client({"hang.py": "import time\ntime.sleep(60)\n"}, ["python", "-B", "hang.py"], 60))
            for attempt in range(60):
                if await executor.control("ps", "--quiet", "--filter", "label=bifang.executor=1"):
                    break
                if task.done():
                    await task
                    raise AssertionError("Check exited before cancellation fixture")
                await asyncio.sleep(0.2)
            else:
                raise AssertionError("No running check observed for cancellation")
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            for attempt in range(60):
                if not await executor.control("ps", "--all", "--quiet", "--filter", "label=bifang.executor=1"):
                    break
                await asyncio.sleep(0.2)
            else:
                raise AssertionError("Cancelled execution container still exists")
    for attempt in range(20):
        if not list(executor.scratch.iterdir()):
            break
        await asyncio.sleep(0.1)
    assert not list(executor.scratch.iterdir())
    result = {"scope": "Actual gVisor checks on the isolated AWS host, original synthetic source only",
              "executor_module_sha256": hashlib.sha256(Path(options.module).read_bytes()).hexdigest(),
              "execution_image": configuration["image"], "runtime_binary_sha256": configuration["runtime_sha256"],
              "runtime": module.RUNTIME, "failing_baseline": before, "passing_candidate": after,
              "independent_tests_sha256": hashlib.sha256(tests.encode()).hexdigest(),
              "selected_uid_environment_mount_write_and_network_boundaries_passed": True,
              "timeout_destroyed_container": True, "output_flood_rejected": True,
              "missing_runtime_failed_closed": True, "actual_unix_transport": True,
              "disconnect_cancel_destroyed_running_container": True, "private_scratch_empty": True,
              "provider_calls": 0, "public_coding_enabled": False}
    output = Path(options.output)
    output.write_text(json.dumps(result, indent=2) + "\n")
    output.chmod(0o600)
    print(json.dumps(result))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Actual isolated executor proof; no inference or private source")
    parser.add_argument("--module", required=True)
    parser.add_argument("--configuration", required=True)
    parser.add_argument("--output", required=True)
    asyncio.run(verify(parser.parse_args()))
