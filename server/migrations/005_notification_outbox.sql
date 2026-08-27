CREATE TABLE notification_reminders (
    id TEXT PRIMARY KEY,
    dedupe_key TEXT NOT NULL UNIQUE,
    event_type TEXT NOT NULL CHECK (event_type IN ('membership_expiry')),
    customer_id TEXT NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    membership_id TEXT NOT NULL REFERENCES memberships(id) ON DELETE CASCADE,
    trigger_days INTEGER NOT NULL CHECK (trigger_days BETWEEN 1 AND 90),
    trigger_at INTEGER NOT NULL,
    state TEXT NOT NULL DEFAULT 'pending' CHECK (state IN ('pending', 'suppressed', 'completed')),
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);

CREATE INDEX idx_notification_reminders_customer
    ON notification_reminders(customer_id, created_at DESC);

CREATE INDEX idx_notification_reminders_state
    ON notification_reminders(state, trigger_at);

CREATE TABLE notification_deliveries (
    id TEXT PRIMARY KEY,
    reminder_id TEXT NOT NULL REFERENCES notification_reminders(id) ON DELETE CASCADE,
    channel TEXT NOT NULL CHECK (channel IN ('email', 'sms', 'whatsapp')),
    recipient_ref TEXT NOT NULL CHECK (recipient_ref IN ('email', 'phone')),
    status TEXT NOT NULL CHECK (status IN ('blocked_external_config', 'missing_recipient', 'queued', 'sent', 'failed')),
    attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    next_attempt_at INTEGER,
    last_error_code TEXT,
    provider_message_id TEXT,
    sent_at INTEGER,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    UNIQUE(reminder_id, channel)
);

CREATE INDEX idx_notification_deliveries_retry
    ON notification_deliveries(status, next_attempt_at);

UPDATE app_metadata
SET value = 'notification_outbox', updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now')
WHERE key = 'schema_stage';
