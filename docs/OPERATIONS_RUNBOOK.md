# Gravity Fitness Operations Runbook

Last updated: 2026-08-27

This runbook covers safe backup, verification, recovery, rollback, and portable Windows/Linux/Termux operation. It does not change Gravity's localhost-first security boundary.

## Security rules

- Keep `.env`, Firebase service-account files, databases, logs, and backup archives outside Git.
- Treat every backup as sensitive member/business data. Copy backups only to storage you control and encrypt/protect that storage.
- Do not expose the Python server directly to the public internet. Keep `GRAVITY_HOST=127.0.0.1` unless an approved TLS/reverse-proxy boundary is in place.
- Never restore the live database while Gravity is running.
- Never assume payment, tax, notification, or authentication providers are active unless the admin Readiness view reports verified configuration.

## Runtime locations

Default local runtime paths are under `.gravity/`:

- Database: `.gravity/data/gravity.sqlite3`
- Logs: `.gravity/logs/` plus launcher stdout/stderr under `.gravity/`
- PID file: `.gravity/gravity.pid`
- Backups: `.gravity/backups/gravity-*.zip`

All of these paths are gitignored.
## Create and verify a backup

Backups use SQLite's online backup API, so a consistent snapshot can be created while the site is running.

Windows PowerShell:

```powershell
.\scripts\backup-gravity.ps1 -Label daily
.\scripts\verify-backup.ps1 -BackupPath .\.gravity\backups\gravity-daily-<timestamp>.zip
```

Linux / Termux:

```sh
./scripts/backup-gravity.sh daily
./scripts/verify-backup.sh .gravity/backups/gravity-daily-<timestamp>.zip
```

A valid archive contains only `gravity.sqlite3` and `manifest.json`. Verification checks SHA-256, file size, SQLite `quick_check`, foreign keys, migration inventory, and schema stage.

Recommended minimum: create a daily backup, keep multiple generations, and copy at least one verified recent archive off the host device. Do not delete the newest verified backup until a newer backup has passed verification.
## Recovery drill

A recovery drill restores the archive only into a temporary database, validates application queries, and leaves the live database untouched.

Windows:

```powershell
.\scripts\recovery-drill.ps1 -BackupPath .\.gravity\backups\gravity-daily-<timestamp>.zip
```

Linux / Termux:

```sh
./scripts/recovery-drill.sh .gravity/backups/gravity-daily-<timestamp>.zip
```

Run a drill after backup-system changes and periodically thereafter. A drill must report `drillPassed: True` before the archive is considered recovery-tested.

## Live restore

1. Identify the exact verified backup archive.
2. Run the verification command again.
3. Stop Gravity with the platform stop script.
4. Confirm status reports the service stopped.
5. Run the restore command with explicit confirmation.
6. Start Gravity again and verify `/api/health` plus critical private/public routes.

The restore operation refuses to replace the live database if the Gravity PID is still active. Before replacement it creates a verified `pre-restore` backup of the current live database for rollback.
Windows restore:

```powershell
.\scripts\stop-gravity.ps1
.\scripts\status-gravity.ps1
.\scripts\restore-gravity.ps1 -BackupPath .\.gravity\backups\gravity-daily-<timestamp>.zip -Confirm
.\scripts\start-gravity.ps1
.\scripts\status-gravity.ps1
```

Linux / Termux restore:

```sh
./scripts/stop-gravity.sh
./scripts/status-gravity.sh || true
./scripts/restore-gravity.sh .gravity/backups/gravity-daily-<timestamp>.zip --confirm
./scripts/start-gravity.sh
./scripts/status-gravity.sh
```

Do not remove the generated `pre-restore` backup until post-restore smoke checks are complete.

## Scheduled backup automation

Use the operating system scheduler to invoke only the backup wrapper. Keep notification delivery on a separate explicit schedule and do not combine restore with any unattended task.

- Windows: Task Scheduler can run `powershell.exe -NoProfile -ExecutionPolicy Bypass -File <project>\scripts\backup-gravity.ps1 -Label daily`.
- Linux/Termux: cron or an equivalent trusted scheduler can run `<project>/scripts/backup-gravity.sh daily`.

Review backup failures through scheduler history/logging; never silently prune all older copies after a failed backup.
## Linux / Termux deployment

Prerequisites: Python 3.11+, Git, and enough persistent storage for the application plus several backup generations.

```sh
git clone <authorized-repository> grevity_fitness
cd grevity_fitness
cp .env.example .env
# Fill only verified configuration values in .env.
./scripts/setup-gravity.sh
./scripts/start-gravity.sh
./scripts/status-gravity.sh
```

The shell launcher resolves the same `.env` `APP_BASE_URL` as the Python server and waits for the real health contract before reporting startup success.

For Android/Termux, place the project and `.gravity` data on storage that remains available to Termux. If using Termux:Boot, invoke `scripts/start-gravity.sh`; do not copy credentials into the boot script. Keep the host on `127.0.0.1` and use an approved private overlay/TLS gateway for remote access rather than opening the raw application port.

## Application rollback

- Create and verify a database backup before changing application code.
- Record the currently deployed Git commit before updating.
- Prefer a Git revert or a separate known-good checkout/worktree over destructive source-tree resets.
- Database migrations are forward-only. Never delete migration records or manually downgrade the SQLite schema to match older code.
- After code rollback, run `python -m server.gravity --check-db`, start the service, and repeat health/auth/admin/private-route smoke checks.
- If the rollback also requires database restoration, follow the verified live-restore procedure above rather than copying SQLite files while the service is running.

## Final launch gate

Before a production cutover, follow `docs/LAUNCH_RUNBOOK.md`. The `launch-check` wrappers are fail-closed and require a healthy/current database, active owner, at least one active verified plan, production HTTPS/provider/business readiness, and a verified recovery-tested backup no older than 24 hours. The `smoke-gravity` wrappers then validate public/private route boundaries and security headers against the exact launch URL.

Windows:

```powershell
.\scripts\launch-check.ps1
.\scripts\smoke-gravity.ps1 -BaseUrl https://<verified-domain>
```

Linux / Termux:

```sh
./scripts/launch-check.sh
./scripts/smoke-gravity.sh https://<verified-domain>
```

Do not treat a blocked launch check as an error to bypass; it is the intended no-go signal until the named production dependency has been verified.
