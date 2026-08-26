# Gravity Fitness — Codex Project State

Last updated: 2026-08-26

## Architecture decisions

- Use a modular Python 3.11+ server with SQLite because it matches the proven StyleDash Windows-to-Termux operating model.
- Reuse StyleDash security behavior as a specification: first-party hashed sessions, CSRF, explicit Firebase issuer/project verification, private admin boundary, SQLite WAL/foreign keys/migrations, Razorpay verification/idempotency, online backup, and release gates.
- Do not reuse StyleDash's public HTTP monolith, fashion domain, JSON payment state, or receipt-as-invoice assumption.
- Serve only `web/` through an explicit allowlist. Repository files, runtime data, logs, backups, database files, and the unrelated Hydro Buddy project are private.
- Bind to `127.0.0.1` by default. LAN/internet exposure must be explicit and will require a production TLS boundary.

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
- Repaired the malformed membership/schedule document structure, escaped booking values before HTML rendering, disabled browser-asserted Razorpay success/paid invoices, removed direct Firestore business writes, separated class enquiries from free-pass requests, and corrected dialog/mobile overlay behavior.

## Known issues / production blockers

- `BLOCKED_EXTERNAL_CONFIG`: Firebase project `gravity-authe` does not exist or is not accessible to the currently signed-in account. Project access/config and an Admin service account are required for Phase 2 verification.
- `BLOCKED_EXTERNAL_CONFIG`: Razorpay, WhatsApp, SMS, SMTP, final domain, verified business contact details, GST/invoice identity, and final analytics IDs are not configured.
- Existing public content contains unverified claims, scarcity, reviews, metrics, pricing, trainers, photos, opening hours, and contact details. These must not be represented as verified production facts.
- Customer auth, admin, memberships, notifications, dashboard, diet plans, progress, payments, and persistent invoices remain pending later phases.
- Backup/restore scripts and a tested recovery drill remain Phase 10 work.

## Test status

- Baseline static site: home, trainers, and gallery rendered locally before migration.
- Phase 1 automated test evidence: 11/11 `unittest` tests pass on 2026-08-26 using Python 3.12.13. Coverage includes migration idempotency/checksums, SQLite integrity, health response, public routing, sensitive-file/traversal denial, admin/API isolation, security headers, HEAD behavior, request body limits, port-collision rejection, and log/query-token redaction.
- PowerShell lifecycle evidence: setup, database initialization, start, status, stop, restart, and health checks passed. Startup rejects port collisions; Gravity moved to `127.0.0.1:8787` because an unrelated process already owned port 8765.
- Browser smoke evidence: home, trainers, and gallery render from the Gravity server with no console errors or failed content images; membership no longer contains schedule; booking payload HTML is rendered as text (`0` injected nodes); free-pass and class branches are distinct; focus returns on close and Escape closes the dialog.
- Security headers and private-path smoke: `/api/health` returned HTTP 200 with the safe contract; `/firebase.json` returned HTTP 404; `Server` is generic and `X-Request-ID` is present.
- JavaScript syntax, Python compilation, PowerShell parsing, and `git diff --check` pass.
- Full application security review remains later work as auth/admin/payment APIs are added.

## Deployment status

- Firebase public site remains the historical deployment; no new Firebase deployment is planned.
- Laptop deployment through `scripts/start-gravity.ps1`: running and healthy at `http://127.0.0.1:8787` after a verified stop/restart cycle.
- Termux: architecture-compatible; deployment runbook pending Phase 10.

## Next implementation milestone

Phase 2: customer identity tables, Firebase Admin token verification, first-party hashed sessions, CSRF, register/login/logout/password reset/profile completion, verified identifier uniqueness/linking rules, and authorization regression tests.
