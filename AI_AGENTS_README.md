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

## Current coordination - 2026-08-29 22:01 IST

- **ACTIVE SCOPE IS ADMIN PORTAL SOFTWARE ONLY.** Do not work on the existing customer/public website, homepage, public account pages, domain, DNS, ngrok, tunnel, hosting, or customer-site polish unless the operator explicitly starts that work later.
- Frozen Admin V1 runtime remains `c4f2219a77f0a1248497c15c5eef6bc5389dd476`; immutable RC remains `C:\movieXsuggestion\MyProject\grevity_fitness-admin-v1-final-rc-c4f2219`, detached and clean.
- Admin V1 product implementation is complete and validated. Remaining work is Admin-software installation, local lifecycle, backup, cutover, and final Admin-only acceptance.
- Current local service is healthy on `127.0.0.1:8787`, but it remains pinned v9 / migration 009 until explicit Admin Software GO.
- `C:\ProgramData\GravityFitness\gravity.env` and protected runtime directories are absent; Gravity SYSTEM task count is 0; current operator shell is not elevated.
- Chat 2 exact-RC sign-off and Chat 3 exact-RC lifecycle sign-off remain complete. Do not rerun broad completed acceptance. New work must be narrowly Admin-only and release-directed.
- Phase-1 task installation uses `install-gravity-tasks.ps1` without `-EnsureNgrok`. Public/tunnel lifecycle is out of scope.
- Migration 010 is prohibited until protected config, local task preflight/install, deliberate reboot acceptance, and fresh migration-009 backup gates are green and Chat 1 records GO.
- Use the latest `NEW TASK ASSIGNMENTS` section at the end of this file. Any accepted runtime/product/ops code change invalidates frozen RC `c4f2219` and requires a replacement immutable RC.

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


## NEW TASK ASSIGNMENTS - 2026-08-29 19:39 IST

This is the authoritative remaining-work queue for all three chats. It supersedes the 18:41 queue where status has advanced. Completed implementation/rehearsal work must not be restarted. Only the tasks below remain active or become active after their stated dependency.

Current confirmed release state:
- Frozen code SHA: `c4f2219a77f0a1248497c15c5eef6bc5389dd476`.
- Frozen immutable RC: `C:\movieXsuggestion\MyProject\grevity_fitness-admin-v1-final-rc-c4f2219`, detached HEAD and clean.
- `main` is at documentation commit `c65db1b`; there is no later runtime-code commit beyond frozen RC `c4f2219`.
- Final Chat 1 gates on exact RC are green: backend 192/192, Playwright 53/53, Admin/customer 29/29, stress 3/3, accessibility/responsive 9/9, business modules 47/47, ops/reliability 64/64, plus static/security checks.
- Final exact-SHA isolated migration 009 -> 010 rehearsal and pinned-v9 migration-009 rollback pairing are PASS.
- Chat 2 still owes an independent exact-`c4f2219` frontend sign-off; latest Chat 2 handoff `843b8ab` predates final RC creation.
- Chat 3 still owes the SHA-sensitive exact-`c4f2219` 37-test lifecycle/ngrok/task sign-off; its previous 37/37 was on superseded `b6b42d7`.
- Production remains pinned v9 / migration 009 on PID `4644`; protected deployment files are absent, Gravity scheduled-task count is 0, current shell is not elevated, and production ingress is not approved.

Global release freeze: no unrelated features. Any new runtime/product/ops code commit after `c4f2219` invalidates the frozen RC and requires Chat 1 to build a new immutable RC and rerun affected exact-SHA gates before release.

### Chat 1 - Release Lead: Ingress, Protected Lifecycle, Final Go/No-Go

1. Keep `c4f2219` frozen as the release code SHA. Do not integrate new code unless Chat 2 or Chat 3 proves a real release-blocking defect. Documentation-only coordination may continue on `main`.
2. Collect independent exact-RC sign-off from Chat 2 and Chat 3. Chat 2 must validate `c4f2219` UI; Chat 3 must validate `c4f2219` lifecycle tooling 37/37. Do not carry forward their `b6b42d7` sign-offs as if they were SHA-identical acceptance.
3. If either independent validation finds a real code defect, review the smallest fix, integrate only if justified, create a replacement detached RC, refresh release docs, and rerun all affected exact-SHA gates. Otherwise preserve the freeze.
4. Resolve production ingress now. The current free ngrok URL/interstitial is staging-only. Freeze a stable production URL/domain/tunnel design that ordinary browser traffic can use without the free-tier warning page, or keep release NO-GO.
5. Once ingress is chosen, freeze the complete deployment tuple: final RC SHA/path, pinned-v9 rollback SHA/path, live DB, protected Gravity config path, Python/runtime path, ngrok executable/config path, public URL, scheduled-task commands, lifecycle verification command, smoke checks, backup/off-host targets, rollback commands, and abort criteria. Never record secret values.
6. Enter the controlled protected-deployment window only with an elevated operator. Create/install `C:\ProgramData\GravityFitness\gravity.env`, protected ngrok config, and a SYSTEM-accessible ngrok executable/path with least-privilege ACLs. Do not expose file contents or secrets in Git/chat/logs.
7. Before any live ngrok/task mutation, hand the exact frozen tuple to Chat 3 and require a clean non-mutating preflight plus read-only ACL validation. Any mismatch or unreadable/overbroad ACL is a release blocker.
8. With explicit elevation and while the live DB remains migration 009, perform the documented controlled ngrok transition. Never blindly stop PID 15356, never adopt a process that does not exactly match the frozen executable/config/target tuple, and never create a duplicate tunnel.
9. Install and verify `GravityFitness-Watchdog`, `GravityFitness-DailyBackup`, and `GravityFitness-Notifications` as SYSTEM/Highest from exact RC `c4f2219`. Verify working directory, triggers, `IgnoreNew`, enabled state, config/ngrok paths, and secret-free arguments.
10. Perform one deliberate reboot only after lifecycle installation is green. Require Chat 3 to run `release-lifecycle-check.ps1` from exact RC `c4f2219` and return exit 0 plus `ready:true` with current-boot backend/task/ngrok/notification evidence.
11. After reboot acceptance is green and production is still migration 009, create the fresh `pre-admin-v1` live backup with pinned v9, verify it, recovery-drill it, hash it, and copy it to protected off-host storage. Existing rehearsal/recovery archives do not replace this gate.
12. Make and record the explicit production GO/NO-GO decision only after independent Chat 2/3 sign-offs, approved ingress, protected lifecycle/reboot acceptance, and the fresh backup are all green.
13. On GO, execute the guarded final RC + migration-010 cutover and run local/public health, owner TOTP/Admin workspaces, approved-customer login, unknown-phone denial, trainer redaction, payments/renewals, notifications, readiness, task history, and browser smoke. Use Chat 2 and Chat 3 only for read-only acceptance unless a defect is found.
14. On any critical cutover failure, stop the candidate safely and restore the fresh migration-009 backup plus pinned-v9 runtime using the documented procedure. Never edit migration rows or live SQLite/WAL files manually.
15. After successful release, update final runtime/task/ingress/backup evidence, remove superseded NO-GO/rehearsal wording, and complete normal push/tag/release documentation.

Success: one frozen exact RC/rollback tuple, two independent exact-RC sign-offs, approved production ingress, green protected lifecycle/reboot, verified fresh rollback backup, and an explicit GO before migration 010.

### Chat 2 - Exact `c4f2219` Frontend Release Sign-Off

1. Do not create new product features. Preserve `9a7111a`, `760a07b`, and branch-local docs handoffs; do not amend/rebase them.
2. Validate exact detached RC `C:\movieXsuggestion\MyProject\grevity_fitness-admin-v1-final-rc-c4f2219` read-only. Confirm detached HEAD, exact SHA `c4f2219a77f0a1248497c15c5eef6bc5389dd476`, and clean tree before testing.
3. Prove shipped frontend product assets are unchanged versus superseded product RC `b6b42d7` by comparing the `web/` Git tree. The only expected code-source difference is the two test readiness waits from `760a07b` in `tests/e2e/gravity.spec.js`.
4. Run the two corrected deterministic stress cases, focused stress gate, Admin/customer browser gate, and a concise exact-RC responsive/accessibility smoke. Record exact counts and any skips.
5. Reconfirm representative widths 320/360/375/390/430/768/1024/1366/1440/1920, low-height 320x568, 390x667 at 200% text, long unbroken content, large rupee values, bounded 0/1/50/200-row DOM, table scrolling, dialog/action reachability, focus restoration, and all ten Admin workspaces.
6. Recheck the integration-risk flows on exact RC `c4f2219`: notification failure/403, customer workflows, Fees/Membership stale responses, Trainer/Reception/Admin RBAC, Enquiries stale/403 clearing, Readiness recovery/403, customer-search races, Dashboard stale-financial clearing/recovery, expired session, Team Access, and Audit.
7. If all exact-RC checks pass, create only a branch-local README handoff recording the SHA, test counts, `web/` tree comparison, and explicit frontend release PASS. Do not ask Chat 1 to cherry-pick that docs commit.
8. If a real frontend defect is found, reproduce it deterministically and create one minimal frontend/test fix. Any code fix invalidates `c4f2219`; hand the SHA to Chat 1 and stop until a replacement RC exists. Do not touch backend/auth/migration/ops files.
9. After production cutover, perform only read-only browser/rendering/navigation smoke on representative mobile and desktop widths unless Chat 1 explicitly asks for defect investigation. Do not mutate production business data.
10. After exact-SHA sign-off, freeze the Chat 2 branch until Admin V1 release disposition unless a release-blocking frontend defect appears.

Success: exact `c4f2219` gets an independent frontend PASS, the shipped `web/` tree is proven unchanged from `b6b42d7`, and no unnecessary product churn occurs.

### Chat 3 - Exact `c4f2219` Lifecycle Sign-Off + Protected Preflight

1. Sync/read the latest canonical coordination without overwriting branch-local handoff evidence. Do not merge Chat 3 to `main` and do not ask Chat 1 to cherry-pick docs-only handoffs.
2. Immediately validate exact detached RC `C:\movieXsuggestion\MyProject\grevity_fitness-admin-v1-final-rc-c4f2219` read-only. Confirm detached HEAD, exact SHA `c4f2219a77f0a1248497c15c5eef6bc5389dd476`, and clean tree.
3. Rerun `server.tests.test_ngrok_adoption`, `server.tests.test_ops_scripts`, and `server.tests.test_release_lifecycle_check` from that exact RC. Expected focused count is 37 tests; record the actual count/result. This SHA-sensitive sign-off replaces the old `b6b42d7` 37/37 evidence.
4. If the exact-RC focused gate passes, create only a branch-local README handoff recording exact SHA/path, counts, and production-nonmutation. No new lifecycle code is required merely because the SHA changed.
5. Protected preflight remains blocked until Chat 1/operator creates the frozen protected Gravity/ngrok/runtime tuple. Do not create those protected files independently.
6. Once protected paths exist, run the final RC non-mutating preflight: exact SHA/detached cleanliness, Python/runtime identity, loopback target, exact ngrok executable/config identity, three SYSTEM task action/trigger plans, expected working directory, and secret-free arguments.
7. Inspect ACLs read-only. Report whether SYSTEM and the deployment account have the required read/execute access and whether access is too broad. Never print config contents, tokens, recipients, provider credentials, or secret values.
8. Any path mismatch, ACL problem, foreign/stale ngrok PID, wrong target, duplicate tunnel risk, task-plan error, or secret-bearing argument is an explicit NO-GO. Do not repair live state ad hoc unless Chat 1/operator explicitly authorizes the controlled action.
9. During the elevated lifecycle window, execute ngrok/task mutations only with explicit Chat 1/operator authorization for frozen RC `c4f2219`. Preserve duplicate-tunnel fail-closed behavior and never stop an unverified PID.
10. After the deliberate reboot, run exact-RC `release-lifecycle-check.ps1` and require exit 0 + `ready:true`. Capture only safe JSON evidence.
11. Confirm current-boot evidence for backend managed PID/listener/start metadata, all three task states/results, managed ngrok executable/config/target/public health, notification scan+delivery freshness, no stuck runner lock, and no unexpected failure counters.
12. If lifecycle acceptance fails because of a real tooling defect, reproduce it with synthetic/temp evidence first, create one minimal ops/test fix, rerun focused + isolated integration proof, and hand the new SHA to Chat 1. Do not patch production ad hoc.
13. Do not create/restore the final pre-migration backup and do not run migration 010. After cutover, perform only read-only lifecycle verification unless Chat 1 explicitly assigns otherwise.

Success: exact `c4f2219` gets a 37-test lifecycle sign-off; protected deployment preflight is green before any live mutation; reboot acceptance is green with safe current-boot evidence; no independent business-data/migration changes occur.

### Mandatory remaining order - 19:39 queue

1. Chat 2 and Chat 3 independently validate exact frozen RC `c4f2219` now, in parallel. No unrelated code changes.
2. Chat 1 resolves production ingress and freezes the final deployment tuple. Failure to obtain acceptable ingress keeps the release NO-GO.
3. With an elevated operator, Chat 1 prepares protected Gravity/ngrok/runtime paths and least-privilege ACLs while production remains migration 009.
4. Chat 3 runs non-mutating protected-path/task/ngrok/ACL preflight. Any blocker stops the lifecycle window.
5. With explicit authorization only, transition ngrok safely and install/verify all three SYSTEM tasks from exact RC `c4f2219`.
6. Perform one deliberate reboot; Chat 3 post-reboot lifecycle acceptance must return exit 0 + `ready:true` with fresh notification-cycle evidence.
7. Still on migration 009, Chat 1 creates/verifies/recovery-drills/hashes/offsite-copies the fresh `pre-admin-v1` backup.
8. Chat 1 records the explicit GO/NO-GO decision. Only GO permits migration 010 and final RC cutover.
9. On GO: guarded migration/cutover, full production smoke, Chat 2 frontend read-only acceptance, Chat 3 lifecycle read-only acceptance, then final release evidence/tagging.
10. On any critical failure: rollback to the fresh migration-009 backup plus pinned v9; no ad-hoc SQLite/migration edits.

Until step 8 explicitly records GO, production must remain on pinned v9 / migration 009. Frozen code SHA is `c4f2219`; changing code invalidates this release freeze until Chat 1 creates and validates a replacement immutable RC.

## RELEASE LEAD INGRESS UPDATE - 2026-08-29 after 19:39 queue review

- Chat 1 re-read the authoritative `NEW TASK ASSIGNMENTS - 2026-08-29 19:39 IST` queue and preserved frozen runtime SHA `c4f2219a77f0a1248497c15c5eef6bc5389dd476`; no runtime/product/ops code was changed.
- Production-ingress audit found no verified durable production hostname, reserved production tunnel identity, or approved custom-domain value in the repository. Existing domain values are illustrative placeholders or the staging ngrok hostname.
- Ingress decision is therefore explicitly **NO-GO** rather than guessed. Required production topology remains: verified durable HTTPS hostname -> explicitly trusted proxy/tunnel -> loopback Gravity backend `127.0.0.1:8787`.
- Do not authorize migration 010 using the current free ngrok staging hostname/interstitial. A verified operator-owned production hostname/tunnel must be supplied and validated before the deployment tuple can be completed.
- Chat 2 independent exact-`c4f2219` frontend sign-off is still outstanding in canonical coordination.
- Chat 3 SHA-sensitive exact-`c4f2219` 37-test lifecycle/ngrok/task sign-off is still outstanding in canonical coordination.
- Protected Gravity/ngrok paths remain absent, the session is non-elevated, and scheduled-task count remains 0; protected lifecycle/preflight/install/reboot/fresh-backup/cutover work remains gated.
- Next Chat 1 action after both independent sign-offs and a verified production hostname/tunnel decision: freeze the complete deployment tuple, then enter the controlled elevated protected-path window while production remains migration 009.


## NEW TASK ASSIGNMENTS - 2026-08-29 20:04 IST

This is the authoritative remaining-work queue for all three chats. It supersedes the 19:39 queue where status has advanced. Completed implementation, exact-RC test, migration-rehearsal, and ingress-audit work must not be restarted.

Current confirmed release state:
- Frozen runtime code SHA: `c4f2219a77f0a1248497c15c5eef6bc5389dd476`.
- Frozen immutable RC: `C:\movieXsuggestion\MyProject\grevity_fitness-admin-v1-final-rc-c4f2219`, detached HEAD and clean.
- `main` is at documentation-only commit `8279051`; there is no runtime/product/ops code commit after `c4f2219`.
- Chat 1 final exact-RC code/static/security gates, exact-SHA isolated 009 -> 010 rehearsal, and pinned-v9 rollback pairing are PASS.
- Chat 1 production-ingress audit is complete and explicitly NO-GO: no verified durable production hostname/tunnel is available. Operator input is required; do not invent one and do not promote the free ngrok interstitial to production.
- Chat 2 still owes the independent exact-`c4f2219` frontend release sign-off.
- Chat 3 exact-`c4f2219` lifecycle/ngrok/task sign-off is complete: 37/37 PASS; branch-local evidence is `3560923`.
- Production remains pinned v9 / migration 009 on healthy loopback PID `4644`. Protected deployment files are absent, Gravity scheduled-task count is 0, and the available shell is not elevated.

Global release freeze: no unrelated features. Any new runtime/product/ops code change after `c4f2219` invalidates this RC and requires Chat 1 to create and validate a replacement immutable RC. Documentation-only coordination may continue on `main`.

### Chat 1 - Release Lead: Collect Final UI Sign-Off + Operator-Gated Deployment

1. Keep `c4f2219` frozen. Do not integrate new runtime/product/ops code unless Chat 2 or Chat 3 proves a real release-blocking defect.
2. Canonically record Chat 3's completed exact-RC sign-off as evidence: exact SHA/path, detached+clean checks, 37/37 focused PASS, production nonmutation. Do not cherry-pick Chat 3 docs-only `3560923` into the runtime.
3. Collect Chat 2's independent exact-`c4f2219` frontend sign-off. Do not treat the older `b6b42d7` sign-off as final-SHA acceptance.
4. If Chat 2 reports a real defect, review only the smallest justified fix. Any accepted code fix invalidates `c4f2219`: create a replacement detached RC and rerun every affected exact-SHA gate before proceeding.
5. Do not repeat the ingress repository audit. The current blocker is operator input: obtain a verified durable production hostname plus the approved tunnel/proxy identity/provider and ownership details. Do not fabricate or infer these values.
6. Maintain an operator ingress-unblock checklist in release coordination: intended HTTPS hostname, DNS/TLS ownership, tunnel/proxy identity, stable executable/config location, loopback upstream `127.0.0.1:8787`, ordinary-browser root behavior without interstitial, public health behavior, and rollback/disable method. Never record secrets.
7. Once Chat 2 sign-off is green and the operator supplies a verifiable production ingress, validate that ingress without changing production: durable HTTPS hostname, correct tunnel identity, TLS/DNS resolution, trusted forwarding to loopback, normal-browser root rendering, and public health. Any failure keeps release NO-GO.
8. After ingress validation, freeze the complete deployment tuple: final RC SHA/path, pinned-v9 rollback SHA/path, live DB, protected Gravity config path, Python/runtime path, ngrok/tunnel executable+config path, public URL, scheduled-task commands, post-reboot acceptance command, smoke checks, backup/off-host targets, rollback commands, and abort criteria.
9. Enter the protected deployment window only with explicit elevation/operator control. Create/install the protected Gravity config and tunnel executable/config with least-privilege ACLs; do not expose contents or secret values in Git/chat/logs.
10. Before any live tunnel/task mutation, hand the exact frozen tuple to Chat 3 and require its non-mutating protected-path/task/tunnel/ACL preflight to be green.
11. With explicit authorization and while live DB remains migration 009, perform the documented controlled tunnel transition. Never stop an unverified PID, adopt a mismatched process, or create a duplicate tunnel.
12. Install and verify `GravityFitness-Watchdog`, `GravityFitness-DailyBackup`, and `GravityFitness-Notifications` as SYSTEM/Highest from exact frozen RC. Verify action paths, working directory, triggers, enabled state, `IgnoreNew`, protected config/tunnel paths, and secret-free arguments.
13. Perform one deliberate reboot only after lifecycle installation is green. Require Chat 3 exact-RC `release-lifecycle-check.ps1` exit 0 plus `ready:true` with current-boot backend/task/tunnel/notification evidence.
14. After reboot acceptance is green and live DB is still migration 009, create the fresh `pre-admin-v1` live backup with pinned v9; verify it, recovery-drill it, hash it, and copy it to protected off-host storage. Older rehearsal archives do not satisfy this gate.
15. Make and record the explicit production GO/NO-GO decision only after Chat 2 final UI sign-off, approved ingress, protected preflight/lifecycle/reboot acceptance, and fresh backup are all green.
16. On GO, execute the guarded final RC + migration-010 cutover and run local/public health, owner TOTP/Admin workspaces, approved-customer login, unknown-phone denial, trainer redaction, payments/renewals, notifications, readiness, task history, and browser smoke.
17. On critical failure, safely stop the candidate and restore the fresh migration-009 backup plus pinned-v9 runtime using the documented procedure. Never edit migration rows or live SQLite/WAL files manually.
18. After successful release, update final runtime/task/ingress/backup evidence, remove obsolete NO-GO wording, and complete normal push/tag/release documentation.

Success: Chat 1 obtains the remaining independent UI sign-off and real operator ingress, then proves protected lifecycle/reboot and fresh rollback backup before explicitly authorizing migration 010.

### Chat 2 - Immediate Exact `c4f2219` Frontend Release Sign-Off

1. This is Chat 2's only immediate pre-deployment task. Do not start new frontend features or refactor already-passing product code.
2. Validate exact detached RC `C:\movieXsuggestion\MyProject\grevity_fitness-admin-v1-final-rc-c4f2219` read-only. Confirm detached HEAD, exact SHA `c4f2219a77f0a1248497c15c5eef6bc5389dd476`, and clean tree before testing.
3. Prove the shipped `web/` Git tree is byte-identical/tree-identical to superseded product RC `b6b42d7`; the only expected source delta from `760a07b` is the two test readiness waits in `tests/e2e/gravity.spec.js`.
4. Run the two corrected deterministic stress tests, focused stress gate, Admin/customer browser gate, and concise exact-RC responsive/accessibility smoke. Record exact counts, retries, and skips.
5. Reconfirm representative widths 320/360/375/390/430/768/1024/1366/1440/1920, low-height 320x568, 390x667 at 200% text, long unbroken content, large rupee values, bounded 0/1/50/200-row DOM, internal table scrolling, dialog/action reachability, focus restoration, and all ten Admin workspaces.
6. Recheck integration-risk flows on exact RC `c4f2219`: notification failure/403, customer workflows, Fees/Membership stale responses, Trainer/Reception/Admin RBAC, Enquiries stale/403 clearing, Readiness recovery/403, customer-search races, Dashboard stale-financial clearing/recovery, expired session, Team Access, and Audit.
7. If all checks pass, create only a branch-local README handoff with exact SHA/path, `web/` tree comparison, test counts, explicit frontend PASS, and production-nonmutation statement. Do not ask Chat 1 to cherry-pick the docs commit.
8. If a real frontend defect is found, reproduce it deterministically and create one minimal frontend/test fix. Stop afterward and hand the fix SHA to Chat 1 because any code change invalidates frozen RC `c4f2219`. Do not touch backend/auth/migration/ops files.
9. After exact-SHA PASS, freeze the Chat 2 branch until release disposition. During post-cutover smoke, perform read-only rendering/navigation checks only unless Chat 1 explicitly asks for a defect investigation.

Success: exact `c4f2219` receives independent frontend PASS with proof that shipped product assets are unchanged from `b6b42d7`.

### Chat 3 - Sign-Off Complete; Wait for Protected Preflight Gate

1. Exact `c4f2219` SHA-sensitive lifecycle sign-off is COMPLETE. Do not rerun completed tests unless the frozen code SHA changes. Evidence: detached=true, clean=true, exact SHA match, focused ngrok/task/post-reboot modules 37/37 PASS; branch-local docs commit `3560923`.
2. Keep `3560923`, `b920584`, and `e1182d0` branch-local. Chat 1 should record the facts canonically, not cherry-pick those docs commits into the runtime.
3. No new lifecycle feature code is assigned. Protected preflight remains blocked while the protected config/tunnel paths do not exist and the operator session is non-elevated.
4. Once Chat 1/operator provides the approved ingress/deployment tuple and creates protected files, run non-mutating preflight from exact RC `c4f2219`: SHA/detached cleanliness, Python/runtime identity, loopback upstream, exact tunnel executable/config identity, expected public hostname/target, all three SYSTEM task action+trigger plans, working directory, and secret-free arguments.
5. Inspect protected ACLs read-only. Report whether SYSTEM and the deployment account have required read/execute access and whether any access is too broad. Never print config contents, tokens, recipients, provider credentials, or other secret values.
6. Any path mismatch, ACL issue, wrong/foreign/stale tunnel PID, wrong target/hostname, duplicate-tunnel risk, task-plan error, or secret-bearing argument is a clear NO-GO. Do not repair live state ad hoc unless Chat 1/operator explicitly authorizes the controlled action.
7. During the elevated lifecycle window, execute tunnel/task mutations only with explicit Chat 1/operator authorization for exact RC `c4f2219`; never stop an unverified PID and preserve duplicate-tunnel fail-closed behavior.
8. After the deliberate reboot, run exact-RC `release-lifecycle-check.ps1` and require exit 0 + `ready:true`; capture only safe JSON evidence.
9. Confirm current-boot backend managed PID/listener/start metadata, all three task states/results, managed tunnel executable/config/target/public health, notification scan+delivery freshness, no stuck runner lock, and no unexpected failure counters.
10. If lifecycle acceptance exposes a real tooling defect, reproduce it with synthetic/temp evidence first, create one minimal ops/test fix, rerun focused + isolated integration proof, and hand the new SHA to Chat 1. Do not patch production ad hoc.
11. Do not create/restore the final pre-migration backup and do not run migration 010. After cutover, perform only read-only lifecycle verification unless Chat 1 explicitly assigns otherwise.

Success: Chat 3 stays frozen until the protected tuple exists, then proves non-mutating preflight and reboot lifecycle acceptance without independent business-data/migration changes.

### Mandatory remaining order - 20:04 queue

1. Chat 2 completes the independent exact-`c4f2219` frontend sign-off now. Chat 3's exact-RC 37/37 sign-off is already complete.
2. Chat 1 canonically records both independent sign-offs. Any real code defect reopens the RC and requires replacement exact-SHA validation.
3. Operator supplies a verified durable production hostname/tunnel/proxy identity. Until then ingress remains NO-GO; chats must not invent or infer it.
4. Chat 1 validates the supplied ingress and freezes the complete deployment tuple. Failure keeps release NO-GO.
5. With an elevated operator, Chat 1 creates/secures the protected Gravity/tunnel deployment paths while production remains migration 009.
6. Chat 3 runs non-mutating protected-path/task/tunnel/ACL preflight. Any blocker stops the lifecycle window.
7. With explicit authorization only, perform the controlled tunnel transition and install/verify all three SYSTEM tasks from exact RC `c4f2219`.
8. Perform one deliberate reboot; Chat 3 post-reboot lifecycle acceptance must return exit 0 + `ready:true` with fresh notification-cycle evidence.
9. Still on migration 009, Chat 1 creates/verifies/recovery-drills/hashes/offsite-copies the fresh `pre-admin-v1` backup.
10. Chat 1 records the explicit GO/NO-GO decision. Only GO permits migration 010 and final RC cutover.
11. On GO: guarded migration/cutover, full production smoke, Chat 2 frontend read-only acceptance, Chat 3 lifecycle read-only acceptance, then final release evidence/tagging.
12. On critical failure: rollback to the fresh migration-009 backup plus pinned v9; no ad-hoc SQLite/migration edits.

Until step 10 explicitly records GO, production must remain on pinned v9 / migration 009. Frozen runtime SHA is `c4f2219a77f0a1248497c15c5eef6bc5389dd476`. Operator-provided production ingress is now the principal external release blocker after Chat 2 completes its exact-RC sign-off.

## CHAT 1 STATUS - 2026-08-29 after 20:04 queue review

- Chat 1 re-read the authoritative `NEW TASK ASSIGNMENTS - 2026-08-29 20:04 IST` queue and preserves frozen runtime SHA `c4f2219a77f0a1248497c15c5eef6bc5389dd476` and immutable RC `C:\movieXsuggestion\MyProject\grevity_fitness-admin-v1-final-rc-c4f2219`.
- Chat 3 independent exact-RC lifecycle evidence is canonically accepted: exact SHA/path verified, detached HEAD and clean tree, focused ngrok/task/post-reboot modules **37/37 PASS**, production nonmutation; branch-local evidence commit `3560923` is not required in the runtime and must not be cherry-picked merely for documentation.
- Chat 2 independent exact-`c4f2219` frontend sign-off remains the only outstanding independent exact-RC acceptance.
- Production ingress remains explicitly **NO-GO pending operator input**. Required operator ingress-unblock facts: intended durable HTTPS hostname; DNS/TLS ownership/control; approved tunnel/proxy provider and identity; stable SYSTEM-accessible executable/config locations; loopback upstream `127.0.0.1:8787`; ordinary-browser root behavior without interstitial; public health behavior; and rollback/disable method. Record identities/paths only, never secrets.
- No protected deployment files, tunnel transition, SYSTEM tasks, reboot, fresh live backup, migration 010, or cutover may proceed until the required dependencies in the 20:04 queue are satisfied.
- Production remains pinned v9 / migration 009. No runtime/product/ops code was changed by this status update.


## NEW TASK ASSIGNMENTS - 2026-08-29 20:57 IST

This is the authoritative remaining-work queue for all three chats. It supersedes the 20:04 queue where status has advanced. Completed implementation, exact-RC testing, independent sign-off, migration rehearsal, rollback pairing, and ingress repository-audit work must not be restarted.

Current confirmed release state:
- Frozen runtime code SHA: `c4f2219a77f0a1248497c15c5eef6bc5389dd476`.
- Frozen immutable RC: `C:\movieXsuggestion\MyProject\grevity_fitness-admin-v1-final-rc-c4f2219`, detached HEAD and clean.
- `main` is at documentation-only commit `e3f8f14`; there is no runtime/product/ops code commit after frozen RC `c4f2219`.
- Chat 1 final exact-RC code/static/security gates, isolated 009 -> 010 rehearsal, and pinned-v9 migration-009 rollback pairing are PASS.
- Chat 2 independent exact-RC frontend sign-off is COMPLETE. Evidence: `7cb2027`, reconfirmed by `af1db69`; `web/` tree matches `b6b42d7`, and required frontend gates are green with no reproducible product defect.
- Chat 3 independent exact-RC lifecycle sign-off is COMPLETE: 37/37 PASS in branch-local `3560923`; Chat 1 accepted the evidence canonically in `e3f8f14`.
- There is no remaining internal exact-RC acceptance blocker.
- Production ingress remains explicit NO-GO pending operator input: no verified durable production hostname/tunnel/proxy identity is available. The current free ngrok interstitial is staging-only.
- Production remains pinned v9 / migration 009 on PID `4644`; protected deployment files are absent, Gravity scheduled-task count is 0, and the available shell is not elevated.

Global release freeze: no unrelated runtime/product/ops changes. Any such code change after `c4f2219` invalidates this RC and requires Chat 1 to create and validate a replacement immutable RC. Documentation-only coordination may continue on `main`.

### Chat 1 - Release Lead: Operator Ingress + Protected Lifecycle + Final Cutover

1. Keep runtime SHA `c4f2219` frozen. Do not integrate any new runtime/product/ops code unless Chat 2 or Chat 3 proves a real release-blocking defect.
2. Canonically record Chat 2's completed exact-RC frontend PASS in release coordination: exact SHA/path, `web/` tree identity/equivalence to `b6b42d7`, key test counts, no reproducible frontend defect, and production nonmutation. Do not cherry-pick Chat 2 docs-only `7cb2027` or `af1db69` into the release runtime merely for documentation.
3. Treat both independent exact-RC sign-offs as complete. Do not ask Chat 2 or Chat 3 to repeat already-green acceptance unless frozen code changes or a reproducible defect appears.
4. The immediate external blocker is operator input. Obtain the verified durable production ingress facts: intended HTTPS hostname, DNS/TLS ownership/control, approved tunnel/proxy provider and identity, stable executable/config locations, loopback upstream `127.0.0.1:8787`, ordinary-browser root behavior without interstitial, public-health behavior, and rollback/disable method. Never record secrets.
5. Do not invent a hostname, tunnel identity, token, DNS record, certificate state, or provider ownership. If the operator cannot supply verifiable ingress, preserve NO-GO and stop before protected lifecycle changes.
6. Once operator ingress facts are supplied, validate them read-only first: DNS/TLS resolution/control, expected tunnel/proxy identity, normal-browser root rendering, public health, correct forwarding to loopback, and rollback/disable path. Any mismatch keeps the release NO-GO.
7. After ingress validation, freeze the complete deployment tuple: final RC SHA/path, pinned-v9 rollback SHA/path, live DB path, protected Gravity config path, Python/runtime path, tunnel executable/config path, public URL, scheduled-task install/verify commands, post-reboot acceptance command, smoke checks, fresh-backup/off-host targets, rollback commands, and abort criteria.
8. Enter the protected deployment window only with explicit elevation/operator control. Create/install `C:\ProgramData\GravityFitness\gravity.env`, the protected tunnel config, and a SYSTEM-accessible tunnel executable/path with least-privilege ACLs. Do not expose config contents or secret values in Git/chat/logs.
9. Before any live tunnel/task mutation, hand the frozen tuple to Chat 3 and require its non-mutating protected-path/task/tunnel/ACL preflight to be green. Any path, ACL, identity, target, duplicate-process, or secret-bearing-argument blocker stops the lifecycle window.
10. With explicit authorization and while the live DB remains migration 009, perform the documented controlled tunnel transition. Never blindly stop PID `15356`, never adopt a process that does not exactly match the frozen executable/config/target tuple, and never create a duplicate tunnel.
11. Install and verify `GravityFitness-Watchdog`, `GravityFitness-DailyBackup`, and `GravityFitness-Notifications` as SYSTEM/Highest from exact RC `c4f2219`. Verify working directory, actions, triggers, enabled state, `IgnoreNew`, protected config/tunnel paths, release identity, and secret-free arguments.
12. Perform one deliberate reboot only after lifecycle installation is green. Require Chat 3 exact-RC `release-lifecycle-check.ps1` exit 0 plus `ready:true` with current-boot backend/task/tunnel/notification evidence.
13. After reboot acceptance is green and production is still migration 009, create the fresh `pre-admin-v1` live backup with pinned v9; verify it, recovery-drill it, hash it, and copy it to protected off-host storage. Earlier rehearsal/recovery archives do not satisfy this final gate.
14. Make and record the explicit production GO/NO-GO decision only after approved ingress, protected preflight, lifecycle installation, reboot acceptance, and fresh backup are all green. Internal Chat 2/Chat 3 exact-RC sign-offs are already complete.
15. On GO, execute the guarded final RC + migration-010 cutover and run complete smoke: local/public health, owner TOTP/Admin workspaces, approved-customer login, unknown-phone denial, trainer redaction, payments/renewals, notifications, readiness, task history, and browser smoke.
16. During cutover smoke, use Chat 2 for read-only frontend acceptance and Chat 3 for read-only lifecycle acceptance unless a reproducible defect is found.
17. On any critical failure, safely stop the candidate and restore the fresh migration-009 backup plus pinned-v9 runtime using the documented procedure. Never edit migration rows or live SQLite/WAL files manually.
18. After successful release, update final runtime/task/ingress/backup identities, remove obsolete NO-GO/rehearsal wording, record hashes/paths without secrets, and complete normal push/tag/release documentation.

Success: operator ingress is verified, protected lifecycle/reboot and fresh rollback backup are green, and Chat 1 explicitly authorizes migration 010 only after every remaining external/operational gate passes.

### Chat 2 - Frontend Sign-Off Complete; Freeze Until Cutover Smoke

1. Exact frozen RC `c4f2219` frontend sign-off is COMPLETE. Do not rerun completed acceptance merely because coordination docs changed.
2. Preserve branch-local evidence commits `7cb2027` and `af1db69`; do not amend/rebase them and do not ask Chat 1 to cherry-pick them into the release runtime.
3. Current accepted evidence: exact detached/clean SHA verified; shipped `web/` tree identical to `b6b42d7`; corrected deterministic 2/2 PASS; stress 3/3 PASS; Admin/customer 29/29 PASS; responsive/accessibility 4/4 PASS; integration-risk 14/14 PASS; no reproducible frontend defect; no production mutation.
4. Keep the Chat 2 branch frozen until release disposition. No new UI features, refactors, test churn, or product changes are assigned while ingress/lifecycle gates are outstanding.
5. If Chat 1 asks for evidence clarification, provide read-only details from the existing sign-off; do not create a new code commit.
6. If frozen runtime SHA changes because a genuine release-blocking fix is integrated, wait for Chat 1 to create a replacement immutable RC, then rerun only the affected frontend exact-RC acceptance required by the new SHA.
7. After Chat 1 completes the guarded production cutover, perform read-only browser/rendering/navigation acceptance on representative mobile and desktop widths and confirm the released product matches the signed-off RC. Do not mutate production business data.
8. If post-cutover frontend smoke exposes a real reproducible defect, capture deterministic evidence and hand it to Chat 1 before making changes. Any accepted runtime/product code fix reopens the release freeze and requires a replacement RC process.

Success: Chat 2 remains frozen with a valid exact-RC PASS and returns only for read-only post-cutover UI acceptance or a specifically assigned reproducible frontend defect.

### Chat 3 - Lifecycle Sign-Off Complete; Protected Preflight When Unblocked

1. Exact frozen RC `c4f2219` lifecycle/ngrok/task sign-off is COMPLETE: detached=true, clean=true, exact SHA match, focused 37/37 PASS. Do not rerun completed tests unless the frozen runtime SHA changes.
2. Preserve branch-local `3560923`, `b920584`, and `e1182d0`; do not ask Chat 1 to cherry-pick these docs-only handoffs into the release runtime. Chat 1 has already accepted the 37/37 evidence canonically in `e3f8f14`.
3. No new lifecycle feature code is assigned. Remain frozen while ingress is unresolved and protected deployment paths are absent.
4. Once Chat 1/operator supplies the approved ingress/deployment tuple and creates the protected files, run non-mutating preflight from exact RC `c4f2219`: SHA/detached cleanliness, Python/runtime identity, loopback upstream, exact tunnel executable/config identity, expected public hostname/target, all three SYSTEM task action+trigger plans, working directory, release identity, and secret-free arguments.
5. Inspect protected ACLs read-only. Report whether SYSTEM and the deployment account have the required read/execute access and whether access is too broad. Never print config contents, tokens, recipients, provider credentials, or other secret values.
6. Treat any missing/mismatched path, overbroad/insufficient ACL, foreign/stale tunnel PID, wrong target/hostname, duplicate-tunnel risk, task-plan error, wrong release identity, or secret-bearing argument as an explicit NO-GO. Do not repair live state ad hoc unless Chat 1/operator explicitly authorizes the controlled action.
7. During the elevated lifecycle window, execute tunnel/task mutations only with explicit Chat 1/operator authorization for exact RC `c4f2219`; never stop an unverified PID and preserve duplicate-tunnel fail-closed behavior.
8. After the deliberate reboot, run exact-RC `release-lifecycle-check.ps1` and require exit 0 + `ready:true`; capture only safe JSON evidence.
9. Confirm current-boot backend managed PID/listener/start metadata, all three task states/results, managed tunnel executable/config/target/public health, notification scan+delivery freshness, no stuck runner lock, and no unexpected failure counters.
10. If lifecycle acceptance exposes a real tooling defect, reproduce it with synthetic/temp evidence first, create one minimal ops/test fix, rerun focused + isolated integration proof, and hand the new SHA to Chat 1. Do not patch production ad hoc.
11. Do not create/restore the final pre-migration backup and do not run migration 010. Chat 1 owns those gates.
12. After successful cutover, perform only read-only lifecycle verification against the released runtime/task/tunnel state unless Chat 1 explicitly assigns a defect investigation.

Success: Chat 3 stays frozen until the protected tuple exists, then proves non-mutating preflight and post-reboot lifecycle acceptance without independent migration/business-data changes.

### Mandatory remaining order - 20:57 queue

1. Chat 1 canonically records Chat 2's completed exact-`c4f2219` frontend PASS. Both independent exact-RC sign-offs are then fully recorded; no further internal acceptance loop is needed.
2. Operator supplies the verified durable production hostname plus approved tunnel/proxy identity and ownership/control facts. Until then ingress remains NO-GO and no chat may invent or infer the missing values.
3. Chat 1 validates the supplied ingress read-only and freezes the complete deployment tuple. Failure keeps release NO-GO.
4. With explicit elevation/operator control, Chat 1 creates/secures the protected Gravity/tunnel deployment paths while production remains migration 009.
5. Chat 3 runs non-mutating protected-path/task/tunnel/ACL preflight from exact RC `c4f2219`. Any blocker stops the lifecycle window.
6. With explicit authorization only, perform the controlled tunnel transition and install/verify all three SYSTEM tasks from exact RC `c4f2219`.
7. Perform one deliberate reboot; Chat 3 post-reboot lifecycle acceptance must return exit 0 + `ready:true` with fresh notification-cycle evidence.
8. Still on migration 009, Chat 1 creates/verifies/recovery-drills/hashes/offsite-copies the fresh `pre-admin-v1` backup.
9. Chat 1 records the explicit GO/NO-GO decision. Only GO permits migration 010 and final RC cutover.
10. On GO: guarded migration/cutover, full production smoke, Chat 2 frontend read-only acceptance, Chat 3 lifecycle read-only acceptance, then final release evidence/tagging.
11. On critical failure: rollback to the fresh migration-009 backup plus pinned v9; no ad-hoc SQLite/migration edits.

Until step 9 explicitly records GO, production must remain on pinned v9 / migration 009. Frozen runtime SHA is `c4f2219a77f0a1248497c15c5eef6bc5389dd476`. With both internal exact-RC sign-offs complete, operator-provided production ingress is now the primary blocker that must be resolved before protected lifecycle work begins.

## CHAT 1 STATUS - 2026-08-29 after 20:57 queue review

- Chat 1 re-read the authoritative `NEW TASK ASSIGNMENTS - 2026-08-29 20:57 IST` queue and preserves frozen runtime SHA `c4f2219a77f0a1248497c15c5eef6bc5389dd476` and immutable RC `C:\movieXsuggestion\MyProject\grevity_fitness-admin-v1-final-rc-c4f2219`.
- Chat 2 independent exact-RC frontend acceptance is canonically accepted. Evidence commits remain branch-local: `7cb2027`, reconfirmed by `af1db69`; they are documentation evidence only and are not required in the release runtime.
- Accepted Chat 2 evidence: exact detached/clean SHA verified; shipped `web/` tree identical to `b6b42d7`; corrected deterministic tests **2/2 PASS**; focused stress **3/3 PASS**; Admin/customer browser gate **29/29 PASS**; responsive/accessibility **4/4 PASS**; integration-risk flows **14/14 PASS**; no reproducible frontend defect; no production mutation.
- Chat 3 exact-RC lifecycle acceptance remains accepted: exact SHA/path, detached+clean, **37/37 PASS**, no production mutation.
- Both independent exact-RC sign-offs are now fully recorded. Do not ask Chat 2 or Chat 3 to repeat them unless frozen runtime code changes or a reproducible defect appears.
- The next release dependency is external/operator-provided production ingress. Until a verified durable HTTPS hostname plus approved tunnel/proxy identity and ownership/control facts are supplied, ingress remains **NO-GO** and protected lifecycle work must not begin.
- Production remains pinned v9 / migration 009. No runtime/product/ops code was changed by this status update.

## NEW TASK ASSIGNMENTS - 2026-08-29 21:18 IST

This is the authoritative remaining-work queue. It supersedes the 20:57 queue where product priority changed by operator direction.

### Release scope override - Admin Software First

- **Phase 1 target:** Gravity Fitness Admin Portal as Windows/local software on the gym/operator machine.
- **Phase 2 target:** public website/domain/tunnel. Free domain/tunnel work is deferred and must not block Phase 1.
- Frozen runtime stays `c4f2219a77f0a1248497c15c5eef6bc5389dd476`; immutable RC stays `C:\movieXsuggestion\MyProject\grevity_fitness-admin-v1-final-rc-c4f2219`.
- Both independent exact-RC sign-offs are complete. Do not repeat them unless frozen runtime code changes or a reproducible defect appears.
- Phase 1 does not require `ngrok.yml`, a SYSTEM ngrok executable, a public hostname, DNS/TLS, or tunnel transition.
- `install-gravity-tasks.ps1` supports this: install/verify the three SYSTEM tasks without `-EnsureNgrok`.
- `release-lifecycle-check.ps1` remains tunnel-specific and is deferred to Phase 2; do not change frozen ops code merely to remove ngrok from that script.
- Production remains pinned v9 / migration 009 until Chat 1 explicitly records local Admin Software GO.

### Chat 1 - Release Lead: Local Admin Software Installation + Cutover

1. Preserve frozen RC `c4f2219`; no new runtime/product/ops code unless a real release-blocking defect is proved.
2. Record the scope correction in release documentation: Phase 1 is local Admin Software; public ingress is deferred and is not a GO/NO-GO gate for Phase 1.
3. Prepare the local deployment tuple only: exact RC SHA/path, pinned-v9 rollback SHA/path, live DB path, protected `gravity.env`, project Python/runtime, loopback `127.0.0.1:8787`, three SYSTEM task commands, local reboot checks, backup/off-host targets, rollback commands, and abort criteria.
4. Enter an elevated/operator-controlled window and create `C:\ProgramData\GravityFitness\gravity.env` with least-privilege ACLs. Do not create/copy ngrok assets for Phase 1 and do not expose secret values.
5. Before task installation, hand the exact local tuple to Chat 3 for non-mutating config/ACL/task-plan preflight. Any blocker keeps local cutover NO-GO.
6. While live DB remains migration 009, install `GravityFitness-Watchdog`, `GravityFitness-DailyBackup`, and `GravityFitness-Notifications` from exact RC using `install-gravity-tasks.ps1` **without `-EnsureNgrok`**.
7. Verify task actions, working directory, SYSTEM/Highest principal, triggers, enabled state, `IgnoreNew`, exact RC identity, protected config path, and secret-free arguments.
8. Perform one deliberate reboot only after local lifecycle installation is green.
9. Require Chat 3 local post-reboot acceptance: exact RC identity, detached/clean checkout, healthy backend on loopback `127.0.0.1:8787`, all three task states/results, fresh notification-cycle evidence, no stuck runner lock, and no unexpected failure counters. Do not require public/tunnel evidence for Phase 1.
10. After reboot acceptance is green and live DB is still migration 009, create the fresh `pre-admin-v1` live backup with pinned v9; verify it, recovery-drill it, hash it, and copy it to protected off-host storage.
11. Record explicit local Admin Software GO/NO-GO. Only GO permits migration 010 and local Admin V1 cutover.
12. On GO, perform guarded migration 010/local RC cutover and run local smoke: health, owner TOTP/Admin workspaces, customer management, memberships/fees, notifications, enquiries, readiness, Team Access, Coaching, Audit, approved-customer login, unknown-phone denial, trainer redaction, and payments/renewals.
13. Ask Chat 2 for read-only UI acceptance and Chat 3 for read-only local lifecycle acceptance after cutover.
14. On critical failure, restore the fresh migration-009 backup plus pinned-v9 runtime using the documented rollback procedure. Never edit migration rows or live SQLite/WAL files manually.
15. After successful local software release, update final local runtime/task/backup evidence and release/tag documentation. Keep public domain/tunnel work explicitly deferred to Phase 2.

Success: Admin Portal V1 runs as reliable Windows/local software with reboot recovery, scheduled notifications/backups, verified rollback, and migration 010, without waiting for a public domain or tunnel.

### Chat 2 - Frontend Complete; Local Cutover Smoke Only

1. Exact `c4f2219` frontend sign-off remains COMPLETE; preserve `7cb2027` and `af1db69` branch-local.
2. Do not rerun acceptance or start new UI work merely because public ingress was deferred.
3. Keep the Chat 2 branch frozen until Chat 1 completes the local Admin V1 cutover.
4. After cutover, perform read-only Admin Portal rendering/navigation smoke on representative mobile/desktop widths against the local released runtime.
5. Confirm all ten Admin workspaces render and remain usable; do not mutate production business data solely for UI smoke.
6. If a reproducible frontend defect appears, capture deterministic evidence and hand it to Chat 1 before making changes. Any accepted product-code fix reopens the RC process.

Success: Chat 2 stays frozen until local cutover, then confirms the released Admin Portal UI matches the signed-off RC.
### Chat 3 - Local Lifecycle Preflight + Reboot Acceptance

1. Preserve completed exact-RC code acceptance: `3560923`, 37/37 PASS. Do not rerun it unless frozen SHA changes.
2. Public ngrok/tunnel preflight is deferred to Phase 2. Do not block Phase 1 because `ngrok.yml`, ngrok executable, hostname, or public URL is absent.
3. Once Chat 1 creates protected `C:\ProgramData\GravityFitness\gravity.env`, run non-mutating local preflight from exact RC `c4f2219`: SHA/detached cleanliness, Python/runtime identity, loopback target, protected config identity, three SYSTEM task action+trigger plans, working directory, release identity, and secret-free arguments.
4. Run task preflight/verification without `-EnsureNgrok`; confirm the watchdog plan is loopback-backend-only for Phase 1.
5. Inspect protected config ACLs read-only. SYSTEM and deployment/operator access must be sufficient and not overbroad. Never print secrets or config contents.
6. Any missing/mismatched local path, ACL issue, task-plan error, wrong release identity, non-loopback backend target, or secret-bearing argument is a local Admin Software NO-GO.
7. Perform live task mutations only with explicit Chat 1/operator authorization and elevation.
8. After deliberate reboot, perform local read-only acceptance: exact RC SHA/detached/clean state, managed backend PID/listener/start metadata, `127.0.0.1:8787` health, all three task states/results, notification scan/delivery freshness, no stuck runner lock, and no unexpected failure counters.
9. Do not require ngrok/public-health evidence for Phase 1 and do not run the tunnel-specific `release-lifecycle-check.ps1` as the Phase-1 acceptance gate.
10. Do not create/restore the final pre-migration backup and do not run migration 010; Chat 1 owns those actions.
11. After local cutover, perform read-only lifecycle confirmation against the released Admin runtime/tasks unless Chat 1 assigns a specific defect investigation.

Success: Chat 3 proves the local Windows lifecycle independently of public ingress and does not mutate business data or migration state.

### Mandatory remaining order - 21:18 queue

1. Public domain/tunnel work is deferred to Phase 2 and removed from the Admin Software V1 critical path.
2. Chat 1 freezes the local deployment tuple and, with elevation, creates/secures protected `gravity.env` while production remains migration 009.
3. Chat 3 runs non-mutating local config/ACL/task-plan preflight without ngrok. Any blocker stops the local lifecycle window.
4. With explicit authorization, install/verify Watchdog, DailyBackup, and Notifications as SYSTEM/Highest without `-EnsureNgrok`.
5. Perform one deliberate reboot; Chat 3 completes local backend/task/notification acceptance.
6. Still on migration 009, Chat 1 creates/verifies/recovery-drills/hashes/offsite-copies the fresh `pre-admin-v1` backup.
7. Chat 1 records local Admin Software GO/NO-GO. Only GO permits migration 010/local RC cutover.
8. On GO, perform migration/cutover and full local Admin smoke; Chat 2 performs read-only UI acceptance and Chat 3 read-only lifecycle acceptance.
9. On critical failure, rollback to the fresh migration-009 backup plus pinned v9; no ad-hoc SQLite/migration edits.
10. After local Admin V1 is stable, start a separate Phase-2 plan for free/public domain/tunnel access if still desired.

Until step 7 explicitly records GO, production remains pinned v9 / migration 009. Public ingress is not a Phase-1 blocker.

## CHAT 1 LOCAL RELEASE STATUS - 2026-08-29 after 21:18 queue review

- Chat 1 accepted the Phase-1 scope correction: Admin Portal V1 is Windows/local software; public domain/DNS/ngrok/tunnel/public ingress is deferred to Phase 2 and is not a Phase-1 blocker.
- Frozen runtime remains `c4f2219a77f0a1248497c15c5eef6bc5389dd476`; immutable RC remains detached/clean at `C:\movieXsuggestion\MyProject\grevity_fitness-admin-v1-final-rc-c4f2219`. No completed Chat 2/3 acceptance was rerun.
- Phase-1 local deployment tuple is now recorded in `docs/ADMIN_V1_RELEASE_CANDIDATE.md`: exact RC/rollback/live DB/protected config/Python/loopback/task plan/reboot acceptance/backup gate/abort criteria. Task install and preflight explicitly omit `-EnsureNgrok`.
- Current operator session is **not elevated** and `C:\ProgramData\GravityFitness\gravity.env` is absent; therefore Chat 1 stops before protected-config creation as required by the queue.
- Off-host backup destination also requires operator input: only filesystem drive `C:` is currently mounted and documented example `E:\GravityBackups` does not exist. No off-host path is invented.
- Production remains pinned v9 / migration 009; Gravity SYSTEM tasks remain uninstalled. No protected files, task mutations, reboot, backup, migration 010, or cutover were performed.

## NEW TASK ASSIGNMENTS - 2026-08-29 22:01 IST

This is the authoritative remaining-work queue for all three chats. It supersedes the 21:18 queue where scope is now narrower.

**Active product scope: Gravity Fitness Admin Portal software only.**

Do NOT work on the existing customer/public website, homepage, public customer account pages, public login UX, domain, DNS, Firebase Hosting, ngrok, tunnel, public hostname, or website redesign. Those are explicitly deferred.

Frozen Admin V1 runtime:
`c4f2219a77f0a1248497c15c5eef6bc5389dd476`

Immutable RC:
`C:\movieXsuggestion\MyProject\grevity_fitness-admin-v1-final-rc-c4f2219`

Current local service remains pinned v9 / migration 009 until Chat 1 records Admin Software GO. Broad exact-RC acceptance is already complete and must not be restarted.

### Chat 1 - Admin Software Release Lead / Local Cutover Owner

1. Own only Admin Portal completion and release. Do not spend time on the customer/public website.
2. Keep `c4f2219` frozen unless another chat proves a reproducible Admin-software release blocker.
3. Prepare the protected local configuration plan for `C:\ProgramData\GravityFitness\gravity.env` without printing secrets. Reuse verified values from the existing private `.env`; do not ask the operator to retype secrets already present.
4. For local Admin software override only operational values needed for localhost/runtime safety: loopback `127.0.0.1:8787`, local `APP_BASE_URL`, no proxy trust, explicit live data path, protected runtime/log/backup paths, and approved Python path. Preserve the existing `SECRET_KEY`, Firebase/provider/business values unless an Admin-only requirement proves otherwise.
5. Do not create the protected file until an elevated/operator-controlled PowerShell window is available. Before elevation, prepare only secret-free commands/manifests outside the frozen RC.
6. Keep the existing v9 service healthy and live DB on migration 009 while preparation proceeds.
7. Once elevated, create the protected Gravity directories/config with least-privilege ACLs. Never echo secret values into console output, Git, README, or chat.
8. Hand the exact local tuple to Chat 3 and require a non-mutating local task/config/ACL preflight before task installation.
9. Only after Chat 3 preflight is green, install `GravityFitness-Watchdog`, `GravityFitness-DailyBackup`, and `GravityFitness-Notifications` from exact RC as SYSTEM/Highest, explicitly **without `-EnsureNgrok`**.
10. Perform one deliberate reboot only after all three tasks are installed/verified.
11. After Chat 3 reports local reboot acceptance green, and while DB is still migration 009, create a fresh `pre-admin-v1` backup; verify SQLite integrity, run recovery drill, hash the archive, and copy it to an operator-approved second storage location when available. Do not invent a destination.
12. Record explicit Admin Software GO/NO-GO. Only GO permits migration 010 and Admin V1 runtime cutover.
13. On GO, switch from pinned v9 to exact RC `c4f2219`, apply migration 010 through the normal guarded application path, and keep runtime loopback-only.
14. Run **Admin Portal-only** smoke: owner/admin login, Dashboard, Add Customer, customer edit/disable, Memberships, renewal, manual payment, Fees/pending balance, Notifications admin view/scan, Coaching/Diet assignment, Team Access/RBAC, Audit, Readiness/local health. Do not test or modify the customer/public website as part of this release.
15. If critical cutover checks fail, restore the fresh migration-009 backup and pinned-v9 runtime using the documented rollback. Never manually edit SQLite/WAL files or migration rows.
16. After successful Admin-only acceptance, record final runtime SHA/path, DB migration, task state, backup evidence, and Admin V1 release disposition. Public website work remains separate.

### Chat 2 - Admin Portal Operational UX / Release Acceptance

1. Work only on the **Admin Portal UI** in the frozen RC. Do not touch or review customer/public website pages unless an Admin Portal dependency directly requires it.
2. Do not rerun the already-completed broad frontend acceptance. Instead perform one narrow Admin-operator rehearsal on exact RC using isolated/test data.
3. Exercise the owner's real daily flow end-to-end inside Admin only: Dashboard -> Add Customer -> assign initial membership -> record manual payment -> inspect pending balance -> renew membership -> verify updated Memberships/Fees -> inspect Notifications -> create/assign a diet-plan version -> inspect Team Access/Audit.
4. Confirm all Admin-only actions remain usable at representative laptop and small-window sizes; focus on forms, dialogs, tables, row actions, error/success feedback, keyboard reachability, and no blocked controls.
5. Confirm the Admin Portal does not require a public hostname/tunnel for its core owner workflows and uses loopback-safe API behavior in the local-software release.
6. Do not spend time testing customer self-service/login pages, homepage, gallery, plans page, public coaching pages, or any public-site feature.
7. If no reproducible Admin blocker is found, create a branch-local docs handoff with the exact RC SHA/path, Admin-only workflow coverage, PASS verdict, and production nonmutation statement; then freeze again.
8. If a genuine Admin Portal blocker is found, capture a deterministic repro first. Make only the smallest Admin UI/test fix within Chat 2 ownership, then stop and hand the SHA to Chat 1. Any accepted code fix invalidates `c4f2219` and requires replacement RC validation.
9. Prepare the **post-cutover Admin-only browser checklist** for Chat 1: Dashboard, Customers, Memberships, Fees, Notifications, Coaching/Diet, Team Access, Audit, and local error/session behavior. No customer/public website checklist.

### Chat 3 - Local Windows Lifecycle / Task / Reboot Owner

1. Work only on local Admin Software lifecycle. Ignore ngrok, tunnel, public URL, domain, DNS, and customer/public website lifecycle.
2. Do not rerun the completed 37/37 exact-RC lifecycle acceptance. Use that as code-level evidence.
3. In parallel while the real protected config is absent, run a **synthetic/temp local-only preflight rehearsal** from exact RC using non-secret temporary paths and the approved Python runtime. Use `install-gravity-tasks.ps1 -PreflightOnly` and explicitly omit `-EnsureNgrok`.
4. Verify the generated plan contains exactly three tasks: Watchdog, DailyBackup, Notifications; SYSTEM/Highest; exact RC working directory; loopback backend target; `IgnoreNew`; expected triggers; expected release SHA/detached requirement; and no ngrok/tunnel/public arguments.
5. Verify no secret values are embedded in scheduled-task command-line arguments. Record only safe paths/identities/results.
6. Prepare the exact live non-mutating preflight command for `C:\ProgramData\GravityFitness\gravity.env` so it can be run immediately after Chat 1/operator creates the protected config.
7. Once the protected config exists, inspect ACLs read-only and verify SYSTEM plus the intended operator/deployment account have only the required access. Overbroad or insufficient ACLs are NO-GO.
8. Run live `-PreflightOnly` against exact RC. Any SHA, detached-head, Python, config, task-plan, path, principal, argument, or loopback mismatch is NO-GO; do not repair it ad hoc.
9. During the elevated window, perform task mutations only when Chat 1/operator explicitly authorizes them. Do not touch the live DB or run migration 010.
10. After the deliberate reboot, perform **local-only** acceptance: exact RC identity, managed loopback backend health, all three task presence/enabled/state/results, notification-cycle freshness, backup-task readiness, no stuck notification lock, and no unexpected failure counters.
11. Do not use tunnel-specific `release-lifecycle-check.ps1` as the Phase-1 acceptance command. Public/tunnel evidence is out of scope; use the local checks defined in the 21:18/22:01 coordination.
12. If a real lifecycle tooling blocker appears, reproduce it first with synthetic/temp evidence. Make one minimal ops/test fix only if necessary and hand the SHA to Chat 1; do not patch production ad hoc.
13. After Admin V1 cutover, perform read-only lifecycle verification only. Chat 1 owns migration, backup restore, and release disposition.

### Parallel execution order - 22:01 queue

1. **Immediately in parallel:** Chat 1 prepares the secret-safe protected-config/elevated execution plan; Chat 2 performs the narrow Admin-only operator rehearsal; Chat 3 performs synthetic local-only task preflight rehearsal and prepares live preflight commands.
2. Chat 2 reports Admin-only PASS or one deterministic blocker, then freezes. It must not touch the customer/public website.
3. When an elevated operator window is available, Chat 1 creates/secures `C:\ProgramData\GravityFitness\gravity.env` and required protected local directories without exposing secrets.
4. Chat 3 immediately runs protected-config ACL inspection plus live non-mutating local task preflight.
5. If green, Chat 1/operator installs and verifies the three SYSTEM tasks **without `-EnsureNgrok`**.
6. Perform one deliberate reboot; Chat 3 runs local-only reboot acceptance.
7. Still on migration 009, Chat 1 creates/verifies/recovery-drills/hashes the fresh `pre-admin-v1` backup and copies it to an approved second storage target when available.
8. Chat 1 records explicit Admin Software GO/NO-GO. Only GO permits migration 010.
9. On GO, Chat 1 performs guarded Admin V1 cutover to exact RC `c4f2219` and migration 010.
10. Chat 1 runs full Admin-only smoke, Chat 2 runs read-only Admin UI acceptance, and Chat 3 runs read-only local lifecycle acceptance.
11. If all green, Admin Portal Software V1 is complete. Customer/public website work remains deferred until the operator starts a separate task.
12. On critical failure, rollback to the fresh migration-009 backup plus pinned v9; no ad-hoc DB edits.

Until step 8 records GO, the live database remains migration 009 and current runtime remains pinned v9. The only active product is the Admin Portal software.
## CHAT 1 STATUS - 2026-08-29 after 22:01 queue review

- Chat 1 re-read the authoritative `NEW TASK ASSIGNMENTS - 2026-08-29 22:01 IST` queue and is working only on Gravity Fitness Admin Portal software. Customer/public website, domain/DNS, Firebase Hosting, ngrok/tunnel, public hostname, and public redesign remain deferred.
- Frozen runtime/RC remains `c4f2219a77f0a1248497c15c5eef6bc5389dd476` at `C:\movieXsuggestion\MyProject\grevity_fitness-admin-v1-final-rc-c4f2219`, detached and clean. No broad acceptance was restarted and no runtime/product/ops code changed.
- Chat 1 prepared a secret-safe elevated configuration script and local deployment manifest under ignored `.gravity\release-prep\c4f2219\`. They copy existing private `.env` values without printing them, then override only local operational settings: production mode, loopback host/port/base URL, proxy trust disabled, explicit live data path, protected runtime/log/backup paths, and approved Python path.
- Prepared task preflight/install/verify commands use exact RC SHA + detached requirement and explicitly omit `-EnsureNgrok`. No off-host destination is invented.
- Preparation artifacts parse cleanly and contain no embedded `SECRET_KEY`, Firebase web API key, Razorpay key ID/secret, or webhook secret values.
- Current session remains non-elevated; protected `C:\ProgramData\GravityFitness\gravity.env` is still absent and Gravity SYSTEM task count remains 0. Therefore protected-config creation/task installation correctly stops at the elevation boundary.
- Existing v9 service remains healthy on `127.0.0.1:8787`; live DB remains migration 009. Migration 010 remains forbidden until explicit Admin Software GO.
## CHAT 1 REPLACEMENT RC - 2026-08-29 23:11 IST parallel handoff

- Chat 1 reviewed Chat 2 code commit `db19c4ee9b81f7d62748cbc5705d79b15dfd607a` and accepted it as a real deterministic Admin Portal Coaching/Diet release blocker fix. The fix is minimal: capture each submitted form synchronously before `await`, then reset the captured form; a focused E2E regression covers template/version reset, activation, and assignment.
- Only the required code/test fix was integrated into `main`; Chat 2 docs-only handoff `f290051` was not cherry-picked. Integrated runtime commit is `97884e2e117d78ef2cc6363d15308715264c0982` (`Fix admin coaching async form reset`). Prior RC `c4f2219a77f0a1248497c15c5eef6bc5389dd476` is superseded for release use.
- Replacement immutable RC: `C:\movieXsuggestion\MyProject\grevity_fitness-admin-v1-final-rc-97884e2`, detached HEAD, exact SHA `97884e2e117d78ef2cc6363d15308715264c0982`, clean.
- Exact replacement-RC Coaching regression: **1/1 PASS**, then deterministic repeat **3/3 PASS**. Tracked JavaScript syntax: **26/26 PASS**. `git diff --check` PASS.
- Replacement delta versus superseded RC changes only coordination docs plus `tests/e2e/gravity.spec.js` and `web/js/admin-coaching.js`; `server/` and `scripts/` Git trees are byte-identical to `c4f2219`. Therefore migration/runtime lifecycle implementation is unchanged and the prior isolated 009->010 rehearsal remains applicable; no new live migration was performed.
- Prepared protected-config artifacts were moved to ignored `.gravity\release-prep\97884e2\` and corrected: `GRAVITY_ENV=development`, loopback `127.0.0.1:8787`, local HTTP `APP_BASE_URL`, proxy trust false, empty trusted proxy CIDRs, explicit live data path, protected runtime/log/backup paths, and approved Python `C:\Users\91896\AppData\Local\Programs\Python\Python312\python.exe`. The malformed joined proxy setter line is fixed.
- Prepared config script parses cleanly and preserves existing private `.env` secret/provider/business values by copying rather than regenerating them; checked sensitive existing values are not embedded in the preparation script/manifest.
- Live safety reverified read-only: health `ok`, database `ok`, migration `009`, SQLite quick check `ok`, foreign-key errors `0`. Protected `C:\ProgramData\GravityFitness\gravity.env` remains absent and no task/reboot/migration/cutover mutation occurred.
- Chat 2 and Chat 3 must now use replacement exact SHA/path above for their replacement-RC sign-offs. Do not perform protected config creation, task install, reboot, backup cutover, or migration 010 until both replacement-RC sign-offs are green and the ordered gates continue.
