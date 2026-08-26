# Gravity Fitness — Codex Project State

Last updated: 2026-08-26

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

## Known issues / production blockers

- `BLOCKED_EXTERNAL_CONFIG`: Firebase project `gravity-authe` credentials/client configuration and an authorized Admin service account are still required for real customer login verification. The application fails closed and reports auth disabled until configured.
- `BLOCKED_EXTERNAL_CONFIG`: Razorpay, WhatsApp, SMS, SMTP, final domain, verified business contact details, GST/invoice identity, and final analytics IDs are not configured.
- Existing public content contains unverified claims, scarcity, reviews, metrics, pricing, trainers, photos, opening hours, and contact details. These must not be represented as verified production facts.
- Secure admin, memberships, notifications, customer dashboard, diet plans, progress, payments, and persistent invoices remain pending later phases.
- Backup/restore scripts and a tested recovery drill remain Phase 10 work.

## Test status
- Phase 1 automated test evidence: 11/11 `unittest` tests passed on 2026-08-26 using Python 3.12.13.
- Phase 2 post-patch regression evidence: 26/26 `unittest` tests pass on 2026-08-26.
- Phase 2 coverage includes verified email/phone/provider uniqueness, concurrent identity collision, explicit link flow, hash-only session storage, idle/absolute expiry, rotation, logout/logout-all, session cap, CSRF/origin validation, rate limiting, spoofed proxy headers, disabled accounts, Firebase claim/project verification, production cookie flags, profile validation, migration integrity, public/private routing, request limits, and logging redaction.
- Firebase Admin `7.5.0` editable installation through `pip install -e ".[firebase]"` succeeds after package discovery was constrained to `server*`.
- Python compilation, JavaScript syntax checks, and `git diff --check` pass after the final Phase 2 routing patch.
- Fresh laptop restart evidence: Gravity runs under `.venv\Scripts\python.exe`; `/api/health` is HTTP 200, `/account`, `/trainers`, and `/gallery` are HTTP 200, `/api/auth/config` is HTTP 200 with `enabled=false` while credentials are absent, and `/firebase.json` remains HTTP 404.
- Real Firebase sign-in remains blocked only by external `gravity-authe` configuration; no fake success path is enabled.

## Deployment status

- Firebase public site remains the historical deployment; no new Firebase deployment is planned.
- Laptop deployment through `scripts/start-gravity.ps1`: running and healthy at `http://127.0.0.1:8787` on the current Phase 2 working tree.
- Termux: architecture-compatible; deployment runbook pending Phase 10.

## Next implementation milestone

Phase 3: secure admin portal foundation — separate admin identities/sessions, owner bootstrap, TOTP/2FA, RBAC (`Owner`, `Admin`, `Trainer`, `Reception`), CSRF/rate limiting, protected `/admin` routes and APIs, audit logging, integration/system-health views, and authorization regression tests. Reuse proven StyleDash security behavior without importing StyleDash business-domain assumptions.
