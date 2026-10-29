#!/bin/bash
set -euo pipefail
test "$(id -u)" = 0
mountpoint -q /var/lib/bifang-state
test -f /opt/bifang/gvisor/executor-config.json
test -z "$(docker ps --quiet --filter label=bifang.executor=1)"
if getent group 10001 >/dev/null; then
    test "$(getent group 10001 | cut -d: -f1)" = bifang-clients
else
    groupadd --gid 10001 bifang-clients
fi
install -m 0700 remote_executor.py /usr/local/libexec/bifang-executor.py
install -m 0700 cleanup-executor.py /usr/local/libexec/bifang-executor-clean.py
install -m 0700 wait-executor.py /usr/local/libexec/bifang-wait-executor.py
python3 - <<'PY'
import json
from pathlib import Path
import re

settings = json.loads(Path('/opt/bifang/gvisor/executor-config.json').read_text())
assert re.fullmatch(r'sha256:[a-f0-9]{64}', settings['image'])
assert re.fullmatch(r'[a-f0-9]{64}', settings['runtime_sha256'])
assert settings['runtime_binary'] == '/opt/bifang/gvisor/release-20261019.0/runsc'
assert settings['scratch'] == '/var/lib/bifang-state/executor-scratch'
command = '/usr/bin/python3 /usr/local/libexec/bifang-executor.py --image {image} --runtime-binary {runtime_binary} --runtime-sha256 {runtime_sha256} --scratch {scratch} --socket /run/bifang-executor/check.sock'.format(**settings)
unit = '''[Unit]
Description=Bifang narrow isolated check broker
After=docker.service
Requires=docker.service
RequiresMountsFor=/var/lib/bifang-state/executor-scratch
StartLimitIntervalSec=120
StartLimitBurst=3

[Service]
Type=simple
Group=bifang-clients
RuntimeDirectory=bifang-executor
RuntimeDirectoryMode=0750
RuntimeDirectoryPreserve=yes
ExecStartPre=/usr/bin/python3 /usr/local/libexec/bifang-executor-clean.py --scratch /var/lib/bifang-state/executor-scratch --socket /run/bifang-executor/check.sock
ExecStart={command}
ExecStartPost=/usr/bin/python3 /usr/local/libexec/bifang-wait-executor.py
ExecStopPost=/usr/bin/python3 /usr/local/libexec/bifang-executor-clean.py --scratch /var/lib/bifang-state/executor-scratch --socket /run/bifang-executor/check.sock
KillSignal=SIGINT
Restart=on-failure
RestartSec=5
TimeoutStartSec=60
TimeoutStopSec=30
UMask=0077
NoNewPrivileges=yes
CapabilityBoundingSet=CAP_CHOWN CAP_DAC_OVERRIDE CAP_FOWNER
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes
PrivateDevices=yes
RestrictAddressFamilies=AF_UNIX
ReadWritePaths=/run/bifang-executor /var/lib/bifang-state/executor-scratch
InaccessiblePaths=-/run/bifang -/var/lib/bifang-state/jobs

[Install]
WantedBy=multi-user.target
'''.format(command=command)
Path('/etc/systemd/system/bifang-executor.service').write_text(unit)
PY
chmod 0644 /etc/systemd/system/bifang-executor.service
systemd-analyze verify /etc/systemd/system/bifang-executor.service
systemctl daemon-reload
systemctl enable bifang-executor.service
systemctl restart bifang-executor.service
systemctl is-active --quiet bifang-executor.service
test "$(stat -c '%a' /run/bifang-executor)" = 750
test "$(stat -c '%g' /run/bifang-executor)" = 10001
test "$(stat -c '%a' /run/bifang-executor/check.sock)" = 600
printf 'Private executor broker ready\n'
