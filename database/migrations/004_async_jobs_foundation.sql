-- Async processing foundation (P5.3a)
-- Queue/job table only. No runtime behavior changes in this migration.

CREATE TABLE IF NOT EXISTS async_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued'
        CHECK (status IN (
            'queued',
            'running',
            'succeeded',
            'failed',
            'retry_scheduled',
            'cancelled'
        )),

    payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    result_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    error_json JSONB NOT NULL DEFAULT '{}'::jsonb,

    attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    max_attempts INTEGER NOT NULL DEFAULT 3 CHECK (max_attempts >= 1),

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_async_jobs_status
    ON async_jobs (status);

CREATE INDEX IF NOT EXISTS idx_async_jobs_created_at
    ON async_jobs (created_at);

CREATE INDEX IF NOT EXISTS idx_async_jobs_claim
    ON async_jobs (status, created_at)
    WHERE status IN ('queued', 'retry_scheduled');

CREATE INDEX IF NOT EXISTS idx_async_jobs_type_status
    ON async_jobs (job_type, status);

CREATE OR REPLACE FUNCTION set_async_jobs_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_async_jobs_updated_at ON async_jobs;
CREATE TRIGGER trg_async_jobs_updated_at
BEFORE UPDATE ON async_jobs
FOR EACH ROW
EXECUTE FUNCTION set_async_jobs_updated_at();
