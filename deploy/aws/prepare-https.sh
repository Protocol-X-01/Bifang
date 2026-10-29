#!/bin/bash
set -euo pipefail
address="$1"
test "$(id -u)" = 0
python3 -c 'import ipaddress,sys; assert ipaddress.ip_address(sys.argv[1]).version == 4' "$address"
mountpoint -q /var/lib/bifang-state
systemctl is-active --quiet bifang-remote.service
dnf install -y nginx
install -d -m 0755 /var/lib/bifang-state/acme/www/.well-known/acme-challenge
install -d -m 0700 /var/lib/bifang-state/tls/staging /var/lib/bifang-state/tls/production
docker pull certbot/certbot:v5.8.0
image=$(docker image inspect certbot/certbot:v5.8.0 --format '{{index .RepoDigests 0}}')
[[ "$image" =~ ^certbot/certbot@sha256:[a-f0-9]{64}$ ]]
install -d -m 0755 /etc/bifang
printf '%s\n' "$image" > /etc/bifang/certbot-image
chmod 0644 /etc/bifang/certbot-image
cat > /etc/nginx/nginx.conf <<'EOF'
user nginx;
worker_processes auto;
error_log /var/log/nginx/error.log warn;
pid /run/nginx.pid;
events { worker_connections 512; }
http {
    server_tokens off;
    access_log off;
    client_max_body_size 400000;
    client_body_timeout 15s;
    client_header_timeout 15s;
    send_timeout 90s;
    limit_req_zone $binary_remote_addr zone=bifang:10m rate=5r/s;
    limit_req_status 429;
    include /etc/nginx/conf.d/bifang-*.conf;
}
EOF
cat > /etc/nginx/conf.d/bifang-acme.conf <<'EOF'
server {
    listen 80 default_server;
    server_name _;
    location ^~ /.well-known/acme-challenge/ {
        root /var/lib/bifang-state/acme/www;
        default_type text/plain;
        limit_except GET { deny all; }
        try_files $uri =404;
    }
    location / { return 404; }
}
EOF
nginx -t
systemctl enable --now nginx
systemctl reload nginx
test "$(curl --silent --output /dev/null --write-out '%{http_code}' http://127.0.0.1/v1/reviews)" = 404
printf 'ACME listener prepared; provider calls: 0\n'
