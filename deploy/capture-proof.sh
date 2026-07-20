#!/usr/bin/env bash
# Capture non-secret HTTP proof after ECS/TLS is live.
set -euo pipefail

BASE_URL="${BASE_URL:-https://brain.veriflowai.me}"
OUT_DIR="${OUT_DIR:-docs/assets/deployment-proof-$(date -u +%Y%m%dT%H%M%SZ)}"
mkdir -p "$OUT_DIR"

echo "==> Capturing public proof from $BASE_URL"
curl --fail --silent --show-error --max-time 20 "$BASE_URL/api/health" > "$OUT_DIR/health.json"
curl --fail --silent --show-error --max-time 20 "$BASE_URL/api/demo/readiness" > "$OUT_DIR/readiness.json"
curl --fail --silent --show-error --max-time 20 "$BASE_URL/api/integration-catalog" > "$OUT_DIR/integration-catalog.json"
curl --fail --silent --show-error --max-time 20 --head "$BASE_URL/" > "$OUT_DIR/https-headers.txt"

echo "Captured non-secret health, readiness, integration-catalog, and HTTPS headers in $OUT_DIR"
echo "Do not place MCP API keys, provider secrets, or Workbench account identifiers in this directory."
