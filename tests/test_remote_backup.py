import shutil
import sqlite3

import pytest

from bifang.remote_backup import backup_jobs
from bifang.remote_jobs import RemoteReviewRequest, ReviewJobs, journal_mode_for


def review():
    return RemoteReviewRequest(provider="nebius", model="synthetic/review", question="Review fixture",
                               files=[{"path": "fixture.py", "content": "value = 1\n"}], sharing_confirmed=True)


def test_online_backup_restores_receipts_and_idempotency(tmp_path):
    jobs = ReviewJobs(tmp_path / "state")
    backups = tmp_path / "backups"
    backups.mkdir(mode=0o700)
    destination = backups / "snapshot.sqlite3"
    with jobs.connect() as active:
        job, _ = jobs.submit("alice", "backup-request-0001", review())
        claimed = jobs.claim()
        jobs.finish(claimed["id"], claimed["lease"], result={"analysis": "Synthetic fixture"})
        running, _ = jobs.submit("alice", "backup-request-0002", review())
        active_lease = jobs.claim()
        assert active_lease["id"] == running["id"]
        queued, _ = jobs.submit("alice", "backup-request-0003", review())
        assert active.execute("PRAGMA journal_mode").fetchone()[0].upper() == journal_mode_for(sqlite3.sqlite_version_info)
        backup_jobs(jobs, destination)
        assert jobs.get("alice", running["id"])["status"] == "running"
        assert jobs.get("alice", queued["id"])["status"] == "queued"
        jobs.submit("alice", "backup-request-0004", review())
    assert destination.stat().st_mode & 0o077 == 0
    assert list(backups.iterdir()) == [destination]
    restored = tmp_path / "restore"
    restored.mkdir(mode=0o700)
    shutil.copyfile(destination, restored / "review-jobs.sqlite3")
    (restored / "review-jobs.sqlite3").chmod(0o600)
    recovered = ReviewJobs(restored)
    assert recovered.get("alice", job["id"])["result"] == {"analysis": "Synthetic fixture"}
    assert len(recovered.list("alice")) == 3
    for pending in (running, queued):
        receipt = recovered.get("alice", pending["id"])
        assert receipt["status"] == "interrupted" and receipt["error"] == "restored_snapshot"
    assert recovered.claim() is None
    duplicate, created = recovered.submit("alice", "backup-request-0001", review())
    assert not created and duplicate["id"] == job["id"]
    assert recovered.get("bob", job["id"]) is None


def test_backup_refuses_overwrite_and_symlink_destinations(tmp_path):
    jobs = ReviewJobs(tmp_path / "state")
    backups = tmp_path / "backups"
    backups.mkdir(mode=0o700)
    existing = backups / "existing"
    existing.write_text("preserve this file")
    with pytest.raises(FileExistsError):
        backup_jobs(jobs, existing)
    assert existing.read_text() == "preserve this file"
    link = backups / "link"
    link.symlink_to(backups / "absent")
    with pytest.raises(FileExistsError):
        backup_jobs(jobs, link)
    assert not (backups / "absent").exists()


def test_backup_requires_private_real_directory(tmp_path):
    jobs = ReviewJobs(tmp_path / "state")
    shared = tmp_path / "shared"
    shared.mkdir(mode=0o755)
    shared.chmod(0o755)
    with pytest.raises(ValueError):
        backup_jobs(jobs, shared / "backup")
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    linked = tmp_path / "linked"
    linked.symlink_to(private, target_is_directory=True)
    with pytest.raises(ValueError):
        backup_jobs(jobs, linked / "backup")
    assert list(private.iterdir()) == []


def test_failed_backup_removes_staging_file(tmp_path, monkeypatch):
    jobs = ReviewJobs(tmp_path / "state")
    backups = tmp_path / "backups"
    backups.mkdir(mode=0o700)

    def unavailable():
        raise sqlite3.OperationalError("Synthetic failure")

    monkeypatch.setattr(jobs, "connect", unavailable)
    with pytest.raises(sqlite3.OperationalError):
        backup_jobs(jobs, backups / "backup")
    assert list(backups.iterdir()) == []


@pytest.mark.parametrize("version, expected", [
    ((3, 40, 1), "DELETE"), ((3, 44, 5), "DELETE"), ((3, 44, 6), "WAL"),
    ((3, 46, 1), "DELETE"), ((3, 50, 4), "DELETE"), ((3, 50, 7), "WAL"),
    ((3, 51, 2), "DELETE"), ((3, 51, 3), "WAL"), ((3, 52, 0), "WAL"),
])
def test_wal_requires_a_known_fixed_sqlite_release(version, expected):
    assert journal_mode_for(version) == expected
