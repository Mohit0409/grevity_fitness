# Gravity Fitness Operations Runbook

Last updated: 2026-08-29

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

Production operators should instead keep configuration and mutable state outside the checkout. Pass the private config explicitly:

```powershell
.\scripts\start-gravity.ps1 -ConfigPath C:\ProgramData\GravityFitness\gravity.env
```

Set `GRAVITY_RUNTIME_DIR`, `GRAVITY_DATA_DIR`, `GRAVITY_LOG_DIR`, and `GRAVITY_BACKUP_DIR` to protected absolute paths in that file. The managed launcher refuses any `GRAVITY_HOST` other than `127.0.0.1`.

## Windows lifecycle and automatic recovery

The server process owns `gravity.pid` and `gravity.state.json`. Start/stop/status verify the PID, checkout root, Python executable, command line, and loopback health contract before acting. A stale or ambiguous PID is never killed automatically.

```powershell
.\scripts\start-gravity.ps1 -ConfigPath C:\ProgramData\GravityFitness\gravity.env
.\scripts\status-gravity.ps1 -ConfigPath C:\ProgramData\GravityFitness\gravity.env
.\scripts\restart-gravity.ps1 -ConfigPath C:\ProgramData\GravityFitness\gravity.env
.\scripts\stop-gravity.ps1 -ConfigPath C:\ProgramData\GravityFitness\gravity.env
```

Install reboot/crash recovery from an elevated PowerShell window only after those commands pass manually:

```powershell
.\scripts\install-gravity-tasks.ps1 `
  -ConfigPath C:\ProgramData\GravityFitness\gravity.env `
  -OffsiteBackupDirectory E:\GravityBackups
```

This registers:

- `GravityFitness-Watchdog`: starts at reboot and checks every minute; it restarts only a process proven to belong to this checkout.
- `GravityFitness-DailyBackup`: at 02:00 creates, verifies, recovery-drills, and optionally copies a backup off-host.
- `GravityFitness-Notifications`: starts at reboot and then every 60 minutes. It scans the 7, 3, 1, and 0-day membership-expiry windows and processes the server-owned due-delivery outbox.

Add `-EnsureNgrok` only while the temporary ngrok deployment is intentionally in use. Because the watchdog runs as `SYSTEM`, that option requires explicit absolute paths to the protected ngrok configuration and executable; a normal per-user ngrok installation cannot recover after reboot:

```powershell
.\scripts\install-gravity-tasks.ps1 `
  -ConfigPath C:\ProgramData\GravityFitness\gravity.env `
  -EnsureNgrok `
  -NgrokConfigPath C:\ProgramData\GravityFitness\ngrok.yml `
  -NgrokExecutablePath 'C:\Program Files\ngrok\ngrok.exe' `
  -OffsiteBackupDirectory E:\GravityBackups
```

`ngrok.yml` contains the ngrok token. Keep it outside Git in a directory restricted to deployment administrators and `SYSTEM`; never put the token on the task command line. A stable production tunnel is preferred. Review Task Scheduler history and `.gravity/operations.log` after installation. Remove only these tasks with `uninstall-gravity-tasks.ps1`.

### Controlled Windows lifecycle cutover

Use this sequence only from Chat 1's immutable detached release checkout. Replace the tuple values with the exact release paths recorded by Chat 1; never paste an ngrok token into these commands.

```powershell
$releaseRoot = 'C:\ProgramData\GravityFitness\releases\<release-sha>'
$config = 'C:\ProgramData\GravityFitness\gravity.env'
$ngrokConfig = 'C:\ProgramData\GravityFitness\ngrok.yml'
$ngrokExe = 'C:\Program Files\ngrok\ngrok.exe'
$python = 'C:\ProgramData\GravityFitness\python\python.exe'
Set-Location $releaseRoot
$releaseSha = (git rev-parse HEAD).Trim()

.\scripts\install-gravity-tasks.ps1 `
  -ConfigPath $config -EnsureNgrok `
  -NgrokConfigPath $ngrokConfig -NgrokExecutablePath $ngrokExe `
  -ExpectedReleaseSha $releaseSha -RequireDetachedHead -PreflightOnly
```

`-PreflightOnly` is non-mutating and does not require Administrator rights. It must show the three SYSTEM/Highest tasks, the detached clean release SHA, loopback Gravity target, and only path-based arguments.

If an ngrok tunnel is already running, adopt it only when that process already uses the final `$ngrokExe`, `$ngrokConfig`, and loopback Gravity target. Resolve exactly one candidate, probe first, then use `-ConfirmAdopt` only during the controlled operator window:

```powershell
$candidates = @(Get-CimInstance Win32_Process -Filter "Name='ngrok.exe'" |
  Where-Object { $_.CommandLine -like '*http://127.0.0.1:8787*' -and $_.CommandLine -like "*$ngrokConfig*" })
if ($candidates.Count -ne 1) { throw 'Expected exactly one final-path Gravity ngrok process.' }
$ngrokPid = [int]$candidates[0].ProcessId

.\scripts\adopt-ngrok.ps1 -ConfigPath $config `
  -NgrokConfigPath $ngrokConfig -NgrokExecutablePath $ngrokExe `
  -PythonPath $python -ProcessId $ngrokPid

# Elevated controlled operator step after the probe is green:
.\scripts\adopt-ngrok.ps1 -ConfigPath $config `
  -NgrokConfigPath $ngrokConfig -NgrokExecutablePath $ngrokExe `
  -PythonPath $python -ProcessId $ngrokPid -ConfirmAdopt
```

If the running tunnel uses a different executable/config path, **do not adopt it**. During the controlled release window stop only the verified old ngrok PID, then start the final managed tunnel with `start-ngrok.ps1`; its duplicate-tunnel guard must remain enabled.

From the same elevated detached release checkout, install and verify the task definitions:

```powershell
.\scripts\install-gravity-tasks.ps1 `
  -ConfigPath $config -EnsureNgrok `
  -NgrokConfigPath $ngrokConfig -NgrokExecutablePath $ngrokExe `
  -ExpectedReleaseSha $releaseSha -RequireDetachedHead

.\scripts\verify-gravity-tasks.ps1 `
  -ConfigPath $config -ExpectedReleaseSha $releaseSha -RequireDetachedHead `
  -EnsureNgrok -NgrokConfigPath $ngrokConfig -NgrokExecutablePath $ngrokExe

.\scripts\watch-gravity.ps1 -ConfigPath $config -EnsureNgrok `
  -NgrokConfigPath $ngrokConfig -NgrokExecutablePath $ngrokExe
.\scripts\status-gravity.ps1 -ConfigPath $config -Json
.\scripts\status-notifications.ps1 -ConfigPath $config
```

After a planned reboot, rerun `verify-gravity-tasks.ps1`, `status-gravity.ps1`, `admin-health-check.ps1`, and the public `/api/health` check. A missing task, mismatched SHA/path/principal/trigger, unhealthy backend/tunnel, or stale notification scheduler is a release blocker.

Before installing tasks after a code or Python-runtime change, run the isolated lifecycle drill. It uses a temporary port/database, tests start/status/backup/recovery/crash-watchdog/stop, and deletes only its verified temporary directory after success:

```powershell
.\scripts\test-ops-lifecycle.ps1
```

## Daily admin operation on the gym PC

Normal boot should require no command window: Windows starts `GravityFitness-Watchdog`, the watchdog starts the loopback backend (and the explicitly configured tunnel when applicable), `GravityFitness-Notifications` starts its hourly cycle, and the owner opens the bookmarked HTTPS admin URL in a full-screen browser window.

At opening time, run this PII-free status command from a normal PowerShell window:

```powershell
.\scripts\admin-health-check.ps1 -ConfigPath C:\ProgramData\GravityFitness\gravity.env
```

Exit code `0` means the backend health contract, SQLite integrity, migration inventory, latest verified/recovery-drilled backup, scheduler freshness, and at least one notification provider are ready. Any non-zero result is a no-go for recording operational data until the named blocker is understood. The JSON report contains only statuses, aggregate counts, ages, and backup archive names; it does not contain customer contacts, tokens, provider credentials, or database paths.

Daily operator sequence:

1. Run `status-gravity.ps1`, `admin-health-check.ps1`, and `status-notifications.ps1` with the protected config path.
2. Confirm Task Scheduler shows `GravityFitness-Watchdog`, `GravityFitness-DailyBackup`, and `GravityFitness-Notifications` enabled with recent successful runs.
3. Open the bookmarked HTTPS `/admin` URL. Confirm the authenticated dashboard and Readiness view load; never use the loopback backend URL from another device.
4. Before closing, confirm payments/renewals entered that day are visible in the member history and that no scheduler failure count is increasing.
5. Confirm the latest `gravity-daily-*.zip` was verified and recovery-drilled. Do not inspect or email the archive; it contains sensitive member data.

If a check fails, stop data entry, keep the browser closed, and preserve `.gravity/operations.log`, `notification-state.json`, and the latest verified backup for diagnosis. Do not copy the live SQLite/WAL files, retry a payment by repeatedly clicking, edit the database manually, or restore over production while Gravity is running.

## Membership expiry notification automation

The scheduler never implements reminder or delivery business rules. It only invokes the backend CLI in this order: `--scan-notifications 7`, `3`, `1`, `0`, then `--deliver-notifications`. The backend owns idempotent reminder creation, renewal suppression, outbox state, provider retries, and delivery de-duplication.

`GravityFitness-Notifications` uses Task Scheduler's `IgnoreNew` policy and the runner keeps an exclusive `notification-runner.lock` in the protected runtime directory. A dead process leaves a stale PID lock that is safely reclaimed by the next cycle; a live worker is never replaced. Each cycle has a 20-minute task timeout and a non-zero result is retried only on the next hourly schedule.

Run the same protected-config command manually when validating a provider or investigating a failure:

```powershell
.\scripts\run-notifications.ps1 -ConfigPath C:\ProgramData\GravityFitness\gravity.env
.\scripts\status-notifications.ps1 -ConfigPath C:\ProgramData\GravityFitness\gravity.env
```

The safe status report and `notifications.log` record only aggregate fields: scan window, `created`, `deduped`, `suppressed_renewed`, delivery attempted/sent/failed/skipped totals, provider readiness, last successful scan, last successful delivery, and consecutive failure count. They never include recipient addresses/numbers, SMTP passwords, SMS keys, WhatsApp tokens, Firebase JSON, or raw provider output.

Provider readiness is evaluated from the protected configuration each run:

- email requires `SMTP_HOST`, `SMTP_USERNAME`, `SMTP_PASSWORD`, and `EMAIL_FROM`;
- SMS requires `SMS_PROVIDER` and `SMS_API_KEY`;
- WhatsApp requires `WHATSAPP_PROVIDER`, `WHATSAPP_ACCESS_TOKEN`, and `WHATSAPP_PHONE_NUMBER_ID`;
- owner routing is reported separately from `OWNER_EMAIL`, `OWNER_PHONE`, and `OWNER_WHATSAPP` without revealing values.

Do not put any of these values on a scheduled-task command line or in Git. A blocked provider is reported safely; a configured provider that fails delivery makes the cycle fail so the outbox can retry on the next run.

Integration prerequisite: this scheduler deliberately invokes the expiry-day command `--scan-notifications 0`. Install it only after Chat 1's final notification-core change that accepts day `0` has been integrated; it fails safe rather than silently omitting expiry-day reminders when that contract is absent.

## Public enquiry PII retention

Public visit, membership, coaching, and general enquiries are assigned a 180-day `retention_expires_at` value. Gravity automatically deletes expired enquiry rows at server startup; foreign-key cascade removes their notes and events. Expired hashed rate-limit buckets are also removed. This process does not change membership, payment, receipt, customer-account, admin-audit, or coaching records.

An operator may run the same bounded purge explicitly:

```powershell
.\.venv\Scripts\python.exe -m server.gravity --purge-expired-enquiries
```

Linux / Termux:

```sh
.venv/bin/python -m server.gravity --purge-expired-enquiries
```

The command reports only the number of expired enquiries removed. Create a verified backup before changing the retention policy. Do not manually delete live SQLite rows or change the applied migration.

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

A valid archive contains only `gravity.sqlite3` and `manifest.json`. Creation now reopens and verifies the completed ZIP. The backup wrapper then performs a temporary recovery drill by default. Verification checks SHA-256, file size, SQLite `quick_check`, foreign keys, migration inventory, and schema stage.

To verify the copied bytes on separate storage:

```powershell
.\scripts\backup-gravity.ps1 -Label daily -OffsiteDirectory E:\GravityBackups
```

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

For a manual Linux host, the portable shell launchers remain appropriate. For Android/Termux production, use the `runit` services, boot recovery, off-device backup, migration importer, network audit, burn-in, and rollback procedure in `docs/TERMUX_MIGRATION_RUNBOOK.md`. Do not run the manual background launcher and the `runit` service at the same time.

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

## Admin Software V1 production checklist

- [ ] The admin add-customer, membership, fee/payment, pending-balance, renewal, and history contracts are integrated and their temporary-database acceptance matrix is green.
- [ ] Customer creation, manual payment recording, and renewal accept an idempotency key; duplicate clicks/retries return the original result rather than inserting a second record.
- [ ] Payment state, membership activation, invoice/receipt, and audit event commit in one recoverable transaction or a tested compensating workflow.
- [ ] `PRAGMA quick_check`, `PRAGMA foreign_key_check`, and the full migration checksum inventory pass.
- [ ] The latest backup passes checksum, schema, exact customer/membership/payment/notification counts, paid-amount totals, and temporary restore acceptance.
- [ ] The 100/500/1,000/5,000-customer synthetic performance audit is reviewed; required indexes are applied by the backend owner through a forward-only migration.
- [ ] Admin authentication, RBAC, CSRF, origin validation, session expiry, `Cache-Control: no-store` APIs, customer/admin separation, and secret/PII log scans pass.
- [ ] Browser refresh, back/forward, slow/failing/interrupted API, reload, and double-submit tests pass for every money or renewal mutation.
- [ ] Windows lifecycle, crash watchdog, backup, notification scheduler, and tunnel recovery drills pass from the exact production checkout/config.
- [ ] `admin-health-check.ps1`, `launch-check.ps1`, and the production URL smoke test all exit `0`.
- [ ] Task Scheduler actions contain only script/config paths—never tokens, passwords, Firebase JSON, or provider credentials.
- [ ] Recovery roles are assigned, the owner knows the stop/restore/start sequence, and a recent off-device encrypted backup is available.

The current readiness evidence and open blockers are maintained in `docs/ADMIN_V1_QA_REPORT.md`. A checked box must represent observed evidence from the release commit, not an assumption.

## Installable admin direction after V1

V1 remains the backend plus full-screen web admin. Do not add a native Windows wrapper or enable offline mutation. A future PWA may use a dedicated admin manifest and installed-window shell only after Chat 1 approves the core V1 transaction/idempotency contracts. Any service worker must never cache admin API responses, authenticated HTML, CSRF/session material, customer PII, mutation requests, or a stale data-entry UI; navigation should fail closed to an online-required screen. The existing public-site manifest is not an admin installation contract.
