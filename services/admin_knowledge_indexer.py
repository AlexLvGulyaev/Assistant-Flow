"""Admin-only: index files from disk into active retrieval backend (Chroma default, FAISS optional)."""

from __future__ import annotations

import hashlib
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from langchain_core.documents import Document

from providers.rag_embeddings import build_openai_embeddings
from repositories.connection import get_connection
from repositories.document_repository import DocumentRepository
from services.chunking.smart_chunker import SmartChunker
from services.rag_chroma_store import (
    ChromaRagStore,
    RAG_CHROMA_COLLECTION_NAME,
    count_chroma_chunks,
)
from services.rag_document_loader import iter_supported_files, load_and_split_file
from services.retrieval.base import RetrievalBackend
from services.retrieval.chroma_backend import ChromaBackend
from services.retrieval.faiss_backend import (
    FAISS_PG_COLLECTION_LABEL,
    FaissBackend,
    resolve_faiss_index_dir,
)
from services.retrieval.factory import normalize_rag_backend
from services.retrieval.weaviate_backend import WEAVIATE_PG_COLLECTION_LABEL, WeaviateBackend
from services.retrieval_security.document_security import (
    normalize_upload_visibility,
    stamp_chunks_visibility,
)
from utils.config import AppConfig


def _content_type_for_path(path: Path) -> str | None:
    s = path.suffix.lower()
    if s == ".pdf":
        return "application/pdf"
    if s == ".md":
        return "text/markdown"
    if s == ".txt":
        return "text/plain"
    return None


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            block = f.read(65536)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def _hash_prefix12(h: str | None) -> str:
    """Short hash for logs (no full digest)."""
    if not h:
        return "—"
    s = str(h).strip()
    if len(s) <= 12:
        return s
    return s[:12] + "…"


def _load_split_txt_md_for_index(
    file_path: Path, config: AppConfig
) -> tuple[list[Document], str]:
    """
    One read of the file: SHA256 of raw bytes matches exactly what is decoded
    for chunking (avoids TextLoader vs second open skew for .txt/.md).
    """
    raw = file_path.read_bytes()
    file_hash = hashlib.sha256(raw).hexdigest()
    text = raw.decode("utf-8")
    resolved = str(file_path.resolve())
    doc = Document(
        page_content=text,
        metadata={"source": file_path.name, "file_path": resolved},
    )
    chunker = SmartChunker.from_app_config(config)
    chunks = chunker.split_langchain_documents([doc])
    return chunks, file_hash


def _log_doc_index_event(
    *,
    phase: str,
    filename: str,
    hash_changed: bool,
    selected_document_version_id: uuid.UUID,
    version_number: int,
    file_hash: str | None,
    committed: bool,
) -> None:
    print(
        "[assistant-flow] doc_version:"
        f" phase={phase!r}"
        f" file={filename!r}"
        f" hash_changed={hash_changed}"
        f" selected_document_version_id={selected_document_version_id}"
        f" version_number={version_number}"
        f" hash12={_hash_prefix12(file_hash)}"
        f" committed={committed}",
        flush=True,
    )


@dataclass
class FileIndexOutcome:
    path: Path
    chunks: int
    document_id: uuid.UUID | None = None
    version_id: uuid.UUID | None = None
    job_id: uuid.UUID | None = None
    error: str | None = None


@dataclass
class AdminIndexReport:
    files_found: int
    files_indexed_ok: int
    chunks_created: int
    chroma_chunk_count: int
    """Совместимость UI: число чанков в активном vector index (Chroma или FAISS)."""
    vector_index_chunk_count: int
    used_postgres: bool
    outcomes: list[FileIndexOutcome] = field(default_factory=list)

    @property
    def errors(self) -> list[FileIndexOutcome]:
        return [o for o in self.outcomes if o.error]


class AdminKnowledgeIndexer:
    def __init__(
        self,
        config: AppConfig,
        *,
        documents_dir: Path,
        chroma_dir: Path,
        use_postgres: bool,
    ) -> None:
        self._config = config
        self._documents_dir = documents_dir
        self._chroma_dir = chroma_dir
        self._use_postgres = use_postgres
        self._doc_repo = DocumentRepository()

    def _vector_collection_label(self) -> str:
        rb = normalize_rag_backend(self._config.rag_backend)
        if rb == "faiss":
            return FAISS_PG_COLLECTION_LABEL
        if rb == "weaviate":
            return WEAVIATE_PG_COLLECTION_LABEL
        return RAG_CHROMA_COLLECTION_NAME

    def _open_retrieval_backend(
        self, embeddings, *, reindex: bool
    ) -> RetrievalBackend:
        rb = normalize_rag_backend(self._config.rag_backend)
        if rb == "faiss":
            project_root = Path(__file__).resolve().parents[1]
            index_dir = resolve_faiss_index_dir(
                self._config, project_root=project_root
            )
            index_dir.mkdir(parents=True, exist_ok=True)
            backend: RetrievalBackend = FaissBackend(
                index_dir=index_dir,
                embeddings=embeddings,
                app_config=self._config,
                allow_empty=True,
            )
            if reindex:
                print(
                    "[assistant-flow] vector_write_started retrieval_backend=faiss "
                    f"phase=full_reset backend_index_path={index_dir}",
                    flush=True,
                )
                backend.reset_for_full_reindex()
                print(
                    "[assistant-flow] vector_write_done retrieval_backend=faiss "
                    "phase=full_reset",
                    flush=True,
                )
            return backend

        if rb == "weaviate":
            backend_w: RetrievalBackend = WeaviateBackend(
                config=self._config,
                embeddings=embeddings,
            )
            if reindex:
                print(
                    "[assistant-flow] vector_write_started retrieval_backend=weaviate "
                    f"phase=full_reset class={self._config.weaviate_class_name}",
                    flush=True,
                )
                backend_w.reset_for_full_reindex()
                print(
                    "[assistant-flow] vector_write_done retrieval_backend=weaviate "
                    "phase=full_reset",
                    flush=True,
                )
            return backend_w

        if not self._config.chroma_use_http:
            self._chroma_dir.mkdir(parents=True, exist_ok=True)
        store = ChromaRagStore(
            self._config,
            embeddings,
            persist_directory=self._chroma_dir,
        )
        chroma_backend: RetrievalBackend = ChromaBackend(store)
        if reindex:
            print(
                "[assistant-flow] vector_write_started retrieval_backend=chroma "
                f"phase=full_reset persist_directory={self._chroma_dir}",
                flush=True,
            )
            chroma_backend.reset_for_full_reindex()
            print(
                "[assistant-flow] vector_write_done retrieval_backend=chroma "
                "phase=full_reset",
                flush=True,
            )
        return chroma_backend

    def run(self, *, reindex: bool) -> AdminIndexReport:
        files = list(iter_supported_files(self._documents_dir))
        outcomes: list[FileIndexOutcome] = []

        database_url_set = bool((self._config.database_url or "").strip())
        pg_active = self._use_postgres and database_url_set

        embeddings = build_openai_embeddings(self._config)
        rb = normalize_rag_backend(self._config.rag_backend)
        print(
            f"[assistant-flow] indexer: retrieval_backend={rb} reindex={reindex} "
            f"files_found={len(files)}",
            flush=True,
        )
        vector_backend = self._open_retrieval_backend(embeddings, reindex=reindex)

        chunks_total = 0
        ok_files = 0

        for file_path in files:
            outcome = self._index_one_file(
                file_path=file_path,
                vector_backend=vector_backend,
            )
            outcomes.append(outcome)
            if outcome.error:
                continue
            ok_files += 1
            chunks_total += outcome.chunks

        if rb == "chroma":
            vector_n = count_chroma_chunks(
                self._config,
                persist_path=self._chroma_dir,
            )
            print(
                f"[assistant-flow] chroma: collection {RAG_CHROMA_COLLECTION_NAME!r} "
                f"count after index run: {vector_n}",
                flush=True,
            )
        else:
            vector_n = int(vector_backend.collection_count())
            mf = getattr(vector_backend, "manifest_path", None)
            mf_s = str(mf) if mf is not None else "—"
            extra = f" manifest_path={mf_s}" if rb == "faiss" else ""
            if rb == "weaviate":
                extra = f" class={self._config.weaviate_class_name!r}"
            print(
                f"[assistant-flow] vector_index: backend={rb} count_after_run={vector_n}{extra}",
                flush=True,
            )

        closer = getattr(vector_backend, "close", None)
        if callable(closer):
            closer()

        return AdminIndexReport(
            files_found=len(files),
            files_indexed_ok=ok_files,
            chunks_created=chunks_total,
            chroma_chunk_count=vector_n,
            vector_index_chunk_count=vector_n,
            used_postgres=pg_active,
            outcomes=outcomes,
        )

    def index_single_file(
        self,
        file_path: Path,
        *,
        document_visibility: str | None = None,
    ) -> FileIndexOutcome:
        """
        Index one file already under ``documents_dir`` without wiping Chroma.
        Used for admin single-document reindex / post-upload indexing.

        ``document_visibility``: public | internal | restricted; None → только legacy
        ``unspecified`` на чанках (без принудительного stamp).
        """
        root = self._documents_dir.resolve()
        try:
            resolved = file_path.resolve()
        except OSError:
            return FileIndexOutcome(
                path=file_path, chunks=0, error="cannot resolve file path"
            )
        try:
            resolved.relative_to(root)
        except ValueError:
            return FileIndexOutcome(
                path=file_path,
                chunks=0,
                error="file is outside configured documents directory",
            )
        if not resolved.is_file():
            return FileIndexOutcome(path=resolved, chunks=0, error="not a file")

        embeddings = build_openai_embeddings(self._config)
        rb = normalize_rag_backend(self._config.rag_backend)

        if rb == "faiss":
            project_root = Path(__file__).resolve().parents[1]
            index_dir = resolve_faiss_index_dir(
                self._config, project_root=project_root
            )
            index_dir.mkdir(parents=True, exist_ok=True)
            vector_backend: RetrievalBackend = FaissBackend(
                index_dir=index_dir,
                embeddings=embeddings,
                app_config=self._config,
                allow_empty=True,
            )
            print(
                "[assistant-flow] vector_write_started retrieval_backend=faiss "
                "mode=single_file_full_corpus_rebuild "
                f"backend_index_path={index_dir}",
                flush=True,
            )
            try:
                vector_backend.reset_for_full_reindex()
            except Exception as exc:
                print(
                    "[assistant-flow] vector_write_error retrieval_backend=faiss "
                    f"phase=full_reset error={type(exc).__name__}: {exc}",
                    flush=True,
                )
                return FileIndexOutcome(
                    path=resolved,
                    chunks=0,
                    error=f"vector_store reset: {exc}",
                )
            target_resolved = resolved.resolve()
            last_for_target: FileIndexOutcome | None = None
            for fp in iter_supported_files(self._documents_dir):
                vis_arg = (
                    document_visibility
                    if fp.resolve() == target_resolved
                    else None
                )
                outcome = self._index_one_file(
                    file_path=fp,
                    vector_backend=vector_backend,
                    document_visibility=vis_arg,
                )
                if fp.resolve() == target_resolved:
                    last_for_target = outcome
            print(
                "[assistant-flow] vector_write_done retrieval_backend=faiss "
                f"vector_count={vector_backend.collection_count()}",
                flush=True,
            )
            if last_for_target is None:
                return FileIndexOutcome(
                    path=resolved,
                    chunks=0,
                    error="file not found in supported corpus iterator",
                )
            return last_for_target

        if rb == "weaviate":
            vector_backend_w: RetrievalBackend = WeaviateBackend(
                config=self._config,
                embeddings=embeddings,
            )
            print(
                "[assistant-flow] vector_write_started retrieval_backend=weaviate "
                "mode=single_file_full_corpus_rebuild "
                f"class={self._config.weaviate_class_name}",
                flush=True,
            )
            try:
                vector_backend_w.reset_for_full_reindex()
            except Exception as exc:
                print(
                    "[assistant-flow] vector_write_error retrieval_backend=weaviate "
                    f"phase=full_reset error={type(exc).__name__}: {exc}",
                    flush=True,
                )
                return FileIndexOutcome(
                    path=resolved,
                    chunks=0,
                    error=f"vector_store reset: {exc}",
                )
            target_resolved = resolved.resolve()
            last_for_target_w: FileIndexOutcome | None = None
            for fp in iter_supported_files(self._documents_dir):
                vis_arg = (
                    document_visibility
                    if fp.resolve() == target_resolved
                    else None
                )
                outcome = self._index_one_file(
                    file_path=fp,
                    vector_backend=vector_backend_w,
                    document_visibility=vis_arg,
                )
                if fp.resolve() == target_resolved:
                    last_for_target_w = outcome
            print(
                "[assistant-flow] vector_write_done retrieval_backend=weaviate "
                f"vector_count={vector_backend_w.collection_count()}",
                flush=True,
            )
            try:
                vector_backend_w.close()
            except Exception:
                pass
            if last_for_target_w is None:
                return FileIndexOutcome(
                    path=resolved,
                    chunks=0,
                    error="file not found in supported corpus iterator",
                )
            return last_for_target_w

        if not self._config.chroma_use_http:
            self._chroma_dir.mkdir(parents=True, exist_ok=True)

        store = ChromaRagStore(
            self._config,
            embeddings,
            persist_directory=self._chroma_dir,
        )
        chroma_b = ChromaBackend(store)
        return self._index_one_file(
            file_path=resolved,
            vector_backend=chroma_b,
            document_visibility=document_visibility,
        )

    def _resolve_document_visibility_for_file(
        self,
        abs_path: str,
        explicit: str | None,
    ) -> str | None:
        if explicit is not None and str(explicit).strip():
            return normalize_upload_visibility(explicit)
        if not self._use_postgres or not (self._config.database_url or "").strip():
            return None
        try:
            with get_connection() as conn:
                doc_id = self._doc_repo.find_latest_document_id_by_storage_path(
                    conn, abs_path
                )
                if doc_id is None:
                    return None
                vis = self._doc_repo.get_active_version_visibility(conn, doc_id)
                conn.commit()
            return vis
        except Exception:
            return None

    def _index_one_file(
        self,
        *,
        file_path: Path,
        vector_backend: RetrievalBackend,
        document_visibility: str | None = None,
    ) -> FileIndexOutcome:
        abs_path = str(file_path.resolve())
        title = file_path.stem
        source_filename = file_path.name
        rb = normalize_rag_backend(self._config.rag_backend)
        idx_path = ""
        mf_path = ""
        if rb == "faiss":
            idx_path = str(getattr(vector_backend, "index_dir", "") or "")
            mf_path = str(getattr(vector_backend, "manifest_path", "") or "")
        elif rb == "weaviate":
            idx_path = f"weaviate:{self._config.weaviate_class_name}"
            mf_path = ""

        try:
            suffix = file_path.suffix.lower()
            if suffix in (".txt", ".md"):
                raw_chunks, file_hash = _load_split_txt_md_for_index(
                    file_path, self._config
                )
            else:
                raw_chunks = load_and_split_file(file_path, self._config)
                file_hash = _file_sha256(file_path)
        except Exception as exc:
            return FileIndexOutcome(
                path=file_path, chunks=0, error=f"load/split: {exc}"
            )

        if not raw_chunks:
            return FileIndexOutcome(
                path=file_path, chunks=0, error="no chunks produced (empty file?)"
            )

        pg_enabled = self._use_postgres and bool(
            (self._config.database_url or "").strip()
        )
        doc_id: uuid.UUID | None = None
        ver_id: uuid.UUID | None = None
        job_id: uuid.UUID | None = None
        pg_finalize_mode: str = "full"
        pg_version_number: int = 0
        pg_hash_changed: bool = True

        vis_to_stamp = self._resolve_document_visibility_for_file(
            abs_path, document_visibility
        )

        if pg_enabled:
            try:
                (
                    doc_id,
                    ver_id,
                    job_id,
                    pg_finalize_mode,
                    pg_version_number,
                    pg_hash_changed,
                ) = self._postgres_begin_file(
                    abs_path=abs_path,
                    title=title,
                    source_filename=source_filename,
                    file_path=file_path,
                    file_hash=file_hash,
                )
            except Exception as exc:
                return FileIndexOutcome(
                    path=file_path, chunks=0, error=f"postgres begin: {exc}"
                )
            _log_doc_index_event(
                phase="postgres_begin",
                filename=source_filename,
                hash_changed=pg_hash_changed,
                selected_document_version_id=ver_id,
                version_number=pg_version_number,
                file_hash=file_hash,
                committed=True,
            )
            with get_connection() as conn:
                with conn.transaction():
                    self._doc_repo.delete_document_chunks_for_version(conn, ver_id)

        if vis_to_stamp is not None:
            raw_chunks = stamp_chunks_visibility(raw_chunks, vis_to_stamp)
            print(
                "[assistant-flow] indexer: visibility_applied "
                f"file={source_filename!r} visibility={vis_to_stamp}",
                flush=True,
            )

        chunks = self._attach_chroma_metadata(raw_chunks, doc_id, ver_id)

        try:
            print(
                "[assistant-flow] vector_write_started "
                f"retrieval_backend={rb} file={source_filename!r} "
                f"backend_index_path={idx_path or '—'} manifest_path={mf_path or '—'}",
                flush=True,
            )
            vector_backend.delete_vectors_for_document_before_reindex(
                document_id=doc_id,
                source_filename=source_filename,
            )
            vector_ids = vector_backend.add_documents(chunks)
            print(
                "[assistant-flow] vector_write_done "
                f"retrieval_backend={rb} file={source_filename!r} "
                f"vector_count={vector_backend.collection_count()} "
                f"chunks_added={len(chunks)}",
                flush=True,
            )
        except Exception as exc:
            print(
                "[assistant-flow] vector_write_error "
                f"retrieval_backend={rb} file={source_filename!r} "
                f"{type(exc).__name__}: {exc}",
                flush=True,
            )
            if pg_enabled and doc_id and ver_id and job_id:
                self._postgres_fail(job_id, doc_id, str(exc))
            return FileIndexOutcome(
                path=file_path,
                chunks=0,
                document_id=doc_id,
                version_id=ver_id,
                job_id=job_id,
                error=f"vector_store: {exc}",
            )

        if pg_enabled and doc_id and ver_id and job_id:
            try:
                self._postgres_insert_chunk_rows(
                    document_id=doc_id,
                    version_id=ver_id,
                    lc_chunks=chunks,
                    vector_ids=vector_ids,
                )
            except Exception as exc:
                err_text = f"postgres chunk metadata: {exc}"
                self._postgres_fail(job_id, doc_id, err_text)
                return FileIndexOutcome(
                    path=file_path,
                    chunks=len(chunks),
                    document_id=doc_id,
                    version_id=ver_id,
                    job_id=job_id,
                    error=err_text,
                )
            try:
                self._postgres_complete(
                    job_id=job_id,
                    document_id=doc_id,
                    version_id=ver_id,
                    chunk_count=len(chunks),
                    file_hash=file_hash,
                    finalize_mode=pg_finalize_mode,
                )
            except Exception as exc:
                return FileIndexOutcome(
                    path=file_path,
                    chunks=len(chunks),
                    document_id=doc_id,
                    version_id=ver_id,
                    job_id=job_id,
                    error=f"postgres finalize: {exc} (vector index already updated)",
                )
            _log_doc_index_event(
                phase="postgres_finalize",
                filename=source_filename,
                hash_changed=pg_hash_changed,
                selected_document_version_id=ver_id,
                version_number=pg_version_number,
                file_hash=file_hash,
                committed=True,
            )

        return FileIndexOutcome(
            path=file_path,
            chunks=len(chunks),
            document_id=doc_id,
            version_id=ver_id,
            job_id=job_id,
        )

    def _postgres_insert_chunk_rows(
        self,
        document_id: uuid.UUID,
        version_id: uuid.UUID,
        lc_chunks: list[Document],
        vector_ids: list[str],
    ) -> None:
        """Persist per-chunk rows for admin UI / RAG diagnostics (vectors in active backend)."""
        if len(lc_chunks) != len(vector_ids):
            raise RuntimeError(
                f"vector id count mismatch: chunks={len(lc_chunks)} ids={len(vector_ids)}"
            )
        collection = self._vector_collection_label()
        with get_connection() as conn:
            with conn.transaction():
                for i, (doc, cid) in enumerate(zip(lc_chunks, vector_ids)):
                    text = doc.page_content or ""
                    preview = text[:4000] if len(text) > 4000 else text
                    meta_snap = self._chunk_metadata_snapshot_for_pg(
                        dict(doc.metadata) if doc.metadata else {}
                    )
                    self._doc_repo.insert_document_chunk(
                        conn,
                        document_id=document_id,
                        document_version_id=version_id,
                        chunk_index=i,
                        chunk_text_preview=preview if preview else None,
                        token_count=len(text) if text else None,
                        chroma_collection=collection,
                        chroma_id=cid,
                        metadata=meta_snap,
                    )

    @staticmethod
    def _chunk_metadata_snapshot_for_pg(meta: dict[str, Any]) -> dict[str, Any]:
        """
        Подмножество LangChain ``Document.metadata`` для колонки ``document_chunks.metadata``
        (JSONB): только JSON-совместимые скаляры и короткие строки, без вложенных объектов.
        """
        out: dict[str, Any] = {}
        for raw_k, v in (meta or {}).items():
            k = str(raw_k)[:128]
            if not k or k in out:
                continue
            if v is None:
                continue
            if isinstance(v, (bool, int, float)):
                out[k] = v
            elif isinstance(v, str):
                out[k] = v[:8000] if len(v) > 8000 else v
            else:
                s = str(v)
                out[k] = s[:8000] if len(s) > 8000 else s
        return out

    @staticmethod
    def _attach_chroma_metadata(
        chunks: list[Document],
        document_id: uuid.UUID | None,
        version_id: uuid.UUID | None,
    ) -> list[Document]:
        out: list[Document] = []
        for d in chunks:
            meta = dict(d.metadata)
            if document_id is not None:
                meta["document_id"] = str(document_id)
            if version_id is not None:
                meta["document_version_id"] = str(version_id)
            out.append(Document(page_content=d.page_content, metadata=meta))
        return out

    def _postgres_begin_file(
        self,
        *,
        abs_path: str,
        title: str,
        source_filename: str,
        file_path: Path,
        file_hash: str,
    ) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, str, int, bool]:
        """
        Returns (doc_id, version_id, job_id, finalize_mode, version_number, hash_changed).

        finalize_mode:
        - ``reuse_same_content_hash`` — active version already has this file_hash;
          caller must not refresh indexed_at / file_hash (chunk_count only if distinct).
        - ``full`` — new document/version or hash changed or stored hash was NULL (establish metadata).

        ``hash_changed`` is False only for reuse_same_content_hash; otherwise True.
        """
        content_type = _content_type_for_path(file_path)
        started = datetime.now(timezone.utc)

        with get_connection() as conn:
            with conn.transaction():
                existing = self._doc_repo.find_latest_document_id_by_storage_path(
                    conn, abs_path
                )
                if existing is None:
                    doc_id = self._doc_repo.insert_document(
                        conn,
                        title=title,
                        source_filename=source_filename,
                        storage_path=abs_path,
                        content_type=content_type,
                        description=None,
                        status="indexing",
                        uploaded_by=None,
                    )
                    inserted_vid = self._doc_repo.insert_document_version(
                        conn,
                        doc_id,
                        version_number=1,
                        storage_path=abs_path,
                        file_hash=file_hash,
                        indexed_at=None,
                        chunk_count=0,
                        is_active=True,
                    )
                    active_row = self._doc_repo.find_active_version_for_document(
                        conn, doc_id
                    )
                    if active_row is None:
                        raise RuntimeError(
                            "no active document_versions row after first insert"
                        )
                    ver_id = active_row["id"]
                    if ver_id != inserted_vid:
                        print(
                            "[assistant-flow] doc_version: insert RETURNING id does not "
                            f"match find_active (returning={inserted_vid!s}, "
                            f"find_active={ver_id!s}); using find_active",
                            flush=True,
                        )
                    job_id = self._doc_repo.create_indexing_job(
                        conn,
                        doc_id,
                        document_version_id=ver_id,
                        status="running",
                        started_at=started,
                    )
                    return doc_id, ver_id, job_id, "full", 1, True

                doc_id = existing
                self._doc_repo.update_document_status(conn, doc_id, "indexing")
                active = self._doc_repo.find_active_version_for_document(conn, doc_id)

                if active is not None:
                    prev_hash = active.get("file_hash")
                    if prev_hash is not None and prev_hash == file_hash:
                        ver_id = active["id"]
                        job_id = self._doc_repo.create_indexing_job(
                            conn,
                            doc_id,
                            document_version_id=ver_id,
                            status="running",
                            started_at=started,
                        )
                        return (
                            doc_id,
                            ver_id,
                            job_id,
                            "reuse_same_content_hash",
                            int(active["version_number"]),
                            False,
                        )
                    if prev_hash is None:
                        ver_id = active["id"]
                        job_id = self._doc_repo.create_indexing_job(
                            conn,
                            doc_id,
                            document_version_id=ver_id,
                            status="running",
                            started_at=started,
                        )
                        return (
                            doc_id,
                            ver_id,
                            job_id,
                            "full",
                            int(active["version_number"]),
                            True,
                        )

                    old_vid = active["id"]
                    prev_hash_s = str(prev_hash) if prev_hash is not None else None
                    self._doc_repo.deactivate_document_version(conn, active["id"])
                    self._doc_repo.delete_document_chunks_for_version(conn, active["id"])

                else:
                    old_vid = None
                    prev_hash_s = None

                version_number = self._doc_repo.max_version_number(conn, doc_id) + 1

                inserted_vid = self._doc_repo.insert_document_version(
                    conn,
                    doc_id,
                    version_number=version_number,
                    storage_path=abs_path,
                    file_hash=file_hash,
                    indexed_at=None,
                    chunk_count=0,
                    is_active=True,
                )
                active_row = self._doc_repo.find_active_version_for_document(
                    conn, doc_id
                )
                if active_row is None:
                    raise RuntimeError(
                        "no active document_versions row after insert_document_version"
                    )
                ver_id = active_row["id"]
                if ver_id != inserted_vid:
                    print(
                        "[assistant-flow] doc_version: insert RETURNING id does not "
                        f"match find_active (returning={inserted_vid!s}, "
                        f"find_active={ver_id!s}); using find_active",
                        flush=True,
                    )
                job_id = self._doc_repo.create_indexing_job(
                    conn,
                    doc_id,
                    document_version_id=ver_id,
                    status="running",
                    started_at=started,
                )
        return doc_id, ver_id, job_id, "full", version_number, True

    def _postgres_complete(
        self,
        *,
        job_id: uuid.UUID,
        document_id: uuid.UUID,
        version_id: uuid.UUID,
        chunk_count: int,
        file_hash: str | None = None,
        finalize_mode: str = "full",
    ) -> None:
        with get_connection() as conn:
            with conn.transaction():
                job_vid = self._doc_repo.get_indexing_job_document_version_id(
                    conn, job_id
                )
                target_version_id = (
                    job_vid if job_vid is not None else version_id
                )
                if (
                    job_vid is not None
                    and job_vid != version_id
                ):
                    print(
                        "[assistant-flow] doc_version: indexing_jobs.document_version_id "
                        f"({job_vid!s}) != pipeline version_id ({version_id!s}); "
                        "using job FK for UPDATE",
                        flush=True,
                    )
                if finalize_mode == "reuse_same_content_hash":
                    self._doc_repo.update_document_version_chunk_count_if_distinct(
                        conn, target_version_id, chunk_count
                    )
                else:
                    indexed_at = datetime.now(timezone.utc)
                    self._doc_repo.update_document_version_after_index(
                        conn,
                        target_version_id,
                        chunk_count=chunk_count,
                        indexed_at=indexed_at,
                        file_hash=file_hash,
                    )
                self._doc_repo.update_document_status(conn, document_id, "indexed")
                self._doc_repo.finalize_indexing_job(
                    conn, job_id, status="completed", error_text=None
                )

    def _postgres_fail(self, job_id: uuid.UUID, document_id: uuid.UUID, msg: str) -> None:
        with get_connection() as conn:
            with conn.transaction():
                self._doc_repo.update_document_status(conn, document_id, "failed")
                self._doc_repo.finalize_indexing_job(
                    conn, job_id, status="failed", error_text=msg[:8000]
                )
