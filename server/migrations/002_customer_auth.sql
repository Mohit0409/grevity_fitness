CREATE TABLE customers (
    id TEXT PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'disabled', 'deleted')),
    display_name TEXT,
    email TEXT,
    normalized_email TEXT,
    email_verified INTEGER NOT NULL DEFAULT 0 CHECK (email_verified IN (0, 1)),
    phone_e164 TEXT,
    phone_verified INTEGER NOT NULL DEFAULT 0 CHECK (phone_verified IN (0, 1)),
    photo_url TEXT,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    last_login_at INTEGER
);

CREATE UNIQUE INDEX uq_customers_verified_email
    ON customers(normalized_email)
    WHERE normalized_email IS NOT NULL AND email_verified = 1 AND status != 'deleted';

CREATE UNIQUE INDEX uq_customers_verified_phone
    ON customers(phone_e164)
    WHERE phone_e164 IS NOT NULL AND phone_verified = 1 AND status != 'deleted';

CREATE TABLE firebase_identities (
    project_id TEXT NOT NULL,
    firebase_uid TEXT NOT NULL,
    customer_id TEXT NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    last_sign_in_provider TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    last_seen_at INTEGER NOT NULL,
    PRIMARY KEY (project_id, firebase_uid)
);

CREATE INDEX idx_firebase_identities_customer
    ON firebase_identities(customer_id);

CREATE TABLE firebase_provider_identities (
    project_id TEXT NOT NULL,
    sign_in_provider TEXT NOT NULL,
    provider_subject TEXT NOT NULL,
    firebase_uid TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    last_seen_at INTEGER NOT NULL,
    PRIMARY KEY (project_id, sign_in_provider, provider_subject),
    FOREIGN KEY (project_id, firebase_uid)
        REFERENCES firebase_identities(project_id, firebase_uid) ON DELETE CASCADE
);

CREATE INDEX idx_firebase_provider_uid
    ON firebase_provider_identities(project_id, firebase_uid);

CREATE TABLE customer_profiles (
    customer_id TEXT PRIMARY KEY REFERENCES customers(id) ON DELETE CASCADE,
    date_of_birth TEXT,
    gender TEXT CHECK (gender IS NULL OR gender IN ('female', 'male', 'non_binary', 'prefer_not_to_say')),
    address TEXT,
    emergency_contact_name TEXT,
    emergency_contact_phone TEXT,
    health_notes TEXT,
    completed_at INTEGER,
    updated_at INTEGER NOT NULL
);

CREATE TABLE customer_sessions (
    id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL UNIQUE,
    csrf_hash TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    last_seen_at INTEGER NOT NULL,
    idle_expires_at INTEGER NOT NULL,
    absolute_expires_at INTEGER NOT NULL,
    revoked_at INTEGER,
    revoke_reason TEXT,
    ip_hash TEXT,
    user_agent_hash TEXT
);

CREATE INDEX idx_customer_sessions_customer_active
    ON customer_sessions(customer_id, revoked_at, absolute_expires_at);

CREATE TABLE auth_rate_limits (
    scope TEXT NOT NULL,
    key_hash TEXT NOT NULL,
    window_started_at INTEGER NOT NULL,
    request_count INTEGER NOT NULL,
    blocked_until INTEGER,
    updated_at INTEGER NOT NULL,
    PRIMARY KEY (scope, key_hash)
);

CREATE INDEX idx_auth_rate_limits_cleanup
    ON auth_rate_limits(updated_at);

UPDATE app_metadata
SET value = 'customer_auth', updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now')
WHERE key = 'schema_stage';
