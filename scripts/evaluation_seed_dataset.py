#!/usr/bin/env python3
"""
Seed P1-lite evaluation dataset (Russian RAG / conversational-style queries).

  docker exec portfolio-test-assistant-flow-1 python scripts/evaluation_seed_dataset.py

Requires DATABASE_URL and applied migration 006_evaluation_p1_lite.sql.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DATASET_SLUG = "p1_lite_ru_baseline_v1"
VERSION = 1
TITLE = "P1-lite RU baseline (top_k comparison)"

QUERIES_RU: list[str] = [
    "Что такое Assistant Flow и для чего он используется?",
    "Как устроена индексация документов для RAG в этом проекте?",
    "В чём разница между retrieval backend Chroma и FAISS на уровне оператора?",
    "Сколько вопросов о системе я могу задать подряд без потери контекста?",
    "Там — это где? (краткий follow-up без явного объекта)",
    "Какие метрики latency и токенов обычно пишутся в RAG diagnostics?",
    "Что делать, если retrieval вернул пустой результат, а в индексе документы есть?",
]


def main() -> int:
    from dotenv import load_dotenv

    load_dotenv()
    from repositories.connection import get_connection
    from repositories.evaluation_repository import EvaluationRepository

    repo = EvaluationRepository()
    with get_connection() as conn:
        did = repo.insert_dataset(
            conn,
            slug=DATASET_SLUG,
            version=VERSION,
            title=TITLE,
            metadata={"kind": "p1_lite_seed", "locale": "ru"},
        )
        for i, q in enumerate(QUERIES_RU, start=1):
            repo.insert_dataset_item(
                conn, dataset_id=did, ordinal=i, query_text=q, metadata={}
            )
        conn.commit()
    print(f"[evaluation] seeded dataset slug={DATASET_SLUG} version={VERSION} id={did}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
