#!/usr/bin/env sh
set -eu
if [ "$#" -ne 2 ] || [ "$2" != '--confirm' ]; then
  printf 'Usage: %s BACKUP.zip --confirm\n' "$0" >&2
  printf '%s\n' 'Stop Gravity Fitness before restoring the live database.' >&2
  exit 2
fi
. "$(dirname -- "$0")/gravity-common.sh"
gravity_init
pid=$(gravity_pid 2>/dev/null || true)
if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
  printf 'Refusing live restore while Gravity PID %s is running.\n' "$pid" >&2
  exit 1
fi
cd "$GRAVITY_PROJECT_ROOT"
gravity_run "$GRAVITY_PYTHON_BIN" -m server.gravity --restore-backup "$1" --confirm-live-restore
