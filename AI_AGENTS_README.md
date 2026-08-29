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
- Chat 2: the role-aware UI, Team Access, stale Fees response hardening, and audit workspace are integrated through `588ed7a`. Its worktree now has 11 uncommitted frontend files (366 insertions / 93 deletions), spanning the Admin shell, dashboard, customers, memberships, enquiries, coaching, notifications, readiness, CSS/HTML, and browser regression. Do not edit or integrate that active work until Chat 2 supplies a clean tested commit/handoff.
- Chat 3: corrected handoff complete. The stale expected-failure was replaced by normal passing regression `f2bd994`, integrated on `main` as `7295f9f`; it passes and separately duplicates coverage of the >200 customer filter boundary fixed in `2ea3b38`. The fail-closed unmanaged-ngrok guard `e5376dd` was integrated as `d84bdaa` and verified against the live manual tunnel without changing PID 15356. Chat 3 reported targeted acceptance 71/71 PASS; the post-integration full backend gate is 166/166 PASS. No Chat 3 release blocker remains.
- Exact next action: obtain Chat 2's clean tested frontend handoff, then use an elevated operator session to install and verify all three scheduled tasks from an immutable pinned/release checkout and perform a controlled conversion of the current manual ngrok tunnel to managed state. After those blockers clear, rerun release-impacting gates, create and recovery-drill a fresh live migration-009 backup, document the cutover tuple, and only then reconsider migration 010.
