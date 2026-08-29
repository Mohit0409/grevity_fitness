# Gravity Fitness Admin V1 Release Candidate

Last updated: 2026-08-29

Decision: **NO-GO for production migration 010.** Code and isolated migration gates are green, but protected deployment, production ingress, SYSTEM task installation, reboot lifecycle acceptance, and the fresh pre-cutover migration-009 backup are not yet complete. Production remains pinned to v9 / migration 009.

## Final candidate identity

| Item | Exact value |
| --- | --- |
| Final release SHA | `c4f2219a77f0a1248497c15c5eef6bc5389dd476` |
| Immutable detached checkout | `C:\movieXsuggestion\MyProject\grevity_fitness-admin-v1-final-rc-c4f2219` |
| Superseded evidence-only RC | `C:\movieXsuggestion\MyProject\grevity_fitness-admin-v1-final-rc-b6b42d7` / `b6b42d7264a1ee8ca7fac06b994a9fbb8f8fb24e` |
| Pinned rollback runtime | `C:\movieXsuggestion\MyProject\grevity_fitness-runtime-v9` / `49529c9484348bee398147a0a294693d2644ca16` |
| Live database | `C:\movieXsuggestion\MyProject\grevity_fitness\.gravity\data\gravity.sqlite3` |
| Protected config target | `C:\ProgramData\GravityFitness\gravity.env` |
| Protected ngrok config target | `C:\ProgramData\GravityFitness\ngrok.yml` |
| SYSTEM-accessible ngrok target | `C:\Program Files\ngrok\ngrok.exe` |

The candidate is detached HEAD, clean, and exactly matches the final SHA. Mutable `main` is coordination/integration only and is not a production runtime.

## Integrated commit mapping

- Chat 3 lifecycle/adoption/post-reboot stack is integrated on `main` as `922ec5c`, `2d1a4f8`, and `c762b85`.
- Chat 2 product stress work `9a7111a` is integrated as `b6b42d7` (`Harden admin stress layouts`).
- Chat 2 test-only stabilization `760a07b` was explicitly accepted and integrated as `c4f2219`; its only delta is two readiness waits in `tests/e2e/gravity.spec.js`.
- Chat 2/3 README-only handoff commits were not cherry-picked into the release runtime.

## Final exact-RC validation

All gates below ran from `C:\movieXsuggestion\MyProject\grevity_fitness-admin-v1-final-rc-c4f2219` with isolated test data/ports where applicable.

- Backend unittest suite: **192/192 passed**.
- Full Playwright suite: **53/53 passed**.
- Admin/customer focused browser gate: after one transient Enquiries empty-row wait failure, the exact failed stress case passed **3/3 repeated** and the complete focused rerun passed **29/29** on a fresh isolated port.
- Focused Admin stress gate: **3/3 passed**.
- Accessibility/responsive/zoom/keyboard/forced-colors gate: **9/9 passed**.
- Focused Admin/auth/payment/notification business-flow modules: **47/47 passed**.
- Focused ngrok/task/lifecycle/reliability suite: **64/64 passed**.
- Tracked JavaScript syntax: **27/27 files passed**.
- Tracked Python compile: **67/67 files passed**.
- Tracked PowerShell parse: **28/28 files passed**.
- `git diff --check`: passed.
- Private-key header scan: **0 tracked files**.
- Forbidden tracked runtime/credential-file scan: **0 tracked files**.
- High-risk secret-key references were reviewed: production code reads values from environment/config; the only literal examples are empty or explicitly synthetic test/QA values. No production secret value was identified in tracked source.

The RC remained detached and clean after validation.

## Final isolated migration 009 -> 010 rehearsal

A fresh restore was made from the previously verified migration-009 archive into:
`C:\movieXsuggestion\MyProject\grevity_fitness\.gravity\release-rehearsal\c4f2219-final`.

The restored source database SHA-256 matched the verified archive manifest value `7878192FCAEF0103572DAA6C1387F33EE0E2D78ED41F0D5704DF39A1F2AA2DA7` before migration.

Rehearsal results:

- Pre-migration inventory: migrations `001` through `009`, latest `009 notification_owner_fanout`.
- Exact RC applied only migration `010 admin_software_v1`.
- Post-migration inventory: migrations `001` through `010`.
- `app_metadata.schema_stage` became `admin_software_v1`.
- `membership_payments` exists after migration 010.
- Original-column data across all **33 pre-existing business tables** matched the untouched migration-009 restore; mismatch list was empty.
- SQLite `PRAGMA quick_check`: `ok`.
- SQLite foreign-key violations: `0`.
- Exact-RC Admin/auth/payment/notification contract modules passed 47/47, covering Admin login/MFA/workspaces, customer provisioning/auth denial behavior, payments/renewals, notifications, RBAC and financial-redaction paths.
- A separate fresh migration-009 restore was started with the exact pinned-v9 runtime on isolated `127.0.0.1:8901`; `/api/health` returned `status: ok`, the database remained at 9 migrations, `membership_payments` remained absent, `quick_check` was `ok`, and foreign-key violations were `0`. The isolated server was then stopped.

No live migration, restore, runtime switch, task installation, reboot, or ngrok transition occurred during this rehearsal.

## Production state after rehearsal

Read-only verification still shows:

- PID `4644` is the listener on `127.0.0.1:8787`.
- Live database remains migration `009 notification_owner_fanout` with no `membership_payments` table.
- Live SQLite `quick_check` is `ok`; foreign-key violations are `0`.
- `GravityFitness-Watchdog`, `GravityFitness-DailyBackup`, and `GravityFitness-Notifications` are absent; Gravity scheduled-task count is `0`.
- `C:\ProgramData\GravityFitness\gravity.env`, `C:\ProgramData\GravityFitness\ngrok.yml`, and `C:\Program Files\ngrok\ngrok.exe` are absent.

## Production ingress decision

Current ingress remains **NO-GO for polished production**. The free ngrok URL can reach the service and `/api/health` is green with the bypass header, but ordinary root traffic without the bypass header does not render the Gravity Fitness application. No stable production domain/tunnel path without the free-tier interstitial has been frozen yet.

Therefore migration 010/cutover remains prohibited until a stable production ingress is selected and added to the deployment tuple.

## Frozen deployment tuple (incomplete by design)

| Item | Value |
| --- | --- |
| Final RC | `c4f2219a77f0a1248497c15c5eef6bc5389dd476` / `C:\movieXsuggestion\MyProject\grevity_fitness-admin-v1-final-rc-c4f2219` |
| Rollback runtime | `49529c9484348bee398147a0a294693d2644ca16` / `C:\movieXsuggestion\MyProject\grevity_fitness-runtime-v9` |
| Live DB | `C:\movieXsuggestion\MyProject\grevity_fitness\.gravity\data\gravity.sqlite3` |
| Protected config | `C:\ProgramData\GravityFitness\gravity.env` — not created yet |
| Protected ngrok config | `C:\ProgramData\GravityFitness\ngrok.yml` — not created yet |
| ngrok executable | `C:\Program Files\ngrok\ngrok.exe` — not installed yet |
| Production public URL | **UNRESOLVED / NO-GO** |
| Fresh pre-admin-v1 backup | **UNSET until after reboot acceptance while still on migration 009** |
| Off-host backup copy/hash | **UNSET** |

The protected files must be created only in the controlled operator window with least-privilege ACLs. Secret values must never be written to Git, release docs, or chat.

## Controlled lifecycle command sequence

Run from the final detached RC only after protected paths exist. The first step is non-mutating:

```powershell
.\scripts\install-gravity-tasks.ps1 `
  -ConfigPath 'C:\ProgramData\GravityFitness\gravity.env' `
  -EnsureNgrok `
  -NgrokConfigPath 'C:\ProgramData\GravityFitness\ngrok.yml' `
  -NgrokExecutablePath 'C:\Program Files\ngrok\ngrok.exe' `
  -ExpectedReleaseSha 'c4f2219a77f0a1248497c15c5eef6bc5389dd476' `
  -RequireDetachedHead `
  -PreflightOnly
```

Chat 3 must independently run/read this protected-path/task/ngrok preflight before any live lifecycle mutation. Any SHA, ACL, executable/config identity, loopback-target, task-plan, or secret-argument blocker is an immediate NO-GO.

Only with explicit elevation/authorization may the operator then perform the documented controlled ngrok transition and install the three SYSTEM/Highest scheduled tasks. Never launch a duplicate tunnel or stop an unverified PID.

After installation, run `verify-gravity-tasks.ps1` with the same exact SHA/config/ngrok tuple. Keep the live database on migration 009 throughout this lifecycle step.

## Reboot acceptance and final backup gate

After task installation is green, perform exactly one deliberate reboot. Chat 3 must run from the exact final RC:

```powershell
.\scripts\release-lifecycle-check.ps1 `
  -ConfigPath 'C:\ProgramData\GravityFitness\gravity.env' `
  -ExpectedReleaseSha 'c4f2219a77f0a1248497c15c5eef6bc5389dd476' `
  -RequireDetachedHead `
  -EnsureNgrok `
  -NgrokConfigPath 'C:\ProgramData\GravityFitness\ngrok.yml' `
  -NgrokExecutablePath 'C:\Program Files\ngrok\ngrok.exe'
```

Require exit code `0` and JSON `"ready": true`, including current-boot backend/task/ngrok/notification evidence.

Only after that passes, while production is still migration 009, create the fresh `pre-admin-v1` backup using the pinned-v9 backup script, then verify it, recovery-drill it, hash it, and copy it to protected off-host storage. The older rehearsal archives are evidence only and do not satisfy this final gate.

## Final GO / NO-GO rule

Migration 010 remains forbidden until production ingress, protected deployment preflight, elevated ngrok/task installation, reboot acceptance, and the fresh verified/recovery-drilled off-host migration-009 backup are all green and an explicit GO is recorded.

On GO: perform the guarded final-RC/migration-010 cutover and run complete local/public health, owner TOTP/Admin workspaces, approved-customer login, unknown-phone denial, trainer redaction, payment/renewal history, notifications, task history, readiness, and browser smoke.

On any critical failure: stop the candidate safely and restore the fresh migration-009 backup with pinned v9. Never manually edit migration rows or live SQLite/WAL files.

## Ingress resolution update - 2026-08-29 19:39 queue

Chat 1 audited the repository for an already-approved production hostname, reserved production tunnel identity, or custom-domain value. None is present. The only concrete public hostname remains the staging ngrok endpoint; other domain values are examples/placeholders.

Production ingress is therefore explicitly **NO-GO** until the operator supplies and verifies a durable production hostname/tunnel that ordinary browsers can use without the free-tier warning page. The accepted topology is HTTPS on that verified hostname through an explicitly trusted proxy/tunnel to loopback `127.0.0.1:8787`.

No production URL has been invented or frozen. Because ingress is unresolved, the complete deployment tuple cannot yet be finalized and the protected/elevated lifecycle window must not begin. Migration 010 remains prohibited.

## Independent acceptance / operator ingress gate update - 2026-08-29 20:04 IST

- Chat 3 exact final-RC lifecycle acceptance is complete: `c4f2219a77f0a1248497c15c5eef6bc5389dd476`, `C:\movieXsuggestion\MyProject\grevity_fitness-admin-v1-final-rc-c4f2219`, detached and clean, focused ngrok/task/post-reboot suite **37/37 PASS**, with no production mutation. Branch-local documentation evidence is `3560923`; it is not part of the runtime.
- Chat 2 exact-`c4f2219` frontend acceptance remains outstanding and is required before final release disposition.
- Ingress remains **NO-GO pending operator-supplied verified identity**. The unblock checklist is: durable HTTPS hostname; DNS/TLS ownership/control; approved tunnel/proxy provider and identity; stable SYSTEM-accessible executable/config paths; upstream `127.0.0.1:8787`; ordinary-browser root rendering without warning/interstitial; public health behavior; and a documented rollback/disable method.
- Do not place tunnel credentials, tokens, config contents, provider secrets, or recipient data in this document. Identity/path/ownership evidence only.
- Protected deployment, lifecycle installation, reboot acceptance, fresh pre-admin-v1 backup, migration 010, and cutover remain blocked until their ordered gates are satisfied.

## Independent exact-RC acceptance complete - 2026-08-29 20:57 IST

- Chat 2 final frontend sign-off is complete for exact RC `c4f2219a77f0a1248497c15c5eef6bc5389dd476` at `C:\movieXsuggestion\MyProject\grevity_fitness-admin-v1-final-rc-c4f2219`; detached/clean identity was verified and the shipped `web/` tree matches `b6b42d7`.
- Accepted Chat 2 counts: corrected deterministic **2/2 PASS**; focused stress **3/3 PASS**; Admin/customer **29/29 PASS**; responsive/accessibility **4/4 PASS**; integration-risk **14/14 PASS**; no reproducible frontend defect and no production mutation. Branch-local evidence is `7cb2027`, reconfirmed by `af1db69`; these docs-only commits are not runtime inputs.
- Chat 3 final lifecycle sign-off remains accepted at **37/37 PASS** for the same exact detached/clean RC, with no production mutation.
- There is now no remaining internal exact-RC acceptance blocker. Do not repeat already-green Chat 2/3 acceptance unless frozen runtime code changes or a reproducible defect appears.
- Production ingress remains **NO-GO** until the operator supplies verifiable durable hostname/tunnel/proxy identity and ownership/control facts. Protected deployment, tunnel transition, SYSTEM tasks, reboot, fresh backup, migration 010, and cutover remain gated in that order.
