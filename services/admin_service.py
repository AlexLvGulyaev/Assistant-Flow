"""Admin UI / tooling: documents listing, Chroma status, reindex, PostgreSQL logs."""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from repositories.connection import get_connection
from repositories.document_repository import DocumentRepository
from repositories.processing_logs_repository import ProcessingLogsRepository
from services.admin_knowledge_indexer import AdminKnowledgeIndexer
from services.rag_chroma_store import count_chroma_chunks
from services.rag_document_loader import iter_supported_files
from services.runtime_lifecycle_service import RuntimeLifecycleService
from utils.config import AppConfig, load_config

_PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _resolve_dir(raw: str) -> Path:
    p = Path(raw)
    return p if p.is_absolute() else _PROJECT_ROOT / p


@dataclass(frozen=True)
class ReindexRunResult:
    success: bool
    error_message: str | None
    chunks_created: int
    collection_count: int
    files_indexed_ok: int
    files_found: int
    used_postgres: bool


@dataclass(frozen=True)
class KnowledgeBaseStatus:
    collection_count: int
    postgres_documents: int | None
    postgres_chunks_sum: int | None
    postgres_available: bool


@dataclass(frozen=True)
class OverviewInsights:
    """Aggregates for admin «Обзор» (no schema changes)."""

    db_logs_available: bool
    errors_last_24h: int
    processing_done_last_24h: int
    last_event_at: datetime | None
    last_event_stage: str | None


class AdminService:
    """Coordinates paths, Chroma counts, indexer runs, and DB reads for admin UI."""

    def __init__(self, config: AppConfig | None = None) -> None:
        self._config = config or load_config()
        self._documents_dir = _resolve_dir(self._config.rag_documents_dir)
        self._chroma_dir = _resolve_dir(self._config.chroma_persist_dir)
        self._doc_repo = DocumentRepository()
        self._proc_repo = ProcessingLogsRepository()
        self._lifecycle = RuntimeLifecycleService()

    @property
    def documents_directory(self) -> Path:
        return self._documents_dir

    def get_documents_filesystem_count(self) -> int:
        """Number of ``.txt`` files under ``RAG_DOCUMENTS_DIR`` (recursive)."""
        root = self._documents_dir
        if not root.is_dir():
            return 0
        return sum(1 for p in root.rglob("*.txt") if p.is_file())

    def list_documents(self) -> list[str]:
        """Relative paths of indexed file types under RAG_DOCUMENTS_DIR."""
        try:
            paths = iter_supported_files(self._documents_dir)
        except FileNotFoundError:
            return []
        base = self._documents_dir.resolve()
        out: list[str] = []
        for p in paths:
            try:
                rel = p.resolve().relative_to(base)
                out.append(str(rel))
            except ValueError:
                out.append(p.name)
        return sorted(out)

    def save_uploaded_txt(self, filename: str, data: bytes) -> Path:
        """Save a single .txt file into RAG_DOCUMENTS_DIR (MVP)."""
        safe = Path(filename).name
        if not safe.lower().endswith(".txt"):
            raise ValueError("Only .txt files are supported in MVP.")
        if not safe or safe in (".", ".."):
            raise ValueError("Invalid file name.")
        self._documents_dir.mkdir(parents=True, exist_ok=True)
        dest = self._documents_dir / safe
        dest.write_bytes(data)
        execution_id = str(uuid.uuid4())
        self._lifecycle.log_processing_event(
            execution_id=execution_id,
            intake_event_id=None,
            stage="admin_document_uploaded",
            status="success",
            details={"filename": safe, "source": "admin_ui"},
        )
        return dest

    def get_collection_count(self) -> int:
        """Chroma collection chunk count (same helper as CLI /stats)."""
        return count_chroma_chunks(self._config, persist_path=self._chroma_dir)

    def get_knowledge_base_status(self) -> KnowledgeBaseStatus:
        chroma_n = self.get_collection_count()
        db_url = (os.getenv("DATABASE_URL") or "").strip()
        if not db_url:
            return KnowledgeBaseStatus(
                collection_count=chroma_n,
                postgres_documents=None,
                postgres_chunks_sum=None,
                postgres_available=False,
            )
        try:
            with get_connection() as conn:
                doc_n = self._doc_repo.count_documents(conn)
                chunk_sum = self._doc_repo.sum_version_chunk_counts(conn)
                conn.commit()
            return KnowledgeBaseStatus(
                collection_count=chroma_n,
                postgres_documents=doc_n,
                postgres_chunks_sum=chunk_sum,
                postgres_available=True,
            )
        except Exception:
            return KnowledgeBaseStatus(
                collection_count=chroma_n,
                postgres_documents=None,
                postgres_chunks_sum=None,
                postgres_available=False,
            )

    def run_reindex(self) -> ReindexRunResult:
        """Full Chroma reset + index from RAG_DOCUMENTS_DIR (same as admin CLI --reindex)."""
        execution_id = str(uuid.uuid4())
        try:
            doc_count_started = len(iter_supported_files(self._documents_dir))
        except FileNotFoundError:
            doc_count_started = 0

        self._lifecycle.log_processing_event(
            execution_id=execution_id,
            intake_event_id=None,
            stage="admin_reindex_started",
            status="started",
            details={
                "documents_count": doc_count_started,
                "chunks_count": 0,
            },
        )

        indexer = AdminKnowledgeIndexer(
            self._config,
            documents_dir=self._documents_dir,
            chroma_dir=self._chroma_dir,
            use_postgres=True,
        )
        try:
            report = indexer.run(reindex=True)
        except Exception as exc:
            err_text = f"{type(exc).__name__}: {exc}"
            self._lifecycle.log_processing_event(
                execution_id=execution_id,
                intake_event_id=None,
                stage="admin_reindex_error",
                status="error",
                details={
                    "documents_count": doc_count_started,
                    "chunks_count": 0,
                },
                error_text=err_text,
            )
            return ReindexRunResult(
                success=False,
                error_message=err_text,
                chunks_created=0,
                collection_count=0,
                files_indexed_ok=0,
                files_found=0,
                used_postgres=False,
            )

        err_msg: str | None = None
        if report.errors:
            err_msg = "; ".join(
                f"{o.path.name}: {o.error}" for o in report.errors[:8]
            )
        success = True
        if report.files_found > 0 and report.files_indexed_ok == 0:
            success = False
            err_msg = err_msg or "No files indexed successfully."
        elif report.errors:
            success = False

        details_done = {
            "documents_count": report.files_found,
            "chunks_count": report.chroma_chunk_count,
        }
        if success:
            self._lifecycle.log_processing_event(
                execution_id=execution_id,
                intake_event_id=None,
                stage="admin_reindex_done",
                status="success",
                details=details_done,
            )
        else:
            self._lifecycle.log_processing_event(
                execution_id=execution_id,
                intake_event_id=None,
                stage="admin_reindex_error",
                status="error",
                details=details_done,
                error_text=err_msg,
            )

        return ReindexRunResult(
            success=success,
            error_message=err_msg,
            chunks_created=report.chunks_created,
            collection_count=report.chroma_chunk_count,
            files_indexed_ok=report.files_indexed_ok,
            files_found=report.files_found,
            used_postgres=report.used_postgres,
        )

    def get_recent_logs(self, limit: int = 50) -> list[dict[str, Any]]:
        """Last rows from processing_logs (requires DATABASE_URL and schema v2)."""
        if not (os.getenv("DATABASE_URL") or "").strip():
            return []
        try:
            with get_connection() as conn:
                rows = self._proc_repo.list_recent(conn, limit=limit)
                conn.commit()
            return rows
        except Exception:
            return []

    def get_recent_rag_events(
        self,
        limit: int = 50,
        fallback_reason: str | None = None,
    ) -> list[dict[str, Any]]:
        """Last ``rag_answer_done`` events with optional fallback_reason filter."""
        if not (os.getenv("DATABASE_URL") or "").strip():
            return []
        try:
            with get_connection() as conn:
                rows = self._proc_repo.list_recent_rag_events(
                    conn,
                    limit=limit,
                    fallback_reason=fallback_reason,
                )
                conn.commit()
            return rows
        except Exception:
            return []

    def get_recent_route_events(self, route: str, limit: int = 50) -> list[dict[str, Any]]:
        """Last processing logs rows for a given ``details.route`` value."""
        if not (os.getenv("DATABASE_URL") or "").strip():
            return []
        try:
            with get_connection() as conn:
                rows = self._proc_repo.list_recent_route_events(
                    conn,
                    route=route,
                    limit=limit,
                )
                conn.commit()
            return rows
        except Exception:
            return []

    def get_documents_with_versions(self) -> list[dict[str, Any]]:
        """Rows from documents + version aggregates (for admin «Документы» table)."""
        if not (os.getenv("DATABASE_URL") or "").strip():
            return []
        try:
            with get_connection() as conn:
                rows = self._doc_repo.list_documents_with_version_summary(conn)
                conn.commit()
            return rows
        except Exception:
            return []

    def get_document_versions(self, document_id: uuid.UUID) -> list[dict[str, Any]]:
        """All document_versions rows for one document."""
        if not (os.getenv("DATABASE_URL") or "").strip():
            return []
        try:
            with get_connection() as conn:
                rows = self._doc_repo.list_document_versions(conn, document_id)
                conn.commit()
            return rows
        except Exception:
            return []

    def get_overview_insights(self) -> OverviewInsights:
        """Counts and last event from processing_logs for dashboard (24h window)."""
        if not (os.getenv("DATABASE_URL") or "").strip():
            return OverviewInsights(
                db_logs_available=False,
                errors_last_24h=0,
                processing_done_last_24h=0,
                last_event_at=None,
                last_event_stage=None,
            )
        try:
            with get_connection() as conn:
                err_n = self._proc_repo.count_stage_last_hours(
                    conn, stage="processing_error", hours=24
                )
                done_n = self._proc_repo.count_stage_last_hours(
                    conn, stage="processing_done", hours=24
                )
                latest = self._proc_repo.get_latest(conn)
                conn.commit()
            raw_at = latest.get("created_at") if latest else None
            last_at = raw_at if isinstance(raw_at, datetime) else None
            raw_stage = latest.get("stage") if latest else None
            last_stage = str(raw_stage) if raw_stage is not None else None
            return OverviewInsights(
                db_logs_available=True,
                errors_last_24h=err_n,
                processing_done_last_24h=done_n,
                last_event_at=last_at,
                last_event_stage=last_stage,
            )
        except Exception:
            return OverviewInsights(
                db_logs_available=False,
                errors_last_24h=0,
                processing_done_last_24h=0,
                last_event_at=None,
                last_event_stage=None,
            )

    def get_dashboard_stats(self, hours: int = 24) -> dict[str, Any]:
        """
        Aggregates from ``processing_logs`` for the admin dashboard (no schema changes).

        Keys: total_events, success_events, error_events, admin_events, image_generations,
        reindex_runs, by_status, by_stage, by_route, rag_quality.

        ``by_status`` contains only ``success`` and ``error`` (for the dashboard table).
        ``by_route`` counts only ``route_selected`` / ``processing_done`` with a known
        ``details.route`` (``rag``, ``text``, ``image_generation``).
        ``rag_quality`` aggregates rows whose ``details`` indicate RAG (``route`` = ``rag``
        or presence of RAG diagnostic keys).
        """
        h = max(1, min(int(hours), 24 * 365))
        empty_rq: dict[str, Any] = {
            "rag_events": 0,
            "low_relevance": 0,
            "empty_retrieval": 0,
            "empty_context": 0,
            "llm_error": 0,
            "avg_retrieved_count": 0.0,
            "avg_filtered_count": 0.0,
            "avg_context_chars": 0.0,
        }
        empty: dict[str, Any] = {
            "total_events": 0,
            "success_events": 0,
            "error_events": 0,
            "admin_events": 0,
            "image_generations": 0,
            "reindex_runs": 0,
            "by_status": {},
            "by_stage": {},
            "by_route": {
                "rag": 0,
                "text": 0,
                "image_generation": 0,
            },
            "rag_quality": dict(empty_rq),
        }
        if not (os.getenv("DATABASE_URL") or "").strip():
            return empty
        try:
            with get_connection() as conn:
                total = self._proc_repo.count_events_since(conn, hours=h)
                by_status = self._proc_repo.count_by_status_since(conn, hours=h)
                by_stage = self._proc_repo.count_by_stage_since(conn, hours=h)
                by_route_raw = self._proc_repo.count_routes_since(conn, hours=h)
                rag_quality = self._proc_repo.get_rag_quality_stats_since(conn, hours=h)
                conn.commit()
        except Exception:
            return empty

        admin_events = sum(
            c for stg, c in by_stage.items() if str(stg).startswith("admin_")
        )
        reindex_runs = int(by_stage.get("admin_reindex_started", 0))
        by_route = {
            "rag": int(by_route_raw.get("rag", 0)),
            "text": int(by_route_raw.get("text", 0)),
            "image_generation": int(by_route_raw.get("image_generation", 0)),
        }
        # Dashboard status table: terminal outcomes only (exclude e.g. ``started``).
        by_status_dashboard = {
            k: int(v)
            for k, v in by_status.items()
            if str(k).strip().lower() in ("success", "error")
        }

        return {
            "total_events": total,
            "success_events": int(by_status.get("success", 0)),
            "error_events": int(by_status.get("error", 0)),
            "admin_events": admin_events,
            "image_generations": by_route["image_generation"],
            "reindex_runs": reindex_runs,
            "by_status": by_status_dashboard,
            "by_stage": dict(by_stage),
            "by_route": by_route,
            "rag_quality": rag_quality,
        }
