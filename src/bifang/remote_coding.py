from __future__ import annotations

import difflib
import hashlib
import json
import re
import uuid
from contextlib import closing

from pydantic import Field, field_validator, model_validator

from .candidate import selected_path
from .remote_jobs import JobConflict, JobQuota, RemoteReviewRequest, ReviewJobs
from .secret_patterns import SECRET_PATTERN


def snapshot_digest(files: dict[str, str]) -> str:
    manifest = {path: hashlib.sha256(content.encode()).hexdigest() for path, content in files.items()}
    return hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()


class CodingRequest(RemoteReviewRequest):
    writable: list[str] = Field(min_length=1, max_length=8)
    check_command: list[str] = Field(min_length=1, max_length=32)
    check_timeout: int = Field(default=30, ge=1, le=60)
    project_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")

    @field_validator("writable")
    @classmethod
    def safe_outputs(cls, paths):
        if len(paths) != len(set(paths)):
            raise ValueError("Output paths must be unique")
        for path in paths:
            selected_path(path)
            if len(path) > 200 or ":" in path:
                raise ValueError("Choose ordinary relative output paths")
        return paths

    @model_validator(mode="after")
    def bounded_check(self):
        paths = {entry.path for entry in self.files} | set(self.writable)
        for path in paths:
            selected_path(path)
        if (any(not argument or any(ord(character) < 32 for character in argument)
                for argument in self.check_command)
                or sum(len(argument.encode()) for argument in self.check_command) > 2048
                or len(paths) > 8 or any(other.startswith(path + "/") for path in paths for other in paths)):
            raise ValueError("Bound the explicit check command and selected files")
        return self


TERMINAL = {"rejected", "check_denied", "check_failed", "applied", "cancelled", "failed", "interrupted", "deleted"}


class CodingJobs(ReviewJobs):
    def __init__(self, directory, **options):
        super().__init__(directory, **options)
        with closing(self.connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("""CREATE TABLE IF NOT EXISTS coding_projects (
                id TEXT PRIMARY KEY, subject TEXT NOT NULL, revision TEXT NOT NULL,
                files TEXT NOT NULL, updated REAL NOT NULL)""")
            connection.execute("""CREATE TABLE IF NOT EXISTS coding_jobs (
                id TEXT PRIMARY KEY, subject TEXT NOT NULL, request_key TEXT NOT NULL,
                payload_hash TEXT NOT NULL, project_id TEXT NOT NULL, base_revision TEXT NOT NULL,
                request TEXT NOT NULL, status TEXT NOT NULL, created REAL NOT NULL, updated REAL NOT NULL,
                proposal TEXT, candidate TEXT, candidate_sha256 TEXT, receipt TEXT,
                lease TEXT, lease_until REAL, error TEXT, generation TEXT,
                UNIQUE(subject, request_key))""")
            if "generation" not in {row["name"] for row in connection.execute("PRAGMA table_info(coding_jobs)")}:
                connection.execute("ALTER TABLE coding_jobs ADD COLUMN generation TEXT")
            connection.execute("CREATE INDEX IF NOT EXISTS coding_owner ON coding_jobs(subject,created)")
            connection.execute("""CREATE TABLE IF NOT EXISTS coding_decisions (
                job_id TEXT NOT NULL, subject TEXT NOT NULL, action TEXT NOT NULL,
                candidate_sha256 TEXT NOT NULL, approved INTEGER NOT NULL, created REAL NOT NULL,
                PRIMARY KEY(job_id, action))""")

    @staticmethod
    def view(row):
        if row is None:
            return None
        request = json.loads(row["request"])
        return {"id": row["id"], "project_id": row["project_id"], "base_revision": row["base_revision"],
                "status": row["status"], "created_at": row["created"], "updated_at": row["updated"],
                "candidate_sha256": row["candidate_sha256"], "error": row["error"],
                "provider": request["provider"], "requested_model": request["model"],
                "writable": request["writable"], "check_command": request["check_command"],
                "check_timeout": request["check_timeout"],
                "verification": "executed_check" if row["receipt"] else
                    "unverified_model_proposal" if row["proposal"] else "pending_proposal",
                "proposal": json.loads(row["proposal"]) if row["proposal"] else None,
                "generation": json.loads(row["generation"]) if row["generation"] else None,
                "receipt": json.loads(row["receipt"]) if row["receipt"] else None}

    def submit_coding(self, subject, key, request: CodingRequest):
        if (not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", subject)
                or not re.fullmatch(r"[A-Za-z0-9_-]{16,128}", key)
                or request.sharing_confirmed is not True):
            raise ValueError("Require an authenticated owner, idempotency key and source consent")
        payload = request.model_dump_json()
        fingerprint = hashlib.sha256(payload.encode()).hexdigest()
        files = {entry.path: entry.content for entry in request.files}
        revision = snapshot_digest(files)
        now = self.clock()
        with closing(self.connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute("SELECT * FROM coding_jobs WHERE subject=? AND request_key=?", (subject, key)).fetchone()
            if existing:
                if existing["payload_hash"] != fingerprint:
                    raise JobConflict("Idempotency key already belongs to another coding request")
                return self.view(existing), False
            recent = connection.execute("SELECT count(*) FROM coding_jobs WHERE subject=? AND created>?", (subject, now - 86400)).fetchone()[0]
            pending = connection.execute("SELECT status FROM coding_jobs WHERE subject=?", (subject,)).fetchall()
            total = connection.execute("SELECT count(*) FROM coding_jobs").fetchone()[0]
            if recent >= self.daily_limit or sum(row["status"] not in TERMINAL for row in pending) >= 4 or total >= 10000:
                raise JobQuota("Coding job quota reached")
            project_id = request.project_id or uuid.uuid4().hex
            if request.project_id:
                project = connection.execute("SELECT * FROM coding_projects WHERE id=? AND subject=?", (project_id, subject)).fetchone()
                if project is None or project["revision"] != revision:
                    raise JobConflict("Owned project revision must match the submitted source")
            else:
                connection.execute("INSERT INTO coding_projects VALUES(?,?,?,?,?)", (project_id, subject, revision, json.dumps(files), now))
            identity = uuid.uuid4().hex
            connection.execute("""INSERT INTO coding_jobs
                (id,subject,request_key,payload_hash,project_id,base_revision,request,status,created,updated)
                VALUES(?,?,?,?,?,?,?,'queued',?,?)""",
                (identity, subject, key, fingerprint, project_id, revision, payload, now, now))
            return self.view(connection.execute("SELECT * FROM coding_jobs WHERE id=?", (identity,)).fetchone()), True

    def get_coding(self, subject, identity):
        with closing(self.connect()) as connection:
            return self.view(connection.execute("SELECT * FROM coding_jobs WHERE id=? AND subject=?", (identity, subject)).fetchone())

    def project(self, subject, identity):
        with closing(self.connect()) as connection:
            row = connection.execute("SELECT * FROM coding_projects WHERE id=? AND subject=?", (identity, subject)).fetchone()
            return {"id": row["id"], "revision": row["revision"], "files": json.loads(row["files"])} if row else None

    def list_coding(self, subject):
        with closing(self.connect()) as connection:
            rows = connection.execute("SELECT * FROM coding_jobs WHERE subject=? ORDER BY created DESC,id DESC LIMIT 20", (subject,))
            return [{name: value for name, value in self.view(row).items() if name != "proposal"} for row in rows]

    def patch_coding(self, subject, identity):
        with closing(self.connect()) as connection:
            row = connection.execute("SELECT * FROM coding_jobs WHERE id=? AND subject=?", (identity, subject)).fetchone()
            if row is None:
                return None
            if not row["candidate"]:
                raise JobConflict("A candidate is not available")
            before = {entry["path"]: entry["content"] for entry in json.loads(row["request"])["files"]}
            after = json.loads(row["candidate"])
            output = []
            for path, content in sorted(after.items()):
                if before.get(path) == content:
                    continue
                output.append(f"diff --git a/{path} b/{path}\n")
                if path not in before:
                    output.append("new file mode 100644\n")
                for line in difflib.unified_diff(before.get(path, "").splitlines(keepends=True), content.splitlines(keepends=True),
                                                 fromfile=f"a/{path}" if path in before else "/dev/null", tofile=f"b/{path}"):
                    output.append(line if line.endswith("\n") else line + "\n\\ No newline at end of file\n")
            return {"candidate_sha256": row["candidate_sha256"], "patch": "".join(output), "content_trust": "untrusted_source"}

    def forget_coding(self, subject, identity):
        with closing(self.connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT * FROM coding_jobs WHERE id=? AND subject=?", (identity, subject)).fetchone()
            if row is None:
                return None
            if row["status"] not in TERMINAL:
                raise JobConflict("Cancel or finish coding work before deleting its result")
            self.clear_coding(connection, row)
            return self.view(connection.execute("SELECT * FROM coding_jobs WHERE id=?", (identity,)).fetchone())

    def clear_coding(self, connection, row):
        request = json.loads(row["request"])
        redacted = {name: request[name] for name in ("provider", "model", "check_timeout")}
        redacted.update(writable=[], check_command=[])
        connection.execute("""UPDATE coding_jobs SET status='deleted',request=?,proposal=NULL,candidate=NULL,
            receipt=NULL,generation=NULL,error=NULL,lease=NULL,lease_until=NULL,updated=? WHERE id=?""",
            (json.dumps(redacted), self.clock(), row["id"]))

    def forget_project(self, subject, identity):
        with closing(self.connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            project = connection.execute("SELECT 1 FROM coding_projects WHERE id=? AND subject=?", (identity, subject)).fetchone()
            if project is None:
                return None
            jobs = connection.execute("SELECT * FROM coding_jobs WHERE project_id=? AND subject=?", (identity, subject)).fetchall()
            if any(row["status"] not in TERMINAL for row in jobs):
                raise JobConflict("Cancel or finish project jobs before removing source")
            for row in jobs:
                self.clear_coding(connection, row)
            connection.execute("DELETE FROM coding_projects WHERE id=? AND subject=?", (identity, subject))
            return {"id": identity, "status": "deleted", "logical_source_removal": True}

    def claim_coding(self, kind, lease_seconds=120):
        if kind not in {"generate", "check"} or not 1 <= lease_seconds <= 300:
            raise ValueError("Choose a bounded coding worker lease")
        before, after = ("queued", "generating") if kind == "generate" else ("queued_check", "checking")
        with closing(self.connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("""UPDATE coding_jobs SET status='interrupted',lease=NULL,lease_until=NULL,
                error='worker_interrupted',updated=? WHERE status IN ('generating','checking') AND lease_until<=?""",
                (self.clock(), self.clock()))
            row = connection.execute("SELECT * FROM coding_jobs WHERE status=? ORDER BY created,id LIMIT 1", (before,)).fetchone()
            if row is None:
                return None
            lease = uuid.uuid4().hex
            connection.execute("UPDATE coding_jobs SET status=?,lease=?,lease_until=?,updated=? WHERE id=?",
                               (after, lease, self.clock() + lease_seconds, self.clock(), row["id"]))
            return {"id": row["id"], "lease": lease, "request": json.loads(row["request"]),
                    "candidate": json.loads(row["candidate"]) if row["candidate"] else None,
                    "candidate_sha256": row["candidate_sha256"]}

    def propose(self, identity, lease, writes: dict[str, str], *, generation=None):
        with closing(self.connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("""SELECT * FROM coding_jobs WHERE id=? AND lease=?
                AND lease_until>? AND status='generating'""", (identity, lease, self.clock())).fetchone()
            if row is None:
                return False
            request = CodingRequest.model_validate_json(row["request"])
            if generation is not None and (not isinstance(generation, dict)
                        or set(generation) != {"provider", "requested_model", "reported_model", "usage", "verification"}
                        or generation["provider"] != request.provider or generation["requested_model"] != request.model
                        or generation["verification"] != "unverified_model_proposal"
                        or not isinstance(generation["usage"], dict)
                        or any(name not in {"prompt_tokens", "completion_tokens", "total_tokens"}
                               or type(value) is not int or not 0 <= value < 2**63 for name, value in generation["usage"].items())
                        or (generation["reported_model"] is not None
                            and (not isinstance(generation["reported_model"], str) or len(generation["reported_model"]) > 256))):
                raise ValueError("Generation metadata must be a bounded provider receipt")
            if (not isinstance(writes, dict) or not writes or not set(writes) <= set(request.writable)
                    or any(not isinstance(content, str) or len(content.encode()) > 64000 for content in writes.values())):
                raise ValueError("Propose bounded writes only to explicitly selected outputs")
            encoded = json.dumps(writes, ensure_ascii=False)
            if SECRET_PATTERN.search(encoded) or len(encoded.encode()) > 128000:
                raise ValueError("Proposal exceeds limits or contains a credential pattern")
            candidate = {entry.path: entry.content for entry in request.files}
            if all(candidate.get(path) == content for path, content in writes.items()):
                raise ValueError("Candidate must contain a change")
            candidate.update(writes)
            if len(json.dumps(candidate, ensure_ascii=False).encode()) > 128000:
                raise ValueError("Combined candidate exceeds the source budget")
            digest = snapshot_digest(candidate)
            connection.execute("""UPDATE coding_jobs SET proposal=?,candidate=?,candidate_sha256=?,
                generation=?,status='awaiting_write_approval',lease=NULL,lease_until=NULL,updated=? WHERE id=?""",
                (encoded, json.dumps(candidate), digest, json.dumps(generation) if generation is not None else None, self.clock(), identity))
            return True

    def decide(self, subject, identity, action, expected_sha256, approved):
        if action not in {"writes", "check", "review", "stage", "apply"} or type(approved) is not bool:
            raise ValueError("Require an explicit human decision")
        transitions = {"writes": ("awaiting_write_approval", "awaiting_check_approval", "rejected"),
                       "check": ("awaiting_check_approval", "queued_check", "check_denied"),
                       "review": ("verified", "reviewed", "rejected"),
                       "stage": ("reviewed", "staged", "rejected"),
                       "apply": ("staged", "applied", "rejected")}
        with closing(self.connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT * FROM coding_jobs WHERE id=? AND subject=?", (identity, subject)).fetchone()
            if row is None:
                return None
            if not row["candidate_sha256"] or expected_sha256 != row["candidate_sha256"]:
                raise JobConflict("Decision must bind to the exact displayed candidate")
            prior = connection.execute("SELECT * FROM coding_decisions WHERE job_id=? AND action=?", (identity, action)).fetchone()
            if prior:
                if bool(prior["approved"]) != approved or prior["candidate_sha256"] != expected_sha256:
                    raise JobConflict("Decision already recorded; create new work instead of reversing consent")
                return self.view(row)
            before, accepted, denied = transitions[action]
            if row["status"] != before:
                raise JobConflict("This decision is unavailable in the current state")
            if action in {"review", "stage", "apply"}:
                receipt = json.loads(row["receipt"]) if row["receipt"] else {}
                if not receipt.get("passed") or receipt.get("candidate_sha256") != expected_sha256:
                    raise JobConflict("Require an independent passing check for this exact candidate")
            if action == "apply" and approved:
                changed = connection.execute("""UPDATE coding_projects SET files=?,revision=?,updated=?
                    WHERE id=? AND subject=? AND revision=?""",
                    (row["candidate"], expected_sha256, self.clock(), row["project_id"], subject, row["base_revision"])).rowcount
                if changed != 1:
                    raise JobConflict("Project changed; do not apply a stale checked candidate")
            connection.execute("INSERT INTO coding_decisions VALUES(?,?,?,?,?,?)",
                               (identity, subject, action, expected_sha256, int(approved), self.clock()))
            connection.execute("UPDATE coding_jobs SET status=?,updated=? WHERE id=?", (accepted if approved else denied, self.clock(), identity))
            return self.view(connection.execute("SELECT * FROM coding_jobs WHERE id=?", (identity,)).fetchone())

    def finish_check(self, identity, lease, *, candidate_sha256, command, exit_code, timed_out, output_sha256):
        if (type(exit_code) is not int or type(timed_out) is not bool
                or not re.fullmatch(r"[a-f0-9]{64}", output_sha256)):
            raise ValueError("Require an executed check receipt")
        with closing(self.connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("""SELECT * FROM coding_jobs WHERE id=? AND lease=?
                AND lease_until>? AND status='checking'""", (identity, lease, self.clock())).fetchone()
            if row is None:
                return False
            request = json.loads(row["request"])
            if candidate_sha256 != row["candidate_sha256"] or command != request["check_command"]:
                raise JobConflict("Check does not match the approved candidate and command")
            passed = exit_code == 0 and not timed_out
            receipt = {"candidate_sha256": candidate_sha256, "command": command, "exit_code": exit_code,
                       "timed_out": timed_out, "output_sha256": output_sha256, "passed": passed}
            connection.execute("""UPDATE coding_jobs SET receipt=?,status=?,lease=NULL,lease_until=NULL,
                updated=? WHERE id=?""", (json.dumps(receipt), "verified" if passed else "check_failed", self.clock(), identity))
            return True

    def cancel_coding(self, subject, identity):
        with closing(self.connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT * FROM coding_jobs WHERE id=? AND subject=?", (identity, subject)).fetchone()
            if row is None:
                return None
            if row["status"] not in TERMINAL:
                connection.execute("UPDATE coding_jobs SET status='cancelled',lease=NULL,lease_until=NULL,updated=? WHERE id=?",
                                   (self.clock(), identity))
            return self.view(connection.execute("SELECT * FROM coding_jobs WHERE id=?", (identity,)).fetchone())

    def fail_coding(self, identity, lease, error):
        if error not in {"proposal_unavailable", "check_unavailable", "worker_interrupted"}:
            raise ValueError("Use a fixed worker error category")
        with closing(self.connect()) as connection, connection:
            changed = connection.execute("""UPDATE coding_jobs SET status=?,error=?,lease=NULL,
                lease_until=NULL,updated=? WHERE id=? AND lease=? AND lease_until>?
                AND status IN ('generating','checking')""",
                ("interrupted" if error == "worker_interrupted" else "failed", error,
                 self.clock(), identity, lease, self.clock())).rowcount
            return changed == 1

    def coding_lease_active(self, identity, lease):
        with closing(self.connect()) as connection:
            return connection.execute("""SELECT 1 FROM coding_jobs WHERE id=? AND lease=?
                AND lease_until>? AND status IN ('generating','checking')""",
                (identity, lease, self.clock())).fetchone() is not None
