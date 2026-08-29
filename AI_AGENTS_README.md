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

Chat 2 owns the software-style Admin application shell and V1 owner workflows: Dashboard, Customers, customer detail, Add Customer, Memberships, Renew Membership, Record Payment, Fees, Notifications, Team Access UX, responsive behavior, accessibility, and browser E2E.

Current state:

- Branch: `agent/gravity-public-ui`.
- Existing Admin V1 frontend integration on local `main`: `6523989`, `fc19d7f`, and `c91ce85`.
- Next reviewed code handoffs, in integration order: `0a323dd` (`Harden admin role-aware workflows`), `960bf24` (`Clarify least-privilege team access`), and `1654271` (`Prevent stale fee workspace renders`). Skip README-only handoff commits when cherry-picking.
- `0a323dd` adds permission-aware navigation/actions, trainer financial/notification UI redaction, loading/error states, Dashboard retry, and stale customer-search protection.
- `960bf24` makes Team Access owner-friendly and least-privilege: Reception default, no Owner option, exact role capability/restriction preview, human-readable role labels, mobile keyboard-accessible staff table, and synthetic staff-enrollment coverage.
- `1654271` cancels pending debounced Fee searches on immediate filter/refresh actions and ignores stale Fee responses so older requests cannot duplicate or overwrite the newest ledger view.
- Current browser release gate after all three handoffs: 43/43 PASS. Focused Admin gate: 17/17 PASS. Focused Fees + Team Access regression: 3/3 PASS.
- Chat 1 server baseline `028e0aa` now redacts trainer payment/notification data server-side and denies Fees/Payments reads; `9968cd5` rejects creation of a second Owner server-side. Chat 2 UI is aligned with those server rules and is not the authorization boundary.
- Chat 2 must consume Chat 1 server-owned calculations and must not fake persistent customer/payment state client-side.

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


## Current coordination - 2026-08-29 14:55 IST

- Chat 1: backend performance/security integrated through `9968cd5`; full backend rerun in progress. Team Access now rejects creation of a second owner server-side, and trainer read responses are financially/notification redacted server-side.
- Chat 2: Team Access and Fee-race hardening are complete in code commits `960bf24` and `1654271` on top of role-aware handoff `0a323dd`. Browser release gate is 43/43 PASS; focused Admin gate 17/17 PASS. Chat 1 should cherry-pick those three code commits in order and skip README-only handoffs.
- Chat 3: `017080e` is stale as an expected-failure test because Chat 1 fixed the >200 customer filter boundary in `2ea3b38`. Convert it to a normal passing regression after syncing; do not merge the expected-failure form.
- Live production remains migration 009. No Admin V1 migration/deploy until integrated browser + backend + backup gates are green.

## Chat 2 handoff - 2026-08-29 15:54 IST

- Branch: `agent/gravity-public-ui`.
- New code commit: `0b0a4ec` (`Upgrade admin audit trail UX`).
- Chat 1 should cherry-pick `0b0a4ec` after the already integrated Chat 2 commits; do not merge this branch into `main`.
- Changed code: `web/pages/admin.html`, `web/css/admin.css`, `web/js/admin.js`, new `web/js/admin-audit.js`, and `tests/e2e/gravity.spec.js`.
- Audit trail now loads the latest 200 server events with explicit loading/failure/retry states, readable staff/event/target/result presentation, local search/result/event filters, and a keyboard-scrollable table.
- Audit event details open in an accessible dialog. Credential-like metadata keys are suppressed, including nested structured metadata, while useful non-sensitive request/context fields remain visible.
- Mobile 390px audit interaction, overflow protection, and serious/critical axe coverage are included in the new deterministic regression.
- Focused audit regression: 1/1 PASS.
- Admin-focused regression: 18/18 PASS.
- Full Playwright release suite: 44/44 PASS.
- `node --check` for `admin-audit.js`, `admin.js`, and `gravity.spec.js`: PASS. `git diff --check`: PASS.
- No Chat 1 protected backend/auth files and no Chat 3 reliability/ops files were modified. No backend API contract or migration change is required.
- Live production remains migration 009; this handoff does not change the migration 010 rollout gate.

## Chat 2 final QA handoff - 2026-08-29

- Branch: `agent/gravity-public-ui`.
- Code commit: `dd3a407` (`Harden admin final QA edge cases`).
- Chat 1 has already integrated the earlier Audit workspace as `588ed7a`; cherry-pick only `dd3a407` for this final QA slice.
- Changed: `tests/e2e/gravity.spec.js`, `web/pages/admin.html`, `web/css/admin.css`, `web/js/admin.js`, `web/js/admin-customers.js`, `web/js/admin-dashboard.js`, `web/js/admin-enquiries.js`, `web/js/admin-memberships.js`, `web/js/admin-notifications.js`, `web/js/admin-readiness.js`, and `web/js/admin-coaching.js`.
- Fixes: customer access-impact confirmations/acknowledgement and focus restoration; keyboard-focusable scroll regions; Membership stale-response protection; Dashboard stale financial-data clearing and safe 403 behavior; Enquiry stale-search/403/loading protection plus mutation double-submit guards; Readiness loading/error/403 states; Notification stale-response/403 clearing; and safe 401 session-expiry return to login across Admin clients.
- Responsive defect found and fixed: Enquiries no longer expands to table min-content width at 390px.
- Deterministic Admin-focused Playwright gate: 24/24 PASS, including Owner/Admin/Reception/Trainer permissions, customer/payment/renewal/Fees flows, race cases, Notifications, Enquiries, Readiness, session expiry, Team Access, Audit, 390px overflow checks, and serious/critical axe checks.
- Syntax checks for all `web/js/admin*.js` and `tests/e2e/gravity.spec.js`: PASS. `git diff --check`: PASS.
- No backend/domain/auth/migration/ops files changed. No production DB or migration 010 action was performed.
- Frontend blocker: none. Chat 1 should run the final integrated release gate after cherry-pick.

## Chat 2 final RC UI acceptance handoff - 2026-08-29 18:28 IST

- Product stress handoff remains `9a7111a` (`web/css/admin.css`, `tests/e2e/gravity.spec.js`). It is already integrated into final RC `b6b42d7` as the top commit.
- Required 17:56 rerun exposed a test-harness startup race only: Admin module `loadSession()` is asynchronous, while the two stress tests could drive `openView()` before mocked owner handoff completed.
- Test-only follow-up `760a07b` adds two `expect.poll(...currentAdmin...)` readiness waits. No product/UI/backend/auth/migration/ops code changes. `9a7111a` was not amended or rewritten.
- Determinism proof after `760a07b`: repeated deterministic + advanced stress tests 10/10 PASS; focused stress gate 3/3 PASS; Admin/customer browser gate 27/27 PASS; full Playwright 51/51 PASS.
- Static hygiene after `760a07b`: test syntax PASS; all `web/js/admin*.js` syntax PASS; `git diff --check` PASS; diff secret-like value scan PASS; no debug/TEMP/console diagnostic markers.
- Exact final RC inspected read-only: `C:\movieXsuggestion\MyProject\grevity_fitness-admin-v1-final-rc-b6b42d7`, detached clean at `b6b42d7264a1ee8ca7fac06b994a9fbb8f8fb24e`.
- Final RC responsive/stress acceptance: 4/4 PASS, covering Admin widths 320/360/375/390/430/768/1024/1366/1440/1920, 320x568, 390x667 + 200% text, long unbroken content, large rupee values, internal table scrolling, dialog/focus behavior, 0/1/50/200-row bounded DOM, and all ten Admin workspaces.
- Final RC integration-risk UI acceptance: 14/14 PASS covering notification failure/403, customer workflows, Fees/Membership stale responses, Trainer/Reception/Admin RBAC, Enquiries stale/403 clearing, Readiness recovery/403, customer search races, Dashboard stale financial clearing/recovery, expired session, Team Access, and Audit.
- Final RC remained clean after acceptance. No final-RC files were modified.
- Frontend product verdict for exact RC `b6b42d7`: PASS; no integration-only frontend defect found.
- `760a07b` is test-only and does not change the shipped frontend. Chat 1 may cherry-pick it if deterministic final-gate source tests are desired, but doing so changes the consolidated SHA and therefore requires a new immutable RC identity before release.
- No production process, ngrok state, scheduled task, live database, migration row, secret, or protected deployment path was touched by Chat 2.

## Chat 2 18:41 queue boundary evidence - 2026-08-29

- `9a7111a` and test-only `760a07b` remain preserved; neither was amended/rebased.
- Current Chat 1 state checked read-only: `main` is `f5e9f10` on top of product RC `b6b42d7`; `760a07b` is not integrated and no replacement immutable RC exists yet.
- Isolated temporary cherry-pick proof applied `760a07b` onto `b6b42d7` without touching `main` or the RC.
- The simulated integration changed only `tests/e2e/gravity.spec.js` (2 readiness waits).
- `web/` tree before and after the simulated cherry-pick is byte-identical by Git tree identity: `8c9a72dba12f627c6c3d5c50560c39d5d6d1aacb`.
- The temporary proof worktree was removed after verification; no persistent release/runtime state was changed.
- Existing exact-RC `b6b42d7` frontend sign-off remains PASS from the prior 4/4 responsive/stress + 14/14 integration-risk UI acceptance.
- Next Chat 2 action is gated on Chat 1 explicitly accepting/skipping `760a07b` and freezing the chosen exact final RC. No unrelated frontend work should start before that decision.
- No production process, ngrok, scheduled task, protected path, database, migration, secret, or business data was touched.
