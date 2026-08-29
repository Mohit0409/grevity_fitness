# Gravity Fitness - AI Agent Coordination

Last updated: 29 August 2026

This is the canonical ownership map for every AI chat working on Gravity Fitness. Read it before editing any repository file.

## Product Priority

Gravity Fitness Admin Software is the primary V1 product.

Core rule:

- Owner manages the gym.
- Customer sees their membership.
- System handles reminders.

Primary Admin V1 navigation: Dashboard, Customers, Memberships, Fees / Payments, Notifications, then Settings / Advanced.
Public website polishing is secondary unless required for a release regression.

## Repositories / Worktrees

Primary integration repo: `C:\movieXsuggestion\MyProject\grevity_fitness`

| Chat | Role | Status | Branch / worktree |
| --- | --- | --- | --- |
| **Chat 1** | **Admin backend + business logic + final integration lead** | **Active** | `main` / primary repo |
| **Chat 2** | **Admin Software frontend + product UX** | **Active** | `agent/gravity-public-ui` / `C:\movieXsuggestion\MyProject\grevity_fitness-public-ui` |
| **Chat 3** | **Admin reliability + QA + operations** | **Handoff ready; integration pending** | `agent/gravity-admin-ops` / `C:\Users\91896\AppData\Local\Temp\gravity-admin-ops` |

## Current Integration Baseline

- Local `main` baseline before the Chat 1 Admin V1 commit: `49529c9`.
- Local `main` also contains reviewed notification / ops integrations including `d482460`, `145fb37`, `bcb3034`, and notification backend `aadfc6f`.
- `origin/main` remains at `aadfc6f` until final Admin Software release gates are complete.
- Live Gravity remains on migration 009. Migration 010 must not be applied live until Chat 2 and Chat 3 are integrated and final release gates pass.

## Chat 1 - Admin Backend / Integration Lead

Chat 1 owns Admin Software domain logic, customer provisioning, membership lifecycle, manual reception payments, fees, dashboard aggregates, admin API contracts, authentication provisioning policy, database migrations, and final integration.

Current Admin Software Backend V1 state:

- New migration: `010_admin_software_v1.sql`.
- Fresh database applies 10/10 migrations and reports schema stage `admin_software_v1`.
- Migration 009 - 010 preservation regression covers customers, Firebase identities, sessions, memberships, notifications, admins, and existing Razorpay payment intents.
- Customers are owner-created and mobile numbers are normalized / unique for non-deleted accounts.
- First mobile OTP login attaches Firebase identity to the existing owner-created customer.
- Unknown verified phones fail closed with `account_not_provisioned`; customer self-registration is disabled.
- Existing linked identities remain supported.
- Add Customer can atomically create customer + initial membership + optional initial manual payment.
- Manual payment ledger supports cash, UPI, card, bank transfer, and other; pending balance is derived from membership snapshot price minus recorded payments.
- Payment and renewal operations support `Idempotency-Key` replay protection.
- Renewal preserves membership history and suppresses obsolete expiry reminders.
- Customer disable / owner phone change revoke active customer sessions.
- Admin dashboard values are server-calculated, use the India business day, and do not double-count membership history.
- Admin Software targeted suite: 15/15 PASS.
- Auth suite under owner-provisioned model: 15/15 PASS.
- Cross-domain Admin/Auth/Membership/Payment/Notification gate: 65/65 PASS.
- Full backend release suite: 146/146 PASS.

Primary Admin V1 routes:

- `GET /api/admin/dashboard`
- `GET|POST /api/admin/customers`
- `GET|PATCH /api/admin/customers/{customerId}`
- `POST /api/admin/customers/{customerId}/renew`
- `GET /api/admin/memberships`
- `GET /api/admin/payments`
- `GET /api/admin/fees`
- `POST /api/admin/memberships/{membershipId}/payments`
- existing plan and notification routes remain available.

## Chat 2 - Admin Software Frontend

Chat 2 owns the software-style Admin application shell and V1 owner workflows: Dashboard, Customers, customer detail, Add Customer, Memberships, Renew Membership, Record Payment, Fees, Notifications, responsive behavior, accessibility, and browser E2E.

Current state:

- Branch: `agent/gravity-public-ui`.
- Chat 2 Admin Software UI handoff was reviewed and integrated into local `main` as `6523989`, `fc19d7f`, and `c91ce85`. Chat 2 completed its role-aware/loading/race hardening in clean code commit `0a323dd` with README handoff `1eec0c3`; Chat 1 should review/cherry-pick `0a323dd` deliberately and skip the README-only handoff.
- Integrated UI covers the software shell, dashboard, customers, customer detail, memberships, fees, renewal, manual payment, notification views, responsive behavior, accessibility, and stable payment/renewal idempotency keys.
- Chat 2 must consume Chat 1 server-owned calculations and must not fake persistent customer/payment state client-side.
- Chat 2 next slice is actively owned in its worktree: role-aware payment/notification visibility, loading/error states, and stale-request/race hardening across Admin frontend files. Chat 1 must not edit those frontend files while that work is uncommitted.
- Chat 1 customer auth UI now maps `account_not_provisioned` to clear contact-the-gym/reception guidance; customer self-registration remains disabled server-side.

## Chat 3 - Admin Reliability / QA / Operations

Chat 3 owns Admin Software workflow QA, backup/recovery validation, performance/index analysis, operational health checks, Windows/Termux safety, crash/retry testing, and security acceptance tests.

Current state:

- Branch: `agent/gravity-admin-ops`; clean at `017080e` (`test: capture customer filter page boundary`).
- Chat 3 reliability/ops code through `54c38c3` was integrated into local `main` as `a61a684`, `51865fd`, and `2d2b0a3`; release-verification follow-up is `f99cd20`.
- `017080e` marks the old customer-plan page-boundary bug as expected failure. Chat 1 fixed that bug in `2ea3b38`; on the next Chat 3 sync, convert this into a normal passing regression instead of merging the stale expected-failure marker.
- Chat 3 should continue scale/failure/security validation and must not apply migration 010 to the live Gravity database.

## Admin scale checkpoint

- Chat 1 removed customer-list, dashboard, membership-payment, Fees, and Admin-notification N+1/full-scan hot paths without adding a new migration.
- Exact current synthetic 5,000-customer checkpoint: customer list ~58 ms median, search ~67 ms, dashboard ~1.04 s, membership expiry ~0.76 s, Admin notifications ~1.91 s, Fees ~0.81 s.
- Admin notifications improved from ~51.4 seconds median before optimization to ~1.91 seconds median on the same synthetic scale class.
- Fees `pendingOnly` is applied before row limiting and `pendingFeesTotalPaise` now represents the full filtered ledger rather than only returned rows.
- Full backend gate after these shared lifecycle changes: 163/163 PASS. These are synthetic local QA measurements, not production SLO guarantees.

## Existing Notification Provider Reality

- Membership expiry reminders support 7 / 3 / 1 / 0-day windows and customer + owner fan-out across email, SMS, and WhatsApp delivery records.
- SMTP is the only bundled real delivery adapter.
- SMS and WhatsApp remain fail-closed until a real external provider is selected and configured.
- Never claim SMS / WhatsApp production delivery is enabled solely because credentials exist.

## Coordination Rules

1. Read this file and run `git status --short --branch` before editing.
2. Never switch or reset another chat's worktree.
3. Never use `git reset --hard`, `git clean`, checkout-overwrite, or equivalent against another chat's work.
4. Do not edit another active chat's owned files without coordination.
5. Keep secrets, Firebase Admin JSON, `.env`, runtime DBs, logs, and backups outside Git.
6. Use temporary databases for destructive Admin Software tests.
7. Chat 2 and Chat 3 do not merge into `main`; Chat 1 reviews and integrates handoffs deliberately.
8. Every handoff reports branch, commit SHA, changed files, tests, and blockers.
9. Migration 010 stays off the live database until final integrated release gates pass and a fresh verified pre-migration backup exists.
10. Update this file when ownership, handoff SHA, or rollout state changes.

## Current coordination - 2026-08-29 18:41 IST

- Release decision: **intentional no-go; production remains safely pinned to migration 009.** Migration 010 was rehearsed only on an isolated restored copy, was not applied live, no cutover was attempted, and no release push was performed. The exact rehearsal evidence and provisional cutover tuple are in `docs/ADMIN_V1_RELEASE_CANDIDATE.md`.
- Chat 1 has now integrated the Admin V1 release stack through `b6b42d7`: Chat 3 lifecycle/adoption/post-reboot commits appear on `main` as `922ec5c`, `2d1a4f8`, `c762b85`, and Chat 2 stress product code appears as top commit `b6b42d7`. Chat 2's later `760a07b` is test-only and remains outside `main` pending an explicit include/skip decision. Final exact-SHA release gates must be rerun after that decision.
- Current static/security gates pass: `git diff --check`, Python compilation, syntax checks for all 27 tracked JavaScript files, tracked-file secret-value scan, private-key-header scan, and forbidden tracked runtime/credential-file scan. Temporary synthetic Admin QA at 100/500/1,000/5,000 customers reports `ready: true`, no blockers, valid foreign keys, and single-record payment/renewal idempotency replays.
- Chat 1 release ops: the current clean detached RC is `C:\movieXsuggestion\MyProject\grevity_fitness-admin-v1-final-rc-b6b42d7` at `b6b42d7264a1ee8ca7fac06b994a9fbb8f8fb24e`, but it remains provisional until the `760a07b` decision. Live production is still the detached pinned-v9 runtime at `C:\movieXsuggestion\MyProject\grevity_fitness-runtime-v9` / `49529c9`; PID 4644 owns only `127.0.0.1:8787`, health is green, and the live database remains migrations 001-009 / `notification_owner_fanout` with no `membership_payments` table.
- Isolated release rehearsal: the verified/recovery-drilled v9 archive `gravity-rc-rehearsal-20260829T111931084801Z.zip` was restored away from production and migrated 009 -> 010 with the immutable candidate. All original-column data across 33 pre-existing business tables matched the untouched restore; quick/foreign-key checks passed. RC health, MFA Admin login and all workspaces, customer provisioning/verified-phone login, unprovisioned-phone denial, trainer financial redaction, and the second-owner guard passed. A separate restored 009 copy started healthy under pinned v9 on a temporary port and stopped cleanly, proving the rollback pairing. Production was unchanged.
- Public tunnel: ngrok 3.39.9 is running as PID 15356 and `https://foyer-amenity-staff.ngrok-free.dev` forwards to `http://127.0.0.1:8787`. Public API health is HTTP 200 with `ngrok-skip-browser-warning: true`; the free-tier warning/interstitial still applies without that header.
- Rollback readiness: `C:\movieXsuggestion\MyProject\grevity_fitness\.gravity\backups\gravity-pre-runtime-v9-recovery-20260829T095241341470Z.zip` was reverified with the pinned v9 code and passed an isolated recovery drill. It contains migration 009 / `notification_owner_fanout`, 2 customers, 0 memberships, 1 active owner, and 3 active plans. This is a verified rollback checkpoint, not the still-required fresh backup immediately before any future 009 -> 010 migration. The guarded stop/verify/restore/start procedure remains in `docs/OPERATIONS_RUNBOOK.md` and `docs/LAUNCH_RUNBOOK.md`.
- Lifecycle code passed the isolated Windows drill on a temporary port: start/status, online backup, recovery drill, migration export, forced-crash watchdog replacement, and stop all passed. Actual reboot recovery is still **not installed**: `GravityFitness-Watchdog`, `GravityFitness-DailyBackup`, and `GravityFitness-Notifications` are absent. The available host identity is not an administrator. The current ngrok tunnel was started manually and has no managed PID/state files, so installation also requires a controlled stop/adopt/start handoff before enabling the watchdog. The integrated guard was exercised live-safely and refused to launch a duplicate tunnel while PID 15356 remained healthy. The production notification state is stale, so do not claim scheduler health.
- Chat 2: stress product code `9a7111a` is integrated on `main` as `b6b42d7`, and exact detached RC `b6b42d7` received a frontend PASS (responsive/stress 4/4 and integration-risk 14/14). Branch follow-up `760a07b` is test-only (two readiness waits in `tests/e2e/gravity.spec.js`) and makes deterministic source tests 51/51; it is not yet integrated. README-only handoff is `88610ca`.
- Chat 3: lifecycle/adoption/post-reboot code is integrated on `main` as `922ec5c`, `2d1a4f8`, and `c762b85`. Exact detached RC `b6b42d7` independently passed the focused Chat 3 lifecycle/ngrok/task gate 37/37. Branch docs-only handoffs are `b920584` and `e1182d0`; no additional Chat 3 code is pending.
- The earlier work queues have advanced: current `main`/detached RC is `b6b42d7`; Chat 2 product UI and Chat 3 lifecycle tooling both pass on that exact RC. Use the latest `NEW TASK ASSIGNMENTS` section at the end of this file. Migration 010 remains a no-go because Chat 1 still must decide the test-only `760a07b`, refresh the stale release-candidate document, run the final exact-SHA migration rehearsal, resolve production ingress, create protected deployment paths, complete elevated task/ngrok + reboot acceptance, and prove a fresh rollback backup.


## NEW TASK ASSIGNMENTS - 2026-08-29 16:36 IST

This section is the active work queue for all three chats. It supersedes older "next action" notes where they conflict, but all ownership, safety, secret-handling, and migration rules above still apply.

Global release rule: live production stays on migration 009 until Chat 1 explicitly clears every release blocker. Chat 2 and Chat 3 must not merge into `main`, migrate production, stop the live Gravity process, or modify the live database.

### Chat 1 - Release Candidate Integration + Migration Rehearsal

Primary task: build a reproducible Admin V1 release candidate and prove the 009 -> 010 cutover on an isolated copy before considering production.

1. Review Chat 2 final-QA code commit `dd3a407` and integrate only the code commit if clean; skip README-only `097f31a`.
2. Re-run the affected Admin browser gate and full Playwright gate after integration; run static JS/diff/secret checks. Re-run backend gates if any backend or contract file changes during integration.
3. Create an immutable release-candidate checkout/worktree from the exact integrated SHA. Do not use mutable `main` as the future production runtime.
4. Copy the live migration-009 database to a temporary isolated location and rehearse migration 010 there only. Verify schema stage, data preservation, foreign keys, health, Admin login/workspaces, customer provisioning/login behavior, and rollback compatibility.
5. Record a cutover tuple: release SHA, immutable runtime path, config path, live DB path, fresh-backup command/path, rollback runtime/archive, ngrok transition method, scheduled-task install/verify commands, and smoke checks.
6. Do not deploy migration 010 until Chat 3 lifecycle tooling is integrated, an elevated operator can install/verify the SYSTEM tasks, and a fresh live migration-009 backup passes verification + recovery drill immediately before cutover.

Success: Chat 2 final QA is integrated, the isolated 009 -> 010 rehearsal is green, the exact release SHA/runtime and rollback plan are documented, and production is still unchanged unless every release gate is later cleared.

### Chat 2 - Admin Real-World Data Robustness + Small-Screen Stress

Primary task: stress the finished Admin frontend with realistic worst-case content and device constraints; fix only reproducible frontend defects.

1. Continue from clean final-QA commit `dd3a407`; do not modify backend/domain/auth/migration/ops files.
2. Exercise Dashboard, Customers, Memberships, Fees, Notifications, Enquiries, Readiness, Team Access, Coaching, and Audit with deterministic 0/1/50/200-row datasets, long customer/plan names, long enquiry text, large rupee amounts, long audit metadata, and safe error messages.
3. Validate widths 320, 360, 390, 430, 768, 1024, and 1440 plus low-height mobile viewports (for example 320x568 and 390x667) and 200% text scaling.
4. Ensure there is no page-level horizontal overflow; tables scroll inside labelled/focusable regions; dialogs remain usable; action buttons stay reachable; long text wraps/truncates safely; focus is restored; and loading/401/403/failure states never leave stale privileged or financial data visible.
5. Check for duplicate fetches/listeners, request loops, stale response overwrites, and unnecessary DOM growth on 200-row screens. Do not introduce speculative architecture rewrites.
6. Add focused Playwright regression(s) for any defect fixed, including at least one 320px/long-content overflow case. Run Admin-focused E2E, relevant accessibility checks, JS syntax, and `git diff --check`.

Success: one clean code commit (or explicit no-code-needed result), exact changed files/tests, no backend contract changes, and a handoff for Chat 1. This task is frontend-only and must not touch live production.

### Chat 3 - Lifecycle Preflight + Safe Managed-ngrok Adoption

Primary task: remove the remaining reboot-recovery uncertainty without requiring unsafe live changes from a non-elevated session.

1. Implement a safe managed-ngrok adoption path (dedicated script or explicit switch) that can adopt an already-running Gravity tunnel only after proving the process executable, loopback target, expected port, command/config path, and start metadata match. Refuse ambiguous/foreign tunnels and never print the authtoken.
2. Write managed ngrok PID/state atomically and ensure the existing duplicate-unmanaged-tunnel guard remains fail-closed. Add tests for valid adoption, mismatched target/path, stale PID, foreign process, and duplicate-tunnel cases using temporary processes/state only.
3. Add a read-only Windows scheduled-task verifier/preflight that checks all three tasks: `GravityFitness-Watchdog`, `GravityFitness-DailyBackup`, and `GravityFitness-Notifications`; SYSTEM principal/highest run level; immutable working directory; expected triggers; valid script/config/ngrok paths; loopback backend target; scheduler isolation; and secret-free task arguments.
4. If useful, add a non-mutating `-PreflightOnly`/dry-run path to the installer so the exact sanitized task plan can be validated without Administrator rights. Do not weaken the existing elevation requirement for real task creation.
5. Validate the new tooling with unit/static tests and safe temporary lifecycle drills. The current live ngrok PID must not be stopped/adopted/mutated from this task unless an explicitly controlled elevated release operation is authorized later.
6. Handoff the exact elevated command sequence Chat 1/operator should use from the immutable release checkout to adopt/start ngrok, install tasks, verify tasks, and confirm health after reboot.

Success: clean ops/test commit(s), no production mutation, safe adoption/preflight tooling, passing reliability tests, and one explicit remaining elevated operator procedure.

### Integration order for this work queue

1. Chat 1 reviews/integrates Chat 2 `dd3a407` first and establishes the next exact integrated SHA.
2. Chat 2 real-world frontend stress work and Chat 3 lifecycle/adoption tooling proceed independently in their own worktrees.
3. Chat 1 reviews and cherry-picks only clean code commits from those handoffs; README-only handoff commits are optional and should not overwrite newer canonical coordination.
4. After the final code integrations, Chat 1 reruns release-impacting browser/backend/static/security gates and refreshes the immutable release candidate.
5. An elevated operator then performs the controlled ngrok managed-state transition and installs/verifies all three SYSTEM scheduled tasks from that immutable release checkout.
6. Only after lifecycle verification is green: create a fresh live migration-009 backup, verify it, recovery-drill it, capture the final cutover tuple, and make a new go/no-go decision for migration 010.

Do not skip directly to migration 010 because tests are green. Reboot recovery, managed tunnel state, fresh rollback backup, and the exact immutable release SHA are release gates, not optional cleanup.


## NEW TASK ASSIGNMENTS - 2026-08-29 17:19 IST

This is the authoritative active queue. It supersedes the 16:36 assignment section where work has already completed. All ownership, safety, secret-handling, worktree, and migration rules above remain mandatory.

Global release state: production remains on pinned v9 / migration 009. Migration 010 is still NO-GO. Chat 2 and Chat 3 must not merge to `main`, touch the live database, stop PID 4644, adopt/restart live ngrok, or install production scheduled tasks.

### Chat 1 - Final RC Consolidation + Release Gate Orchestration

Primary task: turn the successful provisional rehearsal into the exact final release candidate after the remaining clean handoffs are integrated.

1. Review Chat 3 code/ops commit `4d41870` now and cherry-pick it if clean. Skip README-only handoff `fd3c451` unless a small coordination detail is useful; do not merge the Chat 3 branch.
2. Validate the Chat 3 integration with the focused ngrok/operations/task-preflight suites plus PowerShell parse, Python compile, diff, and secret-value checks. Do not run any live adoption/task installation from the normal non-elevated session.
3. Keep provisional detached RC `5725e47` as rehearsal evidence only. Do not mutate or repurpose that checkout after new code is integrated.
4. Wait for Chat 2 to finish its active stress task and provide one clean code commit. Review/cherry-pick only the clean code commit; do not integrate its temporary/debug state or README-only handoff blindly.
5. After all final code handoffs are integrated, create a NEW clean detached immutable RC at the exact final SHA and update `docs/ADMIN_V1_RELEASE_CANDIDATE.md` with that identity.
6. Run the final integrated gates from isolated ports/data: full backend, full Playwright, Admin-focused browser, JS syntax, Python compile, `git diff --check`, tracked secret/private-key/runtime-file scans, and the relevant operations/reliability tests.
7. Repeat the isolated 009 -> 010 migration rehearsal with the final exact RC SHA (not the old provisional SHA), including data preservation, foreign keys, Admin/customer/RBAC smoke, and pinned-v9 rollback pairing.
8. Close the ingress decision before production: the current free-tier ngrok URL still presents an interstitial without the bypass header. Treat it as staging unless a stable production URL/domain path is explicitly established.
9. Prepare the final operator cutover package: final SHA/runtime, protected `C:\ProgramData\GravityFitness\gravity.env` plan, ngrok adoption-or-controlled-restart path, task preflight/install/verify commands, smoke checks, fresh-backup command, rollback archive/runtime, and abort criteria. Do not put secret values in Git or chat.
10. Do not authorize production migration 010 until Chat 3's post-reboot verifier is integrated, an elevated operator has installed and verified all three SYSTEM tasks, reboot recovery is proven, and the fresh live migration-009 backup passes verification + recovery drill immediately before cutover.

Success: one final immutable RC SHA contains all approved Chat 2/3 code, final integrated/rehearsal gates are green, operator commands are exact, public-ingress status is explicit, and production remains unchanged until a separate go/no-go decision.

### Chat 2 - Finish Stress QA and Produce a Clean Frontend Handoff

Primary task: complete the active small-screen/long-content/large-dataset stress work already in `agent/gravity-public-ui`; do not start a different feature until this handoff is clean.

1. Preserve the legitimate CSS fixes and deterministic stress regressions already being developed in `web/css/admin.css` and `tests/e2e/gravity.spec.js`.
2. Remove temporary diagnostic-only Playwright tests/logging before handoff, including the current `debug ...` stress/geometry/internal-scroll cases, unless a case is converted into a stable assertion-based regression with no console-only diagnostic purpose.
3. Keep strong deterministic coverage for at least: 320x568 long-content containment/dialog usability; 0/1/50/200-row bounded DOM behavior; advanced workspaces with long content; 390x667/200% text scaling; and no page-level horizontal overflow.
4. Recheck Dashboard, Customers, Memberships, Fees, Notifications, Enquiries, Readiness, Team Access, Coaching, and Audit for long unbroken names/metadata, large rupee values, long messages, internal table scrolling, reachable actions, and focus behavior.
5. Verify no duplicate fetch/listener/request-loop or stale-response regression is introduced by the test fixtures or UI fixes. Do not add architecture rewrites or backend contract changes.
6. Run the focused new stress tests first, then the full Admin-focused browser gate and full Playwright suite. Run JS syntax for changed files, accessibility checks used by the suite, and `git diff --check`.
7. Produce ONE clean frontend code commit with only justified product/test changes. Put the handoff/coordination update in a separate optional docs commit. Report exact test counts and changed files to Chat 1.

Success: branch is clean, no `debug ...` tests remain, stress regressions are deterministic and green, no backend/auth/migration/ops files changed, and Chat 1 receives one clean code SHA to integrate.

### Chat 3 - Post-Reboot Release Lifecycle Acceptance

Primary task: build the read-only post-install/post-reboot acceptance check that proves the final Windows deployment actually recovered correctly after the elevated lifecycle step.

1. Continue from clean lifecycle handoff `4d41870` / `fd3c451`; do not modify `main` or the live production state. Sync safely with newer canonical coordination when needed without rewriting shared history.
2. Add a read-only release-lifecycle verification command/script that accepts the protected config path and expected final release SHA and returns a safe JSON result plus non-zero exit on blockers.
3. Verify the backend managed state after boot: exact release checkout/SHA, clean detached checkout where required, expected Python/runtime identity, loopback `127.0.0.1:8787`, managed PID ownership, healthy `/api/health`, and process start metadata consistent with the current Windows boot.
4. Reuse/compose `verify-gravity-tasks.ps1` to prove all three scheduled tasks are present/correct and inspect safe runtime status such as enabled state, LastTaskResult, LastRunTime/NextRunTime where available. Boot-triggered Watchdog/Notifications must have evidence from the current boot; DailyBackup should be evaluated against its daily schedule rather than falsely requiring a boot run.
5. Verify managed ngrok state read-only: managed PID/state files agree with the real process, exact executable/config path and loopback target match, the tunnel API exposes exactly the expected Gravity HTTPS tunnel, and public `/api/health` is green with the ngrok warning-bypass header. Never print/read out the authtoken value.
6. Include safe notification-operability checks: scheduler state/lock is not stuck, last successful cycle/failure counters are reported without recipient/provider secrets, and stale production notification state remains a blocker until an actual scheduled cycle succeeds.
7. Where useful, include latest backup/recovery-drill freshness as a release-health signal, but do not create/restore a live backup from this verifier. It must remain read-only.
8. Add deterministic tests using synthetic/temp evidence for healthy boot, wrong SHA/runtime, stale/foreign PID, missing/bad task, failed LastTaskResult, unmanaged/mismatched ngrok, stale notification state, and success. Run focused ops/reliability tests, PowerShell parse, Python compile, diff, and secret-value scans.
9. Update `docs/OPERATIONS_RUNBOOK.md` with one exact post-reboot acceptance command and the pass/fail interpretation. Do not install tasks, reboot Windows, adopt live ngrok, or migrate the live DB in this Chat 3 task.

Success: one clean code/ops commit (plus optional docs handoff commit) gives Chat 1/operator a single read-only post-reboot verification step with clear blockers and no secrets/PII. Production remains unchanged.

### Integration order for the 17:19 queue

1. Chat 1 reviews/cherry-picks Chat 3 `4d41870` first and validates the ops delta; this removes the current "tooling not integrated" blocker.
2. Chat 2 finishes its currently active stress task and hands off one clean frontend code SHA; Chat 3 builds the post-reboot acceptance verifier independently in its own worktree.
3. Chat 1 reviews/cherry-picks the clean Chat 2 stress SHA and the clean Chat 3 post-reboot-verifier SHA. README-only branch handoffs must not overwrite newer canonical coordination.
4. Chat 1 creates a new final detached immutable RC from the exact consolidated SHA and reruns full integrated/static/security gates plus the final isolated 009 -> 010 rehearsal.
5. Only after that final RC is frozen should an elevated operator prepare the protected config/ngrok paths, perform the controlled managed-ngrok adoption or restart, install all three SYSTEM scheduled tasks, and verify them.
6. Reboot the host only as a deliberate operator acceptance step, then run Chat 3's read-only post-reboot verifier. Any failed lifecycle/task/ngrok/notification check is a production migration NO-GO.
7. After reboot acceptance is green and production is still on migration 009, Chat 1 creates the fresh `pre-admin-v1` live backup, verifies it, recovery-drills it, records hashes/path off-host, and makes the final go/no-go decision.
8. Migration 010 remains prohibited until that final decision. If any cutover-critical check fails, keep/restore the pinned v9 runtime and migration-009 database instead of applying ad-hoc live fixes.

The current free-tier ngrok URL is suitable for staging checks but still shows an interstitial to ordinary browser traffic. Do not silently treat that staging URL as a polished production ingress.


## NEW TASK ASSIGNMENTS - 2026-08-29 17:56 IST

This is the authoritative remaining-work ledger for all three chats. It supersedes earlier task queues where work is complete or status has changed. Every item below is still required unless it is explicitly marked conditional on a later release gate.

Current confirmed state before this queue:
- Production backend is healthy on PID `4644`, bound only to `127.0.0.1:8787`.
- Live database remains at 9 migrations; latest is `009` / `notification_owner_fanout`; `membership_payments` does not exist. Migration 010 remains prohibited.
- Current ngrok PID is `15356`, using the per-user WindowsApps executable and `C:\Users\91896\AppData\Local\ngrok\ngrok.yml`; managed ngrok PID/state files are absent.
- Current shell is not elevated. `GravityFitness-Watchdog`, `GravityFitness-DailyBackup`, and `GravityFitness-Notifications` are all absent.
- Intended protected paths `C:\ProgramData\GravityFitness\gravity.env`, `C:\ProgramData\GravityFitness\ngrok.yml`, and `C:\Program Files\ngrok\ngrok.exe` do not yet exist on this host.
- Chat 2 stress code is clean at `9a7111a`. Chat 3 code is clean as `4d41870` + `af92d84` + `0a77c06`; an isolated cherry-pick onto current `main` passed 37/37 focused tests.
- Old detached RC `5725e47` is rehearsal evidence only. It is not the final release candidate.

Global safety: Chat 2 and Chat 3 must not merge to `main`, migrate or edit the live database, stop PID 4644, stop/adopt/restart live ngrok, install scheduled tasks, or reboot the host unless Chat 1 has frozen the final RC and an explicitly controlled elevated operator step is authorized.

### Chat 1 - Final Integration, Final RC, Production Go/No-Go

Primary responsibility: own every remaining integration/release decision and keep production on v9/migration 009 until all lifecycle, ingress, rollback, and smoke gates are green.

1. Review and cherry-pick Chat 3 code in this order: `4d41870`, `af92d84`, `0a77c06`. Do not merge the Chat 3 branch or use README-only handoff commits. Re-run the focused ngrok/task/lifecycle acceptance tests after integration.
2. Review and cherry-pick Chat 2 stress code `9a7111a`. Confirm only `tests/e2e/gravity.spec.js` and `web/css/admin.css` are affected and no temporary `debug ...` tests or diagnostic-only logging are present.
3. After both handoffs are integrated, update canonical coordination and `docs/ADMIN_V1_RELEASE_CANDIDATE.md` so stale statements about uncommitted Chat 2/3 work are removed.
4. Create a NEW detached, clean, immutable release-candidate checkout at the exact consolidated SHA. Never repurpose `grevity_fitness-admin-v1-rc-5725e47` and never use mutable `main` as production runtime.
5. Run final code gates on the new RC using isolated ports/data: full backend tests, full Playwright, Admin-focused/stress browser tests, JS syntax, Python compile, PowerShell parse, `git diff --check`, tracked secret-value/private-key/runtime-file scans, and relevant ops/reliability suites. Record exact counts.
6. Repeat the isolated migration `009 -> 010` rehearsal using the NEW final RC SHA and a freshly restored migration-009 copy. Recheck data preservation, foreign keys, `membership_payments`, Admin MFA/workspaces, customer provisioning/login denial for unknown phones, trainer financial redaction, second-owner guard, notification workflow, and pinned-v9 rollback compatibility.
7. Decide the production ingress before cutover. The current free ngrok URL is staging-quality because ordinary browser traffic sees the interstitial. Either establish a stable production URL/domain/tunnel path or explicitly keep production rollout NO-GO; do not silently ship the free interstitial as polished production ingress.
8. Freeze the exact deployment tuple: final RC SHA/path, protected config path, live DB path, Python path, ngrok executable/config path, public URL, rollback v9 SHA/path, fresh backup path/hash, scheduled-task commands, post-reboot acceptance command, smoke commands, and abort criteria. Never record secret values.
9. Prepare the protected deployment layout under `C:\ProgramData\GravityFitness` and a SYSTEM-accessible ngrok executable only during the controlled release window. Verify ACLs allow the deployment account/SYSTEM and do not expose secrets broadly.
10. With an elevated operator and while production is still migration 009, run Chat 3 task/ngrok preflight from the final detached RC. If the current per-user ngrok executable/config does not exactly match the final protected paths, do not adopt it; perform the documented controlled transition instead of creating a duplicate tunnel.
11. Install and verify `GravityFitness-Watchdog`, `GravityFitness-DailyBackup`, and `GravityFitness-Notifications` as SYSTEM/Highest from the final immutable RC. Verify exact working directory, config/ngrok paths, triggers, `IgnoreNew`, enabled state, and secret-free arguments.
12. Perform the deliberate reboot acceptance only after task installation is green. Run `release-lifecycle-check.ps1` from the final RC. Any blocker involving SHA/runtime/PID/listener/health/tasks/ngrok/current-boot notification evidence is an immediate NO-GO.
13. After reboot acceptance is green and production is still migration 009, create a fresh `pre-admin-v1` live backup with pinned v9, verify it, recovery-drill it, record hashes/path, and copy it to protected off-host storage. The older rehearsal/recovery archives do not replace this gate.
14. Make the final production go/no-go decision. If NO-GO, leave/restore pinned v9 and migration 009. If GO, perform the guarded cutover to the final RC/migration 010, then run local/public health, owner TOTP/Admin workspaces, real approved customer login, unknown-phone denial, trainer redaction, payment/renewal history, notifications, task history, and readiness smoke.
15. If any cutover-critical check fails, stop the candidate safely and execute the documented rollback to the fresh migration-009 archive plus pinned v9 runtime; do not edit migration rows or live SQLite files manually.
16. After a successful release, record final SHA/runtime/backup/task/ingress evidence in the release docs, remove superseded rehearsal-only wording, then push/tag the reviewed release according to the project's normal source-control policy.

Success: final immutable RC and rollback tuple are reproducible, full final gates and final 009->010 rehearsal are green, protected lifecycle/ingress are operational after reboot, fresh rollback backup is proven, and only then is migration 010 authorized.

### Chat 2 - Final Frontend Handoff + Independent RC UI Acceptance

Primary responsibility: finish the release-side frontend evidence for clean stress commit `9a7111a`; do not start unrelated features before Admin V1 release disposition.

1. Treat `9a7111a` as the code handoff. Keep the branch clean; do not amend/rewrite it. Confirm the handoff contains only `tests/e2e/gravity.spec.js` and `web/css/admin.css` and no debug-only tests/logging.
2. Re-run/record the focused stress regressions covering 320x568 long-content containment/dialog usability, 0/1/50/200-row bounded DOM behavior, advanced workspace long content, 390x667 at 200% text, and no page-level horizontal overflow.
3. Run the Admin-focused browser gate and full Playwright suite from the Chat 2 branch, plus changed-JS syntax/a11y checks and `git diff --check`. Record exact counts and any intentionally skipped cases.
4. Create a separate optional README/handoff commit only if needed to record `9a7111a`, exact changed files, test counts, and blockers. Chat 1 should integrate the code commit, not blindly overwrite canonical coordination with branch README text.
5. After Chat 1 creates the NEW final detached RC, independently validate that exact RC UI without modifying it: widths 320/360/390/430/768/1024/1440, low-height mobile, 200% text, long unbroken content, large rupee values, internal table scrolling, dialog/action reachability, focus restoration, stale privileged-data clearing, and the major Admin workspaces.
6. Recheck Dashboard, Customers, Memberships, Fees, Notifications, Enquiries, Readiness, Team Access, Coaching, and Audit on the final RC for integration-only regressions and request/listener loops.
7. If the final RC exposes a real frontend defect, fix only the reproducible frontend issue in one small new Chat 2 commit, add a deterministic regression, rerun affected/full browser gates, and hand that SHA to Chat 1. Do not touch backend/auth/migration/ops files.
8. If no defect is found, report an explicit frontend release sign-off for the exact final RC SHA and stop changing the branch until after the Admin V1 release decision.

Success: `9a7111a` has complete test evidence, final RC receives an independent responsive/accessibility/stress sign-off, and any later fix is minimal/frontend-only with its own clean SHA.

### Chat 3 - Complete Ops Handoff + Final RC Lifecycle Acceptance Support

Primary responsibility: finish the lifecycle handoff and independently prove the final RC's reboot/lifecycle acceptance tooling; do not perform live lifecycle changes until Chat 1 freezes the RC and authorizes the controlled operator window.

1. Current code handoff sequence is `4d41870` -> `af92d84` -> `0a77c06`. Preserve those commits; do not rewrite history. The isolated cherry-pick proof onto current `main` has passed 37/37 focused tests and should be recorded in the handoff.
2. Create one README-only Chat 3 handoff commit recording: the three code SHAs/order, 64/64 focused Chat 3 suite, 37/37 isolated integration proof, exact-config prefix/suffix collision regressions, safe live ngrok probe result, post-reboot verifier behavior, changed files, and production-nonmutation statement. Chat 1 should not cherry-pick that docs commit unless useful.
3. After Chat 1 integrates the three code commits, inspect the integrated `main`/final RC read-only and rerun the focused ngrok/task/post-reboot tests from that exact integrated checkout. Report any integration-only failure before lifecycle installation.
4. Once Chat 1 provides the final detached RC SHA/path plus intended protected config/Python/ngrok paths, run only non-mutating preflight first: release SHA/detached cleanliness, SYSTEM task plan, script/config paths, loopback target, ngrok executable/config identity, and secret-free arguments.
5. Verify ACL/access assumptions for the protected config and ngrok files. Report whether SYSTEM can read the required files without printing their contents or secret values.
6. During the elevated lifecycle window, Chat 3 may execute live task/ngrok lifecycle commands only if Chat 1/operator explicitly authorizes it for the frozen final RC. Otherwise provide the exact commands and remain read-only. Never kill the old tunnel blindly and never launch a second tunnel.
7. After deliberate reboot, run the final RC `release-lifecycle-check.ps1` and require exit 0 plus `ready:true`. Capture only safe JSON evidence. Diagnose blockers without modifying the live database or migration state.
8. Confirm the post-reboot report proves: final SHA/runtime/Python identity, managed PID/listener/current-boot start metadata, all three tasks present/enabled/successful with correct current-boot evidence, managed ngrok exact executable/config/target/public health, notification scan+delivery success from the current boot with no stuck lock, and no unexpected failure counters.
9. Treat backup/recovery evidence in the post-reboot verifier as informational/read-only. Do not create or restore the final live backup; Chat 1 owns that fresh pre-migration gate after lifecycle acceptance.
10. If the verifier finds a lifecycle defect, create only a minimal ops/test fix in Chat 3, reproduce it with synthetic/temp evidence, rerun the focused suite and isolated integration proof, and hand the new SHA to Chat 1 before any retry of the production lifecycle window.
11. After Chat 1's final go/no-go, remain available for read-only post-cutover lifecycle verification; do not independently run migration 010, restore production, or change business data.

Success: Chat 1 receives a complete auditable ops handoff; final RC preflight is green; post-reboot `release-lifecycle-check.ps1` is green with current-boot task/ngrok/notification evidence; no secrets/PII are exposed and no database mutation is performed by Chat 3.

### Mandatory remaining integration/release order

1. Chat 1 integrates Chat 3 `4d41870` -> `af92d84` -> `0a77c06` and validates them.
2. Chat 1 integrates Chat 2 `9a7111a` and validates the frontend stress delta.
3. Chat 1 creates the NEW immutable final RC. Chat 2 and Chat 3 independently validate that exact RC in their owned areas.
4. Chat 1 reruns full final code/static/security tests and the final isolated migration-010 rehearsal on that RC.
5. Resolve production ingress and create/secure the protected config/ngrok deployment paths. No secrets enter Git/chat.
6. Only with explicit elevation/authorization: transition ngrok safely if necessary, install/verify the three SYSTEM tasks, and keep the live DB on migration 009.
7. Perform one deliberate reboot and require Chat 3's post-reboot lifecycle verifier to be green, including fresh notification-cycle evidence.
8. Still on migration 009, create/verify/recovery-drill/offsite-copy the fresh `pre-admin-v1` backup.
9. Chat 1 makes the final GO/NO-GO decision. Migration 010 is allowed only after every prior item is green.
10. On GO: controlled cutover + full smoke + release documentation/tagging. On any critical failure: rollback to the fresh migration-009 backup and pinned v9; no ad-hoc live database fixes.

Until step 9 explicitly says GO, the correct production state is the current pinned v9 runtime with migration 009.


## NEW TASK ASSIGNMENTS - 2026-08-29 18:41 IST

This is the authoritative remaining-work queue for all three chats. It supersedes the 17:56 queue where status has advanced. Do not restart completed implementation work; only the items below remain active or become active after their stated gate.

Current confirmed release state:
- `main` is clean at `b6b42d7`; detached RC `C:\movieXsuggestion\MyProject\grevity_fitness-admin-v1-final-rc-b6b42d7` is clean at full SHA `b6b42d7264a1ee8ca7fac06b994a9fbb8f8fb24e`.
- Chat 2 product stress commit `9a7111a` and Chat 3 lifecycle stack are already integrated in `b6b42d7`.
- Chat 2 exact-RC product verdict is PASS: responsive/stress 4/4 and integration-risk UI 14/14. A test-only follow-up `760a07b` stabilizes two async Admin stress tests and produces full Playwright 51/51; docs-only handoff is `88610ca`.
- Chat 3 exact-RC lifecycle/ngrok/task gate is 37/37 PASS. No Chat 3 code remains unintegrated; branch handoffs `b920584` and `e1182d0` are docs-only.
- `docs/ADMIN_V1_RELEASE_CANDIDATE.md` is stale: it still names rehearsal SHA `5725e47` and says Chat 2/3 work is uncommitted.
- Production remains pinned v9 on PID `4644`, loopback `127.0.0.1:8787`, migration 009. The current operator session is not elevated, Gravity scheduled-task count is 0, and the protected deployment files do not exist yet.
- The current free ngrok ingress remains staging-quality because ordinary browser traffic sees the free-tier interstitial.

Global freeze rule: no unrelated features. Chat 2/3 must not merge to `main`, mutate production data, run migration 010, stop PID 4644, stop/adopt/restart live ngrok, install tasks, or reboot unless the exact later gate explicitly authorizes it.

### Chat 1 - Final Release Decision + Deployment Orchestration

1. Review Chat 2 test-only commit `760a07b` immediately. Preferred outcome is to integrate it if the two readiness waits are clean because it fixes deterministic source-test startup only. If intentionally skipped, record the reason and preserve proof that shipped product assets are identical; do not leave the decision implicit.
2. If `760a07b` is integrated, create a NEW clean detached immutable RC at the new SHA and retire `b6b42d7` to evidence-only status. If it is skipped, explicitly freeze `b6b42d7` as the final RC.
3. Update canonical `AI_AGENTS_README.md` status and fully rewrite/update `docs/ADMIN_V1_RELEASE_CANDIDATE.md` to the chosen final SHA/path. Remove all stale `5725e47`, "Chat 2 uncommitted", "Chat 3 uncommitted", and "in-progress lifecycle tooling" language.
4. Record exact integrated commit mapping, including whether `760a07b` was accepted or intentionally omitted; do not cherry-pick Chat 2/3 README-only handoff commits blindly.
5. Run the final exact-RC code gates: full backend suite, full Playwright, Admin/customer gate, stress tests, JS syntax, Python compile, PowerShell parse, `git diff --check`, tracked secret-value/private-key/runtime-file scans, and focused ops/reliability suites. Record exact counts in the release doc.
6. Repeat the isolated migration 009 -> 010 rehearsal using the CHOSEN final RC SHA and a fresh restored migration-009 copy. This gate is still required because the existing detailed rehearsal was tied to old SHA `5725e47`.
7. In that final rehearsal verify migration inventory, `membership_payments`, original-column/data preservation, quick/foreign-key checks, Admin MFA/workspaces, customer provisioning and approved-phone login, unknown-phone denial, trainer financial redaction, second-owner guard, payment/renewal history, notification workflow, and pinned-v9 rollback pairing.
8. Resolve the production-ingress decision before live cutover. Either establish a stable production URL/domain/tunnel path without the free interstitial or keep release status NO-GO. Do not describe the current free ngrok URL as finished production ingress.
9. Freeze the final deployment tuple: exact RC SHA/path, pinned-v9 rollback SHA/path, live DB path, protected config path, Python path, ngrok executable/config path, public URL, task install/verify commands, post-reboot acceptance command, fresh-backup/off-host path and hash placeholders, smoke checks, rollback commands, and abort criteria. Never record secret values.
10. Prepare the protected deployment layout only in the controlled operator window: `C:\ProgramData\GravityFitness\gravity.env`, protected ngrok config, and a SYSTEM-accessible ngrok executable/path. Apply least-privilege ACLs and verify SYSTEM/deployment-account readability without exposing contents.
11. Before any live lifecycle change, have Chat 3 run the final RC non-mutating preflight against those exact protected paths. Any SHA/path/task-plan/ACL/ngrok-identity blocker is a NO-GO.
12. With explicit elevation and while the live DB is still migration 009, perform the documented controlled ngrok transition. The current per-user WindowsApps executable/config must not be adopted as the final managed tunnel unless it exactly matches the frozen protected tuple; never start a duplicate tunnel.
13. Install and verify `GravityFitness-Watchdog`, `GravityFitness-DailyBackup`, and `GravityFitness-Notifications` as SYSTEM/Highest from the exact final detached RC. Verify working directory, triggers, `IgnoreNew`, enabled state, config/ngrok paths, and secret-free arguments.
14. Perform one deliberate reboot acceptance only after task installation is green. Require Chat 3 `release-lifecycle-check.ps1` exit 0 and `ready:true`, including current-boot backend/task/ngrok/notification evidence.
15. Still on migration 009 after reboot acceptance, create a fresh `pre-admin-v1` live backup with pinned v9, verify it, recovery-drill it, hash it, and copy it to protected off-host storage. Older rehearsal archives do not satisfy this gate.
16. Make the explicit production GO/NO-GO decision. Migration 010 is prohibited until items 1-15 are green or intentionally resolved in writing.
17. On GO, perform the guarded final RC/migration-010 cutover and run local/public health, owner TOTP/Admin workspaces, approved-customer login, unknown-phone denial, trainer redaction, payments/renewals, notifications, task history, readiness, and browser smoke. Keep Chat 2/3 read-only during smoke unless a defect is found.
18. On any critical failure, execute the documented rollback to the fresh migration-009 archive plus pinned-v9 runtime. Never edit migration rows or live SQLite/WAL files manually.
19. After a successful release, update release evidence, remove obsolete rehearsal wording, record final runtime/task/ingress/backup identities, then push/tag using the normal project policy.

Success: one exact final RC and rollback tuple are reproducible, final code + migration rehearsal + ingress + lifecycle/reboot + fresh-backup gates are green, and migration 010 is only applied after explicit GO.

### Chat 2 - Freeze Product UI + Final-RC Independent Acceptance

1. Preserve `9a7111a` and test-only `760a07b`; do not amend/rewrite either. `88610ca` remains a branch-local docs handoff.
2. Do not start new frontend features. Current `b6b42d7` shipped-product UI verdict is already PASS and should remain the baseline.
3. If Chat 1 SKIPS `760a07b` and freezes `b6b42d7`, report that the existing exact-RC acceptance remains valid and make no further code changes unless a reproducible defect appears.
4. If Chat 1 INTEGRATES `760a07b`, validate the new detached RC read-only. First prove the shipped `web/` product tree is unchanged versus `b6b42d7`; then run the two corrected deterministic stress tests, focused stress gate, Admin/customer browser gate, and a concise responsive/integration smoke on the new exact SHA.
5. For whichever SHA Chat 1 freezes, keep coverage for 320/360/375/390/430/768/1024/1366/1440/1920, 320x568, 390x667 at 200% text, long unbroken content, large rupee values, bounded 0/1/50/200-row DOM behavior, table scrolling, dialogs/focus, and all ten Admin workspaces.
6. Recheck the integration-risk flows on the chosen final RC: notification failure/403, customer workflows, Fees/Membership stale responses, Trainer/Reception/Admin RBAC, Enquiries stale/403 clearing, Readiness recovery/403, customer-search races, Dashboard stale-financial clearing/recovery, expired session, Team Access, and Audit.
7. If a real final-RC frontend defect is found, make one minimal frontend/test commit with a deterministic regression and hand that SHA to Chat 1; any such commit invalidates the frozen RC until Chat 1 integrates/rebuilds it. Do not touch backend/auth/migration/ops files.
8. During post-cutover smoke, remain read-only unless Chat 1 asks for a frontend defect investigation. Verify rendering/navigation on representative mobile and desktop widths without changing production data.
9. After exact-SHA sign-off, stop changing the branch until the Admin V1 release disposition is recorded.

Success: no unnecessary product churn, deterministic test source is resolved, and the exact final RC receives an independent frontend sign-off with no integration-only UI regression.

### Chat 3 - Protected-Deployment Preflight + Lifecycle Acceptance

1. No new lifecycle feature code is currently assigned. Integrated lifecycle commits are already on `main` as `922ec5c`, `2d1a4f8`, `c762b85`; exact RC `b6b42d7` passed Chat 3 focused validation 37/37.
2. Keep branch history and docs handoffs (`b920584`, `e1182d0`) intact; do not ask Chat 1 to cherry-pick docs-only commits.
3. If Chat 1 integrates Chat 2 `760a07b` and creates a new RC SHA, rerun the focused ngrok/task/post-reboot 37-test gate from that exact detached checkout and record the result. Because release-lifecycle identity is SHA-sensitive, do not carry the old SHA sign-off forward silently.
4. Once Chat 1 creates the protected config/ngrok deployment files, run non-mutating preflight from the frozen final RC: exact SHA, detached cleanliness, Python/runtime identity, loopback target, exact ngrok executable/config identity, all three SYSTEM task action/trigger plans, and secret-free arguments.
5. Inspect ACLs read-only and report whether SYSTEM and the deployment account can read/execute only the required protected config/runtime/ngrok files. Do not print file contents, tokens, secret values, recipient data, or provider credentials.
6. If protected paths are absent, ACLs are too broad/narrow, the current ngrok process does not match the frozen tuple, or task preflight is not clean, return a clear NO-GO blocker. Do not create/fix protected deployment files independently unless Chat 1/operator explicitly assigns that controlled action.
7. During the elevated lifecycle window, execute live ngrok/task commands only with explicit Chat 1/operator authorization for the frozen RC. Preserve duplicate-tunnel fail-closed behavior and never stop an unverified PID.
8. After the deliberate reboot, run `release-lifecycle-check.ps1` from the exact final RC and require exit 0 + `ready:true`. Capture only safe JSON evidence.
9. Confirm current-boot evidence for backend managed PID/listener/start metadata, all three task states/results, managed ngrok executable/config/target/public health, notification scan+delivery freshness, no stuck runner lock, and no unexpected failure counters.
10. If lifecycle acceptance fails because of a real tooling defect, reproduce it with synthetic/temp evidence first, create one minimal ops/test fix, rerun focused + isolated integration proof, and hand the new SHA to Chat 1. Do not patch production ad hoc.
11. Do not create/restore the final pre-migration backup and do not run migration 010; Chat 1 owns those gates. After cutover, perform only read-only lifecycle verification unless explicitly assigned otherwise.

Success: exact final RC preflight is green against protected deployment paths, reboot lifecycle acceptance is green with safe evidence, and Chat 3 makes no independent business-data/migration changes.

### Mandatory remaining order - 18:41 queue

1. Chat 1 decides `760a07b` and freezes the exact final SHA. If accepted, rebuild the immutable RC; if skipped, document why `b6b42d7` remains final.
2. Chat 1 refreshes the release-candidate document to that exact SHA and removes stale release facts.
3. Chat 2 and Chat 3 independently validate the chosen exact RC in their owned areas; no unrelated code changes.
4. Chat 1 runs full final gates and the exact-SHA isolated 009 -> 010 rehearsal.
5. Chat 1 resolves production ingress and prepares the protected config/ngrok/runtime tuple with least-privilege ACLs.
6. Chat 3 runs non-mutating protected-path/task/ngrok preflight. Any blocker stops the release sequence.
7. With explicit elevation/authorization only, transition ngrok safely and install/verify the three SYSTEM tasks while the live DB remains migration 009.
8. Perform one deliberate reboot; Chat 3 post-reboot lifecycle acceptance must be green with fresh notification-cycle evidence.
9. Still on migration 009, Chat 1 creates/verifies/recovery-drills/hashes/offsite-copies the fresh `pre-admin-v1` backup.
10. Chat 1 makes the explicit GO/NO-GO decision. Only GO permits migration 010/cutover.
11. On GO: guarded cutover, full smoke, Chat 2/3 read-only acceptance, and release documentation/tagging. On critical failure: rollback to fresh migration-009 backup + pinned v9.

Until step 10 explicitly records GO, production must remain on pinned v9 / migration 009. The current free-tier ngrok ingress does not satisfy polished production-ingress readiness by itself.


## RELEASE LEAD STATUS UPDATE - 2026-08-29 after 18:41 queue execution

This status update records execution of the authoritative `NEW TASK ASSIGNMENTS - 2026-08-29 18:41 IST` queue. It does not supersede the safety/order rules in that queue.

- Chat 1 explicitly accepted Chat 2 test-only `760a07b`; it is integrated on `main` as `c4f2219` and changes only two readiness waits in `tests/e2e/gravity.spec.js`.
- Final code SHA is `c4f2219a77f0a1248497c15c5eef6bc5389dd476`.
- New immutable detached RC is `C:\movieXsuggestion\MyProject\grevity_fitness-admin-v1-final-rc-c4f2219`; it is detached HEAD, exact-SHA, and clean.
- `C:\movieXsuggestion\MyProject\grevity_fitness-admin-v1-final-rc-b6b42d7` is superseded/evidence-only and was not mutated.
- Integrated mapping: Chat 3 lifecycle stack `922ec5c` -> `2d1a4f8` -> `c762b85`; Chat 2 product stress handoff `9a7111a` integrated as `b6b42d7`; Chat 2 test stabilization `760a07b` integrated as `c4f2219`. README-only Chat 2/3 handoffs remain branch-local.
- Exact-RC backend: 192/192 PASS. Full Playwright: 53/53 PASS. Admin/customer focused clean rerun: 29/29 PASS. Admin stress: 3/3 PASS; the deterministic 0/1/50/200-row test also passed 3/3 repeated after one earlier transient Enquiries empty-row wait in a broader subset run.
- Accessibility/responsive focused gate: 9/9 PASS. Focused Admin/auth/payment/notification business modules: 47/47 PASS. Focused ngrok/task/lifecycle/reliability gate: 64/64 PASS.
- Static gates: tracked JS syntax 27/27, tracked Python compile 67/67, tracked PowerShell parse 28/28, `git diff --check` PASS, private-key headers 0, forbidden tracked runtime/credential files 0; reviewed high-risk key references contain environment reads or explicitly synthetic/empty test values, not production credentials.
- Final isolated 009 -> 010 rehearsal under exact RC PASS: source migrations 001-009, only 010 applied, `membership_payments` created, schema stage `admin_software_v1`, 33 pre-existing business tables preserved on original columns/data, SQLite quick check `ok`, foreign-key errors 0.
- Pinned-v9 rollback pairing PASS on a separate migration-009 restore at isolated port 8901: health `ok`, 9 migrations, no `membership_payments`, quick check `ok`, FK errors 0; isolated process was stopped afterward.
- Production unchanged: PID 4644 remains the sole checked listener on `127.0.0.1:8787`; live DB remains migration 009 with no `membership_payments`, quick check `ok`, FK errors 0. Gravity scheduled-task count remains 0 and protected deployment files remain absent.
- Production ingress remains NO-GO: the free ngrok path works with the bypass header, but ordinary root traffic does not render Gravity Fitness. No stable polished production URL/domain tuple is frozen.
- `docs/ADMIN_V1_RELEASE_CANDIDATE.md` has been fully refreshed for final SHA `c4f2219a77f0a1248497c15c5eef6bc5389dd476`, exact RC path, final gates, rehearsal, rollback pairing, lifecycle commands, and remaining NO-GO gates.
- Next safe action for Chat 2: independently validate exact detached RC `c4f2219` read-only, first proving the shipped `web/` tree is unchanged versus `b6b42d7`, then rerun its exact-RC responsive/stress/integration smoke and report sign-off; make no branch changes unless a reproducible defect appears.
- Next safe action for Chat 3: independently rerun its exact-RC 37-test lifecycle/ngrok/task gate from detached RC `c4f2219` and report the SHA-sensitive sign-off. Protected-path preflight remains blocked until Chat 1/operator creates the protected config/ngrok files in the controlled window.
- Release remains **NO-GO**. Do not run migration 010, stop PID 4644, transition live ngrok, install tasks, or reboot. The next Chat 1 boundary is resolving production ingress and entering the controlled protected-path/elevated lifecycle window; Chat 3 preflight must be green before any live lifecycle mutation.
