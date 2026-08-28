#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail
umask 077

CONFIG="${GRAVITY_ENV_FILE:-$HOME/.config/gravity/gravity.env}"
REPO="$(cat "$HOME/.config/gravity/repository")"
if [ "${GRAVITY_ENV_LOADED:-}" != 1 ]; then
  exec python3 "$REPO/scripts/gravity-env.py" --config "$CONFIG" -- \
    env GRAVITY_ENV_LOADED=1 "$0"
fi

output="$(GRAVITY_ENV_FILE="$CONFIG" "$REPO/scripts/backup-gravity.sh" daily)"
created="$(printf '%s\n' "$output" | sed -n 's/^created=//p')"
archive="$(printf '%s' "$created" | python3 -c 'import json,sys; print(json.load(sys.stdin)["path"])')"
remote="${GRAVITY_BACKUP_REMOTE:-}"
required="${GRAVITY_REQUIRE_OFFDEVICE_BACKUP:-true}"
if [ -z "$remote" ]; then
  case "$(printf '%s' "$required" | tr '[:upper:]' '[:lower:]')" in
    1|true|yes|on) echo 'GRAVITY_BACKUP_REMOTE is required but not configured.' >&2; exit 1 ;;
    *) printf '%s\n' "$output"; exit 0 ;;
  esac
fi
case "$remote" in *:*) ;; *) echo 'GRAVITY_BACKUP_REMOTE must be an rclone remote:path.' >&2; exit 1 ;; esac
command -v rclone >/dev/null 2>&1 || { echo 'rclone is required for off-device backup.' >&2; exit 1; }
name="$(basename "$archive")"
target="${remote%/}/$name"
rclone copyto "$archive" "$target" --immutable
rclone check "$(dirname "$archive")" "${remote%/}" --include "$name" --one-way --download
python3 - "$(dirname "$archive")" <<'PY'
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve()
archives = sorted(root.glob("gravity-daily-*.zip"), key=lambda path: path.name, reverse=True)
for archive in archives[14:]:
    resolved = archive.resolve()
    if resolved.parent != root:
        raise SystemExit("Refusing unsafe local backup retention target")
    resolved.unlink()
PY
printf '%s\n' "$output"
printf 'offdevicePath=%s\n' "$target"
