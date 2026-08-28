# Gravity Fitness — AI Agent Coordination

Last updated: 28 August 2026

This is the canonical ownership map for every AI chat working on Gravity Fitness. Read it before editing any repository file. Copies in agent worktrees should match this file.

## Repositories / Worktrees

Primary integration repo: `C:\movieXsuggestion\MyProject\grevity_fitness`

| Chat | Role | Status | Branch / worktree |
| --- | --- | --- | --- |
| **Chat 1** | **Firebase/Auth + integration lead** | **Active** | `main` / `C:\movieXsuggestion\MyProject\grevity_fitness` |
| **Chat 2** | **Public website UI/UX** | **Active** | `agent/gravity-public-ui` / `C:\movieXsuggestion\MyProject\grevity_fitness-public-ui` |
| **Chat 3** | **Hosting, reliability, backups and future Android/Termux deployment** | **Active** | `agent/gravity-ops-mobile` / `C:\Users\91896\AppData\Local\Temp\gravity-ops-mobile` |

## Chat 1 — Firebase/Auth + Integration Lead

Chat 1 owns Google login, Mobile OTP, Firebase token verification, Gravity first-party sessions, identity linking, duplicate-account prevention, auth CSP/security and final integration of approved agent commits.

Chat 1 owns these files while auth work is active:

- `server/gravity/auth.py`
- `server/gravity/firebase_auth.py`
- `server/gravity/http.py`
- `web/js/account-page.js`
- `web/pages/account.html`
- `server/tests/test_auth.py`

`server/tests/test_foundation.py` is a shared hotspot. Chat 1 currently owns its auth/security-header assertions. Other chats may edit unrelated tests only after checking the diff first.

Current Chat 1 state:

- Latest pushed auth browser fix: `1e1958c` (`fix: allow firebase recaptcha verification`).
- Real Google login and real Mobile OTP are working on the public Gravity URL; reCAPTCHA remains enabled and fail closed.
- The verified active customer has both `google.com` and `phone` identities linked to the same Gravity customer, with email and phone both verified; Gravity first-party session creation is confirmed.
- Duplicate-account, cross-account merge, session rotation/revocation and collision protections pass the 15/15 auth regression suite.
- The read-only Firebase provider canary now verifies Google enabled, Phone enabled, and India (`IN`) present in the SMS-region allowlist; the live canary passes.
- Full backend release suite after auth validation: 103/103 tests passed.
- Firebase providers intentionally exposed by Gravity: `google.com` and `phone`.
- Chat 1 auth validation is complete. Remaining Chat 1 work is controlled integration of approved Chat 2 / Chat 3 commits followed by final release gates.
- Chat 1 may integrate approved Chat 2 / Chat 3 commits into `main` only after reviewing conflicts and running the full release gates.

## Chat 2 — Public UI/UX

Chat 2 owns homepage/public layout, trainers/coaching public pages, gallery, membership presentation, mobile navigation, responsive behavior, visual consistency, public accessibility, public performance and public SEO/metadata where auth code is not involved.

Chat 2 must not modify Chat 1 auth-owned files. If a UI task requires `account.html`, `account-page.js` or `http.py`, stop and coordinate with Chat 1.

Current Chat 2 state:

- Branch: `agent/gravity-public-ui`
- Worktree: `C:\movieXsuggestion\MyProject\grevity_fitness-public-ui`
- Responsive UI commit: `bcc18a1` (`Polish Gravity public responsive UI`).
- Coordination-file commit: `3ca6845`.
- Phase 2 performance/accessibility commit: `54cd4a7` (`Harden Gravity public performance and accessibility`).
- Chat 2 public work is green: 16/16 Playwright and 102/102 Python tests passed.
- Chat 2 must not merge into `main`; report the commit SHA to Chat 1/user for integration.

## Chat 3 — Hosting / Reliability / Mobile Deployment

Chat 3 owns Windows lifecycle scripts, runtime/process safety, health/restart automation, backups/recovery, logging/monitoring, tunnel/proxy operations, migration tooling and the future Android/Termux deployment path.

Chat 3 must not modify Chat 1 auth files or Chat 2 public UI files unless the user explicitly reassigns ownership.

Current Chat 3 state:

- Branch: `agent/gravity-ops-mobile`
- Worktree: `C:\Users\91896\AppData\Local\Temp\gravity-ops-mobile`
- Chat 3 currently has active uncommitted ops/runtime work. Do not reset, clean, checkout over, move or overwrite that worktree.
- Chat 3 must commit only to its branch and report the resulting SHA; Chat 1 handles final integration.

## Coordination Rules

1. Read this file and run `git status --short --branch` before editing.
2. Never switch another worktree's branch.
3. Never use `git reset --hard`, `git clean`, checkout-overwrite or equivalent against another chat's work.
4. Do not edit another active chat's owned files without explicit coordination.
5. Keep secrets, Firebase Admin JSON, `.env`, runtime DBs, logs and backups outside Git.
6. Run relevant targeted tests before committing; run broader tests for cross-cutting changes.
7. Chat 2 and Chat 3 do not merge into `main`.
8. Chat 1 is the integration lead: review diffs, resolve conflicts deliberately, integrate approved commits and run final release gates.
9. Every handoff must report branch, commit SHA, changed files, tests run and blockers.
10. Update this coordination file whenever ownership or worktree/branch assignments change.
