#!/bin/bash
set -euo pipefail
image="$1"
previous="$2"
[[ "$image" =~ ^sha256:[a-f0-9]{64}$ ]]
[[ "$previous" =~ ^sha256:[a-f0-9]{64}$ ]]
test "$(id -u)" = 0
mountpoint -q /var/lib/bifang-state
systemctl is-active --quiet bifang-executor
systemctl is-active --quiet bifang-remote
test "$(docker inspect --format '{{.Image}}' bifang-remote)" = "$previous"
test "$(docker image inspect "$image" --format '{{.Id}}')" = "$image"
test "$(stat -c '%u' /var/lib/bifang-state/jobs)" = 10001
test "$(stat -c '%a' /var/lib/bifang-state/jobs)" = 700
test ! -e /var/lib/bifang-state/backups/pre-coding-promotion-20261025.sqlite3
test ! -e /opt/bifang/remote-before-coding-20261025.service
active=$(docker exec bifang-remote python -c "import sqlite3; connection=sqlite3.connect('file:/var/lib/bifang/review-jobs.sqlite3?mode=ro',uri=True); print(connection.execute(\"SELECT count(*) FROM review_jobs WHERE status IN ('queued','running','cancelling')\").fetchone()[0]); connection.close()")
test "$active" = 0
install -m 0600 /etc/systemd/system/bifang-remote.service /opt/bifang/remote-before-coding-20261025.service
rollback() {
    code=$?
    trap - ERR
    install -m 0644 /opt/bifang/remote-before-coding-20261025.service /etc/systemd/system/bifang-remote.service
    systemctl daemon-reload
    systemctl reset-failed bifang-remote.service
    systemctl restart bifang-remote.service
    printf 'Promotion failed; previous service configuration restored\n' >&2
    exit "$code"
}
trap rollback ERR
systemctl stop bifang-remote.service
install -d -m 0700 -o 10001 -g 10001 /var/lib/bifang-state/backups
docker run --rm --network none --read-only --cap-drop ALL --security-opt no-new-privileges \
    --memory 256m --cpus 1 --pids-limit 64 --tmpfs /tmp:rw,nosuid,noexec,size=16m \
    --mount type=bind,src=/var/lib/bifang-state/jobs,dst=/source \
    --mount type=bind,src=/var/lib/bifang-state/backups,dst=/backups \
    "$image" python -m bifang.remote_backup --state /source --destination /backups/pre-coding-promotion-20261025.sqlite3
test "$(stat -c '%a' /var/lib/bifang-state/backups/pre-coding-promotion-20261025.sqlite3)" = 600
install -m 0700 wait-coding-ready.py /usr/local/libexec/bifang-wait-coding-ready.py
cat > /etc/systemd/system/bifang-remote.service <<EOF
[Unit]
Description=Bifang authenticated reviews and independently checked coding
After=network-online.target docker.service bifang-executor.service
Wants=network-online.target bifang-executor.service
Requires=docker.service
RequiresMountsFor=/var/lib/bifang-state/jobs
StartLimitIntervalSec=120
StartLimitBurst=3

[Service]
Type=simple
ExecStartPre=/usr/bin/install -d -m 0700 /run/bifang
ExecStartPre=/usr/bin/python3 /usr/local/libexec/bifang-fetch-runtime-env.py
ExecStartPre=-/usr/bin/docker rm -f bifang-remote
ExecStart=/usr/bin/docker run --rm --name bifang-remote --env-file /run/bifang/service.env --env BIFANG_REMOTE_CODING_SOCKET=/run/bifang-executor/check.sock --read-only --cap-drop ALL --security-opt no-new-privileges --memory 512m --cpus 1 --pids-limit 128 --tmpfs /tmp:rw,nosuid,noexec,size=16m --log-driver json-file --log-opt max-size=10m --log-opt max-file=3 --mount type=bind,src=/var/lib/bifang-state/jobs,dst=/var/lib/bifang --mount type=bind,src=/run/bifang-executor,dst=/run/bifang-executor,readonly -p 127.0.0.1:8125:8125 $image
ExecStartPost=/usr/bin/python3 /usr/local/libexec/bifang-wait-coding-ready.py
ExecStop=/usr/bin/docker stop -t 20 bifang-remote
ExecStopPost=-/usr/bin/docker rm -f bifang-remote
ExecStopPost=/usr/bin/rm -f /run/bifang/service.env
Restart=on-failure
RestartSec=5
TimeoutStartSec=120
TimeoutStopSec=30

[Install]
WantedBy=multi-user.target
EOF
chmod 0644 /etc/systemd/system/bifang-remote.service
systemd-analyze verify /etc/systemd/system/bifang-remote.service
systemctl daemon-reload
systemctl reset-failed bifang-remote.service
systemctl start bifang-remote.service
systemctl is-active --quiet bifang-remote.service
test ! -e /run/bifang/service.env
test "$(docker inspect --format '{{.Image}}' bifang-remote)" = "$image"
trap - ERR
sha256sum /var/lib/bifang-state/backups/pre-coding-promotion-20261025.sqlite3
printf 'Verified coding image promoted; previous unit and backup retained\n'
