#!/usr/bin/env python3
"""
Set manual.overall score (0 / 0.5 / 1) for one evaluation_item.

  docker exec portfolio-test-assistant-flow-1 python scripts/evaluation_score_item.py \\
      --item-id <uuid> --score 1
"""

from __future__ import annotations

import argparse
import sys
import uuid
from typing import Any
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    from dotenv import load_dotenv

    load_dotenv()
    p = argparse.ArgumentParser()
    p.add_argument("--item-id", required=True)
    p.add_argument("--score", type=float, required=True, choices=(0.0, 0.5, 1.0))
    args = p.parse_args()

    iid = uuid.UUID(args.item_id.strip())
    score = float(args.score)

    from repositories.connection import get_connection
    from repositories.evaluation_repository import EvaluationRepository
    from services.evaluation_service import compute_run_summary

    repo = EvaluationRepository()
    with get_connection() as conn:
        with conn.cursor(row_factory=None) as cur:
            cur.execute(
                "SELECT run_id FROM evaluation_item WHERE id = %s",
                (iid,),
            )
            row = cur.fetchone()
        if not row:
            print("item not found", file=sys.stderr)
            return 2
        run_id = row[0]
        if not isinstance(run_id, uuid.UUID):
            run_id = uuid.UUID(str(run_id))
        repo.upsert_metric(
            conn,
            run_id=run_id,
            item_id=iid,
            metric_key="manual.overall",
            metric_value_numeric=score,
            metric_value_json=None,
        )
        loaded = repo.list_items_for_run(conn, run_id=run_id)
        mids: dict[uuid.UUID, list[dict[str, Any]]] = {}
        for m in repo.list_metrics_for_run(conn, run_id=run_id):
            mid = m.get("item_id")
            if mid is None:
                continue
            if not isinstance(mid, uuid.UUID):
                mid = uuid.UUID(str(mid))
            mids.setdefault(mid, []).append(dict(m))
        summary = compute_run_summary(loaded, mids)
        repo.update_run_summary(conn, run_id=run_id, summary=summary)
        conn.commit()
    print(f"[evaluation] manual.overall={score} item_id={iid}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
