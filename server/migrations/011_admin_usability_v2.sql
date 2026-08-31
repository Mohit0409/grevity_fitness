ALTER TABLE customers
ADD COLUMN person_type TEXT NOT NULL DEFAULT 'member'
    CHECK (person_type IN ('member', 'staff'));

ALTER TABLE customers ADD COLUMN joined_at INTEGER;
ALTER TABLE customers ADD COLUMN staff_designation TEXT;
ALTER TABLE customers ADD COLUMN admin_note TEXT;

UPDATE customers
SET joined_at = COALESCE(
    (SELECT MIN(m.starts_at) FROM memberships m WHERE m.customer_id = customers.id),
    created_at
)
WHERE joined_at IS NULL;

CREATE INDEX idx_customers_person_directory
    ON customers(person_type, status, display_name COLLATE NOCASE, id);

CREATE TRIGGER trg_memberships_member_only_insert
BEFORE INSERT ON memberships
WHEN COALESCE((SELECT person_type FROM customers WHERE id = NEW.customer_id), '') != 'member'
BEGIN
    SELECT RAISE(ABORT, 'membership_customer_must_be_member');
END;

CREATE TRIGGER trg_memberships_member_only_customer_update
BEFORE UPDATE OF customer_id ON memberships
WHEN COALESCE((SELECT person_type FROM customers WHERE id = NEW.customer_id), '') != 'member'
BEGIN
    SELECT RAISE(ABORT, 'membership_customer_must_be_member');
END;

CREATE TRIGGER trg_customers_staff_without_memberships
BEFORE UPDATE OF person_type ON customers
WHEN NEW.person_type = 'staff'
 AND EXISTS(SELECT 1 FROM memberships WHERE customer_id = NEW.id)
BEGIN
    SELECT RAISE(ABORT, 'staff_cannot_have_memberships');
END;

UPDATE app_metadata
SET value = 'admin_usability_v2', updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now')
WHERE key = 'schema_stage';
