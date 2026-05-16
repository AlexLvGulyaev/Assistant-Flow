#!/usr/bin/env python3
"""
Import one real conversational interaction (by execution_id) into Evaluation Layer.

  docker exec portfolio-test-assistant-flow-1 python scripts/evaluation_import_session.py \\
      --execution-id <UUID> --dataset interactive_eval_tmp

Then score with existing RAGAS CLI (unchanged):

  docker exec portfolio-test-assistant-flow-1 python scripts/evaluation_ragas.py run \\
      --run-id <RUN_UUID>
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
    p = argparse.ArgumentParser(description="Import one execution_id into evaluation_run")
    p.add_argument("--execution-id", required=True, help="processing_logs.execution_id")
    p.add_argument(
        "--dataset",
        default="interactive_eval_tmp",
        help="evaluation_dataset slug (created if missing)",
    )
    p.add_argument("--name", default=None, help="evaluation_run.name")
    p.add_argument("--notes", default=None, help="evaluation_run.notes")
    args = p.parse_args()

    from services.evaluation_import_service import import_interactions_to_run

    try:
        run_id = import_interactions_to_run(
            execution_ids=[args.execution_id.strip()],
            dataset_slug=args.dataset.strip(),
            run_name=args.name,
            run_notes=args.notes,
        )
    except ValueError as exc:
        print(f"[evaluation-import] error: {exc}", file=sys.stderr)
        return 2

    print(f"[evaluation-import] run_id={run_id} execution_id={args.execution_id.strip()}")
    print(
        "[evaluation-import] next: python scripts/evaluation_ragas.py run "
        f"--run-id {run_id}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
