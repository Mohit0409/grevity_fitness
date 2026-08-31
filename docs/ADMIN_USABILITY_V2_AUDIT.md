# Admin Usability V2 Audit

Audit date: 30 August 2026
Baseline: `aff913a6084c0be8759c9e9848190c1545f89d7d`
Scope: Gravity Fitness Admin Portal only

## Release checkpoint

- `main` and the live immutable RC were clean at `aff913a6084c0be8759c9e9848190c1545f89d7d`.
- Live `/api/health` returned `status=ok` and `database=ok`.
- Live SQLite was migration `010`, schema stage `admin_software_v1`, with `quick_check=ok` and zero foreign-key errors.
- Fresh backup: `C:\ProgramData\GravityFitness\backups\gravity-pre-admin-usability-v2-20260830T153024864446Z.zip`.
- Backup archive SHA-256: `88F06F88DEC2AF0ED686568DD9023A0A362CADCDCAE7E4C61F4758346D529293`.
- Backup verification and isolated recovery drill passed.

## Actionable issue ledger

### Critical domain and data-integrity gaps

1. Membership creation rejects a start more than one day in the past, blocking legitimate historical entry.
2. If that validation were removed alone, a fully historical membership would be stored as `scheduled` instead of `expired`.
3. Start dates have no business-friendly upper bound for unreasonable future scheduling.
4. Gym Staff has no persistent domain distinction from a Member. A UI-only flag would allow Staff to leak into member authentication, coaching, fees, and reminder workflows.
5. The database has no invariant preventing a membership from being attached to a Staff record.
6. The existing onboarding note is silently lost when no opening payment is recorded.

### Daily owner workflow gaps

7. Home summary cards are non-interactive and emphasize broad totals rather than today's work.
8. Home lists expired memberships ahead of memberships expiring today, contrary to the required action priority.
9. Customer search omits membership number and has no Member/Staff filter.
10. A historical membership that is already expired is buried in history instead of being summarized prominently on the profile.
11. The Fees `Fully paid` mode filters in the browser after the server row limit, so large datasets can return a false empty result.
12. Automatic-provider diagnostics load and occupy space every time Follow-ups opens even though manual WhatsApp is the current workflow.
13. Team Access uses “staff account” wording that would be confused with operational gym Staff.
14. Coaching loads all customer records and would include Staff unless the server and UI explicitly select Members only.

### Accessibility, responsive, and reliability gaps

15. Plan and coaching forms rely on placeholders for several accessible names.
16. Several dialogs do not explicitly connect their accessible name to their heading.
17. Flash feedback has no live-region semantics.
18. Client-side month preview can disagree with the server at month-end (for example 31 January plus one month).
19. Coaching performs a redundant Admin session request through an observer after the core shell already established the session.
20. One browser regression still expects the obsolete title `Dashboard`; the intentional owner-facing label is `Home`.

### Operational observation

21. A non-elevated status probe cannot read protected process metadata and reports the exact live RC process as unmanaged even while runtime state and HTTP health identify it correctly. This is recorded for release verification; no live restart is justified by this read-permission false negative.

## Baseline evidence

- Backend: 196 tests passed before one linked-worktree sandbox path error; that exact test passed when rerun in the writable feature worktree.
- Browser: 54/55 passed; the only failure was the stale `Dashboard` title assertion.
- Admin accessibility coverage already checks serious/critical Axe violations in representative customer and responsive flows; the audit found missing labels in advanced forms not reached by those checks.
- Responsive coverage already exercises 320, 360, 375, 390, 430, 768, 1024, 1366, 1440, and 1920 widths, low-height mobile, 200% text, keyboard focus, reduced motion, and long content.
- Synthetic disposable databases at 1, 50, 200, 500, and 1,000 customers completed without blockers. At 1,000 customers, median customer list/search/dashboard/fees timings remained approximately 17/13/98/31 ms on this machine.

## Implementation boundaries

- Add migration `011`; do not rewrite migration `010`.
- Existing customer rows become `member` by default.
- Staff remains operational person data and never grants Admin Portal access.
- Membership dates and fee balances remain server-authoritative.
- Public/customer pages, Firebase Hosting, domain/DNS, tunnel, and public payment UI remain untouched.

## Resolution

All 20 actionable product/code issues above were addressed on `feature/admin-usability-v2`. Item 21 remains an operational read-permission observation: protected runtime identity must be verified with authoritative runtime state, HTTP health, and elevated task checks during cutover rather than the known non-elevated status false negative.
