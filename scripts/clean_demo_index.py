#!/usr/bin/env python3
"""
Hygiene живого демо-индекса Assistant Flow (закрытие долга 04.09, ч.1).

Удаляет тест-фикстуры и не-демо документы из ОБОИХ хранилищ (Chroma —
операционный backend, Weaviate — secondary) и из каталога PostgreSQL
(documents/document_versions/document_chunks).

Идемпотентен: повторный запуск ничего не находит и ничего не меняет.

По умолчанию DRY-RUN (только отчёт). Фактическое удаление — ``--apply``.

Целевые документы:
  - dirty_test_* (7)          — тест-фикстуры мая, попали в демо-индекс;
  - cooking_recipes           — out-of-domain тестовый документ («рецепт пасты»);
  - candidate_scoring         — HR-тестовый документ;
  - ragas_facts_baseline      — синтетический «ООО НоваТех» (решение владельца
                                02.09: из индекса убрать). Канонический файл —
                                evaluation/datasets/ragas_facts_baseline.txt
                                (gitignore на data/ исключает его из
                                data/documents); для RAGAS-оценки временно
                                копируется в data/documents, после оценки
                                чистка возвращает индекс в демо-состояние.

Оставляются сознательно (НЕ цели):
  - p9_6b_restricted_handbook — protected/restricted демо P9.6b visibility;
  - прочие легитимные демо-документы (it_ai_glossary_large и т.д.).

Запуск (внутри контейнера admin-api):
  python scripts/clean_demo_index.py            # dry-run
  python scripts/clean_demo_index.py --apply    # фактическая чистка
"""

from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Имена (documents.title в PG = source в Chroma/Weaviate). Порядок значения не имеет.
TARGET_TITLES: list[str] = [
    "dirty_test_policy",
    "dirty_test_regulation",
    "dirty_test_policy_v2",
    "dirty_test_regulation_v2.txt",
    "dirty_test_af_regulation",
    "dirty_test_af_regulation_cyrillic",
    "dirty_test_af_regulation_cyrillic_v2",
    "cooking_recipes",
    "candidate_scoring",
    "ragas_facts_baseline",
]

# Канонический ragas_facts_baseline.txt лежит в evaluation/datasets/ (data/
# в gitignore). Если его временно копировали в data/documents под RAGAS-оценку,
# чистка обязана удалить копию — потому KEEP_FILES пуст.
KEEP_FILES: set[str] = set()

DOCUMENTS_DIR = Path("/app/data/documents")


def load_targets_from_pg() -> list[dict]:
    """Сопоставляет целевые имена с каталогом PG; возвращает rows с id/версиями."""
    import psycopg
    from psycopg.rows import dict_row
    from utils.config import load_config

    cfg = load_config()
    dsn = cfg.database_url or "postgresql://assistant:assistant@postgres:5432/assistant_flow"
    with psycopg.connect(dsn) as con, con.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT d.id, d.title, d.source_filename, d.status,
                   array_agg(dv.id) AS version_ids
            FROM documents d
            LEFT JOIN document_versions dv ON dv.document_id = d.id
            WHERE d.title = ANY(%s)
            GROUP BY d.id, d.title, d.source_filename, d.status
            ORDER BY d.title
            """,
            (TARGET_TITLES,),
        )
        return [dict(r) for r in cur.fetchall()]


def clean_chroma(document_ids: list[str]) -> int:
    """Удаляет чанки по document_id; возвращает число удалённых id."""
    import chromadb
    from utils.config import load_config

    cfg = load_config()
    client = chromadb.HttpClient(host=cfg.chroma_host, port=cfg.chroma_port)
    removed_total = 0
    for name in client.list_collections():
        col = client.get_collection(name.name)
        for doc_id in document_ids:
            got = col.get(where={"document_id": doc_id}, include=[])
            ids = got.get("ids") or []
            if ids:
                col.delete(where={"document_id": doc_id})
                removed_total += len(ids)
                print(f"  chroma[{name.name}]: deleted {len(ids)} chunks for {doc_id}")
    return removed_total


def clean_weaviate(document_ids: list[str], source_filename: str) -> int:
    """Удаляет векторы документа из Weaviate (BYOV backend, delete_many)."""
    from utils.config import load_config
    from services.retrieval.weaviate_backend import WeaviateBackend

    class _NoEmbed:  # delete-контур embeddings не использует
        def embed_documents(self, texts):  # pragma: no cover
            return [[0.0] * 8 for _ in texts]

        def embed_query(self, text):  # pragma: no cover
            return [0.0] * 8

    cfg = load_config()
    backend = WeaviateBackend(config=cfg, embeddings=_NoEmbed())
    before = backend.collection_count()
    for doc_id in document_ids:
        backend.delete_vectors_for_document_before_reindex(
            document_id=uuid.UUID(doc_id), source_filename=source_filename
        )
    after = backend.collection_count()
    backend.close()
    removed = max(0, before - after)
    if removed:
        print(f"  weaviate: deleted {removed} objects for {source_filename}")
    return removed


def clean_pg(document_ids: list[uuid.UUID]) -> int:
    """Удаляет каталог документа из PG: chunks → versions → document."""
    import psycopg
    from utils.config import load_config

    cfg = load_config()
    dsn = cfg.database_url or "postgresql://assistant:assistant@postgres:5432/assistant_flow"
    with psycopg.connect(dsn) as con, con.cursor() as cur:
        removed = 0
        for doc_id in document_ids:
            cur.execute(
                """
                DELETE FROM document_chunks
                WHERE document_version_id IN (
                    SELECT id FROM document_versions WHERE document_id = %s
                )
                """,
                (doc_id,),
            )
            chunks = cur.rowcount
            cur.execute("DELETE FROM document_versions WHERE document_id = %s", (doc_id,))
            versions = cur.rowcount
            cur.execute("DELETE FROM documents WHERE id = %s", (doc_id,))
            if cur.rowcount:
                removed += 1
                print(f"  pg: document {doc_id} removed (versions={versions}, chunks={chunks})")
        con.commit()
    return removed


def purge_files(source_filenames: list[str]) -> int:
    """Удаляет файлы целей из data/documents (кроме KEEP_FILES)."""
    removed = 0
    for fn in source_filenames:
        if not fn or fn in KEEP_FILES:
            continue
        path = DOCUMENTS_DIR / fn
        if path.exists():
            path.unlink()
            removed += 1
            print(f"  fs: removed {path}")
    return removed


def main() -> int:
    parser = argparse.ArgumentParser(description="AF demo index hygiene")
    parser.add_argument("--apply", action="store_true", help="фактическое удаление (по умолчанию dry-run)")
    args = parser.parse_args()

    targets = load_targets_from_pg()
    found = {t["title"] for t in targets}
    missing = [t for t in TARGET_TITLES if t not in found]
    print(f"targets in PG catalog: {len(targets)}; not found: {missing or '—'}")

    document_ids = [str(t["id"]) for t in targets]
    filenames = [t["source_filename"] for t in targets]

    print("\n== DRY-RUN == " if not args.apply else "\n== APPLY ==")
    print(f"documents: {len(targets)}, chroma ids: {len(document_ids)}")

    if args.apply:
        c = clean_chroma(document_ids)
        w = sum(
            clean_weaviate([str(t["id"])], t["source_filename"] or t["title"])
            for t in targets
        )
        p = clean_pg([uuid.UUID(i) for i in document_ids])
        f = purge_files(filenames)
        print(f"\nremoved: chroma={c}, weaviate={w}, pg_documents={p}, files={f}")
    else:
        print("dry-run: chroma/weaviate/pg/fs cleanup skipped (use --apply)")

    print("\nПроверка после чистки: перезапустите скрипт — 'not found' должен перечислить все цели.")
    return 0


if __name__ == "__main__":
    sys.exit(main())