#!/usr/bin/env python3
"""
Аудит консистентности KB-контура Assistant Flow (долг №2: multi-version docs +
idempotent reindex). Read-only: ничего не удаляет и не пишет.

Сравнивает четыре плоскости:
  1. PostgreSQL каталог: documents / document_versions (is_active) / document_chunks;
  2. файлы в DOCUMENTS_DIR (data/documents);
  3. Chroma (assistant_flow_rag): чанки per source + document_id;
  4. Weaviate (AssistantFlowChunk): объекты per source.

Отчёт:
  - файлы без PG-документа (не проиндексированы / каталог разъехался);
  - PG-документы без файла (файл удалён мимо контура);
  - документы с >1 активной версией (нарушение lifecycle-контракта);
  - версии без чанков, но с indexed_at (неполная финализация);
  - sources в Chroma/Weaviate, которых нет в PG (orphan-векторы);
  - расхождение счётчиков чанков Chroma vs Weaviate vs PG per source.

Запуск (внутри контейнера admin-api):
  python scripts/index_consistency_check.py
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from utils.config import load_config  # noqa: E402

DOCUMENTS_DIR = Path("/app/data/documents")


def pg_catalog() -> dict:
    import psycopg
    from psycopg.rows import dict_row

    cfg = load_config()
    dsn = cfg.database_url or "postgresql://assistant:assistant@postgres:5432/assistant_flow"
    with psycopg.connect(dsn) as con, con.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT d.id, d.title, d.source_filename, d.status,
                   dv.id AS version_id, dv.version_number, dv.is_active,
                   dv.file_hash, dv.indexed_at, dv.chunk_count
            FROM documents d
            LEFT JOIN document_versions dv ON dv.document_id = d.id
            ORDER BY d.title, dv.version_number
            """
        )
        rows = [dict(r) for r in cur.fetchall()]
        cur.execute(
            """
            SELECT dv.document_id, dv.id AS version_id, count(dc.id) AS chunks
            FROM document_versions dv
            LEFT JOIN document_chunks dc ON dc.document_version_id = dv.id
            GROUP BY dv.document_id, dv.id
            """
        )
        chunk_rows = {r["version_id"]: r["chunks"] for r in cur.fetchall()}
    docs = {}
    for r in rows:
        d = docs.setdefault(
            r["id"],
            {
                "title": r["title"],
                "source_filename": r["source_filename"],
                "status": r["status"],
                "versions": [],
            },
        )
        d["versions"].append(r)
    return {"docs": docs, "chunks_per_version": chunk_rows}


def chroma_sources() -> tuple[Counter, Counter]:
    import chromadb

    cfg = load_config()
    client = chromadb.HttpClient(host=cfg.chroma_host, port=cfg.chroma_port)
    col = client.get_collection("assistant_flow_rag")
    got = col.get(include=["metadatas"])
    by_source: Counter = Counter()
    by_doc: Counter = Counter()
    for m in got["metadatas"]:
        by_source[m.get("source") or "?"] += 1
        by_doc[m.get("document_id") or "?"] += 1
    return by_source, by_doc


def weaviate_sources() -> Counter:
    import json
    import urllib.request

    cfg = load_config()
    host = f"http://{cfg.weaviate_host}:{cfg.weaviate_http_port}"
    cls = cfg.weaviate_class_name or "AssistantFlowChunk"
    q = f'{{ Aggregate {{ {cls}(groupBy: "source") {{ groupedBy {{ value }} meta {{ count }} }} }} }}'
    req = urllib.request.Request(
        host + "/v1/graphql",
        data=json.dumps({"query": q}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    d = json.loads(urllib.request.urlopen(req, timeout=30).read().decode())
    rows = d["data"]["Aggregate"][cls]
    return Counter({r["groupedBy"]["value"]: r["meta"]["count"] for r in rows})


def main() -> int:
    cat = pg_catalog()
    ch_by_source, ch_by_doc = chroma_sources()
    wv_by_source = weaviate_sources()

    pg_filenames = {d["source_filename"] for d in cat["docs"].values()}
    files = {p.name for p in DOCUMENTS_DIR.iterdir() if p.is_file()}

    problems: list[str] = []

    files_no_pg = files - pg_filenames
    pg_no_files = pg_filenames - files
    if files_no_pg:
        problems.append(f"файлы без PG-документа: {sorted(files_no_pg)}")
    if pg_no_files:
        problems.append(f"PG-документы без файла: {sorted(pg_no_files)}")

    for doc_id, d in cat["docs"].items():
        active = [v for v in d["versions"] if v["is_active"]]
        if len(active) > 1:
            problems.append(
                f"{d['title']}: {len(active)} активных версий (lifecycle-контракт нарушен)"
            )
        for v in d["versions"]:
            n_chunks = cat["chunks_per_version"].get(v["version_id"], 0)
            if v["is_active"] and v["indexed_at"] is not None and n_chunks == 0:
                problems.append(f"{d['title']} v{v['version_number']}: indexed_at без чанков")
            if not v["is_active"] and n_chunks > 0:
                problems.append(
                    f"{d['title']} v{v['version_number']}: неактивная версия с {n_chunks} чанками"
                )

    pg_sources = {d["source_filename"]: d for d in cat["docs"].values()}
    ch_orphans = set(ch_by_source) - set(pg_sources)
    wv_orphans = set(wv_by_source) - set(pg_sources)
    if ch_orphans:
        problems.append(f"orphan-sources в Chroma (нет в PG): {sorted(ch_orphans)}")
    if wv_orphans:
        problems.append(f"orphan-sources в Weaviate (нет в PG): {sorted(wv_orphans)}")

    all_sources = set(pg_sources) | set(ch_by_source) | set(wv_by_source)
    drift = []
    for s in sorted(all_sources):
        pg_doc = pg_sources.get(s)
        active_chunks = 0
        if pg_doc:
            active_chunks = sum(
                cat["chunks_per_version"].get(v["version_id"], 0)
                for v in pg_doc["versions"]
                if v["is_active"]
            )
        c_n, w_n = ch_by_source.get(s, 0), wv_by_source.get(s, 0)
        if not (active_chunks == c_n == w_n):
            drift.append(f"  {s}: pg={active_chunks} chroma={c_n} weaviate={w_n}")
    if drift:
        problems.append("расхождение счётчиков pg/chroma/weaviate:\n" + "\n".join(drift))

    total_active = sum(
        cat["chunks_per_version"].get(v["version_id"], 0)
        for d in cat["docs"].values()
        for v in d["versions"]
        if v["is_active"]
    )
    print(f"PG документов: {len(cat['docs'])}; активных чанков в PG: {total_active}")
    print(f"Chroma: {sum(ch_by_source.values())} чанков / {len(ch_by_source)} sources")
    print(f"Weaviate: {sum(wv_by_source.values())} объектов / {len(wv_by_source)} sources")

    if problems:
        print("\nПРОБЛЕМЫ:")
        for p in problems:
            print(f" - {p}")
        return 1
    print("\nOK: контур консистентен (PG ↔ файлы ↔ Chroma ↔ Weaviate).")
    return 0


if __name__ == "__main__":
    sys.exit(main())