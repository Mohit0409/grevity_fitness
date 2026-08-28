# Gravity Fitness

Gravity Fitness is being migrated from a static Firebase-hosted site to a portable Python/SQLite application that runs on Windows and can later move to Linux or Android/Termux without changing the core architecture.

## Current milestone

Phase 11 final launch preparation is implemented. Gravity now has a fail-closed production readiness gate, first-party customer/admin security, server-owned memberships/payments/coaching, verified backup/recovery operations, cross-platform launch smoke checks, and a TLS reverse-proxy deployment template. Real production launch remains blocked until verified external configuration, the first owner bootstrap, business-approved active plans, provider canaries, and the final public HTTPS cutover are completed.

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

The server binds to loopback by default. LAN binding must be explicitly configured through `.env`; do not expose the development server directly to the internet.

Architecture decisions, external configuration blockers, and verification evidence are tracked in [`docs/CODEX_PROJECT_STATE.md`](docs/CODEX_PROJECT_STATE.md).
