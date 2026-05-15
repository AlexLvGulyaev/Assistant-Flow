#!/usr/bin/env python3
"""
Create or execute evaluation runs (P1-lite).

  docker exec portfolio-test-assistant-flow-1 python scripts/evaluation_run.py create \\
      --dataset p1_lite_ru_baseline_v1 --top-k 3 --name top3

  docker exec portfolio-test-assistant-flow-1 python scripts/evaluation_run.py execute --run-id <uuid>

  docker exec portfolio-test-assistant-flow-1 python scripts/evaluation_run.py run \\
      --dataset p1_lite_ru_baseline_v1 --top-k 5 --name top5
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    from dotenv import load_dotenv

    load_dotenv()

    p = argparse.ArgumentParser(description="Evaluation P1-lite runs")
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("create", help="Insert evaluation_run (pending)")
    c.add_argument("--dataset", required=True, help="Dataset slug")
    c.add_argument("--dataset-version", type=int, default=None)
    c.add_argument("--top-k", type=int, required=True)
    c.add_argument("--name", default=None)
    c.add_argument("--notes", default=None)
    c.add_argument(
        "--backend-note",
        default=None,
        help="Opaque label stored in config_snapshot (does not switch runtime backend)",
    )

    e = sub.add_parser("execute", help="Run pending evaluation_run")
    e.add_argument("--run-id", required=True)

    r = sub.add_parser("run", help="create + execute in one step")
    r.add_argument("--dataset", required=True)
    r.add_argument("--dataset-version", type=int, default=None)
    r.add_argument("--top-k", type=int, required=True)
    r.add_argument("--name", default=None)
    r.add_argument("--notes", default=None)
    r.add_argument("--backend-note", default=None)

    args = p.parse_args()

    from repositories.connection import get_connection
    from repositories.evaluation_repository import EvaluationRepository
    from services.evaluation_service import execute_run

    repo = EvaluationRepository()

    def do_create(
        *,
        dataset_slug: str,
        dataset_version: int | None,
        top_k: int,
        name: str | None,
        notes: str | None,
        backend_note: str | None,
    ) -> uuid.UUID:
        with get_connection() as conn:
            ds = repo.get_dataset_by_slug(
                conn, slug=dataset_slug, version=dataset_version
            )
            if not ds:
                raise SystemExit(f"dataset not found: {dataset_slug} v={dataset_version}")
            ver = int(ds["version"])
            snap = {
                "top_k": int(top_k),
                "retrieval_backend_note": (backend_note or "").strip() or None,
            }
            rid = repo.insert_run(
                conn,
                dataset_id=ds["id"],
                dataset_version=ver,
                name=name,
                notes=notes,
                config_snapshot=snap,
                status="pending",
            )
            conn.commit()
            return rid

    if args.cmd == "create":
        rid = do_create(
            dataset_slug=args.dataset,
            dataset_version=args.dataset_version,
            top_k=args.top_k,
            name=args.name,
            notes=args.notes,
            backend_note=args.backend_note,
        )
        print(str(rid))
        return 0

    if args.cmd == "execute":
        rid = uuid.UUID(args.run_id.strip())
        summary = execute_run(rid)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0

    if args.cmd == "run":
        rid = do_create(
            dataset_slug=args.dataset,
            dataset_version=args.dataset_version,
            top_k=args.top_k,
            name=args.name,
            notes=args.notes,
            backend_note=args.backend_note,
        )
        print(f"[evaluation] created run_id={rid}", flush=True)
        summary = execute_run(rid)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
