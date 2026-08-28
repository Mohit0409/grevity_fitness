#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

CONFIG="${GRAVITY_ENV_FILE:-$HOME/.config/gravity/gravity.env}"
REPO="$(cat "$HOME/.config/gravity/repository")"
PORT="$(python3 "$REPO/scripts/gravity-env.py" --config "$CONFIG" --print GRAVITY_PORT)"
PORT="${PORT:-8787}"
listeners="$(ss -ltnp 2>/dev/null || true)"
printf '%s\n' "$listeners" | grep -E "127\.0\.0\.1:$PORT([[:space:]]|$)" >/dev/null || {
  echo "Expected loopback listener 127.0.0.1:$PORT is missing." >&2
  exit 1
}
if printf '%s\n' "$listeners" | grep -E "(0\.0\.0\.0|\[::\]|\*):$PORT([[:space:]]|$)" >/dev/null; then
  echo "Unsafe public listener detected on port $PORT." >&2
  exit 1
fi
curl -fsS --max-time 5 "http://127.0.0.1:$PORT/api/health" | grep -Fq '"service":"Gravity Fitness"'
echo "networkBoundary=loopback-only port=$PORT"
sv status gravity gravity-health || true
if [ -f "$HOME/.config/gravity/enable-tunnel" ]; then sv status gravity-tunnel || true; fi
