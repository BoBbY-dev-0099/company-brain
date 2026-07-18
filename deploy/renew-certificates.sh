#!/usr/bin/env bash
# Host-side renewal command used by companybrain-certbot-renew.timer.
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/company-brain}"
cd "$APP_DIR"

docker compose -f docker-compose.yml -f deploy/docker-compose.tls.yml \
    --profile tls run --rm certbot renew --webroot --webroot-path /var/www/certbot --quiet
docker compose -f docker-compose.yml -f deploy/docker-compose.tls.yml \
    --profile full exec -T nginx nginx -s reload
