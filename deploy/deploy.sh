#!/usr/bin/env bash
# Deploy Company Brain on Alibaba Cloud ECS (Docker Compose full profile).
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/company-brain}"
REPO_URL="${REPO_URL:-https://github.com/BoBbY-dev-0099/company-brain.git}"
BRANCH="${BRANCH:-main}"

echo "==> Company Brain ECS deploy"
echo "    APP_DIR=$APP_DIR"

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
  # The provisioned ECS image ships Git 1.8, which predates `git -C`.
  # Enter the checkout explicitly so this deploy path remains portable to
  # older Alibaba Cloud images as well as modern local environments.
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
echo "    BUILD_SHA=$BUILD_SHA"

if [ ! -f .env ]; then
  if [ -f .env.example ]; then
    cp .env.example .env
    echo "Created .env from .env.example — set QWEN_API_KEY before serving traffic."
  else
    echo "Missing .env" >&2
    exit 1
  fi
fi

mkdir -p secrets
chmod 700 secrets || true

docker compose --profile full up --build -d
docker compose --profile full ps

PUBLIC_IP="$(curl -s --max-time 5 ifconfig.me || hostname -I | awk '{print $1}')"
echo ""
echo "App running at http://${PUBLIC_IP}"
echo "Health: curl -s http://127.0.0.1/api/health"
echo "Readiness: curl -s http://127.0.0.1/api/demo/readiness"
echo "TDX guest: ls -l /dev/tdx_guest 2>/dev/null || echo RSA fallback"
