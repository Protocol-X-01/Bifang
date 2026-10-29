#!/bin/bash
set -euo pipefail
address="$1"
test "$(id -u)" = 0
python3 -c 'import ipaddress,sys; assert ipaddress.ip_address(sys.argv[1]).version == 4' "$address"
mountpoint -q /var/lib/bifang-state
image=$(cat /etc/bifang/certbot-image)
[[ "$image" =~ ^certbot/certbot@sha256:[a-f0-9]{64}$ ]]
for environment in staging production; do
    options=()
    if test "$environment" = staging; then options+=(--staging); fi
    docker run --rm --read-only --cap-drop ALL --security-opt no-new-privileges \
        --memory 256m --cpus 1 --pids-limit 128 --tmpfs /tmp:rw,nosuid,noexec,size=32m \
        --mount "type=bind,src=/var/lib/bifang-state/tls/$environment,dst=/etc/letsencrypt" \
        --mount type=bind,src=/var/lib/bifang-state/acme/www,dst=/var/www/acme \
        "$image" certonly --non-interactive --agree-tos --register-unsafely-without-email \
        --preferred-profile shortlived --webroot --webroot-path /var/www/acme \
        --ip-address "$address" --cert-name bifang-ip --keep-until-expiring \
        --work-dir /tmp/work --logs-dir /tmp/logs "${options[@]}"
done
cat > /etc/nginx/conf.d/bifang-https.conf <<'EOF'
server {
    listen 443 ssl default_server;
    server_name _;
    ssl_certificate /var/lib/bifang-state/tls/production/live/bifang-ip/fullchain.pem;
    ssl_certificate_key /var/lib/bifang-state/tls/production/live/bifang-ip/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_session_cache shared:BIFANG_TLS:1m;
    ssl_session_timeout 10m;
    add_header Cache-Control "no-store" always;
    add_header X-Content-Type-Options "nosniff" always;
    location / {
        limit_req zone=bifang burst=20 nodelay;
        proxy_hide_header Cache-Control;
        proxy_hide_header X-Content-Type-Options;
        proxy_pass http://127.0.0.1:8125;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header Connection "";
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_read_timeout 90s;
        proxy_buffering off;
    }
}
EOF
install -m 0700 renew-https.sh /usr/local/libexec/bifang-renew-https.sh
cat > /etc/systemd/system/bifang-renew-https.service <<'EOF'
[Unit]
Description=Renew Bifang short-lived IP certificate and reload HTTPS
After=network-online.target docker.service nginx.service
Wants=network-online.target
Requires=docker.service nginx.service
RequiresMountsFor=/var/lib/bifang-state/tls/production

[Service]
Type=oneshot
ExecStart=/usr/local/libexec/bifang-renew-https.sh
TimeoutStartSec=300
EOF
cat > /etc/systemd/system/bifang-renew-https.timer <<'EOF'
[Unit]
Description=Check Bifang IP certificate renewal twice daily

[Timer]
OnCalendar=*-*-* 00,12:00:00
RandomizedDelaySec=1800
Persistent=true

[Install]
WantedBy=timers.target
EOF
nginx -t
systemctl reload nginx
systemctl daemon-reload
systemctl enable --now bifang-renew-https.timer
/usr/local/libexec/bifang-renew-https.sh --dry-run
curl --fail --silent --resolve "$address:443:127.0.0.1" "https://$address/health"
systemctl is-enabled --quiet bifang-renew-https.timer
printf '\nTrusted HTTPS and renewal dry-run verified\n'
