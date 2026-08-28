# Gravity Fitness — Codex Project State

Last updated: 2026-08-28

## Current release state

Gravity Fitness is a portable Python/SQLite application with a first-party public site, secure customer and administrator boundaries, server-owned memberships/payments/coaching, verified backup and recovery tooling, fail-closed launch gates, and browser release tests. The premium recovery pass is implemented locally and is intended for **staging verification only** until every external blocker is cleared.

The production server remains loopback-bound behind a trusted HTTPS proxy or tunnel. Runtime data, secrets, logs, and backups remain outside Git.

## Verified business truth

- Business: Gravity Fitness
- Operator/owner reference: `swapnil.kaithwas`
- Address: Bungalow No. 41, 1st Floor, Above Canara Bank, CRPF Road, Neemuch Chawni, Neemuch, Madhya Pradesh 458441
- Phone and WhatsApp: +91 79995 26112
- Hours: Monday–Saturday, 6:00am–10:00pm; Sunday closed
- Instagram: `@gravity_fitness_nmh`
- Membership: Basic ₹999/month, Pro ₹1,499/month, Elite ₹2,499/month
- Tax mode: receipt only; `TAX_INVOICE_ENABLED=false`

No plan benefits, coach identities, credentials, testimonials, transformations, ratings, member counts, facility claims, or current gallery media are published without operator verification.

## Architecture and trust boundaries

- Python 3.11+ standard-library HTTP application with an allowlisted `web/` static root.
- SQLite in WAL mode with foreign keys, immutable checksummed migrations, and integrity checks.
- Firebase may prove customer identity only after configuration; Gravity issues revocable hash-only first-party sessions and owns profile/authorization state.
- Administrator authentication is separate and uses password, mandatory TOTP/recovery factor, short first-party sessions, RBAC, throttling, CSRF, and append-only audit records.
- The browser is never authoritative for roles, membership, price, payment success, receipt issuance, booking confirmation, or enquiry workflow state.
- Razorpay order creation, signature/webhook verification, idempotency, payment persistence, and membership activation are server-owned and remain fail-closed while configuration is absent.
- The raw Python service binds to loopback. Public HTTPS must terminate at an explicitly trusted reverse proxy or tunnel.

## Implemented phases

1. Server foundation: typed configuration, safe static routing, security headers, request IDs, structured logs, lifecycle scripts, CI, health checks, and SQLite migrations.
2. Customer auth/profile: pinned Firebase verification, first-party session exchange, CSRF, rate limits, explicit identity linking, customer profile APIs, and a fail-closed member account.
3. Admin control room: owner bootstrap, TOTP/recovery login, RBAC, staff management, member management, audit, and private API boundaries.
4. Membership lifecycle: immutable plan snapshots, assign/renew/cancel/expire operations, customer summaries, and protected plan management.
5. Notifications: idempotent expiry reminder outbox and explicit provider states without fake delivery success.
6. Payments and receipts: server-created Razorpay orders, HMAC verification, webhook deduplication, verified-payment activation, and receipts explicitly marked not a tax invoice.
7. Coaching: bounded progress facts, goals, immutable nutrition-plan versions, role controls, and non-medical disclaimers.
8. Public truth/SEO/accessibility: unsupported claims removed; canonical robots/sitemap/manifest; public accessibility, keyboard, and responsive hardening.
9. Readiness: secret-safe admin readiness surface and verified production configuration gates.
10. Backup/recovery: verified online backups, restricted ZIP manifests, recovery drills, guarded live restore, rollback procedures, and cross-platform wrappers.
11. Launch/cutover: fail-closed launch gate, provider canaries, exact-URL smoke suite, trusted proxy checks, and combined cutover verifier.
12. Deployment hardening: staging tunnel support without treating a warning/interstitial URL as a production domain.
13. Premium product recovery:
   - New charcoal/off-white/acid-lime editorial public experience with no loader, animation bundle, synthetic urgency, stock-person imagery, or duplicated mobile action bar.
   - Verified three-plan catalog only; no invented benefits.
   - Truthful coaching and gallery empty states with a direct official Instagram path.
   - Public visit/membership/coaching/general enquiry workflow with references, signed anonymous CSRF, exact-origin enforcement, rate limits, honeypot, idempotency, validation, and date bounds.
   - Migration `008_public_enquiries.sql` with enquiry, note, event, and hashed rate-limit storage.
   - Admin Enquiries workspace with filters, detail, status, notes, RBAC, and audit.
   - Enquiry PII assigned a 180-day expiry and automatically purged on startup; an explicit operator purge command is also available.
   - Polished fail-closed member account state when Firebase is unavailable and no dead public checkout when Razorpay is unavailable.
   - Dynamic canonical/OG metadata from `APP_BASE_URL`, branded SVG/PNG icon family, Apple touch icon, manifest icons, and 1200×630 social artwork.
   - Playwright release gates for 320/360/375/390/430/768/1024/1440 widths, real isolated enquiry submission, focus/scroll behavior, console errors, first-party-only account failure, SEO endpoints, and axe WCAG checks.
14. Customer account security hardening:
   - Customer payloads now expose only the verified Firebase provider names attached to that Gravity customer.
   - Signed-in members can explicitly add a Google identity or verified mobile OTP identity from the account security panel.
   - Linking reuses the existing recent-token, exact-origin, CSRF, conflict detection, audit, and first-party session-rotation boundary; the browser never merges customers itself.

## Database and operations

- Current migration set: `001` through `008`.
- Current schema stage: public enquiries added after progress/coaching.
- Pre-migration backup evidence: `.gravity/backups/gravity-pre-premium-recovery-20260828T062004667856Z.zip`; it was verified before migration 008 with seven migrations.
- Final release backup evidence: `.gravity/backups/gravity-premium-recovery-final-20260828T110200135089Z.zip`; it contains all eight migrations, passed archive verification, and passed the isolated recovery drill on 2026-08-28.
- Public enquiry PII retention: 180 days. Startup enforcement calls the same purge service exposed by:

```powershell
.\.venv\Scripts\python.exe -m server.gravity --purge-expired-enquiries
```

## Release commands

```powershell
.\.venv\Scripts\python.exe -m compileall -q server
.\.venv\Scripts\python.exe scripts\ci-unittest.py
$env:GRAVITY_E2E_PYTHON=(Resolve-Path .\.venv\Scripts\python.exe).Path
npm ci
npx playwright install chromium
npm run test:e2e
git diff --check
```

## External blockers

- `BLOCKED_EXTERNAL_DOMAIN`: the current ngrok hostname is staging-only and may present an interstitial/warning. It is not a verified production domain.
- `BLOCKED_EXTERNAL_FIREBASE`: customer authentication remains unavailable until verified Firebase client/backend configuration and a real sign-in canary pass. On 2026-08-28 the authenticated workstation Firebase CLI returned `403 PERMISSION_DENIED` for project `gravity-authe`; do not substitute configuration from the separately accessible `gravityfitnessnmh` project.
- `BLOCKED_EXTERNAL_RAZORPAY`: online checkout remains unavailable until verified live credentials, webhook configuration, provider canary, and an approved real end-to-end transaction pass.
- `REQUIRES_OPERATOR_LEGAL_REVIEW`: the privacy notice is an implementation draft and requires operator/legal approval before production launch.
- Final production launch still requires the existing fail-closed launch and cutover gates to report ready. No code in this recovery pass bypasses or weakens those gates.

## Next operator milestone

Restore operator access to Firebase project `gravity-authe`, retrieve and verify that project's web-app configuration, supply a private service-account credential outside Git, and pass the Firebase provider plus real customer sign-in canaries. Then validate the durable production HTTPS domain, Razorpay live configuration if online payments are desired, final legal/privacy approval, and the remaining launch/cutover gates.
