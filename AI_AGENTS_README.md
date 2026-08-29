# Gravity Fitness ? AI Agent Coordination

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

## Chat 1 ? Admin Backend / Integration Lead

Chat 1 owns Admin Software domain logic, customer provisioning, membership lifecycle, manual reception payments, fees, dashboard aggregates, admin API contracts, authentication provisioning policy, database migrations, and final integration.

Current Admin Software Backend V1 state:

- New migration: `010_admin_software_v1.sql`.
- Fresh database applies 10/10 migrations and reports schema stage `admin_software_v1`.
- Migration 009 ? 010 preservation regression covers customers, Firebase identities, sessions, memberships, notifications, admins, and existing Razorpay payment intents.
- Customers are owner-created and mobile numbers are normalized / unique for non-deleted accounts.
- First mobile OTP login attaches Firebase identity to the existing owner-created customer.
- Unknown verified phones fail closed with `account_not_provisioned`; customer self-registration is disabled.
- Existing linked identities remain supported.
- Add Customer can atomically create customer + initial membership + optional initial manual payment.
- Manual payment ledger supports cash, UPI, card, bank transfer, and other; pending balance is derived from membership snapshot price minus recorded payments.
- Payment and renewal operations support `Idempotency-Key` replay protection.
- Renewal preserves membership history and suppresses obsolete expiry reminders.
- Customer disable / owner phone change revoke active customer sessions.
- Admin dashboard values are server-calculated and do not double-count membership history.
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

## Chat 2 ? Admin Software Frontend

Chat 2 owns the software-style Admin application shell and V1 owner workflows: Dashboard, Customers, customer detail, Add Customer, Memberships, Renew Membership, Record Payment, Fees, Notifications, responsive behavior, accessibility, and browser E2E.

Current state:

- Branch: `agent/gravity-public-ui`.
- Admin Software shell baseline: `25f92cf` (`Build Gravity admin management workspace`).
- Complete Admin Software V1 wiring: `2054d78` (`Wire admin software V1 workflows`).
- Idempotency hardening: `28466ae` (`Harden admin payment idempotency`); renewal and manual-payment dialogs send stable `Idempotency-Key` values across retries in addition to disabling duplicate submits.
- Dashboard now consumes Chat 1 server-calculated customer/member/expiry/fee/payment metrics and operational lists.
- Customers now support server-backed search, customer/membership/plan filters, detail/history, transactional Add Customer, edit, enable/disable, renewal, and manual payment recording.
- Fees and Memberships consume the V1 ledger/list APIs; no persistent balance, expiry, customer, membership, or payment state is fabricated client-side.
- Existing customer/owner notification UX remains preserved with safe per-channel delivery statuses.
- Admin Software browser fixture uses synthetic in-memory test data only; no production customers are modified.
- Final post-idempotency Playwright suite: 36/36 PASS on dedicated E2E port 8831.
- Python regression: 102/102 PASS.
- Read-only verification of Chat 1 current Admin Software backend/service HTTP contract: 15/15 PASS.
- Responsive/accessibility coverage includes 320/360/375/390/430/768/1024/1366/1440/1920, 200% text resize, reduced motion, keyboard navigation, dialog focus trapping/Escape/focus restore, and no horizontal page overflow.
- Passing screenshots include `admin-software-v1-390.png`, `admin-software-v1-1366.png`, and the preserved notification screenshot `admin-reminders-390.png`.
- Frontend contract reference: `docs/ADMIN_SOFTWARE_API_CONTRACT.md`.
- Chat 2 did not modify Chat 1-owned auth/backend/account files.
- Remaining cross-chat item: Chat 1-owned customer auth UI must map `account_not_provisioned` to contact-the-gym/reception guidance; Chat 2 did not modify `account-page.js`/`account.html`.
- Code handoff head before this coordination-only commit: `28466ae`. Ready for deliberate Chat 1 integration; Chat 2 must not merge into `main`.

## Chat 3 ? Admin Reliability / QA / Operations

Chat 3 owns Admin Software workflow QA, backup/recovery validation, performance/index analysis, operational health checks, Windows/Termux safety, crash/retry testing, and security acceptance tests.

Current state:

- Branch: `agent/gravity-admin-ops`.
- Clean handoff head: `ff1225e` (`test: stage admin software reliability coverage`).
- Earlier Admin ops commits include `4131635` and handoff documentation `ee4ba10`.
- Chat 1 must review the branch diff before integrating it into `main`.
- Chat 3 must not apply migration 010 to the live Gravity database.

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
