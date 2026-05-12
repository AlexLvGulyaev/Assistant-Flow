#!/usr/bin/env python3
"""
Regression (P6.12 follow-up): AdminService must not NameError on Weaviate collection count.

Ensures ``weaviate_collection_count_best_effort`` is importable and ``get_collection_count``:
- calls the helper when active backend is weaviate;
- returns 0 (degraded) when embeddings init fails or helper returns None — no exception to Overview/Documents.

Run from repo root (needs project deps / venv with psycopg for full AdminService import chain):
  python scripts/test_admin_overview_weaviate_count_smoke.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    from dataclasses import replace

    from services.admin_service import AdminService
    from services.retrieval import weaviate_backend as wb
    from utils.config import load_config

    if not callable(getattr(wb, "weaviate_collection_count_best_effort", None)):
        print("FAIL: weaviate_collection_count_best_effort missing", file=sys.stderr)
        return 1

    cfg = replace(load_config(), rag_backend="weaviate")
    svc = AdminService(cfg)

    with patch.object(svc, "_effective_rag_backend_resolved", return_value="weaviate"):
        with patch(
            "services.admin_service.weaviate_collection_count_best_effort",
            return_value=0,
        ) as m_count:
            n = svc.get_collection_count()
            if n != 0:
                print(f"FAIL: expected 0, got {n}", file=sys.stderr)
                return 1
            if not m_count.called:
                print("FAIL: helper not invoked", file=sys.stderr)
                return 1

    with patch.object(svc, "_effective_rag_backend_resolved", return_value="weaviate"):
        with patch(
            "services.admin_service.weaviate_collection_count_best_effort",
            return_value=None,
        ):
            n = svc.get_collection_count()
            if n != 0:
                print(f"FAIL: None from helper should map to 0, got {n}", file=sys.stderr)
                return 1

    with patch.object(svc, "_effective_rag_backend_resolved", return_value="weaviate"):
        with patch(
            "services.admin_service.build_openai_embeddings",
            side_effect=RuntimeError("simulated missing OPENAI_API_KEY"),
        ):
            n = svc.get_collection_count()
            if n != 0:
                print(f"FAIL: embeddings error should yield 0, got {n}", file=sys.stderr)
                return 1

    # get_knowledge_base_status must not raise (uses get_collection_count)
    with patch.object(svc, "_effective_rag_backend_resolved", return_value="weaviate"):
        with patch("services.admin_service.weaviate_collection_count_best_effort", return_value=3):
            st = svc.get_knowledge_base_status()
            if st.collection_count != 3:
                print(f"FAIL: KB status collection_count {st.collection_count}", file=sys.stderr)
                return 1

    print("OK: test_admin_overview_weaviate_count_smoke")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
