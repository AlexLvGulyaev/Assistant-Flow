-- P1-lite: Evaluation Layer — datasets, runs, items, sparse metric facts (manual + future ragas.*).

CREATE TABLE IF NOT EXISTS evaluation_dataset (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug TEXT NOT NULL,
    version INT NOT NULL DEFAULT 1,
    title TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (slug, version)
);

CREATE INDEX IF NOT EXISTS idx_evaluation_dataset_slug
    ON evaluation_dataset (slug);

CREATE TABLE IF NOT EXISTS evaluation_dataset_item (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dataset_id UUID NOT NULL REFERENCES evaluation_dataset (id) ON DELETE CASCADE,
    ordinal INT NOT NULL,
    query_text TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (dataset_id, ordinal)
);

CREATE INDEX IF NOT EXISTS idx_evaluation_dataset_item_dataset
    ON evaluation_dataset_item (dataset_id);

CREATE TABLE IF NOT EXISTS evaluation_run (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dataset_id UUID NOT NULL REFERENCES evaluation_dataset (id),
    dataset_version INT NOT NULL,
    name TEXT,
    notes TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    config_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    run_summary JSONB,
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_evaluation_run_dataset
    ON evaluation_run (dataset_id, dataset_version);

CREATE INDEX IF NOT EXISTS idx_evaluation_run_status
    ON evaluation_run (status);

CREATE TABLE IF NOT EXISTS evaluation_item (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL REFERENCES evaluation_run (id) ON DELETE CASCADE,
    dataset_item_id UUID REFERENCES evaluation_dataset_item (id) ON DELETE SET NULL,
    ordinal INT NOT NULL,
    query_text TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'ok',
    error_text TEXT,
    answer_text TEXT,
    retrieval_diag JSONB,
    generation_diag JSONB,
    latency_ms_total INT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (run_id, ordinal)
);

CREATE INDEX IF NOT EXISTS idx_evaluation_item_run
    ON evaluation_item (run_id);

CREATE TABLE IF NOT EXISTS evaluation_metric_fact (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID REFERENCES evaluation_run (id) ON DELETE CASCADE,
    item_id UUID REFERENCES evaluation_item (id) ON DELETE CASCADE,
    metric_key TEXT NOT NULL,
    metric_value_numeric DOUBLE PRECISION,
    metric_value_json JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_evaluation_metric_fact_item
    ON evaluation_metric_fact (item_id);

CREATE INDEX IF NOT EXISTS idx_evaluation_metric_fact_key
    ON evaluation_metric_fact (metric_key);

CREATE UNIQUE INDEX IF NOT EXISTS uq_evaluation_metric_item_key
    ON evaluation_metric_fact (item_id, metric_key)
    WHERE item_id IS NOT NULL;
