import base64
import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from bifang.remote_pairing import PairingError, PairingStore, configured_pairing
from bifang.totp import TotpCredential


@pytest.fixture
def fixture(tmp_path):
    clock = [3000.0]
    credential = TotpCredential(base64.b32encode(b"12345678901234567890").decode())
    store = PairingStore(tmp_path / "private", {"owner": credential, "other": credential}, clock=lambda: clock[0])
    return store, credential, clock


def approve(store, credential, clock, pair, subject="owner"):
    return store.approve(subject, pair["user_code"], credential.code(int(clock[0] // 30)))


def test_pair_requires_operator_authenticator_before_one_time_exchange(fixture):
    store, credential, clock = fixture
    pair = store.start("a" * 64, "Owner phone")
    with pytest.raises(PairingError, match="authorization_pending"):
        store.exchange(pair["device_code"])
    assert approve(store, credential, clock, pair) == {"status": "approved"}
    clock[0] += 5
    issued = store.exchange(pair["device_code"])
    assert issued["expires_in"] == 3600
    assert store.subject("Bearer " + issued["access_token"]) == "owner"
    with pytest.raises(PairingError, match="invalid_grant"):
        store.exchange(pair["device_code"])
    assert store.subject("Bearer " + pair["device_code"]) is None


def test_state_is_private_and_contains_hashes_not_device_session_or_totp_secrets(fixture):
    store, credential, clock = fixture
    pair = store.start("a" * 64, "Phone")
    approve(store, credential, clock, pair)
    token = store.exchange(pair["device_code"])["access_token"]
    assert store.path.stat().st_mode & 0o077 == 0
    assert store.path.parent.stat().st_mode & 0o077 == 0
    for path in store.path.parent.iterdir():
        if path.is_file():
            content = path.read_bytes()
            assert pair["device_code"].encode() not in content
            assert token.encode() not in content
            assert credential.provisioning_uri("owner").encode() not in content


def test_authenticator_replay_fence_survives_restart_and_is_atomic(fixture):
    store, credential, clock = fixture
    pairs = [store.start("a" * 64, "Phone") for _ in range(2)]
    def attempt(pair):
        try:
            approve(store, credential, clock, pair)
            return True
        except PairingError:
            return False
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sum(pool.map(attempt, pairs)) == 1
    restarted = PairingStore(store.path.parent, store.credentials, clock=lambda: clock[0])
    pending = restarted.start("b" * 64, "Second phone")
    with pytest.raises(PairingError, match="access_denied"):
        approve(restarted, credential, clock, pending)


def test_session_issuance_is_atomic_and_revocation_is_owner_scoped(fixture):
    store, credential, clock = fixture
    pair = store.start("a" * 64, "Phone")
    approve(store, credential, clock, pair)
    def exchange():
        try:
            return store.exchange(pair["device_code"])["access_token"]
        except PairingError:
            return None
    with ThreadPoolExecutor(max_workers=4) as pool:
        tokens = [item for item in pool.map(lambda _: exchange(), range(4)) if item]
    assert len(tokens) == 1
    assert store.sessions("other") == []
    sessions = store.sessions("owner")
    assert len(sessions) == 1 and "token_hash" not in json.dumps(sessions)
    assert not store.revoke("other", sessions[0]["id"])
    assert store.revoke("owner", sessions[0]["id"])
    assert store.subject("Bearer " + tokens[0]) is None


def test_failed_approvals_and_start_requests_are_persistently_rate_limited(fixture):
    store, credential, clock = fixture
    pair = store.start("a" * 64, "Phone")
    for _ in range(5):
        with pytest.raises(PairingError, match="access_denied"):
            store.approve("owner", pair["user_code"], "invalid")
    with pytest.raises(PairingError, match="slow_down"):
        approve(store, credential, clock, pair)
    for _ in range(5):
        store.start("a" * 64, "Phone")
    restarted = PairingStore(store.path.parent, store.credentials, clock=lambda: clock[0])
    with pytest.raises(PairingError, match="slow_down"):
        restarted.start("a" * 64, "Phone")
    clock[0] += 61
    assert restarted.start("a" * 64, "Phone")


def test_polling_slowdown_expiry_and_explicit_denial_fail_closed(fixture):
    store, credential, clock = fixture
    pair = store.start("a" * 64, "Phone")
    with pytest.raises(PairingError, match="authorization_pending"):
        store.exchange(pair["device_code"])
    with pytest.raises(PairingError, match="slow_down") as caught:
        store.exchange(pair["device_code"])
    assert caught.value.interval == 10
    clock[0] += 301
    with pytest.raises(PairingError, match="expired_token"):
        store.exchange(pair["device_code"])
    with pytest.raises(PairingError, match="access_denied"):
        approve(store, credential, clock, pair)
    denied = store.start("b" * 64, "Phone")
    store.approve("owner", denied["user_code"], credential.code(int(clock[0] // 30)), approved=False)
    with pytest.raises(PairingError, match="access_denied"):
        store.exchange(denied["device_code"])


def test_device_session_expires_and_cannot_authenticate_after_owner_removal(fixture):
    store, credential, clock = fixture
    pair = store.start("a" * 64, "Phone")
    approve(store, credential, clock, pair)
    token = store.exchange(pair["device_code"])["access_token"]
    removed = PairingStore(store.path.parent, {"other": credential}, clock=lambda: clock[0])
    assert removed.subject("Bearer " + token) is None
    clock[0] += 3600
    assert store.subject("Bearer " + token) is None


def test_pairing_refuses_missing_authenticators_and_public_state_permissions(tmp_path):
    with pytest.raises(ValueError):
        PairingStore(tmp_path / "missing", {})
    public = tmp_path / "public"
    public.mkdir(mode=0o755)
    public.chmod(0o755)
    with pytest.raises(ValueError, match="owner-only"):
        PairingStore(public, {"owner": TotpCredential(base64.b32encode(b"12345678901234567890").decode())})


@pytest.mark.parametrize("encoded", ["", "  ", "{}"])
def test_empty_private_authenticator_registry_keeps_pairing_disabled(tmp_path, encoded):
    assert configured_pairing(tmp_path / "private", encoded, {"owner"}) is None
    assert not (tmp_path / "private").exists()


@pytest.mark.parametrize("encoded", ['[]', '{"unknown":"invalid"}', '{"owner":"synthetic-sensitive-value"}', 'not-json', 'x' * 8193])
def test_invalid_private_authenticator_registry_is_not_echoed_or_persisted(tmp_path, encoded):
    with pytest.raises(ValueError, match="details withheld") as caught:
        configured_pairing(tmp_path / "private", encoded, {"owner"})
    assert "synthetic-sensitive-value" not in str(caught.value)
    assert not (tmp_path / "private").exists()


def test_private_authenticator_configuration_binds_only_existing_operator_subjects(tmp_path):
    secret = base64.b32encode(b"12345678901234567890").decode()
    store = configured_pairing(tmp_path / "private", json.dumps({"owner": secret}), {"owner"})
    assert set(store.credentials) == {"owner"}


def test_cancellation_revokes_even_after_exchange_response_was_lost(fixture):
    store, credential, clock = fixture
    pair = store.start("a" * 64, "Phone")
    approve(store, credential, clock, pair)
    token = store.exchange(pair["device_code"])["access_token"]
    assert store.cancel(pair["device_code"]) == {"cancelled": True}
    assert store.subject("Bearer " + token) is None
    with pytest.raises(PairingError, match="access_denied"):
        store.exchange(pair["device_code"])


def test_logout_cannot_revoke_another_owners_session(fixture):
    store, credential, clock = fixture
    pair = store.start("a" * 64, "Phone")
    approve(store, credential, clock, pair)
    token = store.exchange(pair["device_code"])["access_token"]
    store.logout("other", "Bearer " + token)
    assert store.subject("Bearer " + token) == "owner"
    store.logout("owner", "Bearer " + token)
    assert store.subject("Bearer " + token) is None
