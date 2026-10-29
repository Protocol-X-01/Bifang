import base64

import pytest

from bifang.pairing_backup import snapshot
from bifang.remote_pairing import PairingError, PairingStore
from bifang.totp import TotpCredential


def test_recovery_invalidates_devices_and_fences_current_authenticator_codes(tmp_path):
    now = [3000.0]
    credential = TotpCredential(base64.b32encode(b"12345678901234567890").decode())
    store = PairingStore(tmp_path / "live", {"owner": credential}, clock=lambda: now[0])
    pair = store.start("a" * 64, "Phone")
    store.approve("owner", pair["user_code"], credential.code(100))
    issued = store.exchange(pair["device_code"])
    pending = store.start("b" * 64, "Pending")
    backups = tmp_path / "backups"
    backups.mkdir(mode=0o700)
    backup = backups / "pairing.sqlite3"
    snapshot(store.path, backup, clock=lambda: now[0])
    assert backup.stat().st_mode & 0o077 == 0
    assert store.subject("Bearer " + issued["access_token"]) == "owner"
    restored = tmp_path / "restored"
    restored.mkdir(mode=0o700)
    now[0] = 6000.0
    snapshot(backup, restored / "device-pairing.sqlite3", clock=lambda: now[0])
    recovered = PairingStore(restored, {"owner": credential}, clock=lambda: now[0])
    assert recovered.subject("Bearer " + issued["access_token"]) is None
    with pytest.raises(PairingError, match="invalid_grant"):
        recovered.exchange(pending["device_code"])
    fresh = recovered.start("c" * 64, "Fresh")
    with pytest.raises(PairingError, match="access_denied"):
        recovered.approve("owner", fresh["user_code"], credential.code(200))
    now[0] += 60
    assert recovered.approve("owner", fresh["user_code"], credential.code(202)) == {"status": "approved"}


def test_pairing_backup_refuses_shared_paths_overwrite_and_links(tmp_path):
    credential = TotpCredential(base64.b32encode(b"12345678901234567890").decode())
    store = PairingStore(tmp_path / "live", {"owner": credential})
    directory = tmp_path / "backups"
    directory.mkdir(mode=0o700)
    destination = directory / "snapshot"
    snapshot(store.path, destination)
    with pytest.raises(FileExistsError):
        snapshot(store.path, destination)
    linked = directory / "link"
    linked.symlink_to(directory / "absent")
    with pytest.raises(FileExistsError):
        snapshot(store.path, linked)
    directory.chmod(0o755)
    with pytest.raises(ValueError):
        snapshot(store.path, directory / "shared")
    assert not (directory / "shared").exists()
