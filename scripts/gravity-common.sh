#!/usr/bin/env sh

gravity_init() {
  GRAVITY_PROJECT_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
  GRAVITY_CONFIG_FILE=${GRAVITY_ENV_FILE:-"$GRAVITY_PROJECT_ROOT/.env"}
  GRAVITY_CONFIG_ARGUMENTS=''
  if [ -f "$GRAVITY_CONFIG_FILE" ]; then
    GRAVITY_CONFIG_ARGUMENTS=$GRAVITY_CONFIG_FILE
  elif [ -n "${GRAVITY_ENV_FILE:-}" ]; then
    printf 'Gravity environment file does not exist: %s\n' "$GRAVITY_CONFIG_FILE" >&2
    return 1
  fi

  config_value() {
    key=$1
    if [ -n "$GRAVITY_CONFIG_ARGUMENTS" ]; then
      python3 "$GRAVITY_PROJECT_ROOT/scripts/gravity-env.py" --config "$GRAVITY_CONFIG_FILE" --print "$key"
    else
      python3 "$GRAVITY_PROJECT_ROOT/scripts/gravity-env.py" --print "$key"
    fi
  }

  GRAVITY_MANAGED_HOST=$(config_value GRAVITY_HOST)
  GRAVITY_MANAGED_HOST=${GRAVITY_MANAGED_HOST:-127.0.0.1}
  if [ "$GRAVITY_MANAGED_HOST" != '127.0.0.1' ]; then
    printf "Refusing unsafe GRAVITY_HOST '%s'. Managed deployment requires 127.0.0.1.\n" "$GRAVITY_MANAGED_HOST" >&2
    return 1
  fi
  GRAVITY_MANAGED_PORT=$(config_value GRAVITY_PORT)
  GRAVITY_MANAGED_PORT=${GRAVITY_MANAGED_PORT:-8787}
  case "$GRAVITY_MANAGED_PORT" in *[!0-9]*|'') printf '%s\n' 'Invalid GRAVITY_PORT.' >&2; return 1 ;; esac
  if [ "$GRAVITY_MANAGED_PORT" -lt 1 ] || [ "$GRAVITY_MANAGED_PORT" -gt 65535 ]; then
    printf '%s\n' 'GRAVITY_PORT must be between 1 and 65535.' >&2
    return 1
  fi
  GRAVITY_HEALTH_URL="http://127.0.0.1:$GRAVITY_MANAGED_PORT/api/health"

  GRAVITY_RUNTIME=$(config_value GRAVITY_RUNTIME_DIR)
  GRAVITY_RUNTIME=${GRAVITY_RUNTIME:-"$GRAVITY_PROJECT_ROOT/.gravity"}
  case "$GRAVITY_RUNTIME" in /*) ;; *) GRAVITY_RUNTIME="$GRAVITY_PROJECT_ROOT/$GRAVITY_RUNTIME" ;; esac
  GRAVITY_PID_FILE="$GRAVITY_RUNTIME/gravity.pid"
  GRAVITY_STATE_FILE="$GRAVITY_RUNTIME/gravity.state.json"

  GRAVITY_PYTHON_BIN=$(config_value GRAVITY_PYTHON)
  GRAVITY_PYTHON_BIN=${GRAVITY_PYTHON_BIN:-"$GRAVITY_PROJECT_ROOT/.venv/bin/python"}
  case "$GRAVITY_PYTHON_BIN" in /*) ;; *) GRAVITY_PYTHON_BIN="$GRAVITY_PROJECT_ROOT/$GRAVITY_PYTHON_BIN" ;; esac
  export GRAVITY_PROJECT_ROOT GRAVITY_CONFIG_FILE GRAVITY_RUNTIME GRAVITY_PID_FILE GRAVITY_STATE_FILE
  export GRAVITY_PYTHON_BIN GRAVITY_MANAGED_PORT GRAVITY_HEALTH_URL
}

gravity_run() {
  if [ -n "$GRAVITY_CONFIG_ARGUMENTS" ]; then
    exec python3 "$GRAVITY_PROJECT_ROOT/scripts/gravity-env.py" --config "$GRAVITY_CONFIG_FILE" -- "$@"
  fi
  exec python3 "$GRAVITY_PROJECT_ROOT/scripts/gravity-env.py" -- "$@"
}

gravity_capture() {
  if [ -n "$GRAVITY_CONFIG_ARGUMENTS" ]; then
    python3 "$GRAVITY_PROJECT_ROOT/scripts/gravity-env.py" --config "$GRAVITY_CONFIG_FILE" -- "$@"
  else
    python3 "$GRAVITY_PROJECT_ROOT/scripts/gravity-env.py" -- "$@"
  fi
}

gravity_pid() {
  [ -s "$GRAVITY_PID_FILE" ] || return 1
  pid=$(cat "$GRAVITY_PID_FILE" 2>/dev/null || true)
  case "$pid" in *[!0-9]*|'') return 1 ;; esac
  printf '%s\n' "$pid"
}

gravity_managed_pid() {
  pid=${1:-}
  [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null || return 1
  [ -r "/proc/$pid/cmdline" ] && [ -e "/proc/$pid/cwd" ] || return 1
  command=$(tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null || true)
  cwd=$(readlink -f "/proc/$pid/cwd" 2>/dev/null || true)
  [ "$cwd" = "$GRAVITY_PROJECT_ROOT" ] || return 1
  printf '%s' "$command" | grep -Eq '(^|[[:space:]])-m[[:space:]]+server\.gravity([[:space:]]|$)'
}

gravity_healthy() {
  python3 - "$GRAVITY_HEALTH_URL" <<'PY'
import json
import sys
import urllib.request

try:
    with urllib.request.urlopen(sys.argv[1], timeout=3) as response:
        data = json.load(response)
except Exception:
    raise SystemExit(1)
raise SystemExit(0 if data.get("service") == "Gravity Fitness" and data.get("status") == "ok" and data.get("database") == "ok" else 1)
PY
}

gravity_remove_stale_state() {
  rm -f "$GRAVITY_PID_FILE" "$GRAVITY_STATE_FILE"
}

gravity_rotate_log() {
  path=$1
  if [ -f "$path" ] && [ "$(wc -c < "$path")" -ge 10485760 ]; then
    rm -f "$path.1"
    mv "$path" "$path.1"
  fi
}
