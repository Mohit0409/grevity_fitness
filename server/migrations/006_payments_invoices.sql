CREATE TABLE payment_intents (
    id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL REFERENCES customers(id) ON DELETE RESTRICT,
    plan_id TEXT NOT NULL REFERENCES membership_plans(id) ON DELETE RESTRICT,
    plan_name_snapshot TEXT NOT NULL,
    amount_paise INTEGER NOT NULL CHECK (amount_paise > 0),
    currency TEXT NOT NULL CHECK (length(currency) = 3),
    duration_months_snapshot INTEGER NOT NULL CHECK (duration_months_snapshot BETWEEN 1 AND 36),
    provider TEXT NOT NULL DEFAULT 'razorpay' CHECK (provider = 'razorpay'),
    status TEXT NOT NULL CHECK (status IN ('creating','created','paid','failed','cancelled')),
    receipt_reference TEXT NOT NULL UNIQUE,
    provider_order_id TEXT UNIQUE,
    provider_payment_id TEXT UNIQUE,
    last_error_code TEXT,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    paid_at INTEGER
);

CREATE INDEX idx_payment_intents_customer
    ON payment_intents(customer_id, created_at DESC);

CREATE INDEX idx_payment_intents_status
    ON payment_intents(status, updated_at);
CREATE TABLE payment_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    payment_intent_id TEXT REFERENCES payment_intents(id) ON DELETE CASCADE,
    event_key TEXT NOT NULL UNIQUE,
    event_type TEXT NOT NULL,
    provider_event_id TEXT UNIQUE,
    payload_sha256 TEXT NOT NULL CHECK (length(payload_sha256) = 64),
    created_at INTEGER NOT NULL
);

CREATE INDEX idx_payment_events_intent
    ON payment_events(payment_intent_id, id DESC);

CREATE TABLE invoice_records (
    id TEXT PRIMARY KEY,
    document_number TEXT NOT NULL UNIQUE,
    payment_intent_id TEXT NOT NULL UNIQUE REFERENCES payment_intents(id) ON DELETE RESTRICT,
    customer_id TEXT NOT NULL REFERENCES customers(id) ON DELETE RESTRICT,
    membership_id TEXT NOT NULL UNIQUE REFERENCES memberships(id) ON DELETE RESTRICT,
    status TEXT NOT NULL DEFAULT 'pending_business_identity'
        CHECK (status IN ('pending_business_identity','issued','void')),
    plan_name_snapshot TEXT NOT NULL,
    amount_paise INTEGER NOT NULL CHECK (amount_paise > 0),
    currency TEXT NOT NULL CHECK (length(currency) = 3),
    seller_snapshot_json TEXT NOT NULL DEFAULT '{}',
    customer_snapshot_json TEXT NOT NULL DEFAULT '{}',    issued_at INTEGER,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);

CREATE INDEX idx_invoice_records_customer
    ON invoice_records(customer_id, created_at DESC);

UPDATE app_metadata
SET value = 'payments_invoices', updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now')
WHERE key = 'schema_stage';
