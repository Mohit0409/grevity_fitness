# Gravity Fitness — AI Agent Coordination

Last updated: 28 August 2026

This file is the shared ownership map for all AI chats working on Gravity Fitness.
Every AI agent must read this file before editing the repository.

## Repository

Primary repo: `C:\movieXsuggestion\MyProject\grevity_fitness`

Agents should use separate Git branches/worktrees whenever possible. Do not switch another agent's active branch, overwrite another agent's uncommitted changes, or merge into `main` unless the user explicitly assigns integration/merge responsibility.

## Active Chat Ownership

| Chat | Role | Status | Branch / worktree |
| --- | --- | --- | --- |
| Chat 1 | Firebase authentication and customer account security | Active | Owned by Chat 1; do not assume its branch name |
| **Chat 2** | **Public website UI/UX, responsive design, accessibility, performance and public SEO** | **Active** | `agent/gravity-public-ui` / `C:\movieXsuggestion\MyProject\grevity_fitness-public-ui` |
| Chat 3 | Integration, release QA and final cross-feature verification | Reserved / not started unless user assigns it | Create a separate integration branch/worktree |

## Chat 1 — Firebase/Auth Ownership

Chat 1 owns Firebase authentication, account identity flows, session/security integration and related tests.

**Chat 2 and Chat 3 must not modify these while Chat 1 is active:**

- `server/gravity/auth.py`
- `server/gravity/firebase_auth.py`
- `server/gravity/http.py`
- `web/js/account-page.js`
- `web/pages/account.html`
- `server/tests/test_auth.py`

If a public UI task appears to require one of those files, stop and coordinate instead of editing it.

## Chat 2 — Public UI/UX Ownership

Chat 2 owns:

- Homepage and public layout system
- Coaching/trainers public pages
- Gallery
- Membership presentation
- Mobile navigation
- Responsive behavior
- Visual consistency
- Public accessibility
- Public-page performance
- SEO/public metadata where auth code is not involved
- Public Playwright/E2E tests

Current Chat 2 branch: `agent/gravity-public-ui`

Completed public responsive pass commit: `bcc18a12287b50e9c293922259686f03c28f952c`

Current phase: **Phase 2 — public performance and accessibility hardening**.

Chat 2 must not merge into `main`.
## Chat 3 — Integration / Release Ownership

When activated by the user, Chat 3 should:

- Create a fresh integration branch/worktree.
- Bring in the approved Chat 1 and Chat 2 commits.
- Resolve conflicts without silently changing feature ownership.
- Run complete Python and Playwright suites.
- Verify auth + account + enquiry + membership + public navigation together.
- Perform final release/cutover checks.
- Report blockers before any merge to `main`.

Chat 3 should not start new feature work unless the user explicitly assigns it.

## Coordination Rules

1. Read `AI_AGENTS_README.md` before editing.
2. Check `git status` before every work session.
3. Never discard another agent's uncommitted work.
4. Never edit another active chat's protected files without user approval.
5. Commit only to your assigned branch.
6. Do not merge to `main` unless explicitly assigned.
7. Run relevant tests before every commit.
8. Report commit SHA, files changed, tests and blockers.
9. Update this file when ownership, status, branch or handoff changes.
10. Prefer isolated worktrees when multiple agents are active at the same time.
