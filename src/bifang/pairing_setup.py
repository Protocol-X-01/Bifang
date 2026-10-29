from __future__ import annotations

import argparse
import getpass
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

from .totp import TotpCredential, generate_secret


def private_file(path: Path, content: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())


def enroll(subject: str, directory: Path, confirmation, *, clock=time.time, encoder=None) -> None:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", subject):
        raise ValueError("Use an existing operator subject")
    if any((ancestor / ".git").exists() for ancestor in (directory, *directory.parents)):
        raise ValueError("Keep enrollment material outside source repositories")
    parent = directory.parent
    if parent.is_symlink() or not parent.is_dir() or parent.stat().st_mode & 0o077:
        raise ValueError("Choose an existing owner-only parent directory")
    program = encoder or shutil.which("qrencode")
    if not program:
        raise ValueError("Install the local qrencode utility before enrollment")
    directory.mkdir(mode=0o700)
    try:
        secret = generate_secret()
        credential = TotpCredential(secret)
        result = subprocess.run([program, "-t", "SVG", "-o", "-"],
                                input=credential.provisioning_uri(subject).encode(),
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                check=False, timeout=10)
        if result.returncode or len(result.stdout) > 1000000 or b"<svg" not in result.stdout:
            raise ValueError("Could not create the private enrollment QR")
        private_file(directory / "authenticator.svg", result.stdout)
        code = confirmation(directory / "authenticator.svg")
        if credential.matching_step(code, now=clock(), after_step=-1) is None:
            raise ValueError("Authenticator confirmation failed; no configuration saved")
        private_file(directory / "pairing.env", ("BIFANG_REMOTE_AUTHENTICATORS=" + json.dumps({subject: secret}, separators=(",", ":")) + "\n").encode())
    except BaseException:
        for name in ("pairing.env", "authenticator.svg"):
            (directory / name).unlink(missing_ok=True)
        directory.rmdir()
        raise


def main():
    parser = argparse.ArgumentParser(description="Private local Authenticator enrollment for an existing Bifang operator")
    parser.add_argument("--subject", required=True)
    parser.add_argument("--directory", type=Path, required=True, help="New directory inside an owner-only parent; never a repository")
    options = parser.parse_args()
    if not sys.stdin.isatty():
        parser.error("Use an interactive trusted terminal; do not pipe Authenticator codes")

    def confirmation(path):
        print(f"Open this private QR locally and scan it with Authenticator: {path}")
        print("Do not upload the image, put it in source control or share it in chat.")
        return getpass.getpass("Current Authenticator code (hidden): ")

    try:
        enroll(options.subject, options.directory, confirmation)
    except (ValueError, OSError, subprocess.SubprocessError):
        parser.exit(1, "Enrollment did not complete. No service configuration was changed.\n")
    print("Confirmed. Private pairing.env created. Install it through trusted operator configuration; restart explicitly.")
    print("Securely remove the provisioning image after enrollment. This does not rotate or replace any existing factor.")


if __name__ == "__main__":
    main()
