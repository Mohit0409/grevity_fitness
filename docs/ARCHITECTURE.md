# Gravity Fitness Architecture

## Decision summary

Gravity Fitness uses a modular Python application with SQLite and an allowlisted static web root. Python matches the proven StyleDash laptop-to-Termux runtime, while the Gravity implementation deliberately avoids StyleDash's monolithic request handler and JSON-backed payment authority.

```text
Browser / mobile web
        |
        v
Gravity HTTP application (loopback by default)
        |-- allowlisted public files from web/
        |-- /api/health
        |-- public enquiry + customer/auth/membership APIs
        |-- private admin/TOTP/RBAC boundary
        |
        v
SQLite (WAL, foreign keys, migrations, integrity checks)
```

## Trust boundaries

- The browser is untrusted. Identity, roles, membership state, payment outcome, invoice numbering, and notification state will be authoritative only on the server.
- Firebase Authentication will be an external identity proof. The backend will verify tokens against the explicitly configured project and then issue first-party Gravity sessions.
- Admin authentication and authorization will be separate from customer authentication. Public requests will never fall through to admin resources.
- Razorpay order totals and fulfillment will be server-authoritative. Browser callbacks alone will never activate membership or create a paid invoice.
- Runtime state is outside `web/`. The server exposes only `index.html` plus the `assets`, `css`, `js`, and `pages` public prefixes.
- Anonymous enquiries use a signed short-lived double-submit CSRF token, exact-origin checks, idempotency fingerprints, hashed IP/contact throttles, bounded validation, and non-sequential references. Authorised admin/reception users manage workflow state and notes through the separate administrator boundary.
- Public enquiry PII expires after 180 days. Startup and the explicit operator command purge expired parent records and their cascaded notes/events.

## Phase 1 foundation

- `server/gravity/config.py`: typed environment and path configuration.
- `server/gravity/database.py`: SQLite connection invariants, checksummed migrations, integrity health.
- `server/gravity/http.py`: threaded local server, safe static resolver, security headers, request IDs, health API.
- `server/gravity/logging_config.py`: JSON logs with sensitive-key redaction and daily rotation.
- `server/migrations/`: immutable, ordered SQL migrations.
- `scripts/`: Windows and POSIX lifecycle commands.
- `server/tests/`: dependency-free automated foundation regression suite.

## Portability

Core application code uses Python 3.11+ standard library features and relative/configurable paths. Windows scripts are operational wrappers only; the same Python module and SQLite database design run on Linux and Termux. Production internet exposure will require a TLS reverse proxy or tunnel and explicit trusted-proxy configuration.

## Current external decisions

- The `gravity-authe` Firebase project is not visible to the currently signed-in Firebase account. Auth integration remains `BLOCKED_EXTERNAL_CONFIG`, without blocking local development.
- Legal invoice/GST fields require verified business details before production issuance.
- Verified contact details, hours, and the three monthly prices are published. Metrics, reviews, plan benefits, trainer rosters/credentials, testimonials, transformations, and facility/media claims remain unpublished until operator verification.
- The current staging tunnel is not a production domain. Firebase, Razorpay, and the privacy notice remain fail-closed or explicitly review-blocked until external verification is complete.
