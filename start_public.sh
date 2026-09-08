#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PORT="${JCSMS_PORT:-8080}"
RESOLV_FILE="/tmp/jcsms-resolv.conf"

mkdir -p "${PROJECT_DIR}/logs"

if ! curl -fsS --max-time 2 "http://127.0.0.1:${PORT}/health" >/dev/null 2>&1; then
  nohup "${PROJECT_DIR}/start.sh" >"${PROJECT_DIR}/logs/server.log" 2>&1 &
  SERVER_PID=$!
  echo "JCSMS server started, pid=${SERVER_PID}"
  for _ in $(seq 1 30); do
    if curl -fsS --max-time 2 "http://127.0.0.1:${PORT}/health" >/dev/null 2>&1; then
      break
    fi
    sleep 1
  done
fi

cat >"${RESOLV_FILE}" <<'EOF'
nameserver 1.1.1.1
nameserver 8.8.8.8
EOF

echo "Starting temporary Cloudflare HTTPS tunnel. Press Ctrl+C to stop the tunnel."

if unshare --user --map-root-user --mount true >/dev/null 2>&1; then
  exec unshare --user --map-root-user --mount sh -c \
    'mount --bind "$1" /etc/resolv.conf && exec npx --yes cloudflared tunnel --edge-ip-version 4 --protocol http2 --url "http://127.0.0.1:${2}"' \
    jcsms-public "${RESOLV_FILE}" "${PORT}"
fi

exec npx --yes cloudflared tunnel --edge-ip-version 4 --protocol http2 --url "http://127.0.0.1:${PORT}"
