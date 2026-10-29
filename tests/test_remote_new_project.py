import pytest
from pydantic import ValidationError

from bifang.remote_coding import CodingJobs, CodingRequest, snapshot_digest
from bifang.remote_jobs import JobConflict, RemoteReviewRequest


def test_empty_project_requires_all_decisions_before_applying_generated_files(tmp_path):
    payload = {"provider": "nebius", "model": "synthetic-model", "question": "Create a greeting program",
               "files": [], "writable": ["main.py"], "check_command": ["python", "-B", "main.py"],
               "sharing_confirmed": True}
    request = CodingRequest.model_validate(payload)
    store = CodingJobs(tmp_path / "state")
    job, created = store.submit_coding("owner", "new_project_synthetic_key", request)
    assert created
    original = store.project("owner", job["project_id"])
    assert original["files"] == {}
    assert original["revision"] == snapshot_digest({})
    claimed = store.claim_coding("generate")
    assert store.propose(job["id"], claimed["lease"], {"main.py": "print('Hello')\n"})
    job = store.get_coding("owner", job["id"])
    with pytest.raises(JobConflict):
        store.decide("owner", job["id"], "apply", job["candidate_sha256"], True)
    for action in ["writes", "check"]:
        job = store.decide("owner", job["id"], action, job["candidate_sha256"], True)
    claimed = store.claim_coding("check")
    assert store.finish_check(job["id"], claimed["lease"], candidate_sha256=job["candidate_sha256"],
                             command=job["check_command"], exit_code=0, timed_out=False,
                             output_sha256="0" * 64)
    for action in ["review", "stage"]:
        job = store.decide("owner", job["id"], action, job["candidate_sha256"], True)
    assert store.project("owner", job["project_id"]) == original
    job = store.decide("owner", job["id"], "apply", job["candidate_sha256"], True)
    assert job["status"] == "applied"
    assert store.project("owner", job["project_id"])["files"] == {"main.py": "print('Hello')\n"}
    with pytest.raises(ValidationError):
        RemoteReviewRequest.model_validate({key: value for key, value in payload.items()
                                            if key not in {"writable", "check_command"}})
