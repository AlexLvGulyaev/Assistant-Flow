"""Chroma vector store: native chromadb client (Http or Persistent), shared for index + retrieval."""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path
from typing import Any

import chromadb
from chromadb.config import Settings
from chromadb.errors import NotFoundError
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings

from utils.config import AppConfig

RAG_CHROMA_COLLECTION_NAME = "assistant_flow_rag"


def _is_chroma_collection_stale_error(exc: BaseException) -> bool:
    """True when server deleted/recreated the collection and this handle is invalid."""
    if isinstance(exc, NotFoundError):
        return True
    msg = str(exc).lower()
    return "collection" in msg and "does not exist" in msg


def _flatten_metadata(meta: dict[str, Any]) -> dict[str, Any]:
    """Chroma metadata values must be str, int, float, or bool."""
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


def _get_or_create_collection(
    client: chromadb.api.ClientAPI,
    collection_name: str,
):
    try:
        return client.get_collection(collection_name)
    except Exception:
        return client.create_collection(name=collection_name)


def _delete_all_chroma_records(collection: Any) -> int:
    """Remove every record from a collection (batched). Returns number deleted."""
    removed = 0
    batch_size = 1000
    while True:
        batch = collection.get(limit=batch_size, include=["metadatas"])
        ids = batch.get("ids") or []
        if not ids:
            break
        collection.delete(ids=ids)
        removed += len(ids)
    return removed


def _recreate_collection_on_client(
    client: chromadb.api.ClientAPI,
    collection_name: str,
    *,
    backend_label: str,
) -> int:
    """
    Drop named collection if present, then create an empty one.
    If delete is impossible but collection exists, clear all records in place.
    Returns collection.count() after recreate/clear (should be 0).
    """
    print(
        f"[assistant-flow] chroma reindex: recreating collection {collection_name!r} ({backend_label})",
        flush=True,
    )
    try:
        client.delete_collection(name=collection_name)
        print(
            f"[assistant-flow] chroma reindex: collection {collection_name!r} deleted",
            flush=True,
        )
    except Exception as exc:
        print(
            f"[assistant-flow] chroma reindex: delete_collection (ok if absent): "
            f"{type(exc).__name__}: {exc}",
            flush=True,
        )

    try:
        client.create_collection(name=collection_name)
        print(
            f"[assistant-flow] chroma reindex: collection {collection_name!r} created empty",
            flush=True,
        )
    except Exception as exc:
        print(
            f"[assistant-flow] chroma reindex: create_collection failed, "
            f"clearing in place: {type(exc).__name__}: {exc}",
            flush=True,
        )
        coll = client.get_collection(name=collection_name)
        n_cleared = _delete_all_chroma_records(coll)
        print(
            f"[assistant-flow] chroma reindex: cleared {n_cleared} records in place",
            flush=True,
        )

    final = int(client.get_collection(name=collection_name).count())
    print(
        f"[assistant-flow] chroma reindex: collection count after recreate: {final}",
        flush=True,
    )
    return final


def chromadb_client_for_config(
    config: AppConfig,
    *,
    persist_directory: Path,
) -> chromadb.api.ClientAPI:
    """Single client factory: HttpClient or PersistentClient (same settings as store)."""
    if config.chroma_use_http:
        return chromadb.HttpClient(host=config.chroma_host, port=config.chroma_port)
    persist_directory.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(
        path=str(persist_directory),
        settings=Settings(anonymized_telemetry=False),
    )


def reset_chroma_for_reindex(
    config: AppConfig,
    *,
    persist_directory: Path,
    collection_name: str = RAG_CHROMA_COLLECTION_NAME,
) -> None:
    """
    Full reset before reindex: HTTP — delete + recreate collection; local — wipe persist dir.
    Uses the same client factory as ChromaRagStore (dual-mode safe).
    """
    if config.chroma_use_http:
        client = chromadb_client_for_config(
            config,
            persist_directory=persist_directory,
        )
        _recreate_collection_on_client(
            client,
            collection_name,
            backend_label=f"HttpClient {config.chroma_host}:{config.chroma_port}",
        )
        return

    if persist_directory.exists():
        print(
            f"[assistant-flow] chroma reindex: removing local persist directory {persist_directory}",
            flush=True,
        )
        shutil.rmtree(persist_directory)
    persist_directory.mkdir(parents=True, exist_ok=True)
    print(
        "[assistant-flow] chroma reindex: local persist cleared (collection will be created on open)",
        flush=True,
    )
    # Ensure no stale named collection metadata if Chroma left partial state
    client = chromadb_client_for_config(
        config,
        persist_directory=persist_directory,
    )
    _recreate_collection_on_client(
        client,
        collection_name,
        backend_label=f"PersistentClient {persist_directory}",
    )


def count_chroma_chunks(
    config: AppConfig,
    *,
    persist_path: Path,
    collection_name: str = RAG_CHROMA_COLLECTION_NAME,
) -> int:
    """
    Chunk count using the same backend as ChromaRagStore (short-lived client for /stats, reports).
    """
    try:
        if config.chroma_use_http:
            print("count_chunks: opening chromadb HttpClient", flush=True)
            client = chromadb.HttpClient(host=config.chroma_host, port=config.chroma_port)
            coll = client.get_collection(collection_name)
            n = int(coll.count())
            print(f"count_chunks: count = {n}", flush=True)
            return n
        if not persist_path.exists():
            print("count_chunks: count = 0 (persist dir missing)", flush=True)
            return 0
        print("count_chunks: opening chromadb PersistentClient", flush=True)
        client = chromadb.PersistentClient(
            path=str(persist_path),
            settings=Settings(anonymized_telemetry=False),
        )
        try:
            coll = client.get_collection(collection_name)
        except Exception:
            print("count_chunks: count = 0 (no collection)", flush=True)
            return 0
        n = int(coll.count())
        print(f"count_chunks: count = {n}", flush=True)
        return n
    except Exception as exc:
        print(
            f"count_chunks: failed ({type(exc).__name__}: {exc})",
            flush=True,
        )
        return 0


class ChromaRagStore:
    """Read/write Chroma collection via one chromadb client (HTTP or local persistent)."""

    def __init__(
        self,
        config: AppConfig,
        embedding_function: Embeddings,
        *,
        persist_directory: Path,
        collection_name: str = RAG_CHROMA_COLLECTION_NAME,
    ) -> None:
        self._config = config
        self._embedding_function = embedding_function
        self._collection_name = collection_name
        self._persist_directory = Path(persist_directory)

        self._client = chromadb_client_for_config(
            config,
            persist_directory=self._persist_directory,
        )
        self._collection = _get_or_create_collection(self._client, collection_name)

    @property
    def app_config(self) -> AppConfig:
        """Конфиг приложения (для ChromaBackend / reset без дублирования параметров)."""
        return self._config

    def refresh_client_and_collection(self) -> None:
        """Recreate Chroma client and collection handle (e.g. after external reindex)."""
        self._client = chromadb_client_for_config(
            self._config,
            persist_directory=self._persist_directory,
        )
        self._collection = _get_or_create_collection(
            self._client, self._collection_name
        )

    @property
    def persist_directory(self) -> Path:
        return self._persist_directory

    def _similarity_query_once(
        self,
        embedding: list[float],
        k: int,
        *,
        where: dict[str, Any] | None = None,
    ) -> list[tuple[Document, float]]:
        q_kwargs: dict[str, Any] = {
            "query_embeddings": [embedding],
            "n_results": k,
            "include": ["documents", "metadatas", "distances"],
        }
        if where:
            q_kwargs["where"] = where
        result = self._collection.query(**q_kwargs)

        row_docs = result.get("documents") or []
        row_metas = result.get("metadatas") or []
        row_dists = result.get("distances") or []
        docs0 = row_docs[0] if row_docs else []
        metas0 = row_metas[0] if row_metas else []
        dists0 = row_dists[0] if row_dists else []

        out: list[tuple[Document, float]] = []
        for i, text in enumerate(docs0):
            page = (text or "").strip() if text is not None else ""
            meta_raw = metas0[i] if i < len(metas0) else None
            metadata: dict[str, Any] = (
                dict(meta_raw) if isinstance(meta_raw, dict) else {}
            )
            dist = float(dists0[i]) if i < len(dists0) else 0.0
            out.append((Document(page_content=page, metadata=metadata), dist))
        return out

    def delete_vectors_for_document_before_reindex(
        self,
        *,
        document_id: uuid.UUID | None,
        source_filename: str,
    ) -> None:
        """
        Drop existing vectors for this KB document so single-file reindex stays idempotent.

        Indexer attaches ``document_id`` (and ``document_version_id``) to chunk metadata.
        Older rows may only have ``source`` (basename); ``$or`` removes both shapes.
        When PostgreSQL is off, only ``source`` is used.
        """
        fn = (source_filename or "").strip()
        try:
            if document_id is not None and fn:
                self._collection.delete(
                    where={
                        "$or": [
                            {"document_id": str(document_id)},
                            {"source": fn},
                        ]
                    },
                )
                return
            if document_id is not None:
                self._collection.delete(where={"document_id": str(document_id)})
                return
            if fn:
                self._collection.delete(where={"source": fn})
        except Exception as exc:
            print(
                f"[assistant-flow] chroma: targeted delete before reindex failed "
                f"({type(exc).__name__}: {exc}); retrying document_id-only",
                flush=True,
            )
            try:
                if document_id is not None:
                    self._collection.delete(where={"document_id": str(document_id)})
                elif fn:
                    self._collection.delete(where={"source": fn})
            except Exception as exc2:
                print(
                    f"[assistant-flow] chroma: delete retry failed: {exc2}",
                    flush=True,
                )

    def add_documents(self, documents: list[Document], **kwargs: Any) -> list[str]:
        """Add document chunks with embeddings (native collection.add; kwargs unused, kept for API)."""
        del kwargs  # LangChain compatibility; not passed to Chroma
        if not documents:
            return []
        texts = [d.page_content or "" for d in documents]
        metadatas = [_flatten_metadata(dict(d.metadata)) for d in documents]
        embeddings = self._embedding_function.embed_documents(texts)
        ids = [str(uuid.uuid4()) for _ in documents]
        self._collection.add(
            ids=ids,
            documents=texts,
            metadatas=metadatas,
            embeddings=embeddings,
        )
        return ids

    def native_similarity_search_with_score(
        self,
        query: str,
        k: int,
        *,
        where: dict[str, Any] | None = None,
    ) -> list[tuple[Document, float]]:
        """Query via the same collection handle used for indexing (no LangChain Chroma)."""
        if not (query or "").strip() or k <= 0:
            return []
        q = query.strip()
        print("native retrieval: before embed_query", flush=True)
        embedding = self._embedding_function.embed_query(q)
        print("native retrieval: after embed_query", flush=True)
        print("native retrieval: before collection.query", flush=True)
        try:
            out = self._similarity_query_once(embedding, k, where=where)
            print("native retrieval: after collection.query", flush=True)
            return out
        except Exception as exc:
            if not _is_chroma_collection_stale_error(exc):
                print("native retrieval: after collection.query", flush=True)
                raise
            print(
                "[assistant-flow] chroma collection handle stale, refreshing",
                flush=True,
            )
            self.refresh_client_and_collection()
            print("[assistant-flow] chroma collection refreshed", flush=True)
            print("[assistant-flow] retry retrieval after refresh", flush=True)
            try:
                out = self._similarity_query_once(embedding, k, where=where)
                print("native retrieval: after collection.query", flush=True)
                return out
            except Exception as exc2:
                print(
                    "[assistant-flow] chroma retrieval retry failed: "
                    f"{type(exc2).__name__}: {exc2}",
                    flush=True,
                )
                return []

    def collection_count(self) -> int:
        try:
            return int(self._collection.count())
        except Exception:
            return 0
