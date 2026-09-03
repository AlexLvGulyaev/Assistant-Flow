#!/usr/bin/env python3
"""
Seed RAGAS baseline evaluation dataset (isolated from P1-lite AF corpus).

  docker exec portfolio-test-assistant-flow-1 python scripts/evaluation_seed_ragas_dataset.py

Knowledge file: evaluation/datasets/ragas_facts_baseline.txt.
Он сознательно НЕ лежит в data/documents (чтобы файловые индексаторы не тащили
«НоваТех» в живой демо-индекс). Процедура RAGAS-оценки:
  1) docker cp evaluation/datasets/ragas_facts_baseline.txt <admin-api>:/app/data/documents/
  2) проиндексировать файл через admin (Documents → reindex)
  3) выполнить оценку; 4) вернуть индекс в демо-состояние: python scripts/clean_demo_index.py --apply
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DATASET_SLUG = "ragas_baseline_ru_v1"
VERSION = 1
TITLE = "RAGAS baseline RU (NovaTech facts, isolated corpus)"
KNOWLEDGE_FILE = "ragas_facts_baseline.txt"

# 2 exact_fact, 2 paraphrase, 1 no_answer
DATASET_ITEMS: list[dict[str, Any]] = [
    {
        "ordinal": 1,
        "query_text": "Когда была зарегистрирована компания ООО «НоваТех»?",
        "metadata": {
            "question_type": "exact_fact",
            "ground_truth": "14 марта 2019 года (2019-03-14).",
        },
    },
    {
        "ordinal": 2,
        "query_text": "Кто является генеральным директором НоваТех с января 2022 года?",
        "metadata": {
            "question_type": "exact_fact",
            "ground_truth": "Елена Викторовна Соколова (с 10 января 2022 года).",
        },
    },
    {
        "ordinal": 3,
        "query_text": "Сколько часов даётся на первый ответ службы поддержки по тарифу Премиум?",
        "metadata": {
            "question_type": "paraphrase",
            "ground_truth": "Не более 4 часов, круглосуточно включая выходные.",
            "paraphrase_of": "SLA Премиум: время первого ответа",
        },
    },
    {
        "ordinal": 4,
        "query_text": "Какое максимальное число пользователей допускается на одну корпоративную лицензию NovaBoard?",
        "metadata": {
            "question_type": "paraphrase",
            "ground_truth": "50 учётных записей на одну корпоративную лицензию.",
            "paraphrase_of": "лимит пользователей лицензии",
        },
    },
    {
        "ordinal": 5,
        "query_text": "Какой тикер акций НоваТех на бирже NASDAQ и текущая котировка?",
        "metadata": {
            "question_type": "no_answer",
            "ground_truth": "",
            "expects_no_answer": True,
        },
    },
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
            metadata={
                "kind": "ragas_baseline",
                "locale": "ru",
                "knowledge_file": KNOWLEDGE_FILE,
                "isolated_corpus": True,
            },
        )
        for row in DATASET_ITEMS:
            repo.insert_dataset_item(
                conn,
                dataset_id=did,
                ordinal=int(row["ordinal"]),
                query_text=str(row["query_text"]),
                metadata=dict(row["metadata"]),
            )
        conn.commit()
    print(
        f"[evaluation] seeded RAGAS dataset slug={DATASET_SLUG} version={VERSION} "
        f"id={did} items={len(DATASET_ITEMS)} knowledge_file={KNOWLEDGE_FILE}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
