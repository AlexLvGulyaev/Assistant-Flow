#!/usr/bin/env python3
"""
Compare two evaluation runs (markdown + optional JSON).

  docker exec portfolio-test-assistant-flow-1 python scripts/evaluation_compare_runs.py \\
      --run-a <uuid> --run-b <uuid> --json-out /tmp/compare.json
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _group_metrics(rows: list[dict[str, Any]]) -> dict[uuid.UUID, list[dict[str, Any]]]:
    out: dict[uuid.UUID, list[dict[str, Any]]] = {}
    for m in rows:
        iid = m.get("item_id")
        if iid is None:
            continue
        if not isinstance(iid, uuid.UUID):
            iid = uuid.UUID(str(iid))
        out.setdefault(iid, []).append(dict(m))
    return out


def main() -> int:
    from dotenv import load_dotenv

    load_dotenv()
    p = argparse.ArgumentParser()
    p.add_argument("--run-a", required=True)
    p.add_argument("--run-b", required=True)
    p.add_argument("--json-out", default=None)
    args = p.parse_args()

    ra = uuid.UUID(args.run_a.strip())
    rb = uuid.UUID(args.run_b.strip())

    from repositories.connection import get_connection
    from repositories.evaluation_repository import EvaluationRepository
    from services.evaluation_service import compute_run_summary

    repo = EvaluationRepository()
    with get_connection() as conn:
        a = repo.get_run(conn, run_id=ra)
        b = repo.get_run(conn, run_id=rb)
        if not a or not b:
            print("run not found", file=sys.stderr)
            return 2
        ia = repo.list_items_for_run(conn, run_id=ra)
        ib = repo.list_items_for_run(conn, run_id=rb)
        ma = _group_metrics(repo.list_metrics_for_run(conn, run_id=ra))
        mb = _group_metrics(repo.list_metrics_for_run(conn, run_id=rb))

    sa = compute_run_summary(ia, ma)
    sb = compute_run_summary(ib, mb)

    def fmt(x: Any) -> str:
        if x is None:
            return "null"
        if isinstance(x, float):
            return f"{x:.6g}"
        return str(x)

    lines = [
        "## Evaluation compare (P1-lite)",
        "",
        f"- **Run A:** `{ra}` — {a.get('name') or '—'}",
        f"- **Run B:** `{rb}` — {b.get('name') or '—'}",
        "",
        "| Metric | Run A | Run B |",
        "|--------|-------|-------|",
        f"| avg_manual_score | {fmt(sa.get('avg_manual_score'))} | {fmt(sb.get('avg_manual_score'))} |",
        f"| avg_tokens | {fmt(sa.get('avg_tokens'))} | {fmt(sb.get('avg_tokens'))} |",
        f"| avg_latency_ms | {fmt(sa.get('avg_latency_ms'))} | {fmt(sb.get('avg_latency_ms'))} |",
        f"| fallback_rate | {fmt(sa.get('fallback_rate'))} | {fmt(sb.get('fallback_rate'))} |",
        f"| duplicate_chunk_rate | {fmt(sa.get('duplicate_chunk_rate'))} | {fmt(sb.get('duplicate_chunk_rate'))} |",
        f"| retrieved_count_avg | {fmt(sa.get('retrieved_count_avg'))} | {fmt(sb.get('retrieved_count_avg'))} |",
        f"| item_count | {fmt(sa.get('item_count'))} | {fmt(sb.get('item_count'))} |",
        "",
        "### Items (ordinal alignment)",
        "",
        "| ord | manual A | manual B | fallback A | fallback B | retrieved A | retrieved B |",
        "|-----|----------|----------|------------|------------|-------------|-------------|",
    ]

    by_ord_a = {int(x["ordinal"]): x for x in ia}
    by_ord_b = {int(x["ordinal"]): x for x in ib}
    all_ord = sorted(set(by_ord_a) | set(by_ord_b))

    def man_for(iid: uuid.UUID, mgroup: dict[uuid.UUID, list[dict[str, Any]]]) -> str:
        for m in mgroup.get(iid, []):
            if m.get("metric_key") == "manual.overall":
                return fmt(m.get("metric_value_numeric"))
        return "null"

    def item_id_u(x: dict[str, Any]) -> uuid.UUID:
        iid = x["id"]
        return iid if isinstance(iid, uuid.UUID) else uuid.UUID(str(iid))

    def fb(x: dict[str, Any] | None) -> str:
        if not x:
            return "null"
        rd = x.get("retrieval_diag") or {}
        if isinstance(rd, str):
            try:
                rd = json.loads(rd)
            except Exception:
                rd = {}
        return fmt((rd or {}).get("fallback_reason"))

    def rc(x: dict[str, Any] | None) -> str:
        if not x:
            return "null"
        rd = x.get("retrieval_diag") or {}
        if isinstance(rd, str):
            try:
                rd = json.loads(rd)
            except Exception:
                rd = {}
        return fmt((rd or {}).get("retrieved_count"))

    for o in all_ord:
        xa = by_ord_a.get(o)
        xb = by_ord_b.get(o)
        ma_a = man_for(item_id_u(xa), ma) if xa else "null"
        ma_b = man_for(item_id_u(xb), mb) if xb else "null"
        lines.append(
            f"| {o} | {ma_a} | {ma_b} | {fb(xa)} | {fb(xb)} | {rc(xa)} | {rc(xb)} |"
        )

    text = "\n".join(lines) + "\n"
    print(text)
    if args.json_out:
        out = {"run_a": str(ra), "run_b": str(rb), "summary_a": sa, "summary_b": sb}
        Path(args.json_out).write_text(
            json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"[evaluation] wrote {args.json_out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
