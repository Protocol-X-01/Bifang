from __future__ import annotations

import base64
import binascii
import hmac
import math
import re
import secrets
import struct
from urllib.parse import quote, urlencode


def generate_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


class TotpCredential:
    def __init__(self, secret: str, *, digits: int = 6, algorithm: str = "SHA1"):
        if not isinstance(secret, str) or not re.fullmatch(r"[A-Z2-7]{32,104}", secret):
            raise ValueError("Invalid authenticator credential")
        try:
            key = base64.b32decode(secret + "=" * (-len(secret) % 8))
        except (binascii.Error, ValueError):
            raise ValueError("Invalid authenticator credential") from None
        if not 20 <= len(key) <= 64 or base64.b32encode(key).decode().rstrip("=") != secret:
            raise ValueError("Invalid authenticator credential")
        if (type(digits) is not int or digits not in {6, 8} or not isinstance(algorithm, str)
                or algorithm not in {"SHA1", "SHA256", "SHA512"}):
            raise ValueError("Unsupported authenticator parameters")
        self._key = key
        self._secret = secret
        self.digits = digits
        self.algorithm = algorithm

    def code(self, step: int) -> str:
        if type(step) is not int or not 0 <= step < 2**64:
            raise ValueError("Invalid authenticator time step")
        value = hmac.digest(self._key, struct.pack(">Q", step), self.algorithm.lower())
        offset = value[-1] & 15
        truncated = int.from_bytes(value[offset:offset + 4], "big") & 0x7fffffff
        return str(truncated % (10**self.digits)).zfill(self.digits)

    def matching_step(self, code: str, *, now: float, after_step: int) -> int | None:
        if (type(after_step) is not int or not -1 <= after_step < 2**63 or not isinstance(now, (float, int))
                or isinstance(now, bool) or not 0 <= now < (2**63 - 1) * 30 or not math.isfinite(now)):
            raise ValueError("Invalid authenticator verification state")
        if not isinstance(code, str) or not re.fullmatch(r"[0-9]{" + str(self.digits) + "}", code):
            return None
        step = math.floor(now / 30)
        matched = None
        for candidate in range(max(0, step - 1), step + 2):
            equal = hmac.compare_digest(self.code(candidate), code)
            if equal and candidate > after_step:
                matched = candidate
        return matched

    def provisioning_uri(self, account: str) -> str:
        if not isinstance(account, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", account):
            raise ValueError("Invalid authenticator account label")
        return "otpauth://totp/" + quote("Bifang:" + account, safe="") + "?" + urlencode({
            "secret": self._secret, "issuer": "Bifang", "algorithm": self.algorithm,
            "digits": self.digits, "period": 30,
        })
