import subprocess
from pathlib import Path

import pytest

DIRECTORY = Path(__file__).resolve().parents[1] / "deploy/aws"


@pytest.mark.parametrize("name", ["prepare-https.sh", "enable-https.sh", "renew-https.sh", "normalize-https-headers.sh"])
def test_https_scripts_parse_and_never_mount_runtime_keys(name):
    path = DIRECTORY / name
    subprocess.run(["bash", "-n", str(path)], check=True, capture_output=True)
    content = path.read_text()
    assert "service.env" not in content
    assert "--privileged" not in content
    assert "docker.sock" not in content
    if name != "normalize-https-headers.sh":
        assert "mountpoint -q /var/lib/bifang-state" in content


def test_plain_http_serves_only_challenges():
    content = (DIRECTORY / "prepare-https.sh").read_text()
    assert "location / { return 404; }" in content
    assert "limit_except GET { deny all; }" in content
    assert "proxy_pass" not in content
    assert "access_log off;" in content


def test_https_requires_verified_ip_certificates_and_automated_renewal():
    content = (DIRECTORY / "enable-https.sh").read_text()
    assert "for environment in staging production" in content
    assert "--preferred-profile shortlived" in content
    assert "--ip-address" in content
    assert "TLSv1.2 TLSv1.3" in content
    assert "proxy_pass http://127.0.0.1:8125" in content
    assert "proxy_hide_header Cache-Control;" in content
    assert "proxy_hide_header X-Content-Type-Options;" in content
    assert "OnCalendar=*-*-* 00,12:00:00" in content
    assert "Persistent=true" in content
    assert "bifang-renew-https.sh --dry-run" in content
    assert "--insecure" not in content
    renewal = (DIRECTORY / "renew-https.sh").read_text()
    assert "--no-random-sleep-on-renew" in renewal
