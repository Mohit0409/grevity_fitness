ALTER TABLE customers
ADD COLUMN created_by_admin_user_id TEXT REFERENCES admin_users(id) ON DELETE SET NULL;

CREATE UNIQUE INDEX uq_customers_owner_managed_phone
    ON customers(phone_e164)
    WHERE phone_e164 IS NOT NULL AND status != 'deleted';

CREATE TABLE membership_payments (
    id TEXT PRIMARY KEY,
    membership_id TEXT NOT NULL REFERENCES memberships(id) ON DELETE RESTRICT,
    amount_paise INTEGER NOT NULL CHECK (amount_paise > 0),
    currency TEXT NOT NULL CHECK (length(currency) = 3),
    method TEXT NOT NULL CHECK (method IN ('cash','upi','card','bank_transfer','other')),
    note TEXT,
    paid_at INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'recorded' CHECK (status IN ('recorded','void')),
    recorded_by_admin_user_id TEXT REFERENCES admin_users(id) ON DELETE SET NULL,
    idempotency_key TEXT,
    voided_at INTEGER,
    voided_by_admin_user_id TEXT REFERENCES admin_users(id) ON DELETE SET NULL,
    void_reason TEXT,
    created_at INTEGER NOT NULL
);

CREATE INDEX idx_membership_payments_membership
    ON membership_payments(membership_id, status, paid_at DESC);
CREATE INDEX idx_membership_payments_paid_at
    ON membership_payments(status, paid_at DESC);
CREATE UNIQUE INDEX uq_membership_payments_idempotency
    ON membership_payments(recorded_by_admin_user_id, idempotency_key)
    WHERE idempotency_key IS NOT NULL;

ALTER TABLE memberships ADD COLUMN admin_idempotency_key TEXT;
CREATE UNIQUE INDEX uq_memberships_admin_idempotency
    ON memberships(created_by_admin_user_id, admin_idempotency_key)
    WHERE admin_idempotency_key IS NOT NULL;

CREATE INDEX idx_customers_created_by_admin
    ON customers(created_by_admin_user_id, created_at DESC);

UPDATE app_metadata
SET value = 'admin_software_v1', updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now')
WHERE key = 'schema_stage';
