-- database/schema.sql
-- Assistant Flow / Career Knowledge Assistant
-- PostgreSQL schema v2 (итоговое состояние после migrations, включая 005_platform_settings)

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ----------------------------
-- updated_at helper (используется триггерами ниже)
-- ----------------------------

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ----------------------------
-- Users and access
-- ----------------------------

CREATE TABLE IF NOT EXISTS app_users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    telegram_user_id BIGINT UNIQUE NOT NULL,
    telegram_chat_id BIGINT,
    username TEXT,
    first_name TEXT,
    last_name TEXT,

    role TEXT NOT NULL DEFAULT 'user'
        CHECK (role IN ('user', 'admin')),

    is_active BOOLEAN NOT NULL DEFAULT TRUE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_app_users_telegram_user_id
    ON app_users (telegram_user_id);

CREATE INDEX IF NOT EXISTS idx_app_users_role
    ON app_users (role);


-- ----------------------------
-- Knowledge base documents
-- ----------------------------

CREATE TABLE IF NOT EXISTS documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    title TEXT NOT NULL,
    source_filename TEXT NOT NULL,
    storage_path TEXT NOT NULL,

    content_type TEXT,
    description TEXT,

    status TEXT NOT NULL DEFAULT 'uploaded'
        CHECK (status IN (
            'uploaded',
            'indexing',
            'indexed',
            'failed',
            'archived',
            'deleted'
        )),

    uploaded_by UUID REFERENCES app_users(id) ON DELETE SET NULL,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_documents_status
    ON documents (status);

CREATE INDEX IF NOT EXISTS idx_documents_uploaded_by
    ON documents (uploaded_by);


-- ----------------------------
-- Document versions
-- ----------------------------

CREATE TABLE IF NOT EXISTS document_versions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,

    version_number INTEGER NOT NULL,
    storage_path TEXT NOT NULL,
    file_hash TEXT,

    indexed_at TIMESTAMPTZ,
    chunk_count INTEGER NOT NULL DEFAULT 0,

    is_active BOOLEAN NOT NULL DEFAULT true,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (document_id, version_number)
);

CREATE INDEX IF NOT EXISTS idx_document_versions_document_id
    ON document_versions (document_id);

CREATE UNIQUE INDEX IF NOT EXISTS ux_document_versions_one_active_per_doc
    ON document_versions (document_id)
    WHERE is_active;

COMMENT ON COLUMN document_versions.is_active IS
    'Текущая проиндексированная версия документа; исторические версии — false. '
    'Сумма chunk_count для метрик считается только по is_active = true.';


-- ----------------------------
-- Chat sessions
-- ----------------------------

CREATE TABLE IF NOT EXISTS chat_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    user_id UUID NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,

    mode TEXT NOT NULL DEFAULT 'text'
        CHECK (mode IN ('text', 'rag', 'voice', 'image', 'career', 'hr_screening')),

    is_active BOOLEAN NOT NULL DEFAULT TRUE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_chat_sessions_user_id
    ON chat_sessions (user_id);

CREATE INDEX IF NOT EXISTS idx_chat_sessions_mode
    ON chat_sessions (mode);


-- ----------------------------
-- User preferences
-- ----------------------------

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


-- ----------------------------
-- Intake events (входящие события / трассировка)
-- ----------------------------

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


-- ----------------------------
-- Chat messages
-- ----------------------------

CREATE TABLE IF NOT EXISTS chat_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    session_id UUID NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,

    role TEXT NOT NULL
        CHECK (role IN ('user', 'assistant', 'system')),

    content TEXT NOT NULL,

    modality TEXT NOT NULL DEFAULT 'text'
        CHECK (modality IN ('text', 'voice', 'image', 'file')),

    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,

    execution_id TEXT,
    intake_event_id UUID REFERENCES intake_events(id) ON DELETE SET NULL,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_chat_messages_session_id
    ON chat_messages (session_id);

CREATE INDEX IF NOT EXISTS idx_chat_messages_user_id
    ON chat_messages (user_id);

CREATE INDEX IF NOT EXISTS idx_chat_messages_created_at
    ON chat_messages (created_at);

CREATE INDEX IF NOT EXISTS idx_chat_messages_execution_id
    ON chat_messages (execution_id);

CREATE INDEX IF NOT EXISTS idx_chat_messages_intake_event_id
    ON chat_messages (intake_event_id);


-- ----------------------------
-- Document chunks (метаданные чанков; векторы в ChromaDB)
-- ----------------------------

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


-- ----------------------------
-- Indexing jobs
-- ----------------------------

CREATE TABLE IF NOT EXISTS indexing_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    document_version_id UUID REFERENCES document_versions(id) ON DELETE SET NULL,

    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN (
            'pending',
            'running',
            'completed',
            'failed',
            'cancelled'
        )),

    error_text TEXT,

    execution_id TEXT,
    triggered_by UUID REFERENCES app_users(id) ON DELETE SET NULL,
    job_type TEXT NOT NULL DEFAULT 'index'
        CHECK (job_type IN ('index', 'reindex', 'delete_from_index', 'sync')),
    stats JSONB NOT NULL DEFAULT '{}'::jsonb,

    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_indexing_jobs_status
    ON indexing_jobs (status);

CREATE INDEX IF NOT EXISTS idx_indexing_jobs_document_id
    ON indexing_jobs (document_id);

CREATE INDEX IF NOT EXISTS idx_indexing_jobs_execution_id
    ON indexing_jobs (execution_id);

CREATE INDEX IF NOT EXISTS idx_indexing_jobs_triggered_by
    ON indexing_jobs (triggered_by);


-- ----------------------------
-- Request logs
-- ----------------------------

CREATE TABLE IF NOT EXISTS request_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    user_id UUID REFERENCES app_users(id) ON DELETE SET NULL,
    session_id UUID REFERENCES chat_sessions(id) ON DELETE SET NULL,

    request_type TEXT NOT NULL
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
        )),

    provider TEXT,
    model TEXT,

    input_tokens INTEGER,
    output_tokens INTEGER,

    latency_ms INTEGER,
    success BOOLEAN NOT NULL DEFAULT TRUE,

    execution_id TEXT,
    estimated_cost NUMERIC(12, 6),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    intake_event_id UUID REFERENCES intake_events(id) ON DELETE SET NULL,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_request_logs_user_id
    ON request_logs (user_id);

CREATE INDEX IF NOT EXISTS idx_request_logs_request_type
    ON request_logs (request_type);

CREATE INDEX IF NOT EXISTS idx_request_logs_created_at
    ON request_logs (created_at);

CREATE INDEX IF NOT EXISTS idx_request_logs_execution_id
    ON request_logs (execution_id);

CREATE INDEX IF NOT EXISTS idx_request_logs_intake_event_id
    ON request_logs (intake_event_id);


-- ----------------------------
-- Error logs
-- ----------------------------

CREATE TABLE IF NOT EXISTS error_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    user_id UUID REFERENCES app_users(id) ON DELETE SET NULL,
    session_id UUID REFERENCES chat_sessions(id) ON DELETE SET NULL,

    component TEXT NOT NULL,
    operation TEXT NOT NULL,

    error_type TEXT,
    error_message TEXT NOT NULL,
    traceback TEXT,

    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,

    execution_id TEXT,
    severity TEXT NOT NULL DEFAULT 'error'
        CHECK (severity IN ('debug', 'info', 'warning', 'error', 'critical')),
    is_recoverable BOOLEAN,
    resolved_at TIMESTAMPTZ,
    intake_event_id UUID REFERENCES intake_events(id) ON DELETE SET NULL,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_error_logs_component
    ON error_logs (component);

CREATE INDEX IF NOT EXISTS idx_error_logs_created_at
    ON error_logs (created_at);

CREATE INDEX IF NOT EXISTS idx_error_logs_execution_id
    ON error_logs (execution_id);

CREATE INDEX IF NOT EXISTS idx_error_logs_severity
    ON error_logs (severity);

CREATE INDEX IF NOT EXISTS idx_error_logs_intake_event_id
    ON error_logs (intake_event_id);


-- ----------------------------
-- Processing logs
-- ----------------------------

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
    ON processing_logs (execution_id);

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


-- ----------------------------
-- Outbox (исходящие сообщения)
-- ----------------------------

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


-- ----------------------------
-- Generated assets
-- ----------------------------

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


-- ----------------------------
-- Platform settings (P6.10)
-- ----------------------------

CREATE TABLE IF NOT EXISTS platform_settings (
    key TEXT PRIMARY KEY,
    value_json JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_platform_settings_updated_at
    ON platform_settings (updated_at);


-- ----------------------------
-- Admin audit log
-- ----------------------------

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


-- ----------------------------
-- Usage metrics
-- ----------------------------

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


-- ----------------------------
-- updated_at triggers
-- ----------------------------

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

DROP TRIGGER IF EXISTS trg_user_preferences_updated_at ON user_preferences;
CREATE TRIGGER trg_user_preferences_updated_at
BEFORE UPDATE ON user_preferences
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();
