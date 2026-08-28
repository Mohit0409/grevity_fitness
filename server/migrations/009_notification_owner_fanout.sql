CREATE TABLE notification_reminders_v2 (
    id TEXT PRIMARY KEY,
    dedupe_key TEXT NOT NULL UNIQUE,
    event_type TEXT NOT NULL CHECK (event_type IN ('membership_expiry')),
    customer_id TEXT NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    membership_id TEXT NOT NULL REFERENCES memberships(id) ON DELETE CASCADE,
    trigger_days INTEGER NOT NULL CHECK (trigger_days BETWEEN 0 AND 90),
    trigger_at INTEGER NOT NULL,
    state TEXT NOT NULL DEFAULT 'pending' CHECK (state IN ('pending', 'suppressed', 'completed')),
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);

INSERT INTO notification_reminders_v2
SELECT id,dedupe_key,event_type,customer_id,membership_id,trigger_days,trigger_at,state,payload_json,created_at,updated_at
FROM notification_reminders;

CREATE TABLE notification_deliveries_v2 (
    id TEXT PRIMARY KEY,
    reminder_id TEXT NOT NULL REFERENCES notification_reminders_v2(id) ON DELETE CASCADE,
    channel TEXT NOT NULL CHECK (channel IN ('email', 'sms', 'whatsapp')),
    recipient_role TEXT NOT NULL DEFAULT 'customer' CHECK (recipient_role IN ('customer', 'owner')),
    recipient_ref TEXT NOT NULL CHECK (recipient_ref IN ('email', 'phone', 'whatsapp')),
    status TEXT NOT NULL CHECK (status IN ('blocked_external_config', 'missing_recipient', 'queued', 'sent', 'failed')),
    attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    next_attempt_at INTEGER,
    last_error_code TEXT,
    provider_message_id TEXT,
    sent_at INTEGER,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    UNIQUE(reminder_id, recipient_role, channel)
);

INSERT INTO notification_deliveries_v2(
    id,reminder_id,channel,recipient_role,recipient_ref,status,attempt_count,next_attempt_at,last_error_code,provider_message_id,sent_at,created_at,updated_at
)
SELECT id,reminder_id,channel,'customer',recipient_ref,status,attempt_count,next_attempt_at,last_error_code,provider_message_id,sent_at,created_at,updated_at
FROM notification_deliveries;

DROP TABLE notification_deliveries;
DROP TABLE notification_reminders;
ALTER TABLE notification_reminders_v2 RENAME TO notification_reminders;
ALTER TABLE notification_deliveries_v2 RENAME TO notification_deliveries;

CREATE INDEX idx_notification_reminders_customer ON notification_reminders(customer_id, created_at DESC);
CREATE INDEX idx_notification_reminders_state ON notification_reminders(state, trigger_at);
CREATE INDEX idx_notification_deliveries_retry ON notification_deliveries(status, next_attempt_at);
CREATE INDEX idx_notification_deliveries_role ON notification_deliveries(recipient_role, channel, status);

UPDATE app_metadata
SET value = 'notification_owner_fanout', updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now')
WHERE key = 'schema_stage';
