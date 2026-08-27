CREATE TABLE progress_goals (
    id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    metric_key TEXT NOT NULL CHECK (metric_key IN ('weight_kg','body_fat_pct','waist_cm','workouts_per_week')),
    target_value REAL NOT NULL CHECK (target_value > 0),
    unit TEXT NOT NULL CHECK (unit IN ('kg','percent','cm','sessions_per_week')),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','completed','cancelled')),
    target_at INTEGER,
    created_by_admin_user_id TEXT NOT NULL REFERENCES admin_users(id) ON DELETE RESTRICT,
    completed_at INTEGER,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);

CREATE UNIQUE INDEX uq_progress_goal_active_metric
    ON progress_goals(customer_id, metric_key)
    WHERE status = 'active';

CREATE INDEX idx_progress_goals_customer
    ON progress_goals(customer_id, status, updated_at DESC);

CREATE TABLE progress_measurements (
    id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    metric_key TEXT NOT NULL CHECK (metric_key IN ('weight_kg','body_fat_pct','waist_cm','chest_cm','arm_cm','thigh_cm')),
    value REAL NOT NULL CHECK (value > 0),
    unit TEXT NOT NULL CHECK (unit IN ('kg','percent','cm')),
    measured_at INTEGER NOT NULL,
    created_by_admin_user_id TEXT NOT NULL REFERENCES admin_users(id) ON DELETE RESTRICT,
    created_at INTEGER NOT NULL
);
CREATE INDEX idx_progress_measurements_customer_metric
    ON progress_measurements(customer_id, metric_key, measured_at DESC, created_at DESC);

CREATE TABLE diet_plan_templates (
    id TEXT PRIMARY KEY,
    code TEXT NOT NULL COLLATE NOCASE UNIQUE,
    name TEXT NOT NULL,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'inactive' CHECK (status IN ('active','inactive')),
    created_by_admin_user_id TEXT NOT NULL REFERENCES admin_users(id) ON DELETE RESTRICT,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);

CREATE TABLE diet_plan_versions (
    id TEXT PRIMARY KEY,
    template_id TEXT NOT NULL REFERENCES diet_plan_templates(id) ON DELETE CASCADE,
    version_number INTEGER NOT NULL CHECK (version_number >= 1),
    title TEXT NOT NULL,
    content_json TEXT NOT NULL,
    disclaimer TEXT NOT NULL,
    created_by_admin_user_id TEXT NOT NULL REFERENCES admin_users(id) ON DELETE RESTRICT,
    created_at INTEGER NOT NULL,
    UNIQUE(template_id, version_number)
);

CREATE INDEX idx_diet_plan_versions_template
    ON diet_plan_versions(template_id, version_number DESC);
CREATE TABLE diet_plan_assignments (
    id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    version_id TEXT NOT NULL REFERENCES diet_plan_versions(id) ON DELETE RESTRICT,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','ended','cancelled')),
    starts_at INTEGER NOT NULL,
    ends_at INTEGER,
    assignment_note TEXT,
    assigned_by_admin_user_id TEXT NOT NULL REFERENCES admin_users(id) ON DELETE RESTRICT,
    ended_at INTEGER,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    CHECK (ends_at IS NULL OR ends_at >= starts_at)
);

CREATE UNIQUE INDEX uq_diet_assignment_active_customer
    ON diet_plan_assignments(customer_id)
    WHERE status = 'active';

CREATE INDEX idx_diet_assignments_customer
    ON diet_plan_assignments(customer_id, status, starts_at DESC);

CREATE TABLE diet_plan_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    assignment_id TEXT REFERENCES diet_plan_assignments(id) ON DELETE CASCADE,
    template_id TEXT REFERENCES diet_plan_templates(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    actor_admin_user_id TEXT NOT NULL REFERENCES admin_users(id) ON DELETE RESTRICT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at INTEGER NOT NULL
);
CREATE INDEX idx_diet_plan_events_assignment
    ON diet_plan_events(assignment_id, id DESC);

UPDATE app_metadata
SET value = 'progress_coaching', updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now')
WHERE key = 'schema_stage';
