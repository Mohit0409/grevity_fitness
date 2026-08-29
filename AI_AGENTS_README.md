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

## Current coordination - 2026-08-29 16:22 IST

- Release decision: **intentional no-go; production remains safely pinned to migration 009.** Migration 010 was rehearsed only on an isolated restored copy, was not applied live, no cutover was attempted, and no release push was performed. The exact rehearsal evidence and provisional cutover tuple are in `docs/ADMIN_V1_RELEASE_CANDIDATE.md`.
- Chat 1 integrated Chat 2's committed audit-trail handoff `0b0a4ec` as `588ed7a`, Chat 3's corrected regression and ngrok guard as `7295f9f` and `d84bdaa`, and Chat 2's final-QA code `dd3a407` as `5725e47`; README-only handoff `097f31a` was intentionally skipped. Current integrated gates are backend unittest 166/166 PASS from the unchanged backend, full Playwright 50/50 PASS, and the affected Admin/customer browser gate 27/27 PASS. Affected-JS syntax, diff, tracked-secret, private-key, and forbidden-runtime scans pass.
- Current static/security gates pass: `git diff --check`, Python compilation, syntax checks for all 27 tracked JavaScript files, tracked-file secret-value scan, private-key-header scan, and forbidden tracked runtime/credential-file scan. Temporary synthetic Admin QA at 100/500/1,000/5,000 customers reports `ready: true`, no blockers, valid foreign keys, and single-record payment/renewal idempotency replays.
- Chat 1 release ops: the current rehearsal candidate is exact SHA `5725e47271ecd14bec79ff16923a21a6304ac974` in the clean detached checkout `C:\movieXsuggestion\MyProject\grevity_fitness-admin-v1-rc-5725e47`. Live production is still the detached pinned v9 runtime at `C:\movieXsuggestion\MyProject\grevity_fitness-runtime-v9` / `49529c9`. Managed state ties PID 4644 to that checkout; PID 4644 owns `127.0.0.1:8787`, local health is green, and the live database remains migrations 001-009 / `notification_owner_fanout`. SQLite quick/foreign-key checks pass, `membership_payments` is absent, and aggregate state is 2 customers, 0 memberships, 1 owner, and 3 plans.
- Isolated release rehearsal: the verified/recovery-drilled v9 archive `gravity-rc-rehearsal-20260829T111931084801Z.zip` was restored away from production and migrated 009 -> 010 with the immutable candidate. All original-column data across 33 pre-existing business tables matched the untouched restore; quick/foreign-key checks passed. RC health, MFA Admin login and all workspaces, customer provisioning/verified-phone login, unprovisioned-phone denial, trainer financial redaction, and the second-owner guard passed. A separate restored 009 copy started healthy under pinned v9 on a temporary port and stopped cleanly, proving the rollback pairing. Production was unchanged.
- Public tunnel: ngrok 3.39.9 is running as PID 15356 and `https://foyer-amenity-staff.ngrok-free.dev` forwards to `http://127.0.0.1:8787`. Public API health is HTTP 200 with `ngrok-skip-browser-warning: true`; the free-tier warning/interstitial still applies without that header.
- Rollback readiness: `C:\movieXsuggestion\MyProject\grevity_fitness\.gravity\backups\gravity-pre-runtime-v9-recovery-20260829T095241341470Z.zip` was reverified with the pinned v9 code and passed an isolated recovery drill. It contains migration 009 / `notification_owner_fanout`, 2 customers, 0 memberships, 1 active owner, and 3 active plans. This is a verified rollback checkpoint, not the still-required fresh backup immediately before any future 009 -> 010 migration. The guarded stop/verify/restore/start procedure remains in `docs/OPERATIONS_RUNBOOK.md` and `docs/LAUNCH_RUNBOOK.md`.
- Lifecycle code passed the isolated Windows drill on a temporary port: start/status, online backup, recovery drill, migration export, forced-crash watchdog replacement, and stop all passed. Actual reboot recovery is still **not installed**: `GravityFitness-Watchdog`, `GravityFitness-DailyBackup`, and `GravityFitness-Notifications` are absent. The available host identity is not an administrator. The current ngrok tunnel was started manually and has no managed PID/state files, so installation also requires a controlled stop/adopt/start handoff before enabling the watchdog. The integrated guard was exercised live-safely and refused to launch a duplicate tunnel while PID 15356 remained healthy. The production notification state is stale, so do not claim scheduler health.
- Chat 2: final Admin QA `dd3a407` is integrated as `5725e47`. Chat 2's new real-world small-screen/long-content stress work is active and currently uncommitted in its own worktree; it is not part of the rehearsal SHA.
- Chat 3: lifecycle preflight/managed-ngrok adoption is now complete in clean code commit `4d41870` with README handoff `fd3c451`. It passed 40/40 focused ops tests, a safe live probe against ngrok PID 15356 without mutation, and an isolated lifecycle drill. `4d41870` is not yet integrated on `main`; production reboot recovery remains blocked until Chat 1 integrates it and an elevated operator installs/verifies the SYSTEM tasks.
- The 16:36 work queue has advanced: Chat 1 completed the provisional RC rehearsal, Chat 3 completed lifecycle/adoption tooling, and Chat 2 is still finishing real-world stress QA. Use the latest `NEW TASK ASSIGNMENTS` section at the end of this file as the authoritative queue. Migration 010 remains a no-go until final code consolidation plus the elevated lifecycle/reboot gate are complete.


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
