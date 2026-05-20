-- P9.5: расширение admin_audit_log для security audit trail

ALTER TABLE admin_audit_log
    ADD COLUMN IF NOT EXISTS event_type TEXT,
    ADD COLUMN IF NOT EXISTS principal_email TEXT,
    ADD COLUMN IF NOT EXISTS platform_role TEXT,
    ADD COLUMN IF NOT EXISTS status TEXT,
    ADD COLUMN IF NOT EXISTS reason TEXT,
    ADD COLUMN IF NOT EXISTS request_path TEXT,
    ADD COLUMN IF NOT EXISTS request_method TEXT,
    ADD COLUMN IF NOT EXISTS ip_hash TEXT,
    ADD COLUMN IF NOT EXISTS user_agent TEXT;

CREATE INDEX IF NOT EXISTS idx_admin_audit_log_event_type
    ON admin_audit_log (event_type);

CREATE INDEX IF NOT EXISTS idx_admin_audit_log_status
    ON admin_audit_log (status);

CREATE INDEX IF NOT EXISTS idx_admin_audit_log_platform_role
    ON admin_audit_log (platform_role);
