CREATE TABLE public_enquiries (
    id TEXT PRIMARY KEY,
    reference TEXT NOT NULL UNIQUE,
    idempotency_hash TEXT NOT NULL UNIQUE,
    payload_fingerprint TEXT NOT NULL,
    enquiry_type TEXT NOT NULL CHECK (enquiry_type IN ('trial_visit', 'membership', 'coaching', 'general')),
    name TEXT NOT NULL,
    phone_e164 TEXT NOT NULL,
    email TEXT,
    plan_id TEXT REFERENCES membership_plans(id) ON DELETE SET NULL,
    preferred_date TEXT,
    preferred_time TEXT CHECK (preferred_time IS NULL OR preferred_time IN ('morning', 'afternoon', 'evening', 'flexible')),
    message TEXT,
    status TEXT NOT NULL DEFAULT 'new' CHECK (status IN ('new', 'contacted', 'confirmed', 'closed')),
    source TEXT NOT NULL DEFAULT 'website',
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    last_contacted_at INTEGER,
    retention_expires_at INTEGER NOT NULL
);

CREATE INDEX public_enquiries_status_created_idx
    ON public_enquiries(status, created_at DESC);
CREATE INDEX public_enquiries_type_created_idx
    ON public_enquiries(enquiry_type, created_at DESC);
CREATE INDEX public_enquiries_retention_idx
    ON public_enquiries(retention_expires_at);

CREATE TABLE public_enquiry_notes (
    id TEXT PRIMARY KEY,
    enquiry_id TEXT NOT NULL REFERENCES public_enquiries(id) ON DELETE CASCADE,
    admin_user_id TEXT NOT NULL REFERENCES admin_users(id) ON DELETE RESTRICT,
    note TEXT NOT NULL,
    created_at INTEGER NOT NULL
);

CREATE INDEX public_enquiry_notes_enquiry_idx
    ON public_enquiry_notes(enquiry_id, created_at ASC);

CREATE TABLE public_enquiry_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    enquiry_id TEXT NOT NULL REFERENCES public_enquiries(id) ON DELETE CASCADE,
    admin_user_id TEXT REFERENCES admin_users(id) ON DELETE SET NULL,
    event_type TEXT NOT NULL CHECK (event_type IN ('received', 'status_changed', 'note_added')),
    from_status TEXT,
    to_status TEXT,
    request_id TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at INTEGER NOT NULL
);

CREATE INDEX public_enquiry_events_enquiry_idx
    ON public_enquiry_events(enquiry_id, created_at ASC);

CREATE TABLE public_enquiry_rate_limits (
    scope TEXT NOT NULL,
    key_hash TEXT NOT NULL,
    window_started_at INTEGER NOT NULL,
    request_count INTEGER NOT NULL DEFAULT 0,
    blocked_until INTEGER,
    PRIMARY KEY (scope, key_hash)
);

-- These are the only membership prices currently verified by the operator.
-- Descriptions from the original imported draft are intentionally cleared so
-- no unverified benefits are exposed publicly.
UPDATE membership_plans
SET description = NULL,
    price_paise = CASE code
        WHEN 'basic-monthly' THEN 99900
        WHEN 'pro-monthly' THEN 149900
        WHEN 'elite-monthly' THEN 249900
        ELSE price_paise
    END,
    currency = 'INR',
    duration_months = 1,
    status = 'active',
    sort_order = CASE code
        WHEN 'basic-monthly' THEN 10
        WHEN 'pro-monthly' THEN 20
        WHEN 'elite-monthly' THEN 30
        ELSE sort_order
    END,
    updated_at = strftime('%s','now')
WHERE code IN ('basic-monthly', 'pro-monthly', 'elite-monthly');
