CREATE TABLE membership_plans (
    id TEXT PRIMARY KEY,
    code TEXT NOT NULL COLLATE NOCASE UNIQUE,
    name TEXT NOT NULL,
    description TEXT,
    price_paise INTEGER NOT NULL CHECK (price_paise >= 0),
    currency TEXT NOT NULL DEFAULT 'INR' CHECK (length(currency) = 3),
    duration_months INTEGER NOT NULL CHECK (duration_months BETWEEN 1 AND 36),
    status TEXT NOT NULL DEFAULT 'inactive' CHECK (status IN ('active', 'inactive')),
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);

CREATE TABLE membership_plan_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_id TEXT NOT NULL REFERENCES membership_plans(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL CHECK (event_type IN ('created', 'updated', 'activated', 'deactivated')),
    actor_admin_user_id TEXT REFERENCES admin_users(id) ON DELETE SET NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at INTEGER NOT NULL
);

CREATE INDEX idx_membership_plan_events_plan
    ON membership_plan_events(plan_id, id DESC);

CREATE TABLE memberships (
    id TEXT PRIMARY KEY,
    membership_number TEXT NOT NULL UNIQUE,
    customer_id TEXT NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    plan_id TEXT NOT NULL REFERENCES membership_plans(id),
    plan_name_snapshot TEXT NOT NULL,
    plan_price_paise_snapshot INTEGER NOT NULL CHECK (plan_price_paise_snapshot >= 0),
    currency_snapshot TEXT NOT NULL CHECK (length(currency_snapshot) = 3),
    duration_months_snapshot INTEGER NOT NULL CHECK (duration_months_snapshot BETWEEN 1 AND 36),
    status TEXT NOT NULL CHECK (status IN ('scheduled', 'active', 'expired', 'cancelled')),
    starts_at INTEGER NOT NULL,
    ends_at INTEGER NOT NULL CHECK (ends_at > starts_at),
    source TEXT NOT NULL CHECK (source IN ('admin_manual', 'payment', 'import')),
    payment_reference TEXT,
    created_by_admin_user_id TEXT REFERENCES admin_users(id) ON DELETE SET NULL,
    cancellation_reason TEXT,
    cancelled_at INTEGER,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);

CREATE INDEX idx_memberships_customer_lifecycle
    ON memberships(customer_id, status, starts_at, ends_at);

CREATE INDEX idx_memberships_expiry_scan
    ON memberships(status, ends_at);

CREATE TABLE membership_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    membership_id TEXT NOT NULL REFERENCES memberships(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL CHECK (event_type IN ('created', 'activated', 'expired', 'cancelled')),
    actor_admin_user_id TEXT REFERENCES admin_users(id) ON DELETE SET NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at INTEGER NOT NULL
);

CREATE INDEX idx_membership_events_membership
    ON membership_events(membership_id, id DESC);
INSERT INTO membership_plans (
    id, code, name, description, price_paise, currency,
    duration_months, status, sort_order, created_at, updated_at
) VALUES
    ('plan-basic-monthly', 'basic-monthly', 'Basic', 'Imported draft from the current Gravity public pricing card; verify before activation.', 99900, 'INR', 1, 'inactive', 10, strftime('%s','now'), strftime('%s','now')),
    ('plan-pro-monthly', 'pro-monthly', 'Pro', 'Imported draft from the current Gravity public pricing card; verify before activation.', 149900, 'INR', 1, 'inactive', 20, strftime('%s','now'), strftime('%s','now')),
    ('plan-elite-monthly', 'elite-monthly', 'Elite', 'Imported draft from the current Gravity public pricing card; verify before activation.', 249900, 'INR', 1, 'inactive', 30, strftime('%s','now'), strftime('%s','now'));

UPDATE app_metadata
SET value = 'membership_engine', updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now')
WHERE key = 'schema_stage';
CREATE UNIQUE INDEX uq_memberships_payment_reference
    ON memberships(payment_reference)
    WHERE payment_reference IS NOT NULL;
