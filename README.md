# Gravity Fitness

Gravity Fitness is being migrated from a static Firebase-hosted site to a portable Python/SQLite application that runs on Windows and can later move to Linux or Android/Termux without changing the core architecture.

## Current milestone

The Phase 13 premium product recovery is implemented. Gravity now has a verified-facts-only editorial public site, secure public visit/membership/coaching/general enquiries, an RBAC-protected admin lead workflow, automatic 180-day enquiry retention enforcement, branded social/icon assets, and Playwright browser release gates alongside the existing customer/admin security, membership/payment/coaching engines, backup/recovery operations, and fail-closed launch checks.

This build is **staging ready, not production ready**. Production remains blocked by a durable verified domain, Firebase and Razorpay verification if those features are required, operator/legal approval of the privacy notice, and the unchanged launch/cutover gates.

## Quick start on Windows

```powershell
.\scripts\setup-gravity.ps1
.\scripts\start-gravity.ps1
.\scripts\status-gravity.ps1
```

For production preparation, run the fail-closed launch gate, read-only provider canaries, and combined cutover verifier:

```powershell
.\scripts\launch-check.ps1
.\scripts\provider-canaries.ps1
.\scripts\cutover-check.ps1 -BaseUrl https://<verified-domain>
```

See [`docs/LAUNCH_RUNBOOK.md`](docs/LAUNCH_RUNBOOK.md) before any public cutover.

Open <http://127.0.0.1:8787/>. Stop the background server with:

```powershell
.\scripts\stop-gravity.ps1
```

Set `GRAVITY_PYTHON` before running setup if Python is not on `PATH`.

## Direct development commands

```powershell
.\.venv\Scripts\python.exe -m server.gravity
.\.venv\Scripts\python.exe -m unittest discover -s server\tests -v
```

Browser release gates use an isolated temporary database and cover all required responsive widths, a real enquiry submission, keyboard/focus behavior, SEO endpoints, console errors, and serious/critical automated WCAG checks:

```powershell
npm ci
npx playwright install chromium
$env:GRAVITY_E2E_PYTHON=(Resolve-Path .\.venv\Scripts\python.exe).Path
npm run test:e2e
```

Public enquiry PII expires after 180 days and is purged automatically at server start. Operators may also invoke the same purge explicitly:

```powershell
.\.venv\Scripts\python.exe -m server.gravity --purge-expired-enquiries
```

The server binds to loopback by default. LAN binding must be explicitly configured through `.env`; do not expose the development server directly to the internet.

Architecture decisions, external blockers, and verification evidence are tracked in [`docs/CODEX_PROJECT_STATE.md`](docs/CODEX_PROJECT_STATE.md). The premium recovery handoff is in [`docs/PREMIUM_RECOVERY_REPORT.md`](docs/PREMIUM_RECOVERY_REPORT.md).
