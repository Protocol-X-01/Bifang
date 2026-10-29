import hashlib
import json
import os
import platform
import subprocess
import sys
from pathlib import Path

import pytest

PROBE = Path(__file__).resolve().parents[1] / "scripts/check-sidecar-health.py"


@pytest.mark.skipif(not hasattr(os, "killpg"), reason="Unix process-group probe")
def test_probe_exercises_real_http_fixture_and_cleans_up_owned_port(tmp_path):
    binary = tmp_path / "fixture-server"
    binary.write_text(f"#!{sys.executable}\n" + '''import os
from http.server import BaseHTTPRequestHandler,HTTPServer
class Handler(BaseHTTPRequestHandler):
 def do_GET(self):
  assert self.path == "/health"
  self.send_response(200)
  self.end_headers()
  self.wfile.write(b'{"status":"ok","service":"bifang"}')
 def log_message(self,*args):
  pass
HTTPServer(("127.0.0.1",int(os.environ["BIFANG_SERVER_PORT"])),Handler).serve_forever()
''')
    binary.chmod(0o700)
    report = tmp_path / "health.json"
    result = subprocess.run([sys.executable, str(PROBE), str(binary), "--output", str(report)],
                            capture_output=True, text=True, timeout=20, check=True)
    assert "PASS" in result.stdout
    parsed = json.loads(report.read_text())
    assert parsed["api_health"] and parsed["owned_port_closed"] and not parsed["private_configuration_used"]
    assert parsed["scope"] == "Selected sidecar API on the current host, not GUI or clean installation"
    assert parsed["host_system"] == platform.system()
    assert parsed["host_machine"] == platform.machine()
    assert parsed["binary_sha256"] == hashlib.sha256(binary.read_bytes()).hexdigest()


@pytest.mark.skipif(not hasattr(os, "killpg"), reason="Unix process-group probe")
def test_probe_does_not_record_success_when_binary_exits_early(tmp_path):
    binary = tmp_path / "failing-server"
    binary.write_text(f"#!{sys.executable}\nraise SystemExit(2)\n")
    binary.chmod(0o700)
    report = tmp_path / "health.json"
    result = subprocess.run([sys.executable, str(PROBE), str(binary), "--output", str(report)],
                            capture_output=True, text=True, timeout=20, check=False)
    assert result.returncode != 0 and not report.exists()
