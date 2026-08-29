# Gravity Fitness Admin Software V1 QA Report

Date: 2026-08-29

Branch: `agent/gravity-admin-ops`

Baseline: `49529c9`

## Release decision

**Not ready for daily fee/payment operation.** Existing authentication, membership scheduling, notification suppression, backup integrity, and lifecycle foundations are strong, but the current `main` does not yet expose admin customer creation, manual fee/payment recording, or pending-balance contracts. Two synthetic fault/retry diagnostics also prove release-blocking integrity gaps: payment completion can leave a committed membership when final payment state fails, and two membership submit requests create two renewals.

No production database or real customer data was used. All new acceptance and performance work creates disposable temporary databases.

## Automated journey evidence

The temporary-database acceptance test exercises the currently available chain:

1. synthetic customer fixture (the admin create-customer contract is not present);
2. administrator assigns an active membership;
3. a 7-day expiry reminder and six recipient/channel delivery rows are created;
4. a server-owned Razorpay test intent is verified;
5. the paid intent creates a non-overlapping scheduled renewal;
6. the prior reminder becomes suppressed;
7. time advances through expiry;
8. the old membership moves to history and the renewal becomes active;
9. foreign keys pass;
10. backup, verification, temporary restore, exact row counts, and the paid total pass.

Fault injection after membership insertion proves membership assignment and renewal roll back both the membership and its events. The backup acceptance asserts: 1 customer, 2 memberships, 1 paid payment totaling 99,900 paise, 1 reminder, and 6 deliveries after restore.

## E2E matrix

| Scenario | Current evidence | Status |
| --- | --- | --- |
| 1. Empty gym | Existing database/admin tests | Pass |
| 2. First customer | No admin create-customer contract | Blocked — Chat 1 |
| 3. Customer + full payment | Customer checkout path covered; admin manual payment absent | Partial |
| 4. Customer + partial payment | No fee ledger/partial-payment model | Blocked — Chat 1 |
| 5. Multiple payments | Customer payment history exists; admin ledger absent | Partial |
| 6. Pending fee | No pending-balance calculation/API | Blocked — Chat 1 |
| 7. Expiry | Reconciliation and expiry-window tests | Pass |
| 8. Renewal | Scheduling/history test passes; request idempotency absent | Blocked |
| 9. Notification suppression | Late-renewal and full acceptance tests | Pass |
| 10. Disabled customer | Session revocation and notification suppression tests | Pass |
| 11. Duplicate mobile | Verified-phone uniqueness/auth collision tests | Pass for verified identity; manual entry pending |
| 12. Invalid payment | Signature, amount, currency, webhook, and disabled-provider tests | Pass for online payment |
| 13. 500 customers | Synthetic performance audit | Pass with findings |
| 14. 1,000 customers | Synthetic performance audit | Pass with findings |
| 15. Admin logout/session expiry | Service tests plus refresh/expiry browser test | Pass |
| 16. Crash/restart | Deterministic lifecycle drill | Pass on baseline; rerun at release |
| 17. Backup/restore | Exact-count/paid-total temporary restore | Pass |

## Transaction and duplicate-submit findings for Chat 1 / Chat 2

1. **Payment finalization is split across transactions.** `PaymentService._finalize_verified_payment()` calls `_ensure_membership()`, whose `create_membership()` commits, before starting the payment/invoice transaction. A synthetic failure after that commit leaves a payment-sourced membership while the payment is not paid. Chat 1 should make payment state, membership, invoice, and payment event atomic on one connection, or implement and test an explicit recoverable saga.
2. **Renewal has no request idempotency.** Two identical `create_membership()` calls append two scheduled memberships. Chat 1 should require/persist a unique idempotency key for admin customer, payment, and renewal mutations and return the original result on replay.
3. **The membership form has no in-flight guard.** `web/js/admin-memberships.js` does not disable `#assignMembership` while awaiting the POST. Chat 2 should add a shared submit lock/disabled state after the backend idempotency contract exists. The plan form, customer status buttons, admin creation, and cancellation actions need the same audit.
4. Notification scan already disables its button during the request; the browser double-click test observes one request only.

## Performance results

Median wall-clock milliseconds from five calls on this Windows workstation:

| Synthetic customers | Customer list | Search | Dashboard | Expiry query/render | Notification admin list |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 100 | 15.5 | 7.7 | 9.7 | 14.3 | 60.1 |
| 500 | 13.1 | 15.8 | 13.5 | 31.1 | 68.7 |
| 1,000 | 11.9 | 14.3 | 10.1 | 57.8 | 148.4 |
| 5,000 | 17.5 | 24.9 | 21.9 | 255.8 | 586.3 |

All four databases passed foreign-key integrity. SQLite uses `idx_memberships_expiry_scan` and the customer primary key for expiry queries. Customer list/dashboard and the global notification list scan and create temporary sort/group B-trees. Pending-fee performance cannot be measured until the fee ledger exists.

Chat 1 migration recommendation (not applied here because backend schema ownership was not coordinated):

```sql
-- 010_admin_operations_indexes.sql
CREATE INDEX idx_customers_admin_status ON customers(status);
CREATE INDEX idx_customers_admin_recent ON customers(created_at DESC, id DESC);
CREATE INDEX idx_notification_reminders_admin_recent ON notification_reminders(created_at DESC, id DESC);
```

Leading-wildcard name/email search remains a scan even with ordinary B-tree indexes. At 5,000 rows it measured about 25 ms, so no FTS migration is justified yet. If later volumes/latency require it, Chat 1 should design normalized prefix search or FTS with transactionally maintained content rather than adding an ineffective index.

The 5,000-row notification list is the main observed latency. The missing recent-reminder index contributes, while reconciliation of all live memberships and per-reminder delivery loading also deserve profiling after the index migration.

## Security and operational findings

- Admin APIs require separate admin authentication; customer cookies do not authorize them. Existing RBAC, CSRF, same-origin, TOTP, recovery-code, and session-revocation tests pass.
- JSON APIs use `Cache-Control: no-store`; admin HTML is `no-cache`, not publicly cacheable.
- Static scans find no server secret configuration names in browser JS/HTML and no provider secrets in scheduled-task arguments.
- Logs and scheduler state expose aggregate event/status fields only. The new health report discards backend payload extras and emits no contacts, tokens, database paths, or provider credentials.
- Admin customer/payment creation events do not exist yet because those mutations are absent. When Chat 1 adds them, operations logging should whitelist only `customer_created`, `membership_created`, `membership_renewed`, `payment_recorded`, `notification_cycle`, and `backup_verified` with counts, opaque IDs or request IDs—never full phone/email, payment or session tokens, Firebase data, or provider credentials.
- Windows Task Scheduler already separates watchdog, daily backup, and notifications. Ngrok credentials remain in a protected config file path rather than the command line.
- `scripts/admin-health-check.ps1` now reports backend, database/migrations, latest backup/recovery drill, notification scheduler freshness, and provider readiness without PII.

## PWA decision

Do not implement an admin PWA for V1. Revisit only after the core idempotency/transaction blockers are resolved and Chat 1 approves. A future admin service worker must never cache authenticated HTML/API data or queue offline writes.
