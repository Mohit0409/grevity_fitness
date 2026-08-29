# Gravity Fitness Admin Software - Backend Contract Request

Owner: Chat 1 backend / integration lead
Requested by: Chat 2 admin software UI
Status: frontend must remain fail-closed until these contracts are implemented and approved.

## Why this is required

The current admin backend can list customers, change customer status, manage membership plans, create/renew memberships, list expiring memberships and read notifications. It does not currently expose admin customer creation/editing, a manual fee ledger, manual payment recording, enriched customer-list membership/fee fields, or a global membership list. Chat 2 intentionally does not emulate any of those records in browser memory.

## 1. Customer onboarding

Needed for the Add Customer workflow. Prefer one transactional backend operation so a partially-created customer is not left behind if membership/payment creation fails.

Desired request semantics:

- customer: display name, normalized mobile
- membership: plan id, optional requested start date
- opening payment: optional amount, payment method, payment date/note

Desired response semantics:

- authoritative customer record
- authoritative current/scheduled membership including membership number, startsAt, endsAt, price snapshot and status
- authoritative fee/payment summary
- conflict response for duplicate normalized mobile
- field-level validation response for invalid input

Chat 2 will not choose the final route name until Chat 1 publishes it.

## 2. Customer detail and edit

The customer drawer needs one admin-safe detail response containing:

- id, displayName, normalized phone, status, createdAt
- current membership summary
- membership history
- fee summary: total fee, paid, pending
- recent payment history

A separate authenticated mutation is required for editable customer fields such as displayName/mobile. Existing customer status PATCH should remain available for enable/disable.

## 3. Manual fee ledger and payments

Required for Fees, Record Payment and payment history. The ledger must be server-authoritative and auditable.

Required capabilities:

- list fee balances with customer, membership, total fee, paid, pending, expiry and status
- filter pending / fully paid / expired and search customer
- record a manual payment against a customer/membership
- accepted method enum controlled by backend (for example cash/UPI/card/bank transfer)
- amount > 0 and never above allowed outstanding balance unless backend explicitly supports credit
- optional payment date and note
- immutable audit/event record with actor admin id and request id
- response returns refreshed authoritative fee summary and payment record
- idempotency protection for repeated submissions

Do not reuse Razorpay customer checkout intents as the manual cash/UPI ledger.

## 4. Dashboard operations summary

Extend the admin dashboard response, or add an approved operations-summary route, with server-derived values:

- totalCustomers
- activeMembers
- expiringSoon (recommended 7-day count)
- expiredMemberships
- pendingFeesPaise + currency
- recentPayments
- recentCustomers

Until this exists, Chat 2 shows verified customer total and expiring count only and renders unavailable markers for active/expired/pending-fee metrics.

## 5. Enriched customer list

For a scalable Customers table, the list API should support server-side filters and avoid one membership request per customer:

- q (name/mobile)
- customer status
- plan id
- optional paging/cursor

Each row should include:

- customer id/name/masked-or-full admin-safe phone/status/createdAt
- current membership: planName, membershipNumber, endsAt, daysRemaining, membership status
- fee summary: total/paid/pending

## 6. Global membership list

Required for full Memberships filters beyond the existing expiring endpoint:

- status: active / scheduled / expired / cancelled
- plan id
- expiry window
- customer search
- paging

Rows should include customer identity summary, membership number, plan snapshot, start/expiry, daysRemaining and status.

## Security / audit requirements

All new write operations must keep the existing admin session, permission, same-origin and CSRF protections. Customer creation/edit, manual payments and membership-affecting writes should be audit logged. Responses must not expose secrets, payment-provider credentials or raw internal stack traces.
