CREATE TABLE admin_users (
    id TEXT PRIMARY KEY,
    username TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('owner','admin','trainer','reception')),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','disabled')),
    encrypted_totp_secret TEXT NOT NULL,
    last_totp_counter INTEGER,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    last_login_at INTEGER
);

CREATE TABLE admin_recovery_codes (
    id TEXT PRIMARY KEY,
    admin_user_id TEXT NOT NULL REFERENCES admin_users(id) ON DELETE CASCADE,
    code_hash TEXT NOT NULL UNIQUE,
    created_at INTEGER NOT NULL,
    used_at INTEGER
);

CREATE INDEX idx_admin_recovery_user
    ON admin_recovery_codes(admin_user_id, used_at);

CREATE TABLE admin_login_challenges (
    id TEXT PRIMARY KEY,
    admin_user_id TEXT NOT NULL REFERENCES admin_users(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL UNIQUE,
    created_at INTEGER NOT NULL,
    expires_at INTEGER NOT NULL,
    used_at INTEGER
);CREATE INDEX idx_admin_challenge_lookup
    ON admin_login_challenges(token_hash, expires_at, used_at);

CREATE TABLE admin_sessions (
    id TEXT PRIMARY KEY,
    admin_user_id TEXT NOT NULL REFERENCES admin_users(id) ON DELETE CASCADE,
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

CREATE INDEX idx_admin_sessions_active
    ON admin_sessions(admin_user_id, revoked_at, absolute_expires_at);

CREATE TABLE admin_rate_limits (
    scope TEXT NOT NULL,
    key_hash TEXT NOT NULL,
    window_started_at INTEGER NOT NULL,
    request_count INTEGER NOT NULL,
    blocked_until INTEGER,
    updated_at INTEGER NOT NULL,
    PRIMARY KEY (scope, key_hash)
);

CREATE INDEX idx_admin_rate_limits_cleanup
    ON admin_rate_limits(updated_at);CREATE TABLE admin_audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    admin_user_id TEXT REFERENCES admin_users(id) ON DELETE SET NULL,
    action TEXT NOT NULL,
    target_type TEXT,
    target_id TEXT,
    result TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at INTEGER NOT NULL
);

CREATE INDEX idx_admin_audit_recent
    ON admin_audit_log(created_at DESC, id DESC);

UPDATE app_metadata
SET value = 'admin_security', updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now')
WHERE key = 'schema_stage';
