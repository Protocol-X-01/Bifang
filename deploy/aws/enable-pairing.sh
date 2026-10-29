#!/bin/bash
set -euo pipefail
image="$1"
previous="$2"
revision="${3:-20261026}"
[[ "$revision" =~ ^[0-9]{8}(-r[0-9]+)?$ ]]
[[ "$image" =~ ^sha256:[a-f0-9]{64}$ ]]
[[ "$previous" =~ ^sha256:[a-f0-9]{64}$ ]]
test "$(id -u)" = 0
mountpoint -q /var/lib/bifang-state
systemctl is-active --quiet bifang-remote bifang-executor
test "$(docker inspect --format '{{.Image}}' bifang-remote)" = "$previous"
test "$(docker image inspect "$image" --format '{{.Id}}')" = "$image"
active=$(docker exec bifang-remote python -c "import sqlite3; connection=sqlite3.connect('file:/var/lib/bifang/review-jobs.sqlite3?mode=ro',uri=True); print(connection.execute(\"SELECT (SELECT count(*) FROM review_jobs WHERE status IN ('queued','running','cancelling'))+(SELECT count(*) FROM coding_jobs WHERE status NOT IN ('rejected','check_denied','check_failed','applied','cancelled','failed','interrupted','deleted'))\").fetchone()[0]); connection.close()")
test "$active" = 0
backup="/opt/bifang/pre-pairing-$revision"
test ! -e "$backup"
install -d -m 0700 "$backup"
install -m 0600 /etc/systemd/system/bifang-remote.service "$backup/remote.service"
install -m 0600 /usr/local/libexec/bifang-fetch-runtime-env.py "$backup/fetch-runtime-env.py"
rollback() {
    code=$?
    trap - ERR
    install -m 0644 "$backup/remote.service" /etc/systemd/system/bifang-remote.service
    install -m 0700 "$backup/fetch-runtime-env.py" /usr/local/libexec/bifang-fetch-runtime-env.py
    systemctl daemon-reload
    systemctl reset-failed bifang-remote
    systemctl restart bifang-remote
    printf 'Pairing update failed; previous service and fetcher restored\n' >&2
    exit "$code"
}
trap rollback ERR
systemctl stop bifang-remote
install -d -m 0700 -o 10001 -g 10001 /var/lib/bifang-state/backups
docker run --rm --network none --read-only --cap-drop ALL --security-opt no-new-privileges --memory 256m --pids-limit 64 \
    --tmpfs /tmp:rw,nosuid,noexec,size=16m \
    --mount type=bind,src=/var/lib/bifang-state/jobs,dst=/source \
    --mount type=bind,src=/var/lib/bifang-state/backups,dst=/backups \
    "$image" python -m bifang.remote_backup --state /source --destination "/backups/pre-pairing-$revision.sqlite3"
if test -e /var/lib/bifang-state/jobs/device-pairing.sqlite3; then
    docker run --rm --network none --read-only --cap-drop ALL --security-opt no-new-privileges --memory 256m --pids-limit 64 \
        --mount type=bind,src=/var/lib/bifang-state/jobs,dst=/source,readonly \
        --mount type=bind,src=/var/lib/bifang-state/backups,dst=/backups \
        "$image" python -m bifang.pairing_backup --source /source/device-pairing.sqlite3 --destination "/backups/pre-pairing-auth-$revision.sqlite3"
fi
install -m 0700 fetch-runtime-env.py /usr/local/libexec/bifang-fetch-runtime-env.py
python3 - "$image" "$previous" <<'PY'
from pathlib import Path
import sys
path = Path('/etc/systemd/system/bifang-remote.service')
content = path.read_text()
if content.count(sys.argv[2]) != 1:
    raise RuntimeError('Existing service image binding differs; no replacement made')
path.write_text(content.replace(sys.argv[2], sys.argv[1]))
PY
systemd-analyze verify /etc/systemd/system/bifang-remote.service
systemctl daemon-reload
systemctl reset-failed bifang-remote
systemctl start bifang-remote
systemctl is-active --quiet bifang-remote bifang-executor
test "$(docker inspect --format '{{.Image}}' bifang-remote)" = "$image"
test ! -e /run/bifang/service.env
curl --fail --silent http://127.0.0.1:8125/health
trap - ERR
printf '\nPairing-capable image ready; existing service binding and private backup retained\n'
