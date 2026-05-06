-- Active vs historical document versions (metrics only on active rows).

ALTER TABLE document_versions
    ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT true;

-- Оставить активной только строку с максимальным version_number по каждому document_id.
WITH ranked AS (
    SELECT
        id,
        ROW_NUMBER() OVER (
            PARTITION BY document_id ORDER BY version_number DESC
        ) AS rn
    FROM document_versions
)
UPDATE document_versions dv
SET is_active = (ranked.rn = 1)
FROM ranked
WHERE dv.id = ranked.id;

CREATE UNIQUE INDEX IF NOT EXISTS ux_document_versions_one_active_per_doc
    ON document_versions (document_id)
    WHERE is_active;

COMMENT ON COLUMN document_versions.is_active IS
    'Текущая проиндексированная версия документа; исторические версии — false. '
    'Сумма chunk_count для метрик считается только по is_active = true.';
