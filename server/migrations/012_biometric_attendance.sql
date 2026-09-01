CREATE TABLE biometric_devices (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    vendor TEXT NOT NULL DEFAULT 'zkteco',
    model TEXT NOT NULL DEFAULT 'F09',
    device_serial TEXT,
    device_identifier TEXT NOT NULL,
    host TEXT,
    port INTEGER NOT NULL DEFAULT 4370 CHECK (port BETWEEN 1 AND 65535),
    connection_mode TEXT NOT NULL DEFAULT 'tcp' CHECK (connection_mode IN ('tcp', 'adms', 'mock')),
    enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    status TEXT NOT NULL DEFAULT 'not_configured'
        CHECK (status IN ('not_configured', 'online', 'offline', 'authentication_failed', 'syncing', 'error')),
    last_seen_at INTEGER,
    last_sync_at INTEGER,
    timezone TEXT NOT NULL DEFAULT 'Asia/Kolkata',
    poll_interval_seconds INTEGER NOT NULL DEFAULT 30 CHECK (poll_interval_seconds BETWEEN 10 AND 3600),
    duplicate_window_seconds INTEGER NOT NULL DEFAULT 120 CHECK (duplicate_window_seconds BETWEEN 10 AND 1800),
    visit_gap_seconds INTEGER NOT NULL DEFAULT 14400 CHECK (visit_gap_seconds BETWEEN 600 AND 86400),
    sync_cursor_json TEXT,
    comm_key_encrypted TEXT,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);

CREATE UNIQUE INDEX uq_biometric_devices_identifier
    ON biometric_devices(vendor, device_identifier);

CREATE INDEX idx_biometric_devices_status
    ON biometric_devices(enabled, status, updated_at DESC);

CREATE TABLE biometric_device_users (
    id TEXT PRIMARY KEY,
    device_id TEXT NOT NULL REFERENCES biometric_devices(id) ON DELETE CASCADE,
    device_user_id TEXT NOT NULL,
    display_name TEXT,
    privilege TEXT,
    enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    synced_at INTEGER NOT NULL,
    raw_payload_json TEXT,
    UNIQUE(device_id, device_user_id)
);

CREATE INDEX idx_biometric_device_users_name
    ON biometric_device_users(device_id, display_name COLLATE NOCASE);

CREATE TABLE biometric_person_mappings (
    id TEXT PRIMARY KEY,
    device_id TEXT NOT NULL REFERENCES biometric_devices(id) ON DELETE CASCADE,
    person_id TEXT NOT NULL REFERENCES customers(id) ON DELETE RESTRICT,
    device_user_id TEXT NOT NULL,
    device_display_name TEXT,
    enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    enrolled_status TEXT NOT NULL DEFAULT 'registered'
        CHECK (enrolled_status IN ('unknown', 'registered', 'not_registered')),
    last_verified_at INTEGER,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);

CREATE UNIQUE INDEX uq_biometric_mapping_device_user_active
    ON biometric_person_mappings(device_id, device_user_id)
    WHERE enabled = 1;

CREATE UNIQUE INDEX uq_biometric_mapping_person_device_active
    ON biometric_person_mappings(device_id, person_id)
    WHERE enabled = 1;

CREATE INDEX idx_biometric_mapping_person
    ON biometric_person_mappings(person_id, enabled);

CREATE TABLE attendance_visits (
    id TEXT PRIMARY KEY,
    person_id TEXT NOT NULL REFERENCES customers(id) ON DELETE RESTRICT,
    device_id TEXT NOT NULL REFERENCES biometric_devices(id) ON DELETE RESTRICT,
    visit_date TEXT NOT NULL,
    first_scan_at INTEGER NOT NULL,
    last_scan_at INTEGER NOT NULL,
    scan_count INTEGER NOT NULL DEFAULT 1 CHECK (scan_count >= 1),
    verification_summary TEXT,
    status TEXT NOT NULL DEFAULT 'present' CHECK (status IN ('present', 'closed')),
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);

CREATE INDEX idx_attendance_visits_date
    ON attendance_visits(visit_date, first_scan_at DESC);

CREATE INDEX idx_attendance_visits_person
    ON attendance_visits(person_id, first_scan_at DESC);

CREATE TABLE attendance_events (
    id TEXT PRIMARY KEY,
    device_id TEXT NOT NULL REFERENCES biometric_devices(id) ON DELETE RESTRICT,
    device_event_id TEXT,
    device_user_id TEXT NOT NULL,
    person_id TEXT REFERENCES customers(id) ON DELETE RESTRICT,
    visit_id TEXT REFERENCES attendance_visits(id) ON DELETE SET NULL,
    event_time INTEGER NOT NULL,
    received_at INTEGER NOT NULL,
    verification_type TEXT NOT NULL DEFAULT 'unknown',
    attendance_state TEXT,
    raw_event_hash TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'tcp' CHECK (source IN ('tcp', 'adms', 'mock', 'manual')),
    processing_status TEXT NOT NULL DEFAULT 'stored'
        CHECK (processing_status IN ('stored', 'unmatched', 'malformed', 'duplicate')),
    is_duplicate INTEGER NOT NULL DEFAULT 0 CHECK (is_duplicate IN (0, 1)),
    raw_payload_json TEXT,
    created_at INTEGER NOT NULL,
    UNIQUE(device_id, raw_event_hash)
);

CREATE INDEX idx_attendance_events_time
    ON attendance_events(event_time DESC, id DESC);

CREATE INDEX idx_attendance_events_person_time
    ON attendance_events(person_id, event_time DESC)
    WHERE person_id IS NOT NULL;

CREATE INDEX idx_attendance_events_device_user_time
    ON attendance_events(device_id, device_user_id, event_time DESC);

CREATE INDEX idx_attendance_events_unmatched
    ON attendance_events(device_id, device_user_id, event_time DESC)
    WHERE person_id IS NULL;

UPDATE app_metadata
SET value = 'biometric_attendance_v1', updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now')
WHERE key = 'schema_stage';
