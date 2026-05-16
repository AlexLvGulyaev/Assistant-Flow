#!/usr/bin/env python3
"""
Import recent RAG conversational interactions into one evaluation_run.

  docker exec portfolio-test-assistant-flow-1 python scripts/evaluation_import_recent.py \\
      --limit 5 --dataset interactive_eval_tmp
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    from dotenv import load_dotenv

    load_dotenv()
    p = argparse.ArgumentParser(description="Import recent RAG traces into evaluation_run")
    p.add_argument("--limit", type=int, default=5, help="Max rag_answer_done events")
    p.add_argument(
        "--dataset",
        default="interactive_eval_tmp",
        help="evaluation_dataset slug",
    )
    p.add_argument("--name", default=None)
    p.add_argument("--notes", default=None)
    args = p.parse_args()

    from services.evaluation_import_service import (
        import_interactions_to_run,
        list_recent_rag_execution_ids,
    )

    eids = list_recent_rag_execution_ids(limit=args.limit)
    if not eids:
        print("[evaluation-import] no recent rag_answer_done events found", file=sys.stderr)
        return 2

    try:
        run_id = import_interactions_to_run(
            execution_ids=eids,
            dataset_slug=args.dataset.strip(),
            run_name=args.name or f"interactive-recent-{len(eids)}",
            run_notes=args.notes,
        )
    except ValueError as exc:
        print(f"[evaluation-import] error: {exc}", file=sys.stderr)
        return 2

    print(f"[evaluation-import] run_id={run_id} imported={len(eids)}")
    for eid in eids:
        print(f"  - {eid}")
    print(
        "[evaluation-import] next: python scripts/evaluation_ragas.py run "
        f"--run-id {run_id}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
