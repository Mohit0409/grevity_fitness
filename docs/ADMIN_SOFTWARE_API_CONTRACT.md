# Gravity Fitness Admin Software V1 - Frontend Contract

Owner of backend implementation: Chat 1 / integration lead
Consumer: Chat 2 Admin Software frontend
Status: Chat 2 frontend is wired and tested against Chat 1's current Admin Software V1 contract. Chat 1 backend changes are still owned and committed by Chat 1.

## Principles

- Server values are authoritative for membership dates, balances and payment state.
- The browser never persists a duplicate customer, membership or fee ledger.
- All admin mutations use the existing authenticated admin session, same-origin and CSRF protections.
- UI handles validation/conflict failures without exposing raw internal errors.
- Customer list phone numbers are masked in broad list views; customer detail can show the admin-authorized phone.

## Dashboard

`GET /api/admin/dashboard`

Frontend consumes `stats`:
- `totalCustomers`
- `activeMembers`
- `expiringSoon`
- `expiredMembers`
- `pendingFeesTotalPaise`
- `newCustomersThisMonth`
- `paymentsReceivedTodayPaise`
- `paymentsReceivedThisMonthPaise`

Frontend also consumes:
- `expiring.today`
- `expiring.tomorrow`
- `expiring.threeDays`
- `expiring.sevenDays`
- `pendingFees`
- `recentPayments`
- `recentCustomers`

## Customers

`GET /api/admin/customers`

Supported query parameters used by the UI:
- `q`
- `status`
- `membershipStatus`
- `planId`

Each customer may include an enriched `membership` with its server payment summary.

`POST /api/admin/customers`
Chat 2 sends:
- `displayName`
- `phone` (10-digit Indian input is normalized to `+91...` as a UI convenience; backend still validates)
- `planId`
- optional `startsAt`
- `amountPaidPaise`
- `paymentMethod`
- optional `note`

The successful response provides authoritative `customer`, `membership`, optional `payment`, and `paymentSummary` values. Duplicate phone conflicts return HTTP 409. Field validation returns HTTP 422 with safe `fields` messages.

`GET /api/admin/customers/{id}`

Customer detail includes:
- customer identity/status
- current/upcoming/history/all memberships
- payment summaries on memberships
- payment history
- membership notification history

`PATCH /api/admin/customers/{id}`

Chat 2 uses this for display name, phone and active/disabled status updates.
## Renewal

`POST /api/admin/customers/{id}/renew`

Chat 2 sends:
- `planId`
- optional `startsAt`
- `amountPaidPaise`
- `paymentMethod`
- optional `note`

The UI displays plan fee/new-expiry/pending previews only. After success it reloads customer detail and uses the server-created active/scheduled membership and server payment summary.

## Payments

`GET /api/admin/payments`

Used indirectly through dashboard/detail responses and available for dedicated listing. Supported filters include `customerId` and `membershipId`.

`POST /api/admin/memberships/{id}/payments`

Chat 2 sends:
- `amountPaise`
- `method`
- optional `paidAt`
- optional `note`

The UI never mutates the pending balance optimistically. It waits for the server response, closes on success, then reloads customer/dashboard/membership/fee views. Submit is disabled while a payment request is in flight.

Handled states include partial payment, full payment, invalid amount, overpayment/conflict, network failure and duplicate-submit protection.

## Fees

`GET /api/admin/fees`

Chat 2 uses:
- `q`
- `pendingOnly=1` for pending-only mode

Response fields consumed:
- `pendingFeesTotalPaise`
- `rows[].customerId/customerName/phone`
- `rows[].membership`
- membership `payment.totalPaise/paidPaise/pendingPaise`

The frontend can additionally filter the returned all-balances view to fully paid memberships.

## Memberships

`GET /api/admin/memberships`
Supported backend filters used by Chat 2:
- `status=active|scheduled|expired|cancelled`
- `planId`

Chat 2 implements an additional `Expiring soon` view by requesting `status=active` and filtering the returned server `daysRemaining` value using a 3/7/14/30-day UI window. No expiry date is recomputed as authoritative client state.

Plan catalog continues to use:
- `GET /api/admin/membership/plans`
- existing plan create/update endpoints

## Notifications

`GET /api/admin/notifications`

Existing Chat 2 notification UX remains unchanged: customer and owner Email/SMS/WhatsApp delivery rows are separated and each delivery status is rendered individually. Raw provider errors/tokens are not displayed.

## Remaining Chat 1-owned auth UI item

Chat 1's current auth backend returns HTTP 403 with:

`{"error":"account_not_provisioned"}`

when a phone-authenticated customer has not first been created by Gravity Fitness.
`web/js/account-page.js` and `web/pages/account.html` remain Chat 1-owned auth files. Chat 2 did not modify them.

Required customer-facing handling when Chat 1 completes that UI path:

> Your membership account is not registered with Gravity Fitness yet. Please contact the gym reception.

Do not present this state as an invalid password and do not offer customer self-registration.

## Validation snapshot

Chat 2 synthetic Admin Software V1 browser fixture uses only temporary in-memory test state. It covers customer creation/duplicate mobile, search/filter/detail/edit/status, renewal, payment ledger, fees, memberships, empty/error states and responsive/accessibility behavior.

At the time this contract was refreshed:
- Chat 2 full Playwright suite: 36/36 passed.
- Chat 2 Python regression: 102/102 passed.
- Chat 1 current Admin Software service/HTTP focused tests: 15/15 passed read-only from `main`.

Chat 1 remains responsible for committing/integrating the backend implementation and resolving any contract change before merging Chat 2.