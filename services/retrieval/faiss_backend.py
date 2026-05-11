"""
FAISS retrieval backend (P6.2a): secondary / demo, изолирован от Chroma.

Формат каталога индекса (FAISS_INDEX_DIR):
- vectors.faiss — FAISS IndexFlatL2 (float32)
- chunks.json — массив объектов {"page_content": str, "metadata": dict} в порядке строк индекса
- manifest.json (опционально) — {"embedding_dim": int, "embedding_model": str}

Scores: L2 distance в **шкале FAISS** (backend-local); сравнение с Chroma без normalization запрещено
до отдельного hybrid-слоя (см. RetrievalSearchResult, PROJECT_STATE §29.1).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from services.retrieval.base import (
    RetrievalChunk,
    RetrievalHealth,
    RetrievalSearchResult,
)
from services.retrieval.chunk_metadata import apply_retrieval_metadata_contract
from services.retrieval_security.context import RetrievalSecurityContext
from services.retrieval_security.result_filter import filter_search_results_by_security
from services.retrieval_security.telemetry import emit_retrieval_security_event

if TYPE_CHECKING:
    from langchain_core.embeddings import Embeddings
    from utils.config import AppConfig

VECTORS_FILENAME = "vectors.faiss"
CHUNKS_FILENAME = "chunks.json"
MANIFEST_FILENAME = "manifest.json"


def resolve_faiss_index_dir(config: "AppConfig", *, project_root: Path | None = None) -> Path:
    """Абсолютный путь к каталогу FAISS-индекса (относительные пути — от project_root или cwd)."""
    raw = (getattr(config, "faiss_index_dir", None) or "storage/faiss").strip() or "storage/faiss"
    p = Path(raw)
    if p.is_absolute():
        return p.resolve()
    base = project_root if project_root is not None else Path.cwd()
    return (base / p).resolve()


class FaissBackend:
    """Query-only FAISS: загрузка с диска, поиск через тот же embedding provider, что и у AF."""

    def __init__(
        self,
        *,
        index_dir: Path,
        embeddings: "Embeddings",
    ) -> None:
        self._index_dir = Path(index_dir).resolve()
        self._embeddings = embeddings
        self._vectors_path = self._index_dir / VECTORS_FILENAME
        self._chunks_path = self._index_dir / CHUNKS_FILENAME
        self._manifest_path = self._index_dir / MANIFEST_FILENAME
        self._index: Any = None
        self._chunks: list[dict[str, Any]] = []
        self._manifest: dict[str, Any] = {}
        self._reload_from_disk()

    @property
    def backend_name(self) -> str:
        return "faiss"

    @property
    def index_dir(self) -> Path:
        return self._index_dir

    def _reload_from_disk(self) -> None:
        import faiss  # noqa: PLC0415 — тяжёлая зависимость, только для FAISS-контура

        if not self._vectors_path.is_file():
            raise FileNotFoundError(
                f"FAISS: отсутствует файл индекса {self._vectors_path} "
                f"(ожидается каталог {self._index_dir}). "
                f"Соберите демо-индекс: python scripts/build_faiss_demo_index.py"
            )
        if not self._chunks_path.is_file():
            raise FileNotFoundError(
                f"FAISS: отсутствует {self._chunks_path}. "
                f"Соберите демо-индекс: python scripts/build_faiss_demo_index.py"
            )

        self._index = faiss.read_index(str(self._vectors_path))
        raw = json.loads(self._chunks_path.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            raise ValueError("FAISS: chunks.json должен быть JSON-массивом объектов")
        self._chunks = raw
        if self._manifest_path.is_file():
            self._manifest = json.loads(self._manifest_path.read_text(encoding="utf-8"))
        else:
            self._manifest = {}

        n_idx = int(self._index.ntotal)
        n_chunks = len(self._chunks)
        if n_idx != n_chunks:
            raise ValueError(
                f"FAISS: несовпадение размеров — vectors.ntotal={n_idx}, chunks.json={n_chunks}"
            )
        for i, row in enumerate(self._chunks):
            if not isinstance(row, dict) or "page_content" not in row:
                raise ValueError(f"FAISS: chunks.json[{i}] должен содержать ключ page_content")

        dim_meta = self._manifest.get("embedding_dim")
        if dim_meta is not None and int(dim_meta) != int(self._index.d):
            raise ValueError(
                f"FAISS: manifest embedding_dim={dim_meta} не совпадает с index.d={self._index.d}"
            )

    def collection_count(self) -> int:
        if self._index is None:
            return 0
        return int(self._index.ntotal)

    def search(
        self,
        query: str,
        top_k: int = 5,
        *,
        security_context: RetrievalSecurityContext | None = None,
    ) -> list[RetrievalSearchResult]:
        import numpy as np  # noqa: PLC0415

        if not (query or "").strip() or top_k <= 0:
            return []

        ctx = security_context or RetrievalSecurityContext.permissive_default()
        if not ctx.is_fully_unrestricted():
            emit_retrieval_security_event(
                "retrieval_scope_applied",
                role=ctx.role,
                retrieval_scope=ctx.retrieval_scope,
                chroma_where=False,
                backend="faiss",
            )
        q = query.strip()
        vec = self._embeddings.embed_query(q)
        arr = np.array([vec], dtype=np.float32)
        if arr.shape[1] != self._index.d:
            raise ValueError(
                f"FAISS: размерность запроса {arr.shape[1]} != размерность индекса {self._index.d}"
            )

        ntotal = int(self._index.ntotal)
        requested = int(top_k)
        if not ctx.is_fully_unrestricted():
            # FAISS без metadata-индекса: расширяем выборку, затем фильтруем до top_k.
            requested = min(ntotal, max(requested * 8, requested))
        k = min(requested, ntotal)
        if k <= 0:
            return []

        distances, indices = self._index.search(arr, k)
        out: list[RetrievalSearchResult] = []
        rank = 0
        for i in range(k):
            idx = int(indices[0][i])
            dist = float(distances[0][i])
            if idx < 0 or idx >= len(self._chunks):
                continue
            row = self._chunks[idx]
            page = str(row.get("page_content") or "")
            meta = dict(row.get("metadata") or {})
            meta = apply_retrieval_metadata_contract(
                meta,
                backend=self.backend_name,
                result_rank=rank,
            )
            rank += 1
            out.append(
                RetrievalSearchResult(
                    chunk=RetrievalChunk(page_content=page, metadata=meta),
                    score=dist,
                )
            )
        filtered = filter_search_results_by_security(out, ctx)
        return filtered[: int(top_k)]

    def healthcheck(self) -> RetrievalHealth:
        detail_parts: list[str] = [f"index_dir={self._index_dir}"]
        try:
            n = self.collection_count()
            if n == 0:
                return RetrievalHealth(
                    backend=self.backend_name,
                    ok=False,
                    detail="; ".join(detail_parts + ["индекс пуст (ntotal=0)"]),
                    collection_count=0,
                )
            return RetrievalHealth(
                backend=self.backend_name,
                ok=True,
                detail="; ".join(detail_parts),
                collection_count=n,
            )
        except Exception as exc:
            return RetrievalHealth(
                backend=self.backend_name,
                ok=False,
                detail="; ".join(detail_parts + [f"{type(exc).__name__}: {exc}"]),
                collection_count=None,
            )
