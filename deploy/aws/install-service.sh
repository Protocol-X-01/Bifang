#!/bin/bash
set -euo pipefail
image="$1"
[[ "$image" =~ ^sha256:[a-f0-9]{64}$ ]]
test "$(id -u)" = 0
mountpoint -q /var/lib/bifang-state
test "$(stat -c '%a' /var/lib/bifang-state/jobs)" = 700
test "$(stat -c '%u' /var/lib/bifang-state/jobs)" = 10001
test "$(docker image inspect "$image" --format '{{.Id}}')" = "$image"
install -d -m 0700 /run/bifang
install -d -m 0755 /usr/local/libexec
install -m 0700 fetch-runtime-env.py /usr/local/libexec/bifang-fetch-runtime-env.py
install -m 0700 wait-service-ready.py /usr/local/libexec/bifang-wait-service-ready.py
cat > /etc/systemd/system/bifang-remote.service <<EOF
[Unit]
Description=Bifang authenticated remote review worker
After=network-online.target docker.service
Wants=network-online.target
Requires=docker.service
RequiresMountsFor=/var/lib/bifang-state/jobs
StartLimitIntervalSec=120
StartLimitBurst=3

[Service]
Type=simple
ExecStartPre=/usr/bin/install -d -m 0700 /run/bifang
ExecStartPre=/usr/bin/python3 /usr/local/libexec/bifang-fetch-runtime-env.py
ExecStartPre=-/usr/bin/docker rm -f bifang-remote
ExecStart=/usr/bin/docker run --rm --name bifang-remote --env-file /run/bifang/service.env --read-only --cap-drop ALL --security-opt no-new-privileges --memory 512m --cpus 1 --pids-limit 128 --tmpfs /tmp:rw,nosuid,noexec,size=16m --log-driver json-file --log-opt max-size=10m --log-opt max-file=3 --mount type=bind,src=/var/lib/bifang-state/jobs,dst=/var/lib/bifang -p 127.0.0.1:8125:8125 $image
ExecStartPost=/usr/bin/python3 /usr/local/libexec/bifang-wait-service-ready.py
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
systemctl daemon-reload
systemctl enable --now bifang-remote.service
systemctl is-active --quiet bifang-remote.service
test ! -e /run/bifang/service.env
