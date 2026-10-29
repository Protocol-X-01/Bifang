from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import time
import uuid
from contextlib import closing
from pathlib import Path, PurePosixPath

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .secret_patterns import SECRET_PATTERN


class ReviewFile(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    path: str = Field(min_length=1, max_length=200)
    content: str = Field(max_length=64000)

    @field_validator("path")
    @classmethod
    def safe_path(cls, value):
        path = PurePosixPath(value)
        if (not path.name or path.is_absolute() or path.as_posix() != value or "\\" in value or ":" in value
                or any(part in {"..", ".git", "node_modules"} or part.startswith(".env") for part in path.parts)
                or path.suffix.lower() in {".pem", ".key", ".p12", ".pfx"}
                or any(ord(character) < 32 for character in value)):
            raise ValueError("Select ordinary relative source paths")
        return value


class RemoteReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    provider: str = Field(pattern=r"^(nebius|nvidia)$")
    model: str = Field(min_length=1, max_length=256)
    question: str = Field(min_length=1, max_length=4000)
    files: list[ReviewFile] = Field(min_length=1, max_length=8)
    sharing_confirmed: bool = False

    @model_validator(mode="after")
    def bounded_source(self):
        if not self.model.strip() or not self.question.strip():
            raise ValueError("Choose a model and review question")
        if len({entry.path for entry in self.files}) != len(self.files):
            raise ValueError("Duplicate source path")
        encoded = json.dumps(self.model_dump(), ensure_ascii=False).encode()
        if len(encoded) > 128000 or SECRET_PATTERN.search(encoded.decode()):
            raise ValueError("Source exceeds the limit or contains a credential pattern")
        return self


class JobConflict(Exception):
    pass


class JobQuota(Exception):
    pass


def journal_mode_for(version):
    fixed = (version >= (3, 51, 3) or (3, 50, 7) <= version < (3, 51, 0)
             or (3, 44, 6) <= version < (3, 45, 0))
    return "WAL" if fixed else "DELETE"


class ReviewJobs:
    def __init__(self, directory: Path, *, clock=time.time, daily_limit=20):
        if directory.is_symlink():
            raise ValueError("Use a private state directory")
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        if directory.stat().st_mode & 0o077:
            raise ValueError("State directory must be owner-only")
        self.path = directory / "review-jobs.sqlite3"
        descriptor = os.open(self.path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        os.close(descriptor)
        if self.path.stat().st_mode & 0o077:
            raise ValueError("State database must be owner-only")
        self.clock = clock
        self.daily_limit = daily_limit
        with closing(self.connect()) as connection:
            connection.execute("PRAGMA journal_mode=" + journal_mode_for(sqlite3.sqlite_version_info))
            connection.execute("""CREATE TABLE IF NOT EXISTS review_jobs (
                id TEXT PRIMARY KEY, subject TEXT NOT NULL, request_key TEXT NOT NULL,
                payload_hash TEXT NOT NULL, payload TEXT, metadata TEXT NOT NULL,
                status TEXT NOT NULL, created REAL NOT NULL, updated REAL NOT NULL,
                lease TEXT, lease_until REAL, result TEXT, error TEXT,
                UNIQUE(subject, request_key))""")
            connection.execute("CREATE INDEX IF NOT EXISTS review_owner ON review_jobs(subject, created)")
            connection.execute("CREATE INDEX IF NOT EXISTS review_queue ON review_jobs(status, created)")

    def connect(self):
        connection = sqlite3.connect(self.path, isolation_level=None, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA synchronous=FULL")
        return connection

    @staticmethod
    def public(row):
        if row is None:
            return None
        return {"id": row["id"], "status": row["status"], "created_at": row["created"],
                "updated_at": row["updated"], **json.loads(row["metadata"]),
                "result": json.loads(row["result"]) if row["result"] else None, "error": row["error"]}

    def submit(self, subject: str, key: str, request: RemoteReviewRequest):
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", subject) or not re.fullmatch(r"[A-Za-z0-9_-]{16,128}", key):
            raise ValueError("Invalid subject or idempotency key")
        if request.sharing_confirmed is not True:
            raise ValueError("Confirm source sharing before submitting")
        payload = json.dumps(request.model_dump(), sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        fingerprint = hashlib.sha256(payload.encode()).hexdigest()
        now = self.clock()
        with closing(self.connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute("SELECT * FROM review_jobs WHERE subject=? AND request_key=?", (subject, key)).fetchone()
            if existing:
                if existing["payload_hash"] != fingerprint:
                    raise JobConflict("Idempotency key was already used for another request")
                return self.public(existing), False
            recent = connection.execute("SELECT count(*) FROM review_jobs WHERE subject=? AND created>?", (subject, now - 86400)).fetchone()[0]
            pending = connection.execute("SELECT count(*) FROM review_jobs WHERE subject=? AND status IN ('queued','running','cancelling')", (subject,)).fetchone()[0]
            total = connection.execute("SELECT count(*) FROM review_jobs").fetchone()[0]
            if recent >= self.daily_limit or pending >= 4 or total >= 10000:
                raise JobQuota("Review job quota reached")
            identity = uuid.uuid4().hex
            metadata = {"provider": request.provider, "model": request.model, "read_only": True,
                        "files": [{"path": entry.path, "sha256": hashlib.sha256(entry.content.encode()).hexdigest()}
                                  for entry in request.files]}
            connection.execute("INSERT INTO review_jobs(id,subject,request_key,payload_hash,payload,metadata,status,created,updated) VALUES(?,?,?,?,?,?,'queued',?,?)",
                               (identity, subject, key, fingerprint, payload, json.dumps(metadata), now, now))
            return self.public(connection.execute("SELECT * FROM review_jobs WHERE id=?", (identity,)).fetchone()), True

    def get(self, subject, identity):
        with closing(self.connect()) as connection:
            return self.public(connection.execute("SELECT * FROM review_jobs WHERE id=? AND subject=?", (identity, subject)).fetchone())

    def list(self, subject):
        with closing(self.connect()) as connection:
            return [self.public(row) for row in connection.execute("SELECT * FROM review_jobs WHERE subject=? ORDER BY created DESC,id DESC LIMIT 20", (subject,))]

    def cancel(self, subject, identity):
        with closing(self.connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("UPDATE review_jobs SET status=CASE status WHEN 'queued' THEN 'cancelled' WHEN 'running' THEN 'cancelling' ELSE status END,payload=NULL,updated=? WHERE id=? AND subject=? AND status IN ('queued','running')", (self.clock(), identity, subject))
            return self.public(connection.execute("SELECT * FROM review_jobs WHERE id=? AND subject=?", (identity, subject)).fetchone())

    def recover(self, connection):
        connection.execute("UPDATE review_jobs SET status=CASE status WHEN 'cancelling' THEN 'cancelled' ELSE 'interrupted' END,error='worker_interrupted',payload=NULL,lease=NULL,lease_until=NULL,updated=? WHERE status IN ('running','cancelling') AND lease_until<=?", (self.clock(), self.clock()))

    def claim(self, lease_seconds=120):
        with closing(self.connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            self.recover(connection)
            row = connection.execute("SELECT * FROM review_jobs WHERE status='queued' ORDER BY created,id LIMIT 1").fetchone()
            if row is None:
                return None
            lease = uuid.uuid4().hex
            connection.execute("UPDATE review_jobs SET status='running',lease=?,lease_until=?,updated=? WHERE id=?",
                               (lease, self.clock() + lease_seconds, self.clock(), row["id"]))
            return {"id": row["id"], "lease": lease, "request": json.loads(row["payload"])}

    def heartbeat(self, identity, lease, lease_seconds=120):
        with closing(self.connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT status FROM review_jobs WHERE id=? AND lease=? AND lease_until>?", (identity, lease, self.clock())).fetchone()
            if row is None:
                return "lost"
            connection.execute("UPDATE review_jobs SET lease_until=? WHERE id=? AND lease=?", (self.clock() + lease_seconds, identity, lease))
            return row["status"]

    def finish(self, identity, lease, *, result=None, error=None):
        with closing(self.connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT status FROM review_jobs WHERE id=? AND lease=? AND lease_until>?", (identity, lease, self.clock())).fetchone()
            if row is None or row["status"] not in {"running", "cancelling"}:
                return False
            cancelled = row["status"] == "cancelling"
            status = "cancelled" if cancelled else "failed" if error else "succeeded"
            connection.execute("UPDATE review_jobs SET status=?,result=?,error=?,payload=NULL,lease=NULL,lease_until=NULL,updated=? WHERE id=? AND lease=?",
                               (status, json.dumps(result) if result is not None and not cancelled else None,
                                error if not cancelled else None, self.clock(), identity, lease))
            return True

    def forget(self, subject, identity):
        with closing(self.connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT status FROM review_jobs WHERE subject=? AND id=?", (subject, identity)).fetchone()
            if row is None:
                return None
            if row["status"] in {"queued", "running", "cancelling"}:
                raise JobConflict("Cancel the active job before removing its result")
            connection.execute("UPDATE review_jobs SET status='deleted',metadata='{}',result=NULL,payload=NULL,error=NULL,updated=? WHERE subject=? AND id=?", (self.clock(), subject, identity))
            return self.public(connection.execute("SELECT * FROM review_jobs WHERE subject=? AND id=?", (subject, identity)).fetchone())
