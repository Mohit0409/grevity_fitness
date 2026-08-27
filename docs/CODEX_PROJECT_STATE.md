# Gravity Fitness — Codex Project State

Last updated: 2026-08-27

## Architecture decisions

- Use a modular Python 3.11+ server with SQLite because it matches the proven StyleDash Windows-to-Termux operating model.
- Reuse StyleDash security behavior as a specification: first-party hashed sessions, CSRF, explicit Firebase issuer/project verification, private admin boundary, SQLite WAL/foreign keys/migrations, Razorpay verification/idempotency, online backup, and release gates.
- Do not reuse StyleDash's public HTTP monolith, fashion domain, JSON payment state, or receipt-as-invoice assumption.
- Serve only `web/` through an explicit allowlist. Repository files, runtime data, logs, backups, database files, and the unrelated Hydro Buddy project are private.
- Bind to `127.0.0.1` by default. LAN/internet exposure must be explicit and will require a production TLS boundary.
- Firebase proves customer identity only; Gravity issues revocable first-party sessions and owns authorization/profile state server-side.
- Verified email/phone/provider identities are uniqueness keys. Cross-account merging is never automatic and requires an authenticated explicit link flow.

## Completed work

### Phase 0 — Audit

- Inspected the complete Gravity repository and git history/status.
- Ran the existing site locally and compared it with `https://gravityfitnessnmh.web.app/`.
- Audited public/home, trainers, gallery, assets, SEO, responsive behavior, booking, client payment, invoice, analytics, and Firebase dependencies.
- Audited StyleDash architecture, security, SQLite, Firebase, admin/TOTP, Razorpay, backup, Termux, health, and tests.
- Inspected the supplied Swapnil Instagram profile, linked Gravity business profile, and its Google Maps contribution.
- Confirmed the current signed-in Firebase account can see `gravityfitnessnmh` but not `gravity-authe`.

### Phase 1 — Server foundation
- Moved the live public site under `web/`; unused 50MB FBX/Three.js files and Hydro Buddy are outside the served root.
- Added typed environment placeholders, SQLite migration foundation, safe health API, structured rotating logs, request IDs, security headers, safe static allowlisting, lifecycle scripts, and automated tests.
- Firebase Hosting is no longer required to run the application locally.
- Repaired malformed membership/schedule markup, escaped booking values before HTML rendering, disabled browser-asserted Razorpay success/paid invoices, removed direct Firestore business writes, separated class enquiries from free-pass requests, and corrected dialog/mobile overlay behavior.

### Phase 2 — Customer authentication and profile

- Added immutable customer identity/profile/session schema migration `002_customer_auth.sql` with normalized verified identifiers and uniqueness constraints.
- Added Firebase Admin token verification pinned to the configured project/issuer and fresh authentication boundary.
- Added first-party hash-only sessions with idle/absolute expiry, rotation, revocation, active-session cap, logout-all, and disabled-account handling.
- Added synchronized CSRF protection, same-origin enforcement, bounded request parsing, proxy-aware client-IP rules, persistent throttling, and safe auth error responses.
- Added explicit authenticated identity linking; matching verified email/phone never silently merges two Gravity accounts.
- Added `/api/auth/config`, session exchange/status/logout/link APIs and authenticated `/api/me` GET/PATCH profile APIs.
- Added premium member account UI for email/password, Google, mobile OTP, password reset, verification state, and profile completion.
- Firebase browser auth uses in-memory persistence; Firebase ID tokens are exchanged for Gravity sessions and are not stored in localStorage or the Gravity database.
- Added clean `/account`, `/trainers`, and `/gallery` route aliases while keeping the original `/pages/...` routes compatible.
- Added Windows and POSIX setup support plus CI installation of the Firebase Admin optional dependency.

### Phase 3 — Secure admin portal

- Added separate administrator identities, login challenges, hash-only sessions, CSRF tokens, recovery codes, throttles, and append-only audit records in migration `003_admin_security.sql`.
- Added owner-only terminal bootstrap; the first owner password is entered through a hidden prompt and TOTP/recovery enrollment material is shown only after successful creation.
- Added mandatory password → TOTP/recovery-code authentication with encrypted TOTP secrets, replay protection, one-time recovery codes, short challenge lifetime, 30-minute idle expiry, 8-hour absolute expiry, and a three-session cap.
- Added RBAC for `owner`, `admin`, `trainer`, and `reception`, plus protections against owner self-disable/last-owner removal and immediate session revocation when an administrator is disabled.
- Added protected `/api/admin/*` endpoints for session state, login/2FA, dashboard, members, team access, audit, logout, and controlled status changes; unknown admin/API paths remain deny-by-default.
- Added the `/admin` Control Room UI with server-owned authorization state, CSRF-protected mutations, member management, owner-only team management, and audit views.
- Disabling a customer revokes active customer sessions. Customer and administrator authentication/session namespaces remain separate.
### Phase 4 — Membership engine and lifecycle

- Added migration `004_membership_engine.sql` with plan catalog, memberships, immutable plan snapshots, membership lifecycle events, plan audit events, expiry indexes, and unique verified-payment references.
- Imported the historical Basic/Pro/Elite public prices as inactive drafts. They are not exposed publicly or assignable until an authorized administrator explicitly verifies and activates them.
- Added deterministic calendar-month membership periods, month-end handling, active/scheduled/expired/cancelled transitions, renewal scheduling without overlap, cancellation reasons, expiry reconciliation, and server-calculated days remaining.
- Added idempotent payment-reference protection while keeping payment activation unavailable until a verified server-side payment flow exists.
- Added `membership_plans.manage` separately from `memberships.manage`: owner/admin may manage the plan catalog; reception may assign, renew, cancel, and inspect memberships but cannot alter pricing/plans.
- Added protected admin APIs and Control Room UI for plan management, member assignment/renewal/cancellation, and expiry watch; all mutations remain behind admin session, RBAC, same-origin, and CSRF checks.
- Added authenticated customer membership summary with current membership, upcoming renewal, validity dates, days remaining, and historical expired/cancelled memberships.
- Plan edits never rewrite existing membership price/name/duration snapshots, preserving historical business records.


### Phase 5 — Membership expiry notifications

- Added migration `005_notification_outbox.sql` with idempotent reminder records and per-channel delivery state.
- Expiry scans deduplicate by membership/window and suppress reminders when a renewal already exists or the source membership is no longer active.
- Delivery records support email, SMS, and WhatsApp without copying raw customer contact values into the outbox; only channel/reference and delivery state are stored.
- Missing recipients and unconfigured providers are explicit states; all external providers remain `BLOCKED_EXTERNAL_CONFIG` and no provider-send HTTP endpoint exists.
- Added retry scheduling with bounded exponential backoff, sanitized provider error codes, due-delivery selection, and successful-delivery completion state.
- Added authenticated member reminder history plus Control Room reminder history/manual scans protected by admin session, `notifications.manage`, same-origin, and CSRF checks.

### Phase 6 — Server-owned payments and persistent receipts

- Added migration `006_payments_invoices.sql` with server-owned payment intents, immutable plan/amount snapshots, provider events, and persistent invoice records.
- Razorpay Orders are created server-side; browser-supplied amount, plan name, paid state, invoice number, and tax calculations are never authoritative.
- Checkout success is accepted only after HMAC-SHA256 verification against the server-stored Razorpay order ID; raw webhook bodies are HMAC verified and `X-Razorpay-Event-Id` deduplicates retries.
- Verified payments activate memberships idempotently through the Phase 4 payment-reference constraint. Failed attempts may recover when a later verified capture arrives for the same server order.
- Customer payment/invoice history is authenticated and server-owned. Downloadable verified-payment receipts are explicitly marked `NOT A TAX INVOICE`.
- Persistent invoice records remain `pending_business_identity`; no tax/GST invoice is issued until verified Gravity legal/GST identity exists.
- Removed static Razorpay payment links, browser-generated invoice/tax math, and jsPDF receipt generation from the public page. Real Razorpay checkout remains fail-closed while credentials are absent.

## Known issues / production blockers

- `BLOCKED_EXTERNAL_CONFIG`: Firebase project `gravity-authe` credentials/client configuration and an authorized Admin service account are still required for real customer login verification. The application fails closed and reports auth disabled until configured.
- `BLOCKED_EXTERNAL_CONFIG`: Razorpay, WhatsApp, SMS, SMTP, final domain, verified business contact details, GST/invoice identity, and final analytics IDs are not configured.
- Existing public content contains unverified claims, scarcity, reviews, metrics, pricing, trainers, photos, opening hours, and contact details. These must not be represented as verified production facts.
- Broader customer dashboard features, diet plans, progress, tax-invoice issuance, and real notification-provider delivery remain pending later phases.
- Backup/restore scripts and a tested recovery drill remain Phase 10 work.

## Test status
- Phase 1 automated test evidence: 11/11 `unittest` tests passed on 2026-08-26 using Python 3.12.13.
- Phase 2 post-patch regression evidence: 26/26 `unittest` tests pass on 2026-08-26.
- Phase 2 coverage includes verified email/phone/provider uniqueness, concurrent identity collision, explicit link flow, hash-only session storage, idle/absolute expiry, rotation, logout/logout-all, session cap, CSRF/origin validation, rate limiting, spoofed proxy headers, disabled accounts, Firebase claim/project verification, production cookie flags, profile validation, migration integrity, public/private routing, request limits, and logging redaction.
- Firebase Admin `7.5.0` editable installation through `pip install -e ".[firebase]"` succeeds after package discovery was constrained to `server*`.
- Python compilation, JavaScript syntax checks, and `git diff --check` pass after the final Phase 2 routing patch.
- Fresh laptop restart evidence: Gravity runs under `.venv\Scripts\python.exe`; `/api/health` is HTTP 200, `/account`, `/trainers`, and `/gallery` are HTTP 200, `/api/auth/config` is HTTP 200 with `enabled=false` while credentials are absent, and `/firebase.json` remains HTTP 404.
- Real Firebase sign-in remains blocked only by external `gravity-authe` configuration; no fake success path is enabled.
- Phase 3 release-gate evidence: 30/30 `unittest` tests pass on 2026-08-26, including 4 focused admin-security tests for TOTP replay prevention, one-time recovery codes, RBAC, CSRF, administrator-session revocation, and customer-session revocation.
- Phase 3 `compileall`, `node --check web/js/admin.js`, and `git diff --check` pass. Fresh laptop smoke: `/api/health` 200, `/admin` 200, `/api/admin/session` 200 with `configured=true` and `bootstrapRequired=true`, unauthenticated `/api/admin/dashboard` 401, unknown admin paths 404, `.env` 404, admin source 404, and admin CSS/JS 200.
- Phase 4 focused admin + membership evidence: 11/11 tests pass, covering Reception RBAC, inactive-plan enforcement, renewal scheduling, expiry reconciliation, cancellation, verified-payment idempotency, immutable plan snapshots, and plan audit events.
- Phase 1–4 regression evidence: 38/38 `unittest` tests pass on 2026-08-27 in 26.055s. Python `compileall`, `node --check` for account/admin/membership scripts, and `git diff --check` pass.
- Phase 4 live laptop smoke after migration `004` and fresh restart: PID 4656; `/api/health`, `/account`, `/admin`, `/js/admin-memberships.js`, `/js/account-page.js`, `/css/admin.css`, and `/api/membership/plans` return HTTP 200; the public catalog returns `{\"plans\":[]}` because imported prices are inactive drafts; unauthenticated `/api/me/membership`, `/api/admin/membership/plans`, and `/api/admin/memberships/expiring` return HTTP 401; `/.env` and migration source remain HTTP 404.

- Phase 5 focused notification evidence: 6/6 tests pass, covering deduplication, renewal suppression/reconciliation, PII non-duplication, missing-recipient/provider-blocked states, retry/backoff, successful completion, customer/admin authentication, Reception RBAC, same-origin, CSRF, validation, and deny-by-default provider-send routing.
- Phase 1–5 clean regression evidence: 44/44 `unittest` tests pass on 2026-08-27 in 27.762s. Python `compileall` and `node --check` for admin, membership, notification, account, and account-notification scripts pass in the same zero-exit release gate.
- Phase 5 live laptop smoke after migration `005` and fresh restart: PID 13432; database migrations `5`; `/api/health`, `/account`, `/admin`, `/js/account-notifications.js`, `/js/admin-notifications.js`, and `/api/membership/plans` return HTTP 200; public plans remain empty until verified activation; unauthenticated `/api/me/notifications` and `/api/admin/notifications` return HTTP 401; `/api/admin/notifications/send`, `/.env`, notification source, and migration source return HTTP 404.

- Phase 6 focused payment evidence: 6/6 tests pass, covering server-owned price snapshots, Checkout HMAC verification/idempotency, raw webhook verification/event dedupe, failed→captured recovery, amount mismatch rejection, customer auth/origin/CSRF, membership activation, invoice persistence, and downloadable non-tax receipt behavior.
- Phase 1–6 clean regression evidence: 51/51 `unittest` tests pass on 2026-08-27 in 42.854s. Python `compileall`, all account/admin script syntax checks, and public-page inline JavaScript syntax validation pass in the same zero-exit gate.
- Phase 6 live laptop smoke after migration `006` and fresh restart: PID 15644; database migrations `6`; Razorpay checkout/webhook configured `False` in `test` mode; `/api/health`, `/account`, `/js/account-payments.js`, and `/api/payment/config` return HTTP 200; config returns `enabled=false` with `keyId=null`; unauthenticated payment/invoice/receipt APIs return HTTP 401; unsigned webhook returns HTTP 400 `invalid_webhook`; `/.env`, payment source, and migration source return HTTP 404.

## Deployment status

- Firebase public site remains the historical deployment; no new Firebase deployment is planned.
- Laptop deployment through `scripts/start-gravity.ps1`: running and healthy at `http://127.0.0.1:8787` on the current Phase 6 working tree (fresh PID 15644 at the release smoke, database migrations `6`).
- Termux: architecture-compatible; deployment runbook pending Phase 10.

## Next implementation milestone

Phase 7: customer progress and coaching foundation — server-owned measurements, goals, progress history, trainer/admin entry controls, customer-visible trends, and Indian diet-plan assignments with immutable plan versions. Keep health guidance non-diagnostic and separate from medical advice.
