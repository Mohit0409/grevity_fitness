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

- Release decision: **intentional no-go; production remains safely pinned to migration 009.** Migration 010 was not applied, no live cutover was attempted, and no release push was performed.
- Chat 1 integrated Chat 2's committed audit-trail handoff `0b0a4ec` as `588ed7a`, then integrated Chat 3's corrected regression and ngrok guard as `7295f9f` and `d84bdaa`. Current integrated gates are full backend unittest 166/166 PASS and full Playwright 46/46 PASS; the Admin/customer/reliability browser portion (tests 1-2 and 25-46) is 24/24 PASS. The audit regression covers readable filtering/retry behavior and suppresses credential-like metadata, including nested keys.
- Current static/security gates pass: `git diff --check`, Python compilation, syntax checks for all 27 tracked JavaScript files, tracked-file secret-value scan, private-key-header scan, and forbidden tracked runtime/credential-file scan. Temporary synthetic Admin QA at 100/500/1,000/5,000 customers reports `ready: true`, no blockers, valid foreign keys, and single-record payment/renewal idempotency replays.
- Chat 1 release ops: live production is still the detached pinned v9 runtime at `C:\movieXsuggestion\MyProject\grevity_fitness-runtime-v9` / `49529c9`. Managed state ties PID 4644 to that checkout; PID 4644 owns `127.0.0.1:8787`, local health is green, and the live database remains migrations 001-009 / `notification_owner_fanout`. SQLite quick/foreign-key checks pass, `membership_payments` is absent, and aggregate state is 2 customers, 0 memberships, 1 owner, and 3 plans.
- Public tunnel: ngrok 3.39.9 is running as PID 15356 and `https://foyer-amenity-staff.ngrok-free.dev` forwards to `http://127.0.0.1:8787`. Public API health is HTTP 200 with `ngrok-skip-browser-warning: true`; the free-tier warning/interstitial still applies without that header.
- Rollback readiness: `C:\movieXsuggestion\MyProject\grevity_fitness\.gravity\backups\gravity-pre-runtime-v9-recovery-20260829T095241341470Z.zip` was reverified with the pinned v9 code and passed an isolated recovery drill. It contains migration 009 / `notification_owner_fanout`, 2 customers, 0 memberships, 1 active owner, and 3 active plans. This is a verified rollback checkpoint, not the still-required fresh backup immediately before any future 009 -> 010 migration. The guarded stop/verify/restore/start procedure remains in `docs/OPERATIONS_RUNBOOK.md` and `docs/LAUNCH_RUNBOOK.md`.
- Lifecycle code passed the isolated Windows drill on a temporary port: start/status, online backup, recovery drill, migration export, forced-crash watchdog replacement, and stop all passed. Actual reboot recovery is still **not installed**: `GravityFitness-Watchdog`, `GravityFitness-DailyBackup`, and `GravityFitness-Notifications` are absent. The available host identity is not an administrator. The current ngrok tunnel was started manually and has no managed PID/state files, so installation also requires a controlled stop/adopt/start handoff before enabling the watchdog. The integrated guard was exercised live-safely and refused to launch a duplicate tunnel while PID 15356 remained healthy. The production notification state is stale, so do not claim scheduler health.
- Chat 2: the role-aware UI, Team Access, stale Fees response hardening, and audit workspace are integrated through `588ed7a`. Final Admin QA is now committed cleanly as `dd3a407` with handoff `097f31a`; frontend blocker is none and Chat 1 should review/cherry-pick only `dd3a407` before the next integrated release gate.
- Chat 3: previous reliability handoff is complete. The corrected page-boundary regression is integrated as `7295f9f` and the unmanaged-ngrok duplicate-launch guard is integrated as `d84bdaa`; post-integration backend is 166/166 PASS. Chat 3 now owns the new lifecycle preflight/managed-ngrok adoption task below; production reboot recovery remains an operational release blocker until an elevated operator installs and verifies the SYSTEM tasks.
- Exact next actions are assigned in the `NEW TASK ASSIGNMENTS` section below. Chat 1 integrates/rehearses the release candidate, Chat 2 performs real-world frontend stress QA, and Chat 3 builds safe lifecycle preflight/adoption tooling. Migration 010 remains a no-go until those work items and the elevated lifecycle installation gate are complete.


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
