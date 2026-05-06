-- database/migrations/002_runtime_lifecycle.sql
-- Assistant Flow / Career Knowledge Assistant
-- Migration to DB schema v2 runtime lifecycle contract.
--
-- Safe to run repeatedly on an existing v1 database.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ============================================================
-- Common helpers
-- ============================================================

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ============================================================
-- 1. Extend existing checks and base tables
-- ============================================================

-- chat_sessions: extend modes for product roadmap.
ALTER TABLE chat_sessions
    DROP CONSTRAINT IF EXISTS chat_sessions_mode_check;

ALTER TABLE chat_sessions
    ADD CONSTRAINT chat_sessions_mode_check
    CHECK (mode IN ('text', 'rag', 'voice', 'image', 'career', 'hr_screening'));

-- documents: allow soft delete status.
ALTER TABLE documents
    DROP CONSTRAINT IF EXISTS documents_status_check;

ALTER TABLE documents
    ADD CONSTRAINT documents_status_check
    CHECK (status IN ('uploaded', 'indexing', 'indexed', 'failed', 'archived', 'deleted'));

-- indexing_jobs: add execution tracking, actor, job type and stats.
ALTER TABLE indexing_jobs
    ADD COLUMN IF NOT EXISTS execution_id TEXT,
    ADD COLUMN IF NOT EXISTS triggered_by UUID REFERENCES app_users(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS job_type TEXT NOT NULL DEFAULT 'index',
    ADD COLUMN IF NOT EXISTS stats JSONB NOT NULL DEFAULT '{}'::jsonb;

ALTER TABLE indexing_jobs
    DROP CONSTRAINT IF EXISTS indexing_jobs_status_check;

ALTER TABLE indexing_jobs
    ADD CONSTRAINT indexing_jobs_status_check
    CHECK (status IN ('pending', 'running', 'completed', 'failed', 'cancelled'));

ALTER TABLE indexing_jobs
    DROP CONSTRAINT IF EXISTS indexing_jobs_job_type_check;

ALTER TABLE indexing_jobs
    ADD CONSTRAINT indexing_jobs_job_type_check
    CHECK (job_type IN ('index', 'reindex', 'delete_from_index', 'sync'));

CREATE INDEX IF NOT EXISTS idx_indexing_jobs_execution_id
    ON indexing_jobs (execution_id);

CREATE INDEX IF NOT EXISTS idx_indexing_jobs_triggered_by
    ON indexing_jobs (triggered_by);

-- chat_messages: add execution and intake links.
ALTER TABLE chat_messages
    ADD COLUMN IF NOT EXISTS execution_id TEXT;

-- intake_events is created below, so intake_event_id is added afterwards.

CREATE INDEX IF NOT EXISTS idx_chat_messages_execution_id
    ON chat_messages (execution_id);

-- request_logs: runtime observability extension.
ALTER TABLE request_logs
    ADD COLUMN IF NOT EXISTS execution_id TEXT,
    ADD COLUMN IF NOT EXISTS estimated_cost NUMERIC(12, 6),
    ADD COLUMN IF NOT EXISTS metadata JSONB NOT NULL DEFAULT '{}'::jsonb;

ALTER TABLE request_logs
    DROP CONSTRAINT IF EXISTS request_logs_request_type_check;

ALTER TABLE request_logs
    ADD CONSTRAINT request_logs_request_type_check
    CHECK (request_type IN (
        'text',
        'rag',
        'rag_retrieval',
        'rag_answer',
        'embedding',
        'voice',
        'stt',
        'tts',
        'image_analysis',
        'image_generation',
        'telegram_send',
        'indexing',
        'admin'
    ));

CREATE INDEX IF NOT EXISTS idx_request_logs_execution_id
    ON request_logs (execution_id);

-- error_logs: runtime lifecycle extension.
ALTER TABLE error_logs
    ADD COLUMN IF NOT EXISTS execution_id TEXT,
    ADD COLUMN IF NOT EXISTS severity TEXT NOT NULL DEFAULT 'error',
    ADD COLUMN IF NOT EXISTS is_recoverable BOOLEAN,
    ADD COLUMN IF NOT EXISTS resolved_at TIMESTAMPTZ;

ALTER TABLE error_logs
    DROP CONSTRAINT IF EXISTS error_logs_severity_check;

ALTER TABLE error_logs
    ADD CONSTRAINT error_logs_severity_check
    CHECK (severity IN ('debug', 'info', 'warning', 'error', 'critical'));

CREATE INDEX IF NOT EXISTS idx_error_logs_execution_id
    ON error_logs (execution_id);

CREATE INDEX IF NOT EXISTS idx_error_logs_severity
    ON error_logs (severity);

-- ============================================================
-- 2. Users preferences
-- ============================================================

CREATE TABLE IF NOT EXISTS user_preferences (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL UNIQUE REFERENCES app_users(id) ON DELETE CASCADE,

    default_mode TEXT NOT NULL DEFAULT 'text'
        CHECK (default_mode IN ('text', 'rag', 'voice', 'image', 'career', 'hr_screening')),

    enable_voice BOOLEAN NOT NULL DEFAULT TRUE,
    enable_images BOOLEAN NOT NULL DEFAULT TRUE,
    language TEXT NOT NULL DEFAULT 'ru',
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_user_preferences_user_id
    ON user_preferences(user_id);

DROP TRIGGER IF EXISTS trg_user_preferences_updated_at ON user_preferences;
CREATE TRIGGER trg_user_preferences_updated_at
BEFORE UPDATE ON user_preferences
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

-- ============================================================
-- 3. Intake events
-- ============================================================

CREATE TABLE IF NOT EXISTS intake_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    execution_id TEXT NOT NULL UNIQUE,

    source TEXT NOT NULL
        CHECK (source IN ('telegram', 'admin_ui', 'system', 'cli', 'api')),

    event_type TEXT NOT NULL
        CHECK (event_type IN (
            'message',
            'command',
            'callback',
            'upload',
            'admin_action',
            'indexing_job',
            'system_event'
        )),

    input_type TEXT NOT NULL
        CHECK (input_type IN (
            'text',
            'voice',
            'image',
            'file',
            'callback',
            'document',
            'admin',
            'system'
        )),

    user_id UUID REFERENCES app_users(id) ON DELETE SET NULL,
    external_message_id TEXT,
    telegram_chat_id BIGINT,
    telegram_user_id BIGINT,

    raw_payload JSONB NOT NULL DEFAULT '{}'::jsonb,

    status TEXT NOT NULL DEFAULT 'received'
        CHECK (status IN ('received', 'processing', 'done', 'error', 'cancelled')),

    received_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_intake_events_execution_id
    ON intake_events(execution_id);

CREATE INDEX IF NOT EXISTS idx_intake_events_user_id
    ON intake_events(user_id);

CREATE INDEX IF NOT EXISTS idx_intake_events_status
    ON intake_events(status);

CREATE INDEX IF NOT EXISTS idx_intake_events_received_at
    ON intake_events(received_at);

CREATE UNIQUE INDEX IF NOT EXISTS uq_intake_telegram_message
    ON intake_events(source, telegram_chat_id, external_message_id)
    WHERE source = 'telegram'
      AND telegram_chat_id IS NOT NULL
      AND external_message_id IS NOT NULL;

-- Now that intake_events exists, attach links to existing logs/messages.
ALTER TABLE chat_messages
    ADD COLUMN IF NOT EXISTS intake_event_id UUID REFERENCES intake_events(id) ON DELETE SET NULL;

ALTER TABLE request_logs
    ADD COLUMN IF NOT EXISTS intake_event_id UUID REFERENCES intake_events(id) ON DELETE SET NULL;

ALTER TABLE error_logs
    ADD COLUMN IF NOT EXISTS intake_event_id UUID REFERENCES intake_events(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_chat_messages_intake_event_id
    ON chat_messages (intake_event_id);

CREATE INDEX IF NOT EXISTS idx_request_logs_intake_event_id
    ON request_logs (intake_event_id);

CREATE INDEX IF NOT EXISTS idx_error_logs_intake_event_id
    ON error_logs (intake_event_id);

-- ============================================================
-- 4. Document chunks metadata
-- ============================================================

CREATE TABLE IF NOT EXISTS document_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    document_version_id UUID NOT NULL REFERENCES document_versions(id) ON DELETE CASCADE,
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,

    chunk_index INTEGER NOT NULL,
    chunk_text_preview TEXT,
    token_count INTEGER,

    chroma_collection TEXT NOT NULL DEFAULT 'assistant_flow_documents',
    chroma_id TEXT NOT NULL,

    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (document_version_id, chunk_index),
    UNIQUE (chroma_collection, chroma_id)
);

CREATE INDEX IF NOT EXISTS idx_document_chunks_document_id
    ON document_chunks(document_id);

CREATE INDEX IF NOT EXISTS idx_document_chunks_document_version_id
    ON document_chunks(document_version_id);

-- ============================================================
-- 5. Processing logs and helper function
-- ============================================================

CREATE TABLE IF NOT EXISTS processing_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    execution_id TEXT NOT NULL,
    intake_event_id UUID REFERENCES intake_events(id) ON DELETE SET NULL,

    stage TEXT NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('success', 'error', 'skipped', 'retry', 'started')),

    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    error_text TEXT,
    attempt INTEGER NOT NULL DEFAULT 1,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_processing_logs_execution_id
    ON processing_logs(execution_id);

CREATE INDEX IF NOT EXISTS idx_processing_logs_intake_event_id
    ON processing_logs(intake_event_id);

CREATE INDEX IF NOT EXISTS idx_processing_logs_stage
    ON processing_logs(stage);

CREATE INDEX IF NOT EXISTS idx_processing_logs_created_at
    ON processing_logs(created_at);

CREATE OR REPLACE FUNCTION log_processing_event(
    p_execution_id TEXT,
    p_intake_event_id UUID,
    p_stage TEXT,
    p_status TEXT,
    p_details JSONB DEFAULT '{}'::jsonb,
    p_error_text TEXT DEFAULT NULL,
    p_attempt INTEGER DEFAULT 1
)
RETURNS VOID AS $$
BEGIN
    INSERT INTO processing_logs (
        execution_id,
        intake_event_id,
        stage,
        status,
        details,
        error_text,
        attempt
    )
    VALUES (
        COALESCE(NULLIF(p_execution_id, ''), 'unknown'),
        p_intake_event_id,
        p_stage,
        p_status,
        COALESCE(p_details, '{}'::jsonb),
        p_error_text,
        COALESCE(p_attempt, 1)
    );
END;
$$ LANGUAGE plpgsql;

-- ============================================================
-- 6. Outbox and generated assets
-- ============================================================

CREATE TABLE IF NOT EXISTS outbox (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    execution_id TEXT NOT NULL,
    intake_event_id UUID REFERENCES intake_events(id) ON DELETE SET NULL,
    user_id UUID REFERENCES app_users(id) ON DELETE SET NULL,

    channel TEXT NOT NULL
        CHECK (channel IN ('telegram', 'email', 'webhook', 'admin_ui')),

    recipient TEXT NOT NULL,

    message_type TEXT NOT NULL
        CHECK (message_type IN (
            'text',
            'rag_answer',
            'image',
            'voice',
            'error',
            'admin_notification',
            'system'
        )),

    subject TEXT,
    body TEXT NOT NULL DEFAULT '',
    reply_markup JSONB,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,

    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'sending', 'sent', 'error', 'cancelled')),

    attempt INTEGER NOT NULL DEFAULT 0,
    sent_at TIMESTAMPTZ,
    error_text TEXT,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_outbox_execution_id
    ON outbox(execution_id);

CREATE INDEX IF NOT EXISTS idx_outbox_intake_event_id
    ON outbox(intake_event_id);

CREATE INDEX IF NOT EXISTS idx_outbox_user_id
    ON outbox(user_id);

CREATE INDEX IF NOT EXISTS idx_outbox_status
    ON outbox(status);

CREATE INDEX IF NOT EXISTS idx_outbox_created_at
    ON outbox(created_at);

CREATE TABLE IF NOT EXISTS generated_assets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    execution_id TEXT NOT NULL,
    intake_event_id UUID REFERENCES intake_events(id) ON DELETE SET NULL,
    user_id UUID REFERENCES app_users(id) ON DELETE SET NULL,

    asset_type TEXT NOT NULL
        CHECK (asset_type IN ('image', 'audio', 'video', 'document_preview', 'other')),

    provider TEXT,
    model TEXT,
    prompt TEXT,

    asset_url TEXT,
    file_path TEXT,

    status TEXT NOT NULL DEFAULT 'created'
        CHECK (status IN ('created', 'sent', 'error', 'deleted')),

    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_generated_assets_execution_id
    ON generated_assets(execution_id);

CREATE INDEX IF NOT EXISTS idx_generated_assets_user_id
    ON generated_assets(user_id);

CREATE INDEX IF NOT EXISTS idx_generated_assets_type
    ON generated_assets(asset_type);

CREATE INDEX IF NOT EXISTS idx_generated_assets_created_at
    ON generated_assets(created_at);

-- ============================================================
-- 7. Admin audit and usage metrics
-- ============================================================

CREATE TABLE IF NOT EXISTS admin_audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    admin_user_id UUID REFERENCES app_users(id) ON DELETE SET NULL,
    execution_id TEXT,

    action TEXT NOT NULL,
    target_type TEXT,
    target_id UUID,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_admin_audit_log_admin_user_id
    ON admin_audit_log(admin_user_id);

CREATE INDEX IF NOT EXISTS idx_admin_audit_log_execution_id
    ON admin_audit_log(execution_id);

CREATE INDEX IF NOT EXISTS idx_admin_audit_log_action
    ON admin_audit_log(action);

CREATE INDEX IF NOT EXISTS idx_admin_audit_log_created_at
    ON admin_audit_log(created_at);

CREATE TABLE IF NOT EXISTS usage_metrics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    metric_date DATE NOT NULL DEFAULT CURRENT_DATE,
    metric_name TEXT NOT NULL,
    metric_value NUMERIC NOT NULL DEFAULT 0,
    dimensions JSONB NOT NULL DEFAULT '{}'::jsonb,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE(metric_date, metric_name, dimensions)
);

CREATE INDEX IF NOT EXISTS idx_usage_metrics_metric_date
    ON usage_metrics(metric_date);

CREATE INDEX IF NOT EXISTS idx_usage_metrics_metric_name
    ON usage_metrics(metric_name);

-- ============================================================
-- 8. Existing updated_at triggers: normalize idempotently
-- ============================================================

DROP TRIGGER IF EXISTS trg_app_users_updated_at ON app_users;
CREATE TRIGGER trg_app_users_updated_at
BEFORE UPDATE ON app_users
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_documents_updated_at ON documents;
CREATE TRIGGER trg_documents_updated_at
BEFORE UPDATE ON documents
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_chat_sessions_updated_at ON chat_sessions;
CREATE TRIGGER trg_chat_sessions_updated_at
BEFORE UPDATE ON chat_sessions
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

-- ============================================================
-- 9. Schema marker
-- ============================================================

INSERT INTO processing_logs (
    execution_id,
    stage,
    status,
    details,
    attempt
)
VALUES (
    'schema_v2_migration',
    'database_schema',
    'success',
    '{"schema":"assistant_flow_v2","migration":"002_runtime_lifecycle"}'::jsonb,
    1
);
