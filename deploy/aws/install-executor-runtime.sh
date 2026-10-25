#!/bin/bash
set -euo pipefail
test "$(id -u)" = 0
test "$(uname -m)" = x86_64
mountpoint -q /var/lib/bifang-state
systemctl is-active --quiet bifang-remote
active=$(docker exec bifang-remote python -c "import sqlite3; connection=sqlite3.connect('file:/var/lib/bifang/review-jobs.sqlite3?mode=ro',uri=True); print(connection.execute(\"SELECT count(*) FROM review_jobs WHERE status IN ('queued','running','cancelling')\").fetchone()[0]); connection.close()")
test "$active" = 0
install -d -m 0755 /opt/bifang/gvisor
install -d -m 0700 /opt/bifang/gvisor/downloads
archive=/opt/bifang/gvisor/downloads/gvisor-x86_64-20261019.0.tar.bz2
curl --fail --location --silent --show-error --max-time 180 \
    https://github.com/google/gvisor/releases/download/release-20261019.0/gvisor-x86_64.tar.bz2 --output "$archive"
printf '%s  %s\n' 7cbc2aeeee809dcccfb40e612504a1b76f2c119790cee59e482f7b35428cccc4f71705e7e322442d07d1f7d29b5d9e72e31319fc3088d6dcbec9fc7c1f0d8881 "$archive" | sha512sum -c -
python3 - "$archive" <<'PY'
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys
import tarfile
import tempfile

root = Path('/opt/bifang/gvisor')
destination = root / 'release-20261019.0'
checksum = '7cbc2aeeee809dcccfb40e612504a1b76f2c119790cee59e482f7b35428cccc4f71705e7e322442d07d1f7d29b5d9e72e31319fc3088d6dcbec9fc7c1f0d8881'
if destination.exists():
    assert not destination.is_symlink() and (destination / '.archive-sha512').read_text().strip() == checksum
else:
    staging = Path(tempfile.mkdtemp(prefix='.install-', dir=root))
    with tarfile.open(sys.argv[1], 'r:bz2') as archive:
        members = archive.getmembers()
        assert sum(member.size for member in members) <= 512 * 1024 * 1024
        for member in members:
            path = PurePosixPath(member.name)
            assert not path.is_absolute() and '..' not in path.parts and (member.isfile() or member.isdir())
            member.uid = member.gid = 0
            member.mode = 0o755 if member.isdir() or member.mode & 0o111 else 0o644
            archive.extract(member, path=staging)
    assert (staging / 'runsc').is_file() and (staging / 'gvisor-bin').is_dir()
    (staging / '.archive-sha512').write_text(checksum + '\n')
    staging.chmod(0o755)
    os.rename(staging, destination)
binary = destination / 'runsc'
version = subprocess.check_output([str(binary), '--version'], text=True)
assert version.splitlines()[0] == 'runsc version release-20261019.0'
configuration = Path('/etc/docker/daemon.json')
original = configuration.read_text() if configuration.exists() else '{}'
settings = json.loads(original)
runtime = {'path': str(binary), 'runtimeArgs': ['--platform=systrap', '--network=none']}
existing = settings.setdefault('runtimes', {}).get('bifang-runsc')
assert existing is None or existing == runtime
backup = root / 'docker-daemon-before-20261025.json'
if not backup.exists():
    descriptor = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'w') as stream:
        stream.write(original)
settings['runtimes']['bifang-runsc'] = runtime
descriptor, name = tempfile.mkstemp(prefix='.bifang-daemon-', dir=configuration.parent)
with os.fdopen(descriptor, 'w') as stream:
    json.dump(settings, stream)
    stream.flush()
    os.fsync(stream.fileno())
os.replace(name, configuration)
print(json.dumps({'runtime_version': version.splitlines()[0], 'runtime_sha256': hashlib.sha256(binary.read_bytes()).hexdigest()}))
PY
systemctl reload docker
docker pull python:3.11-slim@sha256:b7a9e5f6a93d6d4a31f129bbd4bdee69efccb6ded0fb230d78aafaf37af98377
install -d -m 0700 /var/lib/bifang-state/executor-scratch
python3 - <<'PY'
import hashlib
import json
from pathlib import Path
import subprocess

binary = Path('/opt/bifang/gvisor/release-20261019.0/runsc')
image = subprocess.check_output(['docker','image','inspect','python:3.11-slim@sha256:b7a9e5f6a93d6d4a31f129bbd4bdee69efccb6ded0fb230d78aafaf37af98377','--format','{{.Id}}'], text=True).strip()
settings = {'image': image, 'runtime_binary': str(binary), 'runtime_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(),
            'scratch': '/var/lib/bifang-state/executor-scratch'}
path = Path('/opt/bifang/gvisor/executor-config.json')
path.write_text(json.dumps(settings, indent=2) + '\n')
path.chmod(0o600)
print(json.dumps({'execution_image': image, 'runtime_configuration_prepared': True}))
PY
systemctl is-active --quiet bifang-remote
curl --fail --silent http://127.0.0.1:8125/health
