import base64
from urllib.parse import parse_qs, urlsplit

import pytest

from bifang.totp import TotpCredential, generate_secret


@pytest.mark.parametrize(("timestamp", "sha1", "sha256", "sha512"), [
    (59, "94287082", "46119246", "90693936"),
    (1111111109, "07081804", "68084774", "25091201"),
    (1111111111, "14050471", "67062674", "99943326"),
    (1234567890, "89005924", "91819424", "93441116"),
    (2000000000, "69279037", "90698825", "38618901"),
    (20000000000, "65353130", "77737706", "47863826"),
])
def test_rfc6238_vectors_for_all_three_algorithms(timestamp, sha1, sha256, sha512):
    for algorithm, length, expected in (("SHA1", 20, sha1), ("SHA256", 32, sha256), ("SHA512", 64, sha512)):
        material = (b"1234567890" * 7)[:length]
        secret = base64.b32encode(material).decode().rstrip("=")
        credential = TotpCredential(secret, digits=8, algorithm=algorithm)
        assert credential.code(timestamp // 30) == expected


def test_verifier_requires_fresh_counter_and_only_allows_one_step_clock_skew():
    credential = TotpCredential(base64.b32encode(b"12345678901234567890").decode())
    code = credential.code(100)
    assert credential.matching_step(code, now=3000, after_step=-1) == 100
    assert credential.matching_step(code, now=3030, after_step=99) == 100
    assert credential.matching_step(code, now=3030, after_step=100) is None
    assert credential.matching_step(code, now=3060, after_step=-1) is None


@pytest.mark.parametrize("code", ["", "12345", "1234567", "１２３４５６", " 123456", 123456, None])
def test_verifier_does_not_coerce_malformed_codes(code):
    credential = TotpCredential(generate_secret())
    assert credential.matching_step(code, now=3000, after_step=-1) is None


@pytest.mark.parametrize("secret", ["", "A" * 31, "a" * 32, "A" * 33, "A" * 105, "A" * 31 + "0", None])
def test_credentials_reject_weak_noncanonical_and_invalid_base32_without_echo(secret):
    with pytest.raises(ValueError, match="Invalid authenticator credential"):
        TotpCredential(secret)


@pytest.mark.parametrize("now", [float("nan"), float("inf"), -1, True, "3000", 10**1000])
def test_invalid_verification_time_fails_closed(now):
    with pytest.raises(ValueError, match="Invalid authenticator verification state"):
        TotpCredential(generate_secret()).matching_step("123456", now=now, after_step=-1)


def test_default_authenticator_provisioning_uri_is_explicit_and_encoded():
    secret = generate_secret()
    credential = TotpCredential(secret)
    parsed = urlsplit(credential.provisioning_uri("owner"))
    assert parsed.scheme == "otpauth" and parsed.netloc == "totp"
    assert parsed.path == "/Bifang%3Aowner"
    assert parse_qs(parsed.query) == {"secret": [secret], "issuer": ["Bifang"], "algorithm": ["SHA1"], "digits": ["6"], "period": ["30"]}
    with pytest.raises(ValueError):
        credential.provisioning_uri("owner?redirect=elsewhere")
