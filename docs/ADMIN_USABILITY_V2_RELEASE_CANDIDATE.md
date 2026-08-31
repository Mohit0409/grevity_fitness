# Admin Usability V2 Release Candidate

Date: 31 August 2026
Baseline: `aff913a6084c0be8759c9e9848190c1545f89d7d`
Branch: `feature/admin-usability-v2`
Scope: Gravity Fitness Admin Portal only

The exact release SHA is the commit containing this document. The immutable RC and production runtime must be created from that SHA without modifying the checkout.

## Delivered behavior

- People replaces the ambiguous Customers workspace and provides Member, Staff, and All filters.
- Historical membership starts are accepted within a generous 30-year range; expiry is server-derived and already-ended periods are stored as expired.
- Staff is persistent operational person data with designation, joining date, status, and note, but no membership, fee, expiry, follow-up, coaching, customer login, or implicit portal access.
- Home is a clickable daily action center with expiring-today, expired, soon, pending-fee, new-member, recent-payment, member, and Staff routes.
- Manual WhatsApp remains the primary review-before-send workflow. Automatic-provider diagnostics are collapsed and deferred as advanced information.
- People and fee search include membership numbers; paid/pending fee filtering is server-side before limits.
- Dialog naming, form labels, live feedback, month-end previews, responsive cards, focus handling, stale-request protection, and coaching request efficiency were corrected.

## Data integrity

- Migration `011_admin_usability_v2.sql` adds `person_type`, `joined_at`, `staff_designation`, and `admin_note` with existing rows defaulted to Member.
- Database triggers prohibit membership creation/retargeting for Staff and prohibit converting a member with memberships into Staff.
- Service-layer checks also exclude Staff from membership, fees, expiry, follow-up, coaching, payment checkout, and customer authentication paths.
- Exact 010-to-011 migration, replay, backfill, SQLite quick check, and foreign-key validation are covered by regression tests.

## Release-gate evidence before commit

- Backend: 202/202 passed.
- Browser: 57/57 passed.
- Focused backend historical/Staff isolation: 4/4 passed.
- Focused browser past-date/Staff/manual-WhatsApp: 3/3 passed.
- Admin QA: 1, 50, 200, 500, and 1,000 rows ready with zero blockers.
- 1,000-row medians: People list 9.456 ms, search 9.266 ms, Home 40.276 ms, pending fees 22.596 ms.
- JavaScript syntax, Python compilation, HTML parsing, and `git diff --check`: passed.

## Release constraints

- Preserve password-only Admin login and `ADMIN_REQUIRE_SECOND_FACTOR=false`.
- Do not modify the prior immutable live RC.
- Before cutover, validate the new detached clean RC with full backend and browser suites, create and recovery-drill a fresh live backup, then use guarded local deployment.
- No destructive real-data acceptance mutations are authorized.
