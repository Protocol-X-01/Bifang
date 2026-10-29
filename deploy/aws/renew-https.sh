#!/bin/bash
set -euo pipefail
test "$(id -u)" = 0
mountpoint -q /var/lib/bifang-state
image=$(cat /etc/bifang/certbot-image)
[[ "$image" =~ ^certbot/certbot@sha256:[a-f0-9]{64}$ ]]
test "$#" = 0 || { test "$#" = 1 && test "$1" = --dry-run; }
docker run --rm --read-only --cap-drop ALL --security-opt no-new-privileges \
    --memory 256m --cpus 1 --pids-limit 128 --tmpfs /tmp:rw,nosuid,noexec,size=32m \
    --mount type=bind,src=/var/lib/bifang-state/tls/production,dst=/etc/letsencrypt \
    --mount type=bind,src=/var/lib/bifang-state/acme/www,dst=/var/www/acme \
    "$image" renew --quiet --no-random-sleep-on-renew --work-dir /tmp/work --logs-dir /tmp/logs "$@"
nginx -t
systemctl reload nginx
