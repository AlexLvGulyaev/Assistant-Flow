"""
FAISS retrieval backend: operational secondary backend (RAG_BACKEND=faiss).

Формат каталога индекса (FAISS_INDEX_DIR):
- vectors.faiss — FAISS IndexFlatL2 (float32)
- chunks.json — массив объектов {"page_content": str, "metadata": dict} в порядке строк индекса
- manifest.json — backend, embedding_dim/model, revision, counts, source, timestamps

Scores: L2 distance в шкале FAISS (backend-local).
"""

from __future__ import annotations

import json
import shutil
import uuid
from datetime import datetime, timezone
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

FAISS_PG_COLLECTION_LABEL = "faiss"


def resolve_faiss_index_dir(config: "AppConfig", *, project_root: Path | None = None) -> Path:
    """Абсолютный путь к каталогу FAISS-индекса (относительные пути — от project_root или cwd)."""
    raw = (getattr(config, "faiss_index_dir", None) or "storage/faiss").strip() or "storage/faiss"
    p = Path(raw)
    if p.is_absolute():
        return p.resolve()
    base = project_root if project_root is not None else Path.cwd()
    return (base / p).resolve()


def count_faiss_chunks_on_disk(index_dir: Path) -> int:
    """Лёгкий подсчёт чанков по chunks.json (для /stats без загрузки FAISS)."""
    p = Path(index_dir).resolve() / CHUNKS_FILENAME
    if not p.is_file():
        return 0
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        return len(raw) if isinstance(raw, list) else 0
    except Exception:
        return 0


def faiss_disk_fingerprint(index_dir: Path) -> tuple[int, int, int]:
    """
    Mtime nanoseconds для manifest / chunks / vectors (0 если файл отсутствует).
    Используется RetrievalBackendManager для обнаружения external reindex без restart.
    """
    base = Path(index_dir).resolve()

    def _mt(p: Path) -> int:
        try:
            return int(p.stat().st_mtime_ns)
        except OSError:
            return 0

    return (
        _mt(base / MANIFEST_FILENAME),
        _mt(base / CHUNKS_FILENAME),
        _mt(base / VECTORS_FILENAME),
    )


def _flatten_metadata(meta: dict[str, Any]) -> dict[str, Any]:
    """JSON-serializable metadata (str/int/float/bool; остальное → str)."""
    out: dict[str, Any] = {}
    for k, v in meta.items():
        if v is None:
            continue
        key = str(k)
        if isinstance(v, (str, int, float, bool)):
            out[key] = v
        else:
            out[key] = str(v)
    return out


class FaissBackend:
    """FAISS: загрузка/персист, индексация, поиск; совместимость эмбеддингов — строго по manifest."""

    def __init__(
        self,
        *,
        index_dir: Path,
        embeddings: "Embeddings",
        app_config: "AppConfig | None" = None,
        allow_empty: bool = False,
    ) -> None:
        self._index_dir = Path(index_dir).resolve()
        self._embeddings = embeddings
        self._app_config = app_config
        self._vectors_path = self._index_dir / VECTORS_FILENAME
        self._chunks_path = self._index_dir / CHUNKS_FILENAME
        self._manifest_path = self._index_dir / MANIFEST_FILENAME
        self._index: Any = None
        self._chunks: list[dict[str, Any]] = []
        self._manifest: dict[str, Any] = {}
        self._index_dir.mkdir(parents=True, exist_ok=True)

        has_vectors = self._vectors_path.is_file() and self._chunks_path.is_file()
        if not has_vectors:
            if not allow_empty:
                raise FileNotFoundError(
                    f"FAISS: отсутствует индекс в {self._index_dir} "
                    f"(нужны {VECTORS_FILENAME} и {CHUNKS_FILENAME}). "
                    f"Операционная индексация: admin_index_documents / AdminKnowledgeIndexer."
                )
            self._init_empty_index()
            self._persist()
            return
        self._reload_from_disk()

    @property
    def backend_name(self) -> str:
        return "faiss"

    @property
    def index_dir(self) -> Path:
        return self._index_dir

    @property
    def manifest_path(self) -> Path:
        return self._manifest_path

    def _probe_embedding_dim(self) -> int:
        vec = self._embeddings.embed_query("__af_faiss_dim_probe__")
        n = len(vec)
        if n <= 0:
            raise RuntimeError("FAISS: embedding probe returned empty vector")
        return n

    def _expected_embedding_model(self) -> str:
        if self._app_config is not None:
            return str(self._app_config.openai_embedding_model or "").strip() or "unknown"
        return str(self._manifest.get("embedding_model") or "unknown")

    def _init_empty_index(self, *, knowledge_base_revision: int = 0) -> None:
        import faiss  # noqa: PLC0415

        dim = self._probe_embedding_dim()
        self._index = faiss.IndexFlatL2(dim)
        self._chunks = []
        now = datetime.now(timezone.utc).isoformat()
        self._manifest = {
            "backend": "faiss",
            "embedding_dim": dim,
            "embedding_model": self._expected_embedding_model(),
            "created_at": now,
            "updated_at": now,
            "chunk_count": 0,
            "document_count": 0,
            "knowledge_base_revision": int(knowledge_base_revision),
            "source": "operational_indexer",
        }

    def _reload_from_disk(self) -> None:
        import faiss  # noqa: PLC0415

        if not self._vectors_path.is_file():
            raise FileNotFoundError(f"FAISS: отсутствует {self._vectors_path}")
        if not self._chunks_path.is_file():
            raise FileNotFoundError(f"FAISS: отсутствует {self._chunks_path}")

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
        self._assert_embedding_contract_readonly()

    def _assert_embedding_contract_readonly(self) -> None:
        """При загрузке с диска: сверить manifest с AppConfig (если передан)."""
        if self._app_config is None:
            return
        exp_model = str(self._app_config.openai_embedding_model or "").strip()
        man_model = str(self._manifest.get("embedding_model") or "").strip()
        if man_model and exp_model and man_model != exp_model:
            raise ValueError(
                f"FAISS manifest embedding_model={man_model!r} не совпадает с "
                f"OPENAI/конфигом openai_embedding_model={exp_model!r}. "
                "Переиндексируйте с тем же провайдером или удалите индекс."
            )

    def _assert_runtime_embedding_contract(self) -> None:
        """Перед search/add при непустом индексе: сверка embedding model (размерность — отдельно при query)."""
        if self._index is None or int(self._index.ntotal) == 0:
            return
        if self._app_config is not None:
            exp_model = str(self._app_config.openai_embedding_model or "").strip()
            man_model = str(self._manifest.get("embedding_model") or "").strip()
            if man_model and exp_model and man_model != exp_model:
                raise ValueError(
                    f"FAISS: индекс собран с embedding_model={man_model!r}, "
                    f"сейчас в конфиге {exp_model!r}. Поиск запрещён до переиндексации."
                )

    def collection_count(self) -> int:
        if self._index is None:
            return 0
        return int(self._index.ntotal)

    def reset_for_full_reindex(self) -> None:
        """Полностью очищает каталог индекса и создаёт пустой индекс той же размерности."""
        old_rev = 0
        if self._manifest_path.is_file():
            try:
                old_rev = int(
                    json.loads(self._manifest_path.read_text(encoding="utf-8")).get(
                        "knowledge_base_revision"
                    )
                    or 0
                )
            except Exception:
                old_rev = 0
        if self._index_dir.exists():
            shutil.rmtree(self._index_dir)
        self._index_dir.mkdir(parents=True, exist_ok=True)
        self._vectors_path = self._index_dir / VECTORS_FILENAME
        self._chunks_path = self._index_dir / CHUNKS_FILENAME
        self._manifest_path = self._index_dir / MANIFEST_FILENAME
        self._init_empty_index(knowledge_base_revision=old_rev + 1)
        self._persist()

    def add_documents(self, documents: list[Any]) -> list[str]:
        import faiss  # noqa: PLC0415
        import numpy as np  # noqa: PLC0415

        if not documents:
            return []
        self._assert_runtime_embedding_contract()
        texts: list[str] = []
        metas: list[dict[str, Any]] = []
        for d in documents:
            texts.append(str(getattr(d, "page_content", None) or ""))
            raw_meta = getattr(d, "metadata", None)
            metas.append(_flatten_metadata(dict(raw_meta) if isinstance(raw_meta, dict) else {}))
        vectors = self._embeddings.embed_documents(texts)
        if not vectors:
            raise RuntimeError("FAISS: embed_documents returned empty")
        dim = len(vectors[0])
        if self._index is None:
            raise RuntimeError("FAISS: index not initialized")
        if int(self._index.d) != dim:
            raise ValueError(
                f"FAISS: batch embedding dim={dim} != index dim={self._index.d} "
                "(несовместимый эмбеддер или повреждённый индекс)."
            )
        man_dim = self._manifest.get("embedding_dim")
        if man_dim is not None and int(man_dim) != dim:
            raise ValueError(
                f"FAISS: manifest embedding_dim={man_dim} != фактическая размерность батча {dim}"
            )

        arr = np.array(vectors, dtype=np.float32)
        self._index.add(arr)
        ids: list[str] = []
        for text, meta in zip(texts, metas):
            cid = str(uuid.uuid4())
            ids.append(cid)
            meta = dict(meta)
            meta["chunk_id"] = cid
            self._chunks.append({"page_content": text, "metadata": meta})

        self._update_manifest_counts()
        self._persist()
        return ids

    def _update_manifest_counts(self) -> None:
        doc_keys: set[str] = set()
        for row in self._chunks:
            md = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
            did = md.get("document_id")
            src = md.get("source")
            if did:
                doc_keys.add(f"id:{did}")
            elif src:
                doc_keys.add(f"src:{src}")
        now = datetime.now(timezone.utc).isoformat()
        self._manifest["chunk_count"] = len(self._chunks)
        self._manifest["document_count"] = len(doc_keys)
        self._manifest["updated_at"] = now
        if self._app_config is not None:
            self._manifest["embedding_model"] = self._expected_embedding_model()
            self._manifest["embedding_dim"] = int(self._index.d) if self._index is not None else 0

    def delete_vectors_for_document_before_reindex(
        self,
        *,
        document_id: uuid.UUID | None,
        source_filename: str,
    ) -> None:
        """
        Пересборка индекса по оставшимся чанкам (без хранения матрицы векторов на диске).
        Дорого при большом корпусе — допустимая simple-safe стратегия для FAISS.
        """
        import faiss  # noqa: PLC0415
        import numpy as np  # noqa: PLC0415

        fn = (source_filename or "").strip()
        doc_s = str(document_id) if document_id is not None else ""

        kept: list[dict[str, Any]] = []
        for row in self._chunks:
            if not isinstance(row, dict):
                continue
            md = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
            md_doc = str(md.get("document_id") or "")
            md_src = str(md.get("source") or "")
            drop = False
            if document_id is not None and fn:
                if md_doc == doc_s or md_src == fn:
                    drop = True
            elif document_id is not None:
                if md_doc == doc_s:
                    drop = True
            elif fn:
                if md_src == fn:
                    drop = True
            if not drop:
                kept.append(row)

        if len(kept) == len(self._chunks):
            return

        dim = int(self._index.d) if self._index is not None else self._probe_embedding_dim()
        new_index = faiss.IndexFlatL2(dim)
        if kept:
            texts = [str(r.get("page_content") or "") for r in kept]
            vecs = self._embeddings.embed_documents(texts)
            arr = np.array(vecs, dtype=np.float32)
            if arr.shape[1] != dim:
                raise ValueError(
                    f"FAISS delete/rebuild: embedding dim {arr.shape[1]} != index dim {dim}"
                )
            new_index.add(arr)
        self._index = new_index
        self._chunks = kept
        self._update_manifest_counts()
        self._persist()

    def _persist(self) -> None:
        import faiss  # noqa: PLC0415

        self._index_dir.mkdir(parents=True, exist_ok=True)
        faiss.write_index(self._index, str(self._vectors_path))
        self._chunks_path.write_text(
            json.dumps(self._chunks, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self._manifest_path.write_text(
            json.dumps(self._manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

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

        self._assert_runtime_embedding_contract()

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
                detail="; ".join(detail_parts + [f"manifest={self._manifest_path.name}"]),
                collection_count=n,
            )
        except Exception as exc:
            return RetrievalHealth(
                backend=self.backend_name,
                ok=False,
                detail="; ".join(detail_parts + [f"{type(exc).__name__}: {exc}"]),
                collection_count=None,
            )
