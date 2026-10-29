import hashlib
from concurrent.futures import ThreadPoolExecutor

import pytest
from pydantic import ValidationError

from bifang.remote_backup import backup_jobs
from bifang.remote_coding import CodingJobs, CodingRequest
from bifang.remote_jobs import JobConflict, JobQuota


def request(**changes):
    values = {"provider": "nebius", "model": "synthetic-model", "question": "Fix the bound",
              "sharing_confirmed": True,
              "files": [{"path": "bounds.py", "content": "def valid(index, items):\n    return index <= len(items)\n"},
                        {"path": "test_bounds.py", "content": "immutable independent check fixture\n"}],
              "writable": ["bounds.py"], "check_command": ["python", "-B", "-m", "unittest"]}
    return CodingRequest.model_validate({**values, **changes})


def create(store, key="synthetic_coding_key_01", **changes):
    return store.submit_coding("owner", key, request(**changes))[0]


def propose(store, job):
    claimed = store.claim_coding("generate")
    assert claimed["id"] == job["id"]
    assert store.propose(job["id"], claimed["lease"], {"bounds.py": "def valid(index, items):\n    return 0 <= index < len(items)\n"})
    return store.get_coding("owner", job["id"])


def approve(store, job, action, decision=True):
    return store.decide("owner", job["id"], action, job["candidate_sha256"], decision)


def checked(store, job, exit_code=0):
    job = approve(store, propose(store, job), "writes")
    job = approve(store, job, "check")
    claimed = store.claim_coding("check")
    assert store.finish_check(job["id"], claimed["lease"], candidate_sha256=job["candidate_sha256"],
                             command=job["check_command"], exit_code=exit_code, timed_out=False,
                             output_sha256=hashlib.sha256(b"synthetic unit-test runner receipt").hexdigest())
    return store.get_coding("owner", job["id"])


def test_exact_candidate_requires_separate_durable_decisions_and_apply(tmp_path):
    store = CodingJobs(tmp_path / "state")
    initial = create(store)
    original = store.project("owner", initial["project_id"])
    job = propose(store, initial)
    assert store.project("owner", job["project_id"]) == original
    assert store.claim_coding("check") is None
    for action in ("check", "review", "stage", "apply"):
        with pytest.raises(JobConflict):
            approve(store, job, action)
    job = approve(store, job, "writes")
    store = CodingJobs(tmp_path / "state")
    assert store.get_coding("owner", job["id"])["status"] == "awaiting_check_approval"
    job = approve(store, job, "check")
    claimed = store.claim_coding("check")
    assert store.finish_check(job["id"], claimed["lease"], candidate_sha256=job["candidate_sha256"],
                             command=job["check_command"], exit_code=0, timed_out=False, output_sha256="0" * 64)
    job = store.get_coding("owner", job["id"])
    with pytest.raises(JobConflict):
        approve(store, job, "apply")
    job = approve(store, job, "review")
    job = approve(store, job, "stage")
    assert store.project("owner", job["project_id"]) == original
    job = approve(store, job, "apply")
    assert job["status"] == "applied"
    project = store.project("owner", job["project_id"])
    assert project["revision"] == job["candidate_sha256"]
    assert "0 <= index < len(items)" in project["files"]["bounds.py"]
    assert project["files"]["test_bounds.py"] == original["files"]["test_bounds.py"]
    assert approve(store, job, "apply")["status"] == "applied"


def test_owner_isolation_and_decision_cannot_change_candidate(tmp_path):
    store = CodingJobs(tmp_path / "state")
    job = propose(store, create(store))
    assert store.get_coding("judge", job["id"]) is None
    assert store.project("judge", job["project_id"]) is None
    assert store.decide("judge", job["id"], "writes", job["candidate_sha256"], True) is None
    assert store.cancel_coding("judge", job["id"]) is None
    with pytest.raises(JobConflict):
        store.decide("owner", job["id"], "writes", "f" * 64, True)
    with pytest.raises(ValueError):
        store.decide("owner", job["id"], "writes", job["candidate_sha256"], "yes")
    assert approve(store, job, "writes", False)["status"] == "rejected"
    assert approve(store, job, "writes", False)["status"] == "rejected"
    with pytest.raises(JobConflict):
        approve(store, job, "writes", True)
    assert store.claim_coding("check") is None


def test_concurrent_idempotent_submission_and_changed_request(tmp_path):
    store = CodingJobs(tmp_path / "state")
    with ThreadPoolExecutor(max_workers=4) as pool:
        rows = list(pool.map(lambda ignored: store.submit_coding("owner", "same_synthetic_key", request()), range(4)))
    assert sum(created for job, created in rows) == 1
    assert len({job["id"] for job, created in rows}) == 1
    with pytest.raises(JobConflict):
        store.submit_coding("owner", "same_synthetic_key", request(question="changed"))


@pytest.mark.parametrize("changes", [
    {"writable": ["../escape.py"]}, {"writable": [".env"]}, {"writable": [".aws/credentials"]},
    {"writable": ["bounds.py", "bounds.py"]}, {"writable": ["bounds.py/nested"]},
    {"files": [{"path": ".ssh/id_rsa", "content": "synthetic"}]},
    {"check_command": ["python", "bad\nargument"]}, {"check_command": []},
    {"check_timeout": True}, {"check_timeout": 61},
])
def test_capability_and_check_bounds(changes):
    with pytest.raises((ValueError, ValidationError)):
        request(**changes)


@pytest.mark.parametrize("writes", [{"test_bounds.py": "weaken checks"}, {"../escape.py": "escape"},
                                    {"bounds.py": "x" * 64001}, {"bounds.py": 3}, {}])
def test_proposals_cannot_escape_selected_write_capabilities(tmp_path, writes):
    store = CodingJobs(tmp_path / "state")
    job = create(store)
    claimed = store.claim_coding("generate")
    with pytest.raises(ValueError):
        store.propose(job["id"], claimed["lease"], writes)
    assert store.get_coding("owner", job["id"])["status"] == "generating"


def test_cancel_and_expired_lease_fence_late_model_results(tmp_path):
    now = [100]
    store = CodingJobs(tmp_path / "state", clock=lambda: now[0])
    job = create(store)
    claimed = store.claim_coding("generate", lease_seconds=2)
    assert store.claim_coding("generate") is None
    now[0] += 3
    assert store.claim_coding("generate") is None
    assert store.get_coding("owner", job["id"])["status"] == "interrupted"
    assert store.propose(job["id"], claimed["lease"], {"bounds.py": "late"}) is False
    second = create(store, key="second_synthetic_key")
    claimed = store.claim_coding("generate")
    assert store.cancel_coding("owner", second["id"])["status"] == "cancelled"
    assert store.propose(second["id"], claimed["lease"], {"bounds.py": "late"}) is False


def test_failed_check_cannot_stage_or_apply(tmp_path):
    store = CodingJobs(tmp_path / "state")
    job = checked(store, create(store), exit_code=1)
    assert job["status"] == "check_failed"
    for action in ("review", "stage", "apply"):
        with pytest.raises(JobConflict):
            approve(store, job, action)


def test_check_receipt_must_match_human_approved_command_and_snapshot(tmp_path):
    store = CodingJobs(tmp_path / "state")
    job = approve(store, propose(store, create(store)), "writes")
    job = approve(store, job, "check")
    claimed = store.claim_coding("check")
    for digest, command in (("f" * 64, job["check_command"]), (job["candidate_sha256"], ["true"])):
        with pytest.raises(JobConflict):
            store.finish_check(job["id"], claimed["lease"], candidate_sha256=digest,
                               command=command, exit_code=0, timed_out=False, output_sha256="0" * 64)
    assert store.get_coding("owner", job["id"])["status"] == "checking"
    store.cancel_coding("owner", job["id"])
    assert store.finish_check(job["id"], claimed["lease"], candidate_sha256=job["candidate_sha256"],
                              command=job["check_command"], exit_code=0, timed_out=False, output_sha256="0" * 64) is False


def test_project_revision_conflict_prevents_stale_apply(tmp_path):
    store = CodingJobs(tmp_path / "state")
    first = create(store)
    second = create(store, key="another_synthetic_key", project_id=first["project_id"])
    first = checked(store, first)
    second = checked(store, second)
    for action in ("review", "stage", "apply"):
        first = approve(store, first, action)
    for action in ("review", "stage"):
        second = approve(store, second, action)
    with pytest.raises(JobConflict, match="Project changed"):
        approve(store, second, "apply")
    with pytest.raises(JobConflict):
        create(store, key="third_synthetic_key", project_id=first["project_id"])
    with pytest.raises(JobConflict):
        store.submit_coding("judge", "other_owner_project", request(project_id=first["project_id"]))


def test_backup_keeps_live_approval_state_but_interrupts_restored_jobs(tmp_path):
    store = CodingJobs(tmp_path / "state")
    job = approve(store, propose(store, create(store)), "writes")
    directory = tmp_path / "backups"
    directory.mkdir(mode=0o700)
    backup_jobs(store, directory / "snapshot.sqlite3")
    assert store.get_coding("owner", job["id"])["status"] == "awaiting_check_approval"
    restored = tmp_path / "restored"
    restored.mkdir(mode=0o700)
    (restored / "review-jobs.sqlite3").write_bytes((directory / "snapshot.sqlite3").read_bytes())
    (restored / "review-jobs.sqlite3").chmod(0o600)
    recovered = CodingJobs(restored)
    assert recovered.get_coding("owner", job["id"])["status"] == "interrupted"
    assert recovered.claim_coding("generate") is None and recovered.claim_coding("check") is None
    with pytest.raises(JobConflict):
        approve(recovered, job, "check")


def test_consent_and_pending_quota_fail_closed(tmp_path):
    store = CodingJobs(tmp_path / "state")
    with pytest.raises(ValueError):
        create(store, sharing_confirmed=False)
    for number in range(4):
        create(store, key=f"synthetic_pending_{number}")
    with pytest.raises(JobQuota):
        create(store, key="synthetic_pending_extra")


def test_existing_coding_database_gets_generation_column_without_losing_jobs(tmp_path):
    store = CodingJobs(tmp_path / "state")
    job = create(store)
    connection = store.connect()
    try:
        connection.execute("ALTER TABLE coding_jobs DROP COLUMN generation")
    finally:
        connection.close()
    reopened = CodingJobs(tmp_path / "state")
    assert reopened.get_coding("owner", job["id"])["status"] == "queued"
    assert reopened.get_coding("owner", job["id"])["generation"] is None


def test_deleted_coding_tombstone_stays_deleted_after_backup_and_restore(tmp_path):
    store = CodingJobs(tmp_path / "state")
    job = create(store)
    store.cancel_coding("owner", job["id"])
    assert store.forget_project("owner", job["project_id"])["status"] == "deleted"
    directory = tmp_path / "backups"
    directory.mkdir(mode=0o700)
    backup_jobs(store, directory / "snapshot.sqlite3")
    restored = tmp_path / "restored"
    restored.mkdir(mode=0o700)
    (restored / "review-jobs.sqlite3").write_bytes((directory / "snapshot.sqlite3").read_bytes())
    (restored / "review-jobs.sqlite3").chmod(0o600)
    recovered = CodingJobs(restored)
    same, created = recovered.submit_coding("owner", "synthetic_coding_key_01", request())
    assert not created and same["status"] == "deleted"
    assert recovered.project("owner", job["project_id"]) is None
    assert recovered.claim_coding("generate") is None and recovered.claim_coding("check") is None
