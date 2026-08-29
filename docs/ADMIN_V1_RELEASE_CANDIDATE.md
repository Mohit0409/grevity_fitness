# Gravity Fitness Admin V1 Release Candidate

Last updated: 2026-08-29

Decision: **NO-GO for production migration 010.** The current candidate is a
reproducible rehearsal candidate, not a deployment authorization. Production
remains on the pinned v9 runtime and migration 009.

## Candidate identity

| Item | Exact value |
| --- | --- |
| Integrated release SHA | `5725e47271ecd14bec79ff16923a21a6304ac974` |
| Immutable detached checkout | `C:\movieXsuggestion\MyProject\grevity_fitness-admin-v1-rc-5725e47` |
| Integrated Chat 2 code | `dd3a407` (README-only `097f31a` intentionally skipped) |
| Current production runtime | `C:\movieXsuggestion\MyProject\grevity_fitness-runtime-v9` at `49529c9484348bee398147a0a294693d2644ca16` |
| Intended protected config | `C:\ProgramData\GravityFitness\gravity.env` (not yet installed/verified) |
| Live database | `C:\movieXsuggestion\MyProject\grevity_fitness\.gravity\data\gravity.sqlite3` |

The candidate checkout is detached, clean, and exactly matches the release SHA.
It must be replaced with a new detached checkout if later Chat 2 stress or Chat 3
lifecycle commits are integrated. Mutable `main` must never be used as the
production runtime.

## Integrated verification

- Affected Admin/customer Playwright gate: 27/27 passed on isolated port 8893.
- Full Playwright gate: 50/50 passed on isolated port 8894.
- Syntax checks passed for all 11 affected JavaScript files.
- `git diff --check`, tracked secret-value scan, private-key header scan, and
  forbidden runtime/credential-file scan passed.
- The integration changed only frontend and E2E files. Backend/contracts were
  unchanged, so the prior integrated backend result remains 166/166 passed.

## Isolated migration rehearsal

An online backup of the still-running migration-009 database was created with
the pinned v9 backup implementation. The live service was not stopped.

| Item | Value |
| --- | --- |
| Rehearsal archive | `C:\movieXsuggestion\MyProject\grevity_fitness\.gravity\backups\gravity-rc-rehearsal-20260829T111931084801Z.zip` |
| Archive SHA-256 | `f7fd6ccce5240495fb5ac0dc27338da1d371e699cdbc40640409d5ff081ac888` |
| Database SHA-256 in manifest | `7878192fcaef0103572daa6c1387f33ee0e2d78ed41f0d5704df39a1f2aa2da7` |
| Migrated rehearsal copy | `C:\movieXsuggestion\MyProject\grevity_fitness\.gravity\release-rehearsal\5725e47\data\gravity.sqlite3` |
| Untouched rollback comparison | `C:\movieXsuggestion\MyProject\grevity_fitness\.gravity\release-rehearsal\5725e47\comparison\gravity.sqlite3` |

The archive passed verification and a recovery drill. The isolated database
moved from migration 009 / `notification_owner_fanout` to migration 010 /
`admin_software_v1`. SQLite `quick_check` returned `ok`, the foreign-key check
returned zero violations, and `membership_payments` was created. All original
columns in all 33 pre-existing non-metadata tables matched the restored 009 copy;
there were no original-data mismatches. The new nullable customer column was
NULL for both legacy customers as designed.

The migrated RC server then passed these real HTTP checks against the isolated
copy:

- `/api/health` and the Admin page returned HTTP 200.
- A temporary isolated admin completed password plus TOTP authentication.
- Admin session, Dashboard, Customers, Memberships, Payments, Fees, Plans,
  Notifications, Audit, Readiness, Enquiries, and Coaching APIs returned 200.
- Admin customer provisioning atomically created one customer and membership;
  a zero initial payment created no ledger row.
- The newly provisioned phone completed Firebase-identity exchange and was
  linked/verified; an unknown phone was rejected with HTTP 403
  `account_not_provisioned` and created no customer.
- Trainer Dashboard/customer financial data was redacted and Fees returned 403.
- Attempting to create a second owner was rejected.

For rollback compatibility, the rehearsal archive was restored separately to
migration 009 and started using the exact pinned v9 checkout on isolated port
8896. Health returned 200/`ok`; the database remained at nine migrations, had
no `membership_payments` table, passed `quick_check`, and had zero foreign-key
violations. The isolated v9 process was then stopped cleanly.

## Cutover tuple and commands

The following tuple is intentionally incomplete where a release gate has not
yet happened. A placeholder must not be mistaken for approval.

### Fresh pre-cutover backup

Immediately before any 009 -> 010 cutover, while production is still on v9, run
from a trusted PowerShell session:

```powershell
& 'C:\movieXsuggestion\MyProject\grevity_fitness-runtime-v9\scripts\backup-gravity.ps1' `
  -ConfigPath 'C:\ProgramData\GravityFitness\gravity.env' `
  -Label pre-admin-v1
```

Capture the exact returned `gravity-pre-admin-v1-<UTC>.zip` path and hashes, run
the v9 `verify-backup.ps1` and `recovery-drill.ps1` against that exact archive,
and copy it to protected off-host storage. The final archive path is deliberately
**unset** because this fresh backup must be made immediately before cutover. The
rehearsal archive above is verified evidence but is not the final backup gate.

### Rollback

Until cutover, the known-good rollback runtime is the detached v9 checkout at
`49529c9484348bee398147a0a294693d2644ca16`. The currently verified rehearsal
rollback archive is the exact `gravity-rc-rehearsal-20260829T111931084801Z.zip`
archive above. At cutover, replace that archive in the tuple with the exact fresh
`pre-admin-v1` archive.

If rollback requires data recovery: stop the candidate with its guarded stop
script, confirm it is stopped, re-verify the chosen migration-009 archive,
restore it with `restore-gravity.ps1 -Confirm`, start the pinned v9 runtime with
the same protected config, and rerun health/private-boundary/public smoke. Never
run pinned v9 against the migrated live database and never edit migration records.

### Ngrok transition

Current state is an unmanaged ngrok 3.39.9 process (PID 15356) publishing
`https://foyer-amenity-staff.ngrok-free.dev` to
`http://127.0.0.1:8787`. It has not been stopped or adopted.

Chat 3 is implementing a fail-closed adoption probe. After that code is committed,
reviewed, integrated, and included in a refreshed immutable release checkout, an
elevated operator must either:

1. prove the existing process executable, command/config path, target, start
   metadata, and public health and then adopt it with the final `adopt-ngrok.ps1`
   interface; or
2. if any proof fails or the per-user executable/config is unsuitable for SYSTEM,
   perform a controlled stop and start using a protected config plus a SYSTEM-
   accessible ngrok executable.

Do not run an unreviewed script from Chat 3's dirty worktree and do not launch a
second tunnel.

### Scheduled tasks

The expected final command shape below comes from Chat 3's in-progress tooling;
it is not executable from this candidate until Chat 3 hands off a clean commit
and Chat 1 refreshes the SHA/runtime:

```powershell
# Non-mutating preflight from the final detached checkout
.\scripts\install-gravity-tasks.ps1 `
  -ConfigPath 'C:\ProgramData\GravityFitness\gravity.env' `
  -EnsureNgrok `
  -NgrokConfigPath 'C:\ProgramData\GravityFitness\ngrok.yml' `
  -NgrokExecutablePath 'C:\Program Files\ngrok\ngrok.exe' `
  -ExpectedReleaseSha '<FINAL_RELEASE_SHA>' `
  -RequireDetachedHead `
  -PreflightOnly

# Elevated installation after the preflight is green
.\scripts\install-gravity-tasks.ps1 `
  -ConfigPath 'C:\ProgramData\GravityFitness\gravity.env' `
  -EnsureNgrok `
  -NgrokConfigPath 'C:\ProgramData\GravityFitness\ngrok.yml' `
  -NgrokExecutablePath 'C:\Program Files\ngrok\ngrok.exe' `
  -ExpectedReleaseSha '<FINAL_RELEASE_SHA>' `
  -RequireDetachedHead

# Read-only verification
.\scripts\verify-gravity-tasks.ps1 `
  -ConfigPath 'C:\ProgramData\GravityFitness\gravity.env' `
  -ExpectedReleaseSha '<FINAL_RELEASE_SHA>' `
  -RequireDetachedHead `
  -EnsureNgrok `
  -NgrokConfigPath 'C:\ProgramData\GravityFitness\ngrok.yml' `
  -NgrokExecutablePath 'C:\Program Files\ngrok\ngrok.exe'
```

The verifier must report all three tasks present and correct:
`GravityFitness-Watchdog`, `GravityFitness-DailyBackup`, and
`GravityFitness-Notifications`, running as SYSTEM at highest privilege with the
final detached checkout as their working directory and no secrets in arguments.
Actual reboot recovery must then be observed and reverified.

### Final smoke checks

Run these from the final immutable checkout with the protected config and exact
public URL:

```powershell
. .\scripts\gravity-common.ps1
Import-GravityEnvironment -Path 'C:\ProgramData\GravityFitness\gravity.env'
.\scripts\status-gravity.ps1 -ConfigPath 'C:\ProgramData\GravityFitness\gravity.env'
.\scripts\admin-health-check.ps1 -ConfigPath 'C:\ProgramData\GravityFitness\gravity.env'
.\scripts\launch-check.ps1
.\scripts\provider-canaries.ps1
.\scripts\smoke-gravity.ps1 -BaseUrl 'https://foyer-amenity-staff.ngrok-free.dev'
.\scripts\cutover-check.ps1 -BaseUrl 'https://foyer-amenity-staff.ngrok-free.dev'
```

Also complete an owner TOTP login and every Admin workspace, one approved real
Firebase customer login, customer provisioning/login denial for an unknown
phone, trainer financial redaction, task history/notification freshness, and
public health with `ngrok-skip-browser-warning: true`. The ngrok free-tier
interstitial remains a production-domain blocker even if the staging smoke is
green.

## Remaining no-go gates

1. Chat 2's current small-screen/long-content stress changes are uncommitted and
   not part of this SHA.
2. Chat 3's lifecycle/adoption tooling is uncommitted and not part of this SHA.
3. No protected `C:\ProgramData\GravityFitness\gravity.env` deployment has been
   installed or verified.
4. The current operator session is not elevated; the three SYSTEM tasks remain
   absent and reboot recovery is unproven.
5. The current tunnel remains unmanaged.
6. The required fresh migration-009 backup immediately before cutover does not
   yet exist.
7. A final immutable SHA/runtime and full gates must be regenerated after the
   remaining code handoffs.

## Production-unchanged proof

After the rehearsal, managed state still ties PID 4644 to the detached v9
checkout, and PID 4644 is the only listener on `127.0.0.1:8787`. Local health is
green. The live database remains at migration 009 / `notification_owner_fanout`,
has no `membership_payments` table, passes quick/foreign-key checks, and contains
2 customers, 0 memberships, 1 active owner, and 3 active plans. Ngrok PID 15356
still targets the same loopback service. No production migration, restore,
runtime switch, scheduled-task install, or ngrok transition occurred.
