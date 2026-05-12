-- P6.10: key/value platform settings (active RAG backend, future flags).
-- Application reads `active_rag_backend`; absent row → env bootstrap default (no SQL seed of env).

CREATE TABLE IF NOT EXISTS platform_settings (
    key TEXT PRIMARY KEY,
    value_json JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_platform_settings_updated_at
    ON platform_settings (updated_at);
