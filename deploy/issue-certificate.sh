#!/usr/bin/env bash
# Issue a Let's Encrypt certificate after DNS points DOMAIN at this ECS host.
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/company-brain}"
DOMAIN="${DOMAIN:-brain.veriflowai.me}"
LETSENCRYPT_EMAIL="${LETSENCRYPT_EMAIL:?Set LETSENCRYPT_EMAIL before issuing a certificate}"

cd "$APP_DIR"
COMPOSE=(docker compose -f docker-compose.yml -f deploy/docker-compose.tls.yml)

# nginx starts in an HTTP bootstrap mode before the certificate exists. It
# serves only as much as necessary for the webroot challenge and keeps the
# existing public-IP demonstration route reachable while DNS is pending.
"${COMPOSE[@]}" --profile full up -d mongodb api nginx

DNS_IPS="$(getent ahostsv4 "$DOMAIN" 2>/dev/null | awk '{print $1}' | sort -u || true)"
PUBLIC_IP="$(curl -fsS --max-time 8 ifconfig.me 2>/dev/null || true)"
if [ -z "$PUBLIC_IP" ] || [ -z "$DNS_IPS" ] || ! printf '%s\n' "$DNS_IPS" | grep -Fxq "$PUBLIC_IP"; then
    echo "DNS for $DOMAIN does not yet resolve to this host (public IP: ${PUBLIC_IP:-unknown})." >&2
    echo "Add the A record first, wait for propagation, then rerun this script." >&2
    exit 2
fi

"${COMPOSE[@]}" --profile tls run --rm certbot certonly \
    --webroot \
    --webroot-path /var/www/certbot \
    --email "$LETSENCRYPT_EMAIL" \
    --agree-tos \
    --no-eff-email \
    --non-interactive \
    --keep-until-expiring \
    -d "$DOMAIN"

set_env_value() {
    key="$1"
    value="$2"
    if grep -q "^${key}=" .env; then
        sed -i "s|^${key}=.*|${key}=${value}|" .env
    else
        printf '\n%s=%s\n' "$key" "$value" >> .env
    fi
}

# Do not advertise a public remote connector until the certificate exists.
set_env_value PUBLIC_BASE_URL "https://${DOMAIN}"
set_env_value MCP_SERVER_URL "https://${DOMAIN}/mcp/"
set_env_value MCP_REMOTE_ENABLED true
set_env_value MCP_REQUIRE_API_KEY true
set_env_value MCP_LEGACY_SSE_ENABLED false
set_env_value MCP_ALLOWED_ORIGINS "https://${DOMAIN}"
set_env_value CORS_ALLOWED_ORIGINS "https://${DOMAIN}"

"${COMPOSE[@]}" --profile full up -d --force-recreate api nginx
"${COMPOSE[@]}" --profile full exec -T nginx nginx -t

# The API is recreated immediately before nginx. Give it a short readiness
# window so certificate issuance does not report a false failure on a healthy
# deployment that is still starting its application process.
for attempt in $(seq 1 15); do
    if curl --fail --silent --show-error --resolve "${DOMAIN}:443:127.0.0.1" \
        "https://${DOMAIN}/api/health" >/dev/null; then
        break
    fi
    if [ "$attempt" -eq 15 ]; then
        echo "HTTPS health check did not become ready after certificate issuance." >&2
        exit 1
    fi
    sleep 2
done

echo "TLS enabled: https://${DOMAIN}/app/inbox"
