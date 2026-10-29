from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

from .remote_jobs import journal_mode_for
from .totp import TotpCredential


class PairingError(Exception):
    def __init__(self, code: str, *, interval: int = 5):
        super().__init__(code)
        self.code = code
        self.interval = interval


class PairingStore:
    def __init__(self, directory: Path, credentials: dict[str, TotpCredential], *, clock=time.time):
        if (not isinstance(credentials, dict) or not 1 <= len(credentials) <= 32
                or any(not isinstance(subject, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", subject)
                or not isinstance(value, TotpCredential) for subject, value in credentials.items())):
            raise ValueError("Configure operator authenticator credentials before enabling pairing")
        if directory.is_symlink():
            raise ValueError("Use a private pairing state directory")
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        if directory.stat().st_mode & 0o077:
            raise ValueError("Pairing state directory must be owner-only")
        self.path = directory / "device-pairing.sqlite3"
        descriptor = os.open(self.path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        os.close(descriptor)
        if self.path.stat().st_mode & 0o077:
            raise ValueError("Pairing state database must be owner-only")
        self.credentials = dict(credentials)
        self.clock = clock
        connection = self.connect()
        try:
            connection.execute("PRAGMA journal_mode=" + journal_mode_for(sqlite3.sqlite_version_info))
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS device_pairs (
                    proof_hash TEXT PRIMARY KEY, user_code TEXT UNIQUE NOT NULL,
                    label TEXT NOT NULL, subject TEXT, status TEXT NOT NULL,
                    created REAL NOT NULL, expires REAL NOT NULL,
                    next_poll REAL NOT NULL, interval INTEGER NOT NULL, session_id TEXT);
                CREATE TABLE IF NOT EXISTS device_sessions (
                    id TEXT PRIMARY KEY, token_hash TEXT UNIQUE NOT NULL,
                    subject TEXT NOT NULL, label TEXT NOT NULL,
                    created REAL NOT NULL, expires REAL NOT NULL, revoked INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS authenticator_steps (
                    subject TEXT PRIMARY KEY, last_step INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS pairing_attempts (bucket TEXT NOT NULL, created REAL NOT NULL);
                CREATE INDEX IF NOT EXISTS pairing_attempt_bucket ON pairing_attempts(bucket,created);
                CREATE INDEX IF NOT EXISTS device_session_owner ON device_sessions(subject,expires);
            """)
            columns = {row[1] for row in connection.execute("PRAGMA table_info(device_pairs)")}
            if "session_id" not in columns:
                connection.execute("ALTER TABLE device_pairs ADD COLUMN session_id TEXT")
        finally:
            connection.close()

    def connect(self):
        connection = sqlite3.connect(self.path, isolation_level=None, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA synchronous=FULL")
        return connection

    @contextmanager
    def transaction(self):
        connection = self.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def hash(value: str) -> str:
        return hashlib.sha256(value.encode()).hexdigest()

    @staticmethod
    def limited(connection, bucket, now, maximum):
        connection.execute("DELETE FROM pairing_attempts WHERE created<?", (now - 60,))
        used = connection.execute("SELECT count(*) FROM pairing_attempts WHERE bucket=?", (bucket,)).fetchone()[0]
        if used >= maximum:
            return True
        connection.execute("INSERT INTO pairing_attempts(bucket,created) VALUES(?,?)", (bucket, now))
        return False

    def start(self, bucket: str, label: str) -> dict:
        if not re.fullmatch(r"[a-f0-9]{64}", bucket) or not re.fullmatch(r"[A-Za-z0-9 ._-]{1,64}", label):
            raise PairingError("invalid_request")
        now = self.clock()
        error = None
        with self.transaction() as connection:
            connection.execute("DELETE FROM device_pairs WHERE expires<?", (now - 600,))
            connection.execute("DELETE FROM device_sessions WHERE expires<?", (now,))
            pending = connection.execute("SELECT count(*) FROM device_pairs WHERE expires>? AND status IN ('pending','approved')", (now,)).fetchone()[0]
            if self.limited(connection, "start:" + bucket, now, 6) or pending >= 64:
                error = "slow_down"
            else:
                proof = secrets.token_urlsafe(32)
                code = "".join(secrets.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(8))
                connection.execute("INSERT INTO device_pairs(proof_hash,user_code,label,subject,status,created,expires,next_poll,interval) VALUES(?,?,?,?,?,?,?,?,?)",
                                   (self.hash(proof), code, label, None, "pending", now, now + 300, now, 5))
        if error:
            raise PairingError(error)
        return {"device_code": proof, "user_code": code[:4] + "-" + code[4:], "expires_in": 300, "interval": 5}

    def approve(self, subject: str, user_code: str, authenticator_code: str, *, approved: bool = True) -> dict:
        now = self.clock()
        error = None
        code = user_code.replace("-", "").upper() if isinstance(user_code, str) else ""
        with self.transaction() as connection:
            if self.limited(connection, "approve:" + subject, now, 5):
                error = "slow_down"
            elif subject not in self.credentials or type(approved) is not bool or not re.fullmatch(r"[A-Z2-9]{8}", code):
                error = "access_denied"
            else:
                pair = connection.execute("SELECT * FROM device_pairs WHERE user_code=?", (code,)).fetchone()
                previous = connection.execute("SELECT last_step FROM authenticator_steps WHERE subject=?", (subject,)).fetchone()
                step = self.credentials[subject].matching_step(authenticator_code, now=now, after_step=previous[0] if previous else -1)
                if pair is None or pair["expires"] <= now or pair["status"] != "pending" or step is None:
                    error = "access_denied"
                else:
                    connection.execute("INSERT INTO authenticator_steps VALUES(?,?) ON CONFLICT(subject) DO UPDATE SET last_step=excluded.last_step", (subject, step))
                    connection.execute("UPDATE device_pairs SET subject=?,status=? WHERE proof_hash=?", (subject, "approved" if approved else "denied", pair["proof_hash"]))
        if error:
            raise PairingError(error)
        return {"status": "approved" if approved else "denied"}

    def exchange(self, device_code: str) -> dict:
        if not isinstance(device_code, str) or not re.fullmatch(r"[A-Za-z0-9_-]{43}", device_code):
            raise PairingError("invalid_grant")
        now = self.clock()
        error = None
        interval = 5
        with self.transaction() as connection:
            pair = connection.execute("SELECT * FROM device_pairs WHERE proof_hash=?", (self.hash(device_code),)).fetchone()
            if pair is None or pair["status"] == "consumed":
                error = "invalid_grant"
            elif pair["expires"] <= now:
                error = "expired_token"
            elif pair["status"] == "denied":
                error = "access_denied"
            elif pair["next_poll"] > now:
                interval = min(30, pair["interval"] + 5)
                connection.execute("UPDATE device_pairs SET interval=?,next_poll=? WHERE proof_hash=?", (interval, now + interval, pair["proof_hash"]))
                error = "slow_down"
            elif pair["status"] == "pending":
                interval = pair["interval"]
                connection.execute("UPDATE device_pairs SET next_poll=? WHERE proof_hash=?", (now + interval, pair["proof_hash"]))
                error = "authorization_pending"
            elif connection.execute("SELECT count(*) FROM device_sessions WHERE subject=? AND revoked=0 AND expires>?", (pair["subject"], now)).fetchone()[0] >= 32:
                error = "access_denied"
            else:
                token = secrets.token_urlsafe(32)
                identity = secrets.token_hex(16)
                connection.execute("INSERT INTO device_sessions VALUES(?,?,?,?,?,?,0)",
                                   (identity, self.hash(token), pair["subject"], pair["label"], now, now + 3600))
                connection.execute("UPDATE device_pairs SET status='consumed',session_id=? WHERE proof_hash=?", (identity, pair["proof_hash"]))
        if error:
            raise PairingError(error, interval=interval)
        return {"access_token": token, "token_type": "Bearer", "expires_in": 3600}

    def subject(self, authorization: str) -> str | None:
        scheme, separator, token = authorization.partition(" ")
        if not separator or scheme.lower() != "bearer" or not re.fullmatch(r"[A-Za-z0-9_-]{43}", token):
            return None
        connection = self.connect()
        try:
            row = connection.execute("SELECT subject FROM device_sessions WHERE token_hash=? AND revoked=0 AND expires>?", (self.hash(token), self.clock())).fetchone()
            return row["subject"] if row and row["subject"] in self.credentials else None
        finally:
            connection.close()

    def cancel(self, device_code: str) -> dict:
        if not isinstance(device_code, str) or not re.fullmatch(r"[A-Za-z0-9_-]{43}", device_code):
            raise PairingError("invalid_grant")
        with self.transaction() as connection:
            pair = connection.execute("SELECT session_id FROM device_pairs WHERE proof_hash=?", (self.hash(device_code),)).fetchone()
            if pair is None:
                raise PairingError("invalid_grant")
            if pair["session_id"]:
                connection.execute("UPDATE device_sessions SET revoked=1 WHERE id=?", (pair["session_id"],))
            connection.execute("UPDATE device_pairs SET status='denied' WHERE proof_hash=?", (self.hash(device_code),))
        return {"cancelled": True}

    def logout(self, subject: str, authorization: str) -> dict:
        scheme, separator, token = authorization.partition(" ")
        if not separator or scheme.lower() != "bearer" or not re.fullmatch(r"[A-Za-z0-9_-]{43}", token):
            raise PairingError("invalid_grant")
        with self.transaction() as connection:
            connection.execute("UPDATE device_sessions SET revoked=1 WHERE subject=? AND token_hash=?", (subject, self.hash(token)))
        return {"revoked": True}

    def sessions(self, subject: str) -> list[dict]:
        connection = self.connect()
        try:
            return [dict(row) for row in connection.execute("SELECT id,label,created,expires,revoked FROM device_sessions WHERE subject=? AND expires>? ORDER BY created DESC LIMIT 64", (subject, self.clock()))]
        finally:
            connection.close()

    def revoke(self, subject: str, identity: str) -> bool:
        if not re.fullmatch(r"[a-f0-9]{32}", identity):
            return False
        with self.transaction() as connection:
            return connection.execute("UPDATE device_sessions SET revoked=1 WHERE subject=? AND id=?", (subject, identity)).rowcount == 1


def configured_pairing(directory: Path, encoded: str, operator_subjects: set[str]) -> PairingStore | None:
    if not encoded.strip():
        return None
    try:
        if len(encoded) > 8192:
            raise ValueError("Registry exceeds bounds")
        records = json.loads(encoded)
        if not isinstance(records, dict) or len(records) > 32 or not set(records) <= operator_subjects:
            raise ValueError("Invalid operator subjects")
        if not records:
            return None
        credentials = {subject: TotpCredential(value) for subject, value in records.items()}
    except (ValueError, TypeError):
        raise ValueError("Invalid private authenticator registry; details withheld") from None
    return PairingStore(directory, credentials)
