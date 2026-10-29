import json
import subprocess
from urllib.parse import parse_qs, urlsplit

import pytest

from bifang.pairing_setup import enroll
from bifang.totp import TotpCredential


def test_private_enrollment_confirms_possession_without_seed_in_arguments(tmp_path, monkeypatch):
    tmp_path.chmod(0o700)
    secret = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"
    monkeypatch.setattr("bifang.pairing_setup.generate_secret", lambda: secret)

    def encode(arguments, **options):
        assert secret not in str(arguments)
        assert arguments == ["fixture-qr", "-t", "SVG", "-o", "-"]
        assert parse_qs(urlsplit(options["input"].decode()).query)["secret"] == [secret]
        return subprocess.CompletedProcess(arguments, 0, b'<svg xmlns="http://www.w3.org/2000/svg"></svg>')

    monkeypatch.setattr("bifang.pairing_setup.subprocess.run", encode)
    target = tmp_path / "new-enrollment"

    def confirm(path):
        assert path.is_file() and path.stat().st_mode & 0o077 == 0
        assert not (target / "pairing.env").exists()
        return TotpCredential(secret).code(100)

    enroll("owner", target, confirm, clock=lambda: 3000.0, encoder="fixture-qr")
    assert target.stat().st_mode & 0o077 == 0
    configuration = target / "pairing.env"
    assert configuration.stat().st_mode & 0o077 == 0
    assert json.loads(configuration.read_text().split("=", 1)[1]) == {"owner": secret}
    with pytest.raises(FileExistsError):
        enroll("owner", target, confirm, encoder="fixture-qr")
    assert configuration.is_file()


def test_failed_confirmation_removes_provisioning_material(tmp_path, monkeypatch):
    tmp_path.chmod(0o700)
    monkeypatch.setattr("bifang.pairing_setup.subprocess.run", lambda *args, **kwargs: subprocess.CompletedProcess(args, 0, b"<svg></svg>"))
    with pytest.raises(ValueError, match="confirmation failed"):
        enroll("owner", tmp_path / "failed", lambda path: "invalid", clock=lambda: 3000, encoder="fixture-qr")
    assert list(tmp_path.iterdir()) == []


def test_enrollment_rejects_shared_parent_and_invalid_subject(tmp_path):
    tmp_path.chmod(0o755)
    with pytest.raises(ValueError, match="owner-only"):
        enroll("owner", tmp_path / "shared", lambda path: "123456", encoder="fixture-qr")
    tmp_path.chmod(0o700)
    with pytest.raises(ValueError, match="operator"):
        enroll("not/a/subject", tmp_path / "bad", lambda path: "123456", encoder="fixture-qr")
    assert list(tmp_path.iterdir()) == []


def test_enrollment_refuses_private_source_repository(tmp_path):
    tmp_path.chmod(0o700)
    (tmp_path / ".git").mkdir()
    with pytest.raises(ValueError, match="repositories"):
        enroll("owner", tmp_path / "enrollment", lambda path: "123456", encoder="fixture-qr")
    assert not (tmp_path / "enrollment").exists()
