#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

CONFIG="${GRAVITY_ENV_FILE:-$HOME/.config/gravity/gravity.env}"
REPO="$(cat "$HOME/.config/gravity/repository")"
PORT="$(python3 "$REPO/scripts/gravity-env.py" --config "$CONFIG" --print GRAVITY_PORT)"
PORT="${PORT:-8787}"
listeners="$(ss -ltnp 2>/dev/null || true)"
if printf '%s\n' "$listeners" | grep -E "(^|[[:space:]])127\.0\.0\.1:$PORT([[:space:]]|$)" >/dev/null; then
  if printf '%s\n' "$listeners" | grep -E "(0\.0\.0\.0|\[::\]|\*):$PORT([[:space:]]|$)" >/dev/null; then
    echo "Unsafe public listener detected on port $PORT." >&2
    exit 1
  fi
  inspection="socket-table"
else
  RUNTIME_DIR="$(python3 "$REPO/scripts/gravity-env.py" --config "$CONFIG" --print GRAVITY_RUNTIME_DIR)"
  if [ -z "$RUNTIME_DIR" ]; then
    RUNTIME_DIR="$REPO/.gravity"
  elif [[ "$RUNTIME_DIR" != /* ]]; then
    RUNTIME_DIR="$REPO/$RUNTIME_DIR"
  fi
  STATE_FILE="$RUNTIME_DIR/gravity.state.json"
  python3 - "$STATE_FILE" "$PORT" <<'PY'
import json
from pathlib import Path
import sys

state_path = Path(sys.argv[1])
expected_port = int(sys.argv[2])
try:
    state = json.loads(state_path.read_text(encoding="utf-8"))
except (OSError, ValueError, json.JSONDecodeError) as exc:
    raise SystemExit(f"Runtime listener state is unavailable: {exc}")
if state.get("host") != "127.0.0.1":
    raise SystemExit(f"Unsafe runtime host in {state_path}: {state.get('host')!r}")
if int(state.get("port", -1)) != expected_port:
    raise SystemExit(
        f"Runtime port mismatch in {state_path}: {state.get('port')!r} != {expected_port}"
    )
PY
  inspection="runtime-state"
fi
curl -fsS --max-time 5 "http://127.0.0.1:$PORT/api/health" | grep -Fq '"service":"Gravity Fitness"'
echo "networkBoundary=loopback-only port=$PORT inspection=$inspection"
sv status gravity gravity-health || true
if [ -f "$HOME/.config/gravity/enable-tunnel" ]; then sv status gravity-tunnel || true; fi
