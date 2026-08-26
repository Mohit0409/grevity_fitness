# Gravity Fitness

Gravity Fitness is being migrated from a static Firebase-hosted site to a portable Python/SQLite application that runs on Windows and can later move to Linux or Android/Termux without changing the core architecture.

## Current milestone

Phase 1 establishes the application server, safe static hosting, SQLite migrations, structured logs, health checks, configuration placeholders, local operations scripts, and automated foundation tests. The existing public site is preserved under `web/` while unsafe browser-trusted payment behavior is disabled.

## Quick start on Windows

```powershell
.\scripts\setup-gravity.ps1
.\scripts\start-gravity.ps1
.\scripts\status-gravity.ps1
```

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
