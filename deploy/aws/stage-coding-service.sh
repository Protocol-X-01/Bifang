#!/bin/bash
set -euo pipefail
image="$1"
[[ "$image" =~ ^sha256:[a-f0-9]{64}$ ]]
test "$(id -u)" = 0
mountpoint -q /var/lib/bifang-state
systemctl is-active --quiet bifang-executor
test "$(docker image inspect "$image" --format '{{.Id}}')" = "$image"
if docker container inspect bifang-coding-stage >/dev/null 2>&1; then
    printf 'Inspect existing staging container; refusing replacement\n' >&2
    exit 1
fi
install -d -m 0700 /run/bifang-coding-stage
install -d -m 0700 -o 10001 -g 10001 /var/lib/bifang-state/coding-stage
trap 'rm -f /run/bifang-coding-stage/service.env' EXIT
python3 - <<'PY'
import importlib.util
import hashlib
import json
import os
from pathlib import Path
import secrets

specification = importlib.util.spec_from_file_location('private_runtime', '/usr/local/libexec/bifang-fetch-runtime-env.py')
module = importlib.util.module_from_spec(specification)
specification.loader.exec_module(module)
module.fetch_environment(Path('/run/bifang-coding-stage/service.env'))
clients = {'owner':secrets.token_urlsafe(48),'other':secrets.token_urlsafe(48)}
registry = json.dumps([{'subject':subject,'token_sha256':hashlib.sha256(value.encode()).hexdigest()}
                       for subject,value in clients.items()],separators=(',',':'))
path=Path('/run/bifang-coding-stage/service.env')
lines=path.read_text().splitlines()
path.write_text('\n'.join('BIFANG_REMOTE_CLIENTS='+registry if line.startswith('BIFANG_REMOTE_CLIENTS=') else line for line in lines)+'\n')
descriptor=os.open('/run/bifang-coding-stage/fixture-clients.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
with os.fdopen(descriptor,'w') as stream:
    json.dump(clients,stream)
PY
docker run --detach --rm --name bifang-coding-stage --env-file /run/bifang-coding-stage/service.env \
    --env BIFANG_REMOTE_CODING_SOCKET=/run/bifang-executor/check.sock \
    --read-only --cap-drop ALL --security-opt no-new-privileges --memory 512m --cpus 1 --pids-limit 128 \
    --tmpfs /tmp:rw,nosuid,noexec,size=16m --log-driver json-file --log-opt max-size=10m --log-opt max-file=3 \
    --mount type=bind,src=/var/lib/bifang-state/coding-stage,dst=/var/lib/bifang \
    --mount type=bind,src=/run/bifang-executor,dst=/run/bifang-executor,readonly \
    -p 127.0.0.1:8126:8125 "$image" >/dev/null
python3 - <<'PY'
import json
import time
from urllib.request import urlopen

for attempt in range(100):
    try:
        with urlopen('http://127.0.0.1:8126/health',timeout=2) as response:
            value=json.load(response)
        if value.get('status')=='ok' and value.get('coding_enabled') is True:
            print(json.dumps({'private_staging_coding_ready':True,'public_coding_enabled':False}))
            break
    except (OSError,ValueError):
        pass
    time.sleep(0.2)
else:
    raise SystemExit('Coding staging readiness failed; inspect existing container, not a replacement')
PY
curl --fail --silent http://127.0.0.1:8125/health
