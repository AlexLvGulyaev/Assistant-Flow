"""
Минимальный контракт metadata для retrieval chunks (P6.2b).

Не выполняет нормализацию scores — только поля metadata для downstream / hybrid readiness.
Эволюция схемы: только backward-compatible расширения (см. PROJECT_STATE §29.2).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def apply_retrieval_metadata_contract(
    meta: dict[str, Any],
    *,
    backend: str,
    result_rank: int,
) -> dict[str, Any]:
    """
    Дополняет metadata без ломания существующих документов: только setdefault / явные дефолты.

    Обязательные ключи после вызова: source, chunk_id, backend.
    Опционально добавляется retrieval_timestamp (UTC ISO), если ключа ещё не было.
    document_id, version_id, tags — пробрасываются как есть, если уже есть в meta.

    P6.7: заготовки полей metadata для security filtering (значения по умолчанию не
    меняют семантику существующих индексов — только ``setdefault``).
    """
    out: dict[str, Any] = dict(meta)

    raw_src = out.get("source")
    src_str = str(raw_src).strip() if raw_src is not None else ""
    out["source"] = src_str or "unknown"

    cid = out.get("chunk_id")
    if cid is None or not str(cid).strip():
        alt = out.get("id")
        if alt is not None and str(alt).strip():
            out["chunk_id"] = str(alt).strip()
        else:
            out["chunk_id"] = f"{backend}-synthetic-rank-{result_rank}"

    out["backend"] = backend

    out.setdefault("retrieval_timestamp", datetime.now(timezone.utc).isoformat())

    out.setdefault("document_type", "unspecified")
    out.setdefault("visibility", "unspecified")
    out.setdefault("tags", [])

    return out
