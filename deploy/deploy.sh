#!/usr/bin/env bash
# Deploy Company Brain on Alibaba Cloud ECS with a safe HTTP-to-HTTPS path.
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/company-brain}"
REPO_URL="${REPO_URL:-https://github.com/BoBbY-dev-0099/company-brain.git}"
BRANCH="${BRANCH:-main}"
DOMAIN="${DOMAIN:-brain.veriflowai.me}"

echo "==> Company Brain ECS deploy"
echo "    APP_DIR=$APP_DIR"
echo "    DOMAIN=$DOMAIN"

if ! command -v docker >/dev/null 2>&1; then
  echo "==> Installing Docker"
  curl -fsSL https://get.docker.com | sh
  systemctl enable --now docker
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "==> Docker Compose plugin missing"
  exit 1
fi

mkdir -p "$(dirname "$APP_DIR")"
if [ ! -d "$APP_DIR/.git" ]; then
  git clone -b "$BRANCH" "$REPO_URL" "$APP_DIR"
else
  # The provisioned ECS image may ship Git 1.8, which predates `git -C`.
  (
    cd "$APP_DIR"
    git fetch origin "$BRANCH"
    git checkout "$BRANCH"
    git pull --ff-only origin "$BRANCH"
  )
fi

cd "$APP_DIR"

# Keep the runtime self-identifying. Docker Compose passes this through to the
# API, which exposes it from /demo/readiness for deployment proof.
export BUILD_SHA="$(git rev-parse HEAD)"
export DOMAIN
echo "    BUILD_SHA=$BUILD_SHA"

if [ ! -f .env ]; then
  if [ -f .env.example ]; then
    cp .env.example .env
    echo "Created .env from .env.example - set QWEN_API_KEY before serving traffic."
  else
    echo "Missing .env" >&2
    exit 1
  fi
fi

mkdir -p secrets
chmod 700 secrets || true

COMPOSE=(docker compose -f docker-compose.yml -f deploy/docker-compose.tls.yml)
# Force recreation so newly published ports (notably 443 during the first TLS
# rollout) are applied even if Compose considers the existing service image
# current.
"${COMPOSE[@]}" --profile full up --build -d --force-recreate
"${COMPOSE[@]}" --profile full ps

PUBLIC_IP="$(curl -s --max-time 5 ifconfig.me || hostname -I | awk '{print $1}')"
echo ""
echo "HTTP bootstrap: http://${PUBLIC_IP}"
echo "Health: curl -s http://127.0.0.1/api/health"
echo "Readiness: curl -s http://127.0.0.1/api/demo/readiness"
echo "TDX guest: ls -l /dev/tdx_guest 2>/dev/null || echo RSA fallback"

if [ "${ISSUE_TLS_CERTIFICATE:-false}" = "true" ]; then
  : "${LETSENCRYPT_EMAIL:?Set LETSENCRYPT_EMAIL when ISSUE_TLS_CERTIFICATE=true}"
  APP_DIR="$APP_DIR" DOMAIN="$DOMAIN" LETSENCRYPT_EMAIL="$LETSENCRYPT_EMAIL" \
    bash deploy/issue-certificate.sh
  echo "Install the renewal timer once:"
  echo "  sudo cp deploy/companybrain-certbot-renew.{service,timer} /etc/systemd/system/"
  echo "  sudo systemctl daemon-reload && sudo systemctl enable --now companybrain-certbot-renew.timer"
else
  echo "TLS is not issued yet. The public-IP HTTP bootstrap remains available."
  echo "After DNS A ${DOMAIN} -> ${PUBLIC_IP} and ECS TCP/443 are ready, run:"
  echo "  ISSUE_TLS_CERTIFICATE=true LETSENCRYPT_EMAIL=you@example.com sudo bash deploy/deploy.sh"
fi
