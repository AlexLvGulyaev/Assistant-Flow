"""Admin-only: index files from disk into Chroma and optionally record metadata in PostgreSQL."""

from __future__ import annotations

import hashlib
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from providers.rag_embeddings import build_openai_embeddings
from repositories.connection import get_connection
from repositories.document_repository import DocumentRepository
from services.rag_chroma_store import (
    ChromaRagStore,
    RAG_CHROMA_COLLECTION_NAME,
    count_chroma_chunks,
    reset_chroma_for_reindex,
)
from services.rag_document_loader import iter_supported_files, load_and_split_file
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
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=config.rag_chunk_size,
        chunk_overlap=config.rag_chunk_overlap,
        length_function=len,
    )
    resolved = str(file_path.resolve())
    doc = Document(
        page_content=text,
        metadata={"source": file_path.name, "file_path": resolved},
    )
    chunks = splitter.split_documents([doc])
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

    def run(self, *, reindex: bool) -> AdminIndexReport:
        files = iter_supported_files(self._documents_dir)
        outcomes: list[FileIndexOutcome] = []

        if reindex:
            reset_chroma_for_reindex(
                self._config,
                persist_directory=self._chroma_dir,
            )
        if not self._config.chroma_use_http:
            self._chroma_dir.mkdir(parents=True, exist_ok=True)

        database_url_set = bool((os.getenv("DATABASE_URL") or "").strip())
        pg_active = self._use_postgres and database_url_set

        embeddings = build_openai_embeddings(self._config)
        store = ChromaRagStore(
            self._config,
            embeddings,
            persist_directory=self._chroma_dir,
        )

        chunks_total = 0
        ok_files = 0

        for file_path in files:
            outcome = self._index_one_file(
                file_path=file_path,
                store=store,
            )
            outcomes.append(outcome)
            if outcome.error:
                continue
            ok_files += 1
            chunks_total += outcome.chunks

        chroma_n = count_chroma_chunks(
            self._config,
            persist_path=self._chroma_dir,
        )
        print(
            f"[assistant-flow] chroma: collection {RAG_CHROMA_COLLECTION_NAME!r} "
            f"count after index run: {chroma_n}",
            flush=True,
        )

        return AdminIndexReport(
            files_found=len(files),
            files_indexed_ok=ok_files,
            chunks_created=chunks_total,
            chroma_chunk_count=chroma_n,
            used_postgres=pg_active,
            outcomes=outcomes,
        )

    def index_single_file(self, file_path: Path) -> FileIndexOutcome:
        """
        Index one file already under ``documents_dir`` without wiping Chroma.
        Used for admin single-document reindex / post-upload indexing.
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

        if not self._config.chroma_use_http:
            self._chroma_dir.mkdir(parents=True, exist_ok=True)

        embeddings = build_openai_embeddings(self._config)
        store = ChromaRagStore(
            self._config,
            embeddings,
            persist_directory=self._chroma_dir,
        )
        return self._index_one_file(file_path=resolved, store=store)

    def _index_one_file(
        self,
        *,
        file_path: Path,
        store: ChromaRagStore,
    ) -> FileIndexOutcome:
        abs_path = str(file_path.resolve())
        title = file_path.stem
        source_filename = file_path.name

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
            (os.getenv("DATABASE_URL") or "").strip()
        )
        doc_id: uuid.UUID | None = None
        ver_id: uuid.UUID | None = None
        job_id: uuid.UUID | None = None
        pg_finalize_mode: str = "full"
        pg_version_number: int = 0
        pg_hash_changed: bool = True

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

        chunks = self._attach_chroma_metadata(raw_chunks, doc_id, ver_id)

        try:
            store.delete_vectors_for_document_before_reindex(
                document_id=doc_id,
                source_filename=source_filename,
            )
            chroma_ids = store.add_documents(chunks)
        except Exception as exc:
            if pg_enabled and doc_id and ver_id and job_id:
                self._postgres_fail(job_id, doc_id, str(exc))
            return FileIndexOutcome(
                path=file_path,
                chunks=0,
                document_id=doc_id,
                version_id=ver_id,
                job_id=job_id,
                error=f"chroma: {exc}",
            )

        if pg_enabled and doc_id and ver_id and job_id:
            try:
                self._postgres_insert_chunk_rows(
                    document_id=doc_id,
                    version_id=ver_id,
                    lc_chunks=chunks,
                    chroma_ids=chroma_ids,
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
                    error=f"postgres finalize: {exc} (chroma already updated)",
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
        chroma_ids: list[str],
    ) -> None:
        """Persist per-chunk rows for admin UI / RAG diagnostics (vectors stay in Chroma)."""
        if len(lc_chunks) != len(chroma_ids):
            raise RuntimeError(
                f"chroma id count mismatch: chunks={len(lc_chunks)} ids={len(chroma_ids)}"
            )
        collection = RAG_CHROMA_COLLECTION_NAME
        with get_connection() as conn:
            with conn.transaction():
                for i, (doc, cid) in enumerate(zip(lc_chunks, chroma_ids)):
                    text = doc.page_content or ""
                    preview = text[:4000] if len(text) > 4000 else text
                    self._doc_repo.insert_document_chunk(
                        conn,
                        document_id=document_id,
                        document_version_id=version_id,
                        chunk_index=i,
                        chunk_text_preview=preview if preview else None,
                        token_count=len(text) if text else None,
                        chroma_collection=collection,
                        chroma_id=cid,
                        metadata={},
                    )

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
