from __future__ import annotations

import argparse
import json
import os
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path

from .remote_jobs import ReviewJobs


def backup_jobs(jobs: ReviewJobs, destination: Path) -> None:
    parent = destination.parent
    if parent.is_symlink() or not parent.is_dir() or parent.stat().st_mode & 0o077:
        raise ValueError("Choose an existing owner-only backup directory")
    if destination.exists() or destination.is_symlink():
        raise FileExistsError("Choose a new backup filename")
    descriptor, name = tempfile.mkstemp(prefix=".bifang-backup-", dir=parent)
    os.close(descriptor)
    staging = Path(name)
    try:
        with closing(jobs.connect()) as source, closing(sqlite3.connect(staging)) as target:
            source.backup(target)
            target.execute("""UPDATE review_jobs SET status='interrupted', payload=NULL,
                result=NULL, error='restored_snapshot', lease=NULL, lease_until=NULL, updated=?
                WHERE status IN ('queued','running','cancelling')""", (jobs.clock(),))
            if target.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='coding_jobs'").fetchone():
                target.execute("""UPDATE coding_jobs SET status='interrupted', lease=NULL,
                    lease_until=NULL, error='restored_snapshot', updated=?
                    WHERE status NOT IN ('rejected','check_denied','check_failed','applied','cancelled','failed','interrupted','deleted')""",
                    (jobs.clock(),))
            target.commit()
            if target.execute("PRAGMA quick_check").fetchone() != ("ok",):
                raise RuntimeError("Backup integrity check failed")
        with staging.open("rb") as stream:
            os.fsync(stream.fileno())
        os.link(staging, destination)
        descriptor = os.open(parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    finally:
        staging.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description="Create a private, consistent remote-job database backup")
    parser.add_argument("--state", required=True, type=Path)
    parser.add_argument("--destination", required=True, type=Path)
    options = parser.parse_args()
    if not (options.state / "review-jobs.sqlite3").is_file():
        parser.error("Select an existing remote-job state directory")
    backup_jobs(ReviewJobs(options.state), options.destination)
    print(json.dumps({"backup_created": True, "integrity": "ok"}))


if __name__ == "__main__":
    main()
