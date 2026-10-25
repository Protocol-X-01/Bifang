#!/bin/bash
set -euo pipefail
test "$(id -u)" = 0
configuration=/etc/nginx/conf.d/bifang-https.conf
test -f "$configuration"
backup=$(mktemp /etc/nginx/conf.d/.bifang-https-backup.XXXXXX)
trap 'rm -f "$backup"' EXIT
cp -p "$configuration" "$backup"
python3 - "$configuration" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
content = path.read_text()
anchor = "        proxy_pass http://127.0.0.1:8125;"
assert content.count(anchor) == 1
for header in ("Cache-Control", "X-Content-Type-Options"):
    directive = "        proxy_hide_header " + header + ";"
    if directive not in content:
        content = content.replace(anchor, directive + "\n" + anchor)
path.write_text(content)
PY
if ! nginx -t; then
    cp -p "$backup" "$configuration"
    exit 1
fi
systemctl reload nginx
printf 'Bifang HTTPS response headers normalized\n'
