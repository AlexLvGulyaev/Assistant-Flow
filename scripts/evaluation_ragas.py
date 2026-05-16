#!/usr/bin/env python3
"""
RAGAS evaluation for completed Assistant Flow evaluation runs (offline).

  docker exec portfolio-test-assistant-flow-1 python scripts/evaluation_ragas.py check-deps
  docker exec portfolio-test-assistant-flow-1 pip install -r requirements-ragas.txt
  docker exec portfolio-test-assistant-flow-1 python scripts/evaluation_ragas.py run --run-id <uuid>
  docker exec portfolio-test-assistant-flow-1 python scripts/evaluation_ragas.py show-metrics --run-id <uuid>
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


def cmd_check_deps() -> int:
    from services.evaluation.ragas_adapter import check_ragas_dependencies

    dep = check_ragas_dependencies()
    print(json.dumps(dep, ensure_ascii=False, indent=2))
    if dep.get("ready"):
        print("[evaluation-ragas] dependencies OK", flush=True)
        return 0
    print(
        "[evaluation-ragas] install: pip install -r requirements-ragas.txt",
        file=sys.stderr,
        flush=True,
    )
    return 1


def cmd_run(run_id: uuid.UUID) -> int:
    from services.evaluation_ragas_service import execute_ragas_for_run

    out = execute_ragas_for_run(run_id)
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    status = (out.get("ragas") or {}).get("status")
    return 0 if status in ("ok", "partial") else 2


def cmd_show_metrics(run_id: uuid.UUID) -> int:
    from repositories.connection import get_connection
    from repositories.evaluation_repository import EvaluationRepository

    repo = EvaluationRepository()
    with get_connection() as conn:
        run = repo.get_run(conn, run_id=run_id)
        if not run:
            print("run not found", file=sys.stderr)
            return 2
        metrics = repo.list_metrics_for_run(conn, run_id=run_id)
        items = repo.list_items_for_run(conn, run_id=run_id)

    ragas_metrics = [m for m in metrics if str(m.get("metric_key", "")).startswith("ragas.")]
    print(f"run_id={run_id} status={run.get('status')} name={run.get('name')}")
    print(f"items={len(items)} ragas_metric_facts={len(ragas_metrics)}")
    if run.get("run_summary"):
        rs = run["run_summary"]
        if isinstance(rs, str):
            rs = json.loads(rs)
        ragas_summary = (rs or {}).get("ragas")
        if ragas_summary:
            print("\nrun_summary.ragas:")
            print(json.dumps(ragas_summary, ensure_ascii=False, indent=2))

    print("\n| ordinal | metric_key | value | status |")
    print("|---------|------------|-------|--------|")
    ord_by_item = {str(it["id"]): int(it["ordinal"]) for it in items}
    for m in sorted(
        ragas_metrics,
        key=lambda x: (
            ord_by_item.get(str(x.get("item_id")), 0),
            str(x.get("metric_key")),
        ),
    ):
        iid = str(m.get("item_id"))
        ord_ = ord_by_item.get(iid, "?")
        val = m.get("metric_value_numeric")
        mj = m.get("metric_value_json") or {}
        if isinstance(mj, str):
            try:
                mj = json.loads(mj)
            except Exception:
                mj = {}
        st = mj.get("status") or ("ok" if val is not None else "—")
        print(f"| {ord_} | {m.get('metric_key')} | {val} | {st} |")
    return 0


def main() -> int:
    from dotenv import load_dotenv

    load_dotenv()
    p = argparse.ArgumentParser(description="RAGAS evaluation (AF Evaluation Layer)")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("check-deps", help="Verify optional ragas stack imports")

    r = sub.add_parser("run", help="Run RAGAS on completed evaluation_run")
    r.add_argument("--run-id", required=True)

    s = sub.add_parser("show-metrics", help="Print ragas.* metric facts for a run")
    s.add_argument("--run-id", required=True)

    args = p.parse_args()
    if args.cmd == "check-deps":
        return cmd_check_deps()
    rid = uuid.UUID(args.run_id.strip())
    if args.cmd == "run":
        return cmd_run(rid)
    if args.cmd == "show-metrics":
        return cmd_show_metrics(rid)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
