# Gravity Fitness Android / Termux Migration Runbook

Last updated: 2026-08-28

This is the production migration path from the Windows laptop to an Android phone running Termux. It preserves the same Python + SQLite architecture and the same security boundary:

```text
Internet -> stable HTTPS tunnel -> 127.0.0.1:8787 -> Gravity -> SQLite
```

Port `8787` must never listen on `0.0.0.0`, the phone LAN address, or a router port-forward. The public hostname belongs to the tunnel; the Python process remains loopback-only.

## Deployment decision

Use a stable named Cloudflare Tunnel for the production hostname. Keep ngrok only as a temporary diagnostic path. An ephemeral ngrok URL can change after restart and then invalidate `APP_BASE_URL`, Firebase authorized domains, OAuth origins, cookies, webhooks, and public links.

Android can stop background processes for battery or memory pressure. Gravity therefore uses four independent Termux `runit` services:

- `gravity`: foreground Python server; `runit` restarts it after a crash.
- `gravity-health`: loopback health watchdog plus daily verified/recovery-drilled backup.
- `gravity-notifications`: invokes the server-owned expiry reminder scans (7, 3, 1, and 0 days) and due-delivery worker once per hour; a single runtime lock prevents concurrent delivery workers.
- `gravity-tunnel`: named HTTPS tunnel, enabled only after the local service and hostname are verified.

Termux:Boot asks those services to come up after reboot. The server itself owns `.pid` and `.state.json`, so live restore protection is retained under `runit`.

## Phase 0: prepare the phone

1. Install Termux and Termux:Boot from the same supported source. Open Termux:Boot once so Android permits boot execution.
2. Exclude Termux and Termux:Boot from battery optimization. Allow background activity and auto-start where the Android vendor exposes those settings.
3. Use reliable power, cooling, storage, and network. Do not place the database on shared/external Android storage; keep it in Termux private storage.
4. Configure device encryption, a screen lock, and SSH public-key authentication if remote administration is needed. Do not expose Termux SSH directly to the internet.
5. Plan at least two off-device backup copies. A backup stored only on the phone is not disaster recovery.

## Phase 1: freeze and export from Windows

Do not stop the laptop site yet.

```powershell
git status --short
git rev-parse HEAD
.\scripts\status-gravity.ps1 -ConfigPath C:\ProgramData\GravityFitness\gravity.env
.\scripts\export-gravity-migration.ps1 `
  -ConfigPath C:\ProgramData\GravityFitness\gravity.env `
  -OutputDirectory E:\GravityMigration
```

The export creates a fresh online SQLite backup, verifies its checksum/schema, performs a temporary recovery drill, copies it to the selected destination, and writes `gravity-migration.json` with the source commit and archive SHA-256. It intentionally excludes `.env`, credentials, tokens, logs, and raw live database files.

Copy secrets separately over an authenticated encrypted channel. Never add them to the migration directory or Git.

## Phase 2: install the same code on Termux

```bash
pkg update
pkg install git python
git clone <authorized-repository> "$HOME/gravity-fitness"
cd "$HOME/gravity-fitness"
git checkout <sourceCommit-from-gravity-migration.json>
./scripts/setup-gravity.sh
./deploy/termux/install-termux.sh --install-packages
```

The first installer run creates `~/.config/gravity/gravity.env` with mode `600` and intentionally pauses. Edit that private file:

- `GRAVITY_HOST=127.0.0.1`
- `GRAVITY_PORT=8787`
- `APP_BASE_URL=https://<stable-production-hostname>`
- absolute private data, log, backup, Python, and Firebase service-account paths
- a new strong `SECRET_KEY` and verified provider/business settings
- an encrypted `rclone` remote in `GRAVITY_BACKUP_REMOTE`

Keep `GRAVITY_REQUIRE_OFFDEVICE_BACKUP=true`. Then rerun:

```bash
./deploy/termux/install-termux.sh
sv up gravity gravity-health gravity-notifications
./deploy/termux/network-audit.sh
```

The installer refuses a non-loopback host, non-HTTPS production URL, weak/blank secret, missing Python runtime, or an existing unrelated service definition.
Rerun the installer after deploying a new Git commit so the audited service definitions are copied into Termux's service directory; runtime `down` markers never modify the Git checkout.

## Phase 3: import the verified database

Copy the migration directory into Termux private storage, not shared storage. Keep the tunnel disabled.

```bash
cd "$HOME/gravity-fitness"
./deploy/termux/import-migration.sh "$HOME/private-transfer/GravityMigration"
./deploy/termux/network-audit.sh
```

The importer fails closed unless:

- the archive SHA-256 matches `gravity-migration.json`;
- the Windows recovery drill was recorded as passed;
- the phone checkout exactly matches the exported Git commit;
- the archive passes Gravity verification again;
- `runit` confirms Gravity is down before live restore;
- loopback health passes after restart.

The live restore creates its own verified `pre-restore` safety backup before replacing an existing phone database.

## Phase 4: configure the stable HTTPS tunnel

Create a named remotely-managed Cloudflare Tunnel in the controlled Cloudflare account. Configure exactly one public hostname route to:

```text
http://127.0.0.1:8787
```

Store only the tunnel token in:

```text
~/.config/gravity/cloudflared-token
```

```bash
chmod 600 "$HOME/.config/gravity/cloudflared-token"
touch "$HOME/.config/gravity/enable-tunnel"
chmod 600 "$HOME/.config/gravity/enable-tunnel"
sv-enable gravity-tunnel
sv up gravity-tunnel
```

Do not put the token in the repo, process arguments, boot script, shell history, or `gravity.env`. The service uses `cloudflared --token-file`, which requires cloudflared 2025.4.0 or newer; the installer checks this before enabling the tunnel.

Verify the public URL from a different network, then run:

```bash
./scripts/smoke-gravity.sh "https://<stable-production-hostname>"
./scripts/launch-check.sh
./deploy/termux/network-audit.sh
```

Confirm Firebase authorized domains, redirect origins, CSP, cookies, and any webhooks use the stable hostname before cutover.

## Phase 5: burn-in and cutover

Run the phone in parallel for at least 48 hours without accepting production writes. During burn-in verify:

- reboot recovery with the screen locked;
- crash recovery (`sv restart gravity`) and tunnel recovery;
- no listener on `0.0.0.0:8787`, `[::]:8787`, or the phone LAN IP;
- daily local backup, recovery drill, and downloaded `rclone check` success;
- log rotation and available storage;
- public and loopback health after network changes;
- Android battery/thermal behavior under realistic load.

For final cutover:

1. Put the laptop deployment into a maintenance/no-write window.
2. Export a new `migration` bundle and import it on the phone.
3. Run loopback health, network audit, launch check, and public smoke.
4. Enable/switch the stable tunnel route to the phone.
5. Test customer login, an owner login, a read-only admin path, and a reversible low-risk business flow.
6. Keep the laptop stopped but intact as rollback capacity. Do not allow both copies to accept writes.

## Rollback

If the phone fails during cutover:

1. Disable the phone tunnel: `sv down gravity-tunnel`.
2. Stop phone writes: `sv down gravity`.
3. If the phone accepted any real writes, create and verify a phone backup before doing anything else.
4. Restore the tunnel route to the laptop.
5. Start the laptop only from its known-good commit/data and repeat health/smoke checks.

SQLite is single-writer state. Never run laptop and phone as active-active servers and never merge two independently modified database files.

## Notification scheduler

`gravity-notifications` writes safe aggregate cycle reports to `~/.local/state/gravity/notifications.log` and state to `~/.local/state/gravity/notification-state.json`. Inspect it without exposing recipients or provider credentials:

```bash
sh ./scripts/status-notifications.sh
sv status gravity gravity-health gravity-notifications
```

The service waits one hour between cycles, so a delivery/provider/database failure is retried on the next cycle without busy-looping. `runit` starts the service after a crash and Termux:Boot requests it after reboot. As on Windows, do not enable the service until Chat 1's final backend contract accepting `--scan-notifications 0` for expiry-day reminders is integrated.

Provider secrets stay only in the mode-600 private Gravity configuration. The safe state records whether email, SMS, WhatsApp, and owner recipient routes are configured or blocked; it never records raw addresses, phone numbers, passwords, API keys, access tokens, or Firebase JSON.

## Routine operations

```bash
sv status gravity gravity-health gravity-tunnel
tail -n 100 "$HOME/.local/state/gravity/logs/health.log"
./deploy/termux/backup-offdevice.sh
./deploy/termux/network-audit.sh
```

Keep the newest verified backup on the phone plus multiple immutable off-device generations. Test restoration quarterly and after any migration, storage, schema, tunnel, or backup change.
