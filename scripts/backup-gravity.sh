#!/usr/bin/env sh
set -eu

LABEL=${1:-manual}
OFFSITE_DIRECTORY=${2:-}
. "$(dirname -- "$0")/gravity-common.sh"
gravity_init
[ -x "$GRAVITY_PYTHON_BIN" ] || { printf 'Gravity Python environment is missing: %s\n' "$GRAVITY_PYTHON_BIN" >&2; exit 1; }
cd "$GRAVITY_PROJECT_ROOT"
created=$(gravity_capture "$GRAVITY_PYTHON_BIN" -m server.gravity --create-backup --backup-label "$LABEL")
archive=$(printf '%s' "$created" | python3 -c 'import json,sys; print(json.load(sys.stdin)["path"])')
verified=$(gravity_capture "$GRAVITY_PYTHON_BIN" -m server.gravity --verify-backup "$archive")
drill=$(gravity_capture "$GRAVITY_PYTHON_BIN" -m server.gravity --recovery-drill "$archive")
printf '%s' "$drill" | python3 -c 'import json,sys; raise SystemExit(0 if json.load(sys.stdin).get("drillPassed") else 1)'

offsite=''
if [ -n "$OFFSITE_DIRECTORY" ]; then
  mkdir -p "$OFFSITE_DIRECTORY"
  chmod 700 "$OFFSITE_DIRECTORY" 2>/dev/null || true
  offsite="$OFFSITE_DIRECTORY/$(basename "$archive")"
  [ ! -e "$offsite" ] || { printf 'Off-device backup already exists: %s\n' "$offsite" >&2; exit 1; }
  cp -p "$archive" "$offsite"
  chmod 600 "$offsite" 2>/dev/null || true
  gravity_capture "$GRAVITY_PYTHON_BIN" -m server.gravity --verify-backup "$offsite" >/dev/null
fi
printf 'created=%s\n' "$created"
printf 'verified=%s\n' "$verified"
printf 'recoveryDrill=%s\n' "$drill"
[ -z "$offsite" ] || printf 'offsitePath=%s\n' "$offsite"
