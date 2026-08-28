#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail
umask 077

[ "$#" -eq 1 ] || { echo "usage: import-migration.sh DIRECTORY" >&2; exit 2; }
BUNDLE="$(readlink -f "$1")"
MANIFEST="$BUNDLE/gravity-migration.json"
CONFIG="${GRAVITY_ENV_FILE:-$HOME/.config/gravity/gravity.env}"
REPO="$(cat "$HOME/.config/gravity/repository")"
[ -r "$MANIFEST" ] || { echo 'Migration manifest is missing.' >&2; exit 1; }

read_manifest() {
  python3 - "$MANIFEST" "$1" <<'PY'
import json
import sys
with open(sys.argv[1], encoding="utf-8") as handle:
    value = json.load(handle)[sys.argv[2]]
print(value)
PY
}
backup_name="$(read_manifest backupFile)"
expected_hash="$(read_manifest backupSha256)"
source_commit="$(read_manifest sourceCommit)"
drill="$(read_manifest recoveryDrillPassed)"
[ "$drill" = True ] || [ "$drill" = true ] || { echo 'Source recovery drill was not recorded as passed.' >&2; exit 1; }
case "$backup_name" in */*|..*) echo 'Unsafe backup filename in manifest.' >&2; exit 1 ;; esac
BACKUP="$BUNDLE/$backup_name"
[ -r "$BACKUP" ] || { echo 'Migration backup is missing.' >&2; exit 1; }
actual_hash="$(sha256sum "$BACKUP" | awk '{print $1}')"
[ "$actual_hash" = "$expected_hash" ] || { echo 'Migration archive SHA-256 mismatch.' >&2; exit 1; }
current_commit="$(git -C "$REPO" rev-parse HEAD)"
[ "$current_commit" = "$source_commit" ] || { echo "Checkout $current_commit does not match source $source_commit." >&2; exit 1; }

PYTHON="$(python3 "$REPO/scripts/gravity-env.py" --config "$CONFIG" --print GRAVITY_PYTHON)"
PYTHON="${PYTHON:-$REPO/.venv/bin/python}"
python3 "$REPO/scripts/gravity-env.py" --config "$CONFIG" -- "$PYTHON" -m server.gravity --verify-backup "$BACKUP"
sv down gravity
for _ in $(seq 1 20); do
  sv status gravity 2>&1 | grep -q '^down:' && break
  sleep 1
done
sv status gravity 2>&1 | grep -q '^down:' || { echo 'Gravity service did not stop; restore aborted.' >&2; exit 1; }
python3 "$REPO/scripts/gravity-env.py" --config "$CONFIG" -- "$PYTHON" -m server.gravity --restore-backup "$BACKUP" --confirm-live-restore
sv up gravity
PORT="$(python3 "$REPO/scripts/gravity-env.py" --config "$CONFIG" --print GRAVITY_PORT)"
PORT="${PORT:-8787}"
for _ in $(seq 1 30); do
  curl -fsS --max-time 3 "http://127.0.0.1:$PORT/api/health" | grep -Fq '"service":"Gravity Fitness"' && {
    echo 'Migration import completed and loopback health passed.'
    exit 0
  }
  sleep 1
done
echo 'Restore completed but Gravity did not become healthy; inspect svlogd output.' >&2
exit 1
