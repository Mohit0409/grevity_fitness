#!/usr/bin/env sh
set -eu
[ "$#" -eq 1 ] || { printf 'Usage: %s BACKUP.zip\n' "$0" >&2; exit 2; }
. "$(dirname -- "$0")/gravity-common.sh"
gravity_init
cd "$GRAVITY_PROJECT_ROOT"
gravity_run "$GRAVITY_PYTHON_BIN" -m server.gravity --recovery-drill "$1"
