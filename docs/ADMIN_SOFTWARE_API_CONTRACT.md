# Gravity Fitness Admin Software - People and Membership Contract

Status: Admin Usability V2 release candidate

## Principles

- The server is authoritative for membership dates, status, balances, and payment state.
- `personType=member` and `personType=staff` are persistent operational records. Staff records never grant Admin Portal login access; Team Access remains separate.
- Staff cannot own memberships, fees, coaching assignments, customer sessions, or expiry follow-ups. The database and service layer enforce this boundary.
- Existing customer rows migrate safely to `member`.
- Admin mutations retain authenticated-session, CSRF, RBAC, transaction, idempotency, and audit protections.
- Broad list responses mask mobile numbers; permission-checked detail responses may return the saved number.

## Home

`GET /api/admin/dashboard`

`stats` includes `totalCustomers` (members), `totalStaff`, `activeMembers`, `expiringSoon`, `expiredMembers`, `pendingFeesTotalPaise`, `newCustomersThisMonth`, `paymentsReceivedTodayPaise`, and `paymentsReceivedThisMonthPaise`.

Operational collections include `expiring.today`, `expiring.tomorrow`, `expiring.threeDays`, `expiring.sevenDays`, `pendingFees`, `recentPayments`, and member-only `recentCustomers`.

## People

`GET /api/admin/customers`

Supported filters: `q`, `personType=member|staff`, `status`, `membershipStatus`, `planId`, and `limit`. Search matches name, mobile, membership number, and staff designation. Membership filters apply only to members.

Every person includes `personType`, `joinedAt`, `designation`, and `note`. A member may include the selected membership and its payment summary. A staff row always has `membership=null`.

`POST /api/admin/customers`

Common fields: `personType`, `displayName`, `phone`, and optional `note`.

Member fields: `planId`, optional historical/future `startsAt`, `amountPaidPaise`, `paymentMethod`, and optional payment `note`. Valid starts can be up to 30 years old or one year ahead. The server derives expiry and immediately records a fully historical period as expired.

Staff fields: `designation`, `joinedAt`, and `status=active|disabled`. Plan, membership, fee, and payment fields are rejected as inapplicable. A successful staff response contains `customer`, with `membership`, `payment`, and `paymentSummary` set to null.

Duplicate mobile conflicts return HTTP 409. Field validation returns HTTP 422 with safe field messages.

`GET /api/admin/customers/{id}`

Member detail includes current/upcoming/history memberships, payment summaries/history, and notification history. Staff detail contains only the operational person profile.

`PATCH /api/admin/customers/{id}`

Common editable fields are `displayName`, `phone`, `status`, and `note`. Staff additionally supports `designation` and `joinedAt`. Person type is immutable. Member mobile/status changes retain customer-session revocation behavior; staff records never create customer sessions.

## Memberships and renewal

`GET /api/admin/memberships` accepts `status`, `planId`, and `limit`; results are member-only.

`POST /api/admin/customers/{id}/renew` accepts `planId`, optional `startsAt`, `amountPaidPaise`, `paymentMethod`, and optional `note`. Staff renewal is rejected. Overlapping live periods remain blocked and history is preserved.

Plan catalog endpoints remain under `/api/admin/membership/plans`.

## Payments and fees

`POST /api/admin/memberships/{id}/payments` accepts `amountPaise`, `method`, optional `paidAt`, and optional `note`. The UI waits for the server response and reloads authoritative balance state; idempotency and overpayment protection remain server-side.

`GET /api/admin/fees` accepts `q`, `balance=pending|paid`, legacy `pendingOnly=1`, and `limit`. Filtering occurs before the server limit. Search includes member name, mobile, and membership number. Staff is excluded.

## Follow-ups and coaching

Expiry collections and manual WhatsApp actions are member-only. The browser opens a prefilled `wa.me` destination for owner review and never sends automatically.

Automatic provider diagnostics are advanced, collapsed by default, and loaded only when expanded. Core manual follow-up use does not require provider configuration.

Coaching customer selection is explicitly `personType=member&status=active`; the service rejects staff IDs as a defense in depth.

## Authentication boundary

Only active `member` records can provision, link, or continue customer sessions. A phone matching only a Staff record receives the existing safe `account_not_provisioned` behavior. Admin username/password access remains independently managed through Team Access.

## Validation snapshot

- Backend regression: 202/202 passed.
- Browser regression: 57/57 passed.
- Disposable Admin QA at 1, 50, 200, 500, and 1,000 rows: ready with zero blockers.
- Migration coverage includes exact 010-to-011 upgrade, default-member backfill, joined-date backfill, replay, SQLite quick check, and foreign-key check.
