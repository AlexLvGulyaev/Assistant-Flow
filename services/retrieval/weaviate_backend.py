"""
Weaviate operational retrieval backend (P6.9).

Vectors предоставляет Assistant Flow (OpenAI embeddings); vectorizer = none.
Класс и свойства схемы задаются через AppConfig (WEAVIATE_CLASS_NAME).
"""

from __future__ import annotations

import uuid
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

WEAVIATE_PG_COLLECTION_LABEL = "weaviate"


def _flatten_prop_value(v: Any) -> Any:
    """Weaviate properties: str, int, float, bool; rest → str."""
    if v is None:
        return None
    if isinstance(v, (str, int, float, bool)):
        return v
    return str(v)


class WeaviateBackend:
    """Operational Weaviate: BYOV embeddings, schema ensure, CRUD aligned with RetrievalBackend."""

    def __init__(
        self,
        *,
        config: "AppConfig",
        embeddings: "Embeddings",
    ) -> None:
        import weaviate  # noqa: PLC0415
        from weaviate.classes.config import Configure  # noqa: PLC0415

        self._config = config
        self._embeddings = embeddings
        self._class_name = (config.weaviate_class_name or "AssistantFlowChunk").strip()
        if not self._class_name:
            raise ValueError("WEAVIATE_CLASS_NAME must not be empty for WeaviateBackend")

        raw_url = (getattr(config, "weaviate_url", None) or "").strip()
        if raw_url:
            from urllib.parse import urlparse

            parsed = urlparse(raw_url)
            host = (parsed.hostname or "").strip() or config.weaviate_host
            if not host:
                raise ValueError("WEAVIATE_URL must include a host when set")
            http_port = int(parsed.port or 8080)
            grpc_port = int(getattr(config, "weaviate_grpc_port", 50051) or 50051)
            secure = parsed.scheme == "https"
            self._client = weaviate.connect_to_custom(
                http_host=host,
                http_port=http_port,
                http_secure=secure,
                grpc_host=host,
                grpc_port=grpc_port,
                grpc_secure=secure,
            )
        else:
            host = (config.weaviate_host or "weaviate").strip() or "weaviate"
            self._client = weaviate.connect_to_custom(
                http_host=host,
                http_port=int(config.weaviate_http_port or 8080),
                http_secure=False,
                grpc_host=host,
                grpc_port=int(config.weaviate_grpc_port or 50051),
                grpc_secure=False,
            )
        self._ensure_schema()

    def close(self) -> None:
        try:
            self._client.close()
        except Exception:
            pass

    def _ensure_schema(self) -> None:
        from weaviate.classes.config import (  # noqa: PLC0415
            Configure,
            DataType,
            Property,
            VectorDistances,
        )

        if self._client.collections.exists(self._class_name):
            return
        self._client.collections.create(
            name=self._class_name,
            vectorizer_config=Configure.Vectorizer.none(),
            vector_index_config=Configure.VectorIndex.distance(VectorDistances.L2),
            properties=[
                Property(name="text", data_type=DataType.TEXT),
                Property(name="chunk_id", data_type=DataType.TEXT),
                Property(name="document_id", data_type=DataType.TEXT),
                Property(name="document_version_id", data_type=DataType.TEXT),
                Property(name="source", data_type=DataType.TEXT),
                Property(name="chunk_index", data_type=DataType.INT),
                Property(name="total_chunks", data_type=DataType.INT),
            ],
        )

    def _collection(self) -> Any:
        return self._client.collections.get(self._class_name)

    @property
    def backend_name(self) -> str:
        return "weaviate"

    def reset_for_full_reindex(self) -> None:
        if self._client.collections.exists(self._class_name):
            self._client.collections.delete(self._class_name)
        self._ensure_schema()

    def delete_vectors_for_document_before_reindex(
        self,
        *,
        document_id: uuid.UUID | None,
        source_filename: str,
    ) -> None:
        from weaviate.classes.query import Filter  # noqa: PLC0415

        fn = (source_filename or "").strip()
        coll = self._collection()
        has_doc = document_id is not None
        doc_s = str(document_id) if has_doc else ""

        if has_doc and fn:
            flt = Filter.any_of(
                [
                    Filter.by_property("document_id").equal(doc_s),
                    Filter.by_property("source").equal(fn),
                ]
            )
        elif has_doc:
            flt = Filter.by_property("document_id").equal(doc_s)
        elif fn:
            flt = Filter.by_property("source").equal(fn)
        else:
            return
        coll.data.delete_many(where=flt)

    def add_documents(self, documents: list[Any]) -> list[str]:
        if not documents:
            return []
        texts: list[str] = []
        props_list: list[dict[str, Any]] = []
        ids: list[str] = []
        for d in documents:
            text = str(getattr(d, "page_content", None) or "")
            raw_meta = getattr(d, "metadata", None)
            meta = dict(raw_meta) if isinstance(raw_meta, dict) else {}
            cid = str(uuid.uuid4())
            ids.append(cid)
            chunk_index = meta.get("chunk_index")
            total_chunks = meta.get("total_chunks")
            try:
                cidx = int(chunk_index) if chunk_index is not None else -1
            except (TypeError, ValueError):
                cidx = -1
            try:
                tchunks = int(total_chunks) if total_chunks is not None else -1
            except (TypeError, ValueError):
                tchunks = -1
            props = {
                "text": text,
                "chunk_id": cid,
                "document_id": str(meta.get("document_id") or ""),
                "document_version_id": str(meta.get("document_version_id") or ""),
                "source": str(meta.get("source") or ""),
                "chunk_index": cidx,
                "total_chunks": tchunks,
            }
            props = {k: _flatten_prop_value(v) for k, v in props.items()}
            texts.append(text)
            props_list.append(props)

        vectors = self._embeddings.embed_documents(texts)
        if len(vectors) != len(props_list):
            raise RuntimeError(
                f"Weaviate: embed_documents len={len(vectors)} != chunks={len(props_list)}"
            )

        coll = self._collection()
        with coll.batch.dynamic() as batch:
            for props, vec in zip(props_list, vectors):
                batch.add_object(properties=props, vector=vec)
        return ids

    def collection_count(self) -> int:
        coll = self._collection()
        agg = coll.aggregate.over_all(total_count=True)
        tc = getattr(agg, "total_count", None)
        if tc is None:
            return 0
        try:
            return int(tc)
        except (TypeError, ValueError):
            return 0

    def search(
        self,
        query: str,
        top_k: int = 5,
        *,
        security_context: RetrievalSecurityContext | None = None,
    ) -> list[RetrievalSearchResult]:
        from weaviate.classes.query import MetadataQuery  # noqa: PLC0415

        if not (query or "").strip() or top_k <= 0:
            return []
        q = query.strip()
        ctx = security_context or RetrievalSecurityContext.permissive_default()
        if not ctx.is_fully_unrestricted():
            emit_retrieval_security_event(
                "retrieval_scope_applied",
                role=ctx.role,
                retrieval_scope=ctx.retrieval_scope,
                chroma_where=False,
                backend="weaviate",
            )

        vec = self._embeddings.embed_query(q)
        coll = self._collection()
        n = self.collection_count()
        requested = int(top_k)
        if not ctx.is_fully_unrestricted():
            requested = min(n, max(requested * 8, requested)) if n > 0 else requested
        lim = max(1, min(requested, n) if n > 0 else requested)
        resp = coll.query.near_vector(
            near_vector=vec,
            limit=lim,
            return_metadata=MetadataQuery(distance=True),
        )
        out: list[RetrievalSearchResult] = []
        rank = 0
        for obj in resp.objects:
            props = obj.properties or {}
            page = str(props.get("text") or "")
            meta = {
                "source": props.get("source"),
                "chunk_id": props.get("chunk_id"),
                "document_id": props.get("document_id"),
                "document_version_id": props.get("document_version_id"),
            }
            ci = props.get("chunk_index")
            tc = props.get("total_chunks")
            if ci is not None:
                meta["chunk_index"] = ci
            if tc is not None:
                meta["total_chunks"] = tc
            meta = {k: v for k, v in meta.items() if v is not None and v != ""}
            dist = None
            if obj.metadata and obj.metadata.distance is not None:
                dist = float(obj.metadata.distance)
            else:
                dist = 0.0
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
        detail = f"class={self._class_name}"
        try:
            if not self._client.is_ready():
                return RetrievalHealth(
                    backend=self.backend_name,
                    ok=False,
                    detail=f"{detail}; weaviate not ready",
                    collection_count=None,
                )
            n = self.collection_count()
            return RetrievalHealth(
                backend=self.backend_name,
                ok=True,
                detail=f"{detail}; ready count={n}",
                collection_count=n,
            )
        except Exception as exc:
            return RetrievalHealth(
                backend=self.backend_name,
                ok=False,
                detail=f"{detail}; {type(exc).__name__}: {exc}",
                collection_count=None,
            )


def weaviate_collection_count_best_effort(
    config: "AppConfig",
    *,
    embeddings: "Embeddings",
) -> int:
    """Для Admin stats: best-effort count без долгого удержания соединения."""
    store = WeaviateBackend(config=config, embeddings=embeddings)
    try:
        return int(store.collection_count())
    finally:
        store.close()
