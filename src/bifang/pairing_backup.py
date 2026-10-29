from __future__ import annotations

import argparse
import math
import os
import sqlite3
import tempfile
import time
from contextlib import closing
from pathlib import Path


def snapshot(source: Path, destination: Path, *, clock=time.time) -> None:
    parent = destination.parent
    if (source.is_symlink() or not source.is_file() or source.stat().st_mode & 0o077
            or source.parent.is_symlink() or source.parent.stat().st_mode & 0o077):
        raise ValueError("Select a trusted owner-only pairing database")
    if parent.is_symlink() or not parent.is_dir() or parent.stat().st_mode & 0o077:
        raise ValueError("Select an existing owner-only destination directory")
    if destination.exists() or destination.is_symlink():
        raise FileExistsError("Pairing recovery never overwrites existing state")
    descriptor, name = tempfile.mkstemp(prefix=".pairing-snapshot-", dir=parent)
    os.close(descriptor)
    staging = Path(name)
    try:
        with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as original, closing(sqlite3.connect(staging)) as target:
            original.backup(target)
            target.execute("PRAGMA trusted_schema=OFF")
            expected = {"device_pairs", "device_sessions", "authenticator_steps", "pairing_attempts"}
            tables = {row[0] for row in target.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if tables != expected or target.execute("PRAGMA quick_check").fetchone() != ("ok",):
                raise ValueError("Invalid pairing recovery database")
            target.execute("DELETE FROM device_pairs")
            target.execute("DELETE FROM device_sessions")
            target.execute("DELETE FROM pairing_attempts")
            target.execute("UPDATE authenticator_steps SET last_step=max(last_step,?)", (math.floor(clock() / 30) + 1,))
            target.commit()
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
    parser = argparse.ArgumentParser(description="Private pairing backup/recovery; all device sessions and pending requests are discarded")
    parser.add_argument("--source", type=Path, required=True, help="Existing trusted private pairing database or backup")
    parser.add_argument("--destination", type=Path, required=True, help="New private backup file, or device-pairing.sqlite3 in a stopped fresh state directory")
    options = parser.parse_args()
    try:
        snapshot(options.source.absolute(), options.destination.absolute())
    except (OSError, ValueError, sqlite3.Error):
        parser.exit(1, "Pairing snapshot failed; existing state was not replaced.\n")
    print("Pairing snapshot created. Sessions discarded; authenticator replay fence advanced. Keep factor configuration separately private.")


if __name__ == "__main__":
    main()
