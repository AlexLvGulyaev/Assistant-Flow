"""Admin UI / tooling: documents listing, Chroma status, reindex, PostgreSQL logs."""

from __future__ import annotations

import os
import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from collections import defaultdict
from typing import Any
import mimetypes

from repositories.connection import get_connection
from repositories.document_repository import DocumentRepository
from repositories.processing_logs_repository import ProcessingLogsRepository
from services.admin_knowledge_indexer import AdminKnowledgeIndexer
from services.asset_repository import AssetNotFoundError, AssetValidationError
from services.asset_repository_factory import create_asset_repository
from services.async_job_service import AsyncJob, AsyncJobService
from services.audio_browser_preview import ensure_mp3_browser_preview, needs_browser_mp3_preview
from services.rag_chroma_store import count_chroma_chunks
from services.rag_document_loader import iter_supported_files
from services.runtime_lifecycle_service import RuntimeLifecycleService
from utils.config import AppConfig, load_config

_PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _sniff_audio_content_type(path: Path) -> str | None:
    """Best-effort magic sniff when filename mime guess fails (voice assets)."""
    try:
        head = path.read_bytes()[:32]
    except OSError:
        return None
    if len(head) >= 3 and head[:3] == b"ID3":
        return "audio/mpeg"
    if len(head) >= 2 and head[0] == 0xFF and (head[1] & 0xE0) == 0xE0:
        return "audio/mpeg"
    if head.startswith(b"OggS"):
        return "audio/ogg"
    if head.startswith(b"RIFF") and b"WAVE" in head[:12]:
        return "audio/wav"
    if head.startswith(b"fLaC"):
        return "audio/flac"
    if head.startswith(b"\x1aE\xdf\xa3"):
        return "audio/webm"
    return None


def _read_kb_text_preview(path: Path, max_chars: int = 12000) -> str | None:
    if not path.is_file():
        return None
    if path.suffix.lower() not in (".txt", ".md"):
        return None
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    if len(raw) <= max_chars:
        return raw
    return raw[:max_chars] + "\n…"


SUMMARY_LOG_SAMPLE_CAP = 500

SUMMARY_LIFECYCLE_STAGE_ORDER: tuple[str, ...] = (
    "intake_received",
    "route_selected",
    "text_answer_done",
    "rag_answer_done",
    "stt_started",
    "stt_completed",
    "tts_started",
    "tts_completed",
    "tts_skipped",
    "tts_error",
    "voice_processing_done",
    "voice_processing_error",
    "processing_done",
    "admin_reindex_started",
    "admin_reindex_done",
    "processing_error",
)

_AUDIO_PIPELINE_STAGES: frozenset[str] = frozenset(
    {
        "stt_started",
        "stt_completed",
        "tts_started",
        "tts_completed",
        "tts_skipped",
        "tts_error",
        "voice_processing_done",
        "voice_processing_error",
        "audio_generation_done",
        "audio_generation_error",
    }
)


def _summary_filter_rows_since_hours(
    rows: list[dict[str, Any]], *, hours: int
) -> list[dict[str, Any]]:
    delta = timedelta(hours=max(1, int(hours)))
    cutoff = datetime.now(timezone.utc) - delta
    out: list[dict[str, Any]] = []
    for r in rows:
        t = r.get("created_at")
        if isinstance(t, datetime):
            tt = t if t.tzinfo else t.replace(tzinfo=timezone.utc)
        elif isinstance(t, str):
            try:
                raw_s = t.replace("Z", "+00:00")
                tt = datetime.fromisoformat(raw_s)
                if tt.tzinfo is None:
                    tt = tt.replace(tzinfo=timezone.utc)
                else:
                    tt = tt.astimezone(timezone.utc)
            except (TypeError, ValueError):
                continue
        else:
            continue
        if tt >= cutoff:
            out.append(r)
    return out


def _summary_extract_latency_ms(details: dict[str, Any]) -> float | None:
    for key in ("latency_ms", "duration_ms", "elapsed_ms"):
        v = details.get(key)
        if v is None:
            continue
        try:
            return float(v)
        except (TypeError, ValueError):
            continue
    return None


def _summary_extract_tokens_increment(details: dict[str, Any]) -> int | None:
    v = details.get("total_tokens")
    if v is not None:
        try:
            return int(float(v))
        except (TypeError, ValueError):
            pass
    usage = details.get("token_usage")
    if isinstance(usage, dict):
        u_tot = usage.get("total_tokens")
        if u_tot is not None:
            try:
                return int(float(u_tot))
            except (TypeError, ValueError):
                pass
        pairs = (
            ("input_tokens", "output_tokens"),
            ("prompt_tokens", "completion_tokens"),
        )
        for a, b in pairs:
            x = usage.get(a)
            y = usage.get(b)
            if x is None and y is None:
                continue
            s = 0
            ok = False
            for part in (x, y):
                if part is None:
                    continue
                try:
                    s += int(float(part))
                    ok = True
                except (TypeError, ValueError):
                    continue
            if ok:
                return s
    u_obj = details.get("usage")
    if isinstance(u_obj, dict):
        v2 = u_obj.get("total_tokens")
        if v2 is not None:
            try:
                return int(float(v2))
            except (TypeError, ValueError):
                pass
    return None


def _summary_telemetry_sample(rows: list[dict[str, Any]]) -> dict[str, Any]:
    latencies: list[float] = []
    tokens_sum = 0
    tokens_any = False
    pm_counts: dict[tuple[str, str], int] = defaultdict(int)
    prov_row_counts: dict[str, int] = defaultdict(int)
    eids: set[str] = set()
    for r in rows:
        eid = str(r.get("execution_id") or "").strip()
        if eid:
            eids.add(eid)
        d = r.get("details")
        if not isinstance(d, dict):
            continue
        lm = _summary_extract_latency_ms(d)
        if lm is not None:
            latencies.append(lm)
        inc = _summary_extract_tokens_increment(d)
        if inc is not None:
            tokens_sum += inc
            tokens_any = True
        prov = str(d.get("provider") or d.get("llm_provider") or "").strip()
        model = str(d.get("model") or d.get("llm_model") or "").strip()
        if prov:
            prov_row_counts[prov] += 1
        if prov or model:
            pm_counts[(prov or "—", model or "—")] += 1

    avg_lat = round(sum(latencies) / len(latencies), 1) if latencies else None
    max_lat = round(max(latencies), 1) if latencies else None
    top_pm: str | None = None
    if pm_counts:
        (prov_t, model_t), _n = max(pm_counts.items(), key=lambda x: x[1])
        top_pm = f"{prov_t} / {model_t}"

    by_prov = dict(sorted(prov_row_counts.items(), key=lambda x: (-x[1], x[0])))

    return {
        "unique_execution_ids_in_sample": len(eids),
        "tokens_total": int(tokens_sum) if tokens_any else None,
        "avg_latency_ms": avg_lat,
        "max_latency_ms": max_lat,
        "top_provider_model": top_pm,
        "by_provider_row_counts": by_prov,
    }


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
        self._asset_repository = create_asset_repository(self._config)
        self._async_jobs = AsyncJobService()
        self._doc_repo = DocumentRepository()
        self._proc_repo = ProcessingLogsRepository()
        self._lifecycle = RuntimeLifecycleService()

    @property
    def documents_directory(self) -> Path:
        return self._documents_dir

    @property
    def chroma_persist_path(self) -> Path:
        """Resolved Chroma persist directory (same as indexer / RAG store)."""
        return self._chroma_dir

    @property
    def app_config(self) -> AppConfig:
        return self._config

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
        if not isinstance(data, (bytes, bytearray)) or len(data) == 0:
            raise ValueError("Uploaded file is empty.")
        content_type = mimetypes.guess_type(safe)[0] or "text/plain"
        asset_ref = self._asset_repository.save_bytes(
            bytes(data),
            namespace="documents",
            filename=safe,
            content_type=content_type,
        )
        src = self._asset_repository.resolve_path(asset_ref)
        if not src.exists() or not src.is_file():
            raise RuntimeError(
                f"AssetRepository saved file is not accessible: {src}"
            )

        # Always copy to active RAG compatibility directory from config.
        rag_documents_dir = _resolve_dir(self._config.rag_documents_dir)
        rag_documents_dir.mkdir(parents=True, exist_ok=True)
        dest = rag_documents_dir / safe
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        if not dest.exists() or not dest.is_file():
            raise RuntimeError(
                f"Compatibility copy failed for uploaded document: {dest}"
            )
        execution_id = str(uuid.uuid4())
        self._lifecycle.log_processing_event(
            execution_id=execution_id,
            intake_event_id=None,
            stage="admin_document_uploaded",
            status="success",
            details={
                "filename": safe,
                "source": "admin_ui",
                "asset_ref": asset_ref.relative_path,
                "asset_storage_path": str(src),
                "asset_storage_exists": src.exists(),
                "content_type": asset_ref.content_type,
                "size": asset_ref.size_bytes,
                "size_bytes": asset_ref.size_bytes,
                "sha256": asset_ref.sha256,
                # Compatibility copy used by current RAG indexer and document preview.
                "compatibility_path": str(dest),
                "compatibility_exists": dest.exists(),
                "rag_documents_dir": str(rag_documents_dir),
            },
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

    def enqueue_reindex_job(
        self,
        *,
        payload: dict[str, Any] | None = None,
        max_attempts: int = 3,
    ) -> AsyncJob:
        """
        Async foundation helper (P5.3b): enqueue `rag_reindex` job only.
        Current UI/runtime still use synchronous `run_reindex()` fallback.
        """
        return self._async_jobs.create_job(
            job_type="rag_reindex",
            payload_json=payload or {},
            max_attempts=max_attempts,
        )

    def retry_async_job(self, job_id: uuid.UUID | str) -> AsyncJob:
        """Manual safe retry: eligible failed/retry_scheduled -> queued."""
        return self._async_jobs.retry_job(job_id)

    def get_recent_logs(
        self,
        limit: int = 50,
        *,
        offset: int = 0,
        since_hours: int | None = None,
    ) -> list[dict[str, Any]]:
        """Last rows from processing_logs (requires DATABASE_URL and schema v2)."""
        if not (os.getenv("DATABASE_URL") or "").strip():
            return []
        try:
            with get_connection() as conn:
                rows = self._proc_repo.list_recent(
                    conn,
                    limit=limit,
                    offset=offset,
                    since_hours=since_hours,
                )
                conn.commit()
            return rows
        except Exception:
            return []

    def get_media_asset_preview(
        self, asset_ref: str, *, allowed_prefixes: tuple[str, ...] = ("image/",)
    ) -> tuple[Path, str]:
        """
        Resolve a stored asset reference for safe preview serving.

        Returns tuple: (absolute path, content_type). Raises ValueError when
        ref/content type is invalid or file is missing.
        """
        ref = (asset_ref or "").strip()
        if not ref:
            raise ValueError("asset_ref is required")
        try:
            path = self._asset_repository.resolve_path(ref)
            if not path.is_file():
                raise ValueError("asset not found")
            guessed = (mimetypes.guess_type(path.name)[0] or "").lower()
            ref_norm = ref.replace("\\", "/").lower()
            under_audio_ns = "/audio/" in f"/{ref_norm}/" or ref_norm.startswith("audio/")
            if not any(guessed.startswith(prefix) for prefix in allowed_prefixes):
                sniffed = _sniff_audio_content_type(path)
                if sniffed and any(sniffed.startswith(prefix) for prefix in allowed_prefixes):
                    guessed = sniffed
                elif under_audio_ns and "audio/" in allowed_prefixes:
                    guessed = sniffed or "audio/ogg"
                else:
                    raise ValueError("asset type is not allowed")
            serve_path, serve_ct = path, guessed
            if any(p.startswith("audio/") for p in allowed_prefixes) and guessed.startswith(
                "audio/"
            ):
                if needs_browser_mp3_preview(path, guessed):
                    mp3_p = ensure_mp3_browser_preview(
                        path, cache_root=Path(self._config.asset_storage_dir)
                    )
                    if mp3_p is not None:
                        serve_path, serve_ct = mp3_p, "audio/mpeg"
            return serve_path, serve_ct
        except (AssetValidationError, AssetNotFoundError) as exc:
            raise ValueError("invalid asset_ref") from exc

    def list_async_jobs(
        self,
        *,
        limit: int = 50,
        status: str | None = None,
        job_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Read-only async_jobs list for Admin UI visibility (P5.3c).
        Safe fallback: returns [] if DB/table is unavailable.
        """
        if not (os.getenv("DATABASE_URL") or "").strip():
            return []
        lim = max(1, min(int(limit), 200))
        st = (status or "").strip().lower()
        jt = (job_type or "").strip()
        try:
            with get_connection() as conn, conn.cursor() as cur:
                if st and jt:
                    cur.execute(
                        """
                        SELECT
                            id,
                            job_type,
                            status,
                            attempts,
                            max_attempts,
                            payload_json,
                            result_json,
                            error_json,
                            created_at,
                            started_at,
                            finished_at,
                            updated_at
                        FROM async_jobs
                        WHERE status = %s
                          AND job_type = %s
                        ORDER BY created_at DESC
                        LIMIT %s
                        """,
                        (st, jt, lim),
                    )
                elif st:
                    cur.execute(
                        """
                        SELECT
                            id,
                            job_type,
                            status,
                            attempts,
                            max_attempts,
                            payload_json,
                            result_json,
                            error_json,
                            created_at,
                            started_at,
                            finished_at,
                            updated_at
                        FROM async_jobs
                        WHERE status = %s
                        ORDER BY created_at DESC
                        LIMIT %s
                        """,
                        (st, lim),
                    )
                elif jt:
                    cur.execute(
                        """
                        SELECT
                            id,
                            job_type,
                            status,
                            attempts,
                            max_attempts,
                            payload_json,
                            result_json,
                            error_json,
                            created_at,
                            started_at,
                            finished_at,
                            updated_at
                        FROM async_jobs
                        WHERE job_type = %s
                        ORDER BY created_at DESC
                        LIMIT %s
                        """,
                        (jt, lim),
                    )
                else:
                    cur.execute(
                        """
                        SELECT
                            id,
                            job_type,
                            status,
                            attempts,
                            max_attempts,
                            payload_json,
                            result_json,
                            error_json,
                            created_at,
                            started_at,
                            finished_at,
                            updated_at
                        FROM async_jobs
                        ORDER BY created_at DESC
                        LIMIT %s
                        """,
                        (lim,),
                    )
                rows_raw = cur.fetchall()
                cols = [c.name for c in cur.description] if cur.description else []
                conn.commit()
            out: list[dict[str, Any]] = []
            for r in rows_raw:
                out.append({cols[i]: r[i] for i in range(len(cols))})
            return out
        except Exception:
            return []

    def get_logs_execution_ids_page(
        self,
        *,
        page: int,
        page_size: int,
    ) -> tuple[list[dict[str, Any]], int]:
        """Page of execution_ids + total distinct execution_ids."""
        if not (os.getenv("DATABASE_URL") or "").strip():
            return [], 0
        pg = max(0, int(page))
        size = max(1, min(int(page_size), 500))
        off = pg * size
        try:
            with get_connection() as conn:
                total = self._proc_repo.count_distinct_execution_ids(conn)
                items = self._proc_repo.list_recent_execution_ids(
                    conn, limit=size, offset=off
                )
                conn.commit()
            return items, int(total)
        except Exception:
            return [], 0

    def get_logs_execution_ids_total(self) -> int:
        """Total number of distinct execution_id in processing logs."""
        if not (os.getenv("DATABASE_URL") or "").strip():
            return 0
        try:
            with get_connection() as conn:
                total = self._proc_repo.count_distinct_execution_ids(conn)
                conn.commit()
            return int(total)
        except Exception:
            return 0

    def get_logs_events_for_execution_ids(
        self,
        execution_ids: list[str],
    ) -> list[dict[str, Any]]:
        """All processing logs rows for selected execution_ids."""
        if not (os.getenv("DATABASE_URL") or "").strip():
            return []
        try:
            with get_connection() as conn:
                rows = self._proc_repo.list_events_for_execution_ids(
                    conn,
                    execution_ids=execution_ids,
                )
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

    def get_recent_text_events(self, limit: int = 50) -> list[dict[str, Any]]:
        """Full processing logs chains for recent text requests grouped by execution_id."""
        if not (os.getenv("DATABASE_URL") or "").strip():
            return []
        try:
            with get_connection() as conn:
                rows = self._proc_repo.list_recent_text_events(conn, limit=limit)
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

    def upload_txt_and_index(self, filename: str, data: bytes) -> dict[str, Any]:
        """Save ``.txt`` via asset pipeline, copy to RAG dir, then index one file."""
        dest = self.save_uploaded_txt(filename, data)
        indexer = AdminKnowledgeIndexer(
            self._config,
            documents_dir=self._documents_dir,
            chroma_dir=self._chroma_dir,
            use_postgres=True,
        )
        outcome = indexer.index_single_file(dest)
        doc_id = str(outcome.document_id) if outcome.document_id else None
        return {
            "filename": dest.name,
            "path": str(dest),
            "success": outcome.error is None,
            "error": outcome.error,
            "chunks": outcome.chunks,
            "document_id": doc_id,
        }

    def reindex_document_file(self, document_id: uuid.UUID) -> dict[str, Any]:
        """Re-embed one on-disk document (no global Chroma reset)."""
        if not (os.getenv("DATABASE_URL") or "").strip():
            return {"success": False, "error": "DATABASE_URL not configured"}
        row: dict[str, Any] | None = None
        try:
            with get_connection() as conn:
                row = self._doc_repo.get_document(conn, document_id)
                conn.commit()
        except Exception as exc:
            return {"success": False, "error": f"postgres: {exc}"}
        if not row:
            return {"success": False, "error": "document not found"}
        storage = str(row.get("storage_path") or "").strip()
        source_fn = str(row.get("source_filename") or "").strip()
        path = Path(storage) if storage else Path()
        if not path.is_file() and source_fn:
            path = self._documents_dir / source_fn
        if not path.is_file():
            return {"success": False, "error": "source file not found on disk"}

        execution_id = str(uuid.uuid4())
        self._lifecycle.log_processing_event(
            execution_id=execution_id,
            intake_event_id=None,
            stage="admin_document_reindex_started",
            status="started",
            details={
                "document_id": str(document_id),
                "filename": source_fn or path.name,
                "path": str(path),
            },
        )
        indexer = AdminKnowledgeIndexer(
            self._config,
            documents_dir=self._documents_dir,
            chroma_dir=self._chroma_dir,
            use_postgres=True,
        )
        outcome = indexer.index_single_file(path)
        if outcome.error:
            self._lifecycle.log_processing_event(
                execution_id=execution_id,
                intake_event_id=None,
                stage="admin_document_reindex_error",
                status="error",
                details={
                    "document_id": str(document_id),
                    "filename": source_fn or path.name,
                },
                error_text=str(outcome.error)[:8000],
            )
            return {
                "success": False,
                "error": outcome.error,
                "chunks": outcome.chunks,
                "document_id": str(document_id),
            }
        self._lifecycle.log_processing_event(
            execution_id=execution_id,
            intake_event_id=None,
            stage="admin_document_reindex_done",
            status="success",
            details={
                "document_id": str(document_id),
                "filename": source_fn or path.name,
                "chunks": outcome.chunks,
            },
        )
        return {
            "success": True,
            "error": None,
            "chunks": outcome.chunks,
            "document_id": str(document_id),
        }

    def get_document_detail_bundle(
        self,
        document_id: uuid.UUID,
        *,
        version_number: int | None = None,
    ) -> dict[str, Any]:
        """Document row, versions, chunk rows, FS preview, and raw timeline rows."""
        if not (os.getenv("DATABASE_URL") or "").strip():
            return {"error": "postgres_unavailable"}
        try:
            with get_connection() as conn:
                doc = self._doc_repo.get_document(conn, document_id)
                if not doc:
                    return {"error": "not_found"}
                versions = self._doc_repo.list_document_versions(conn, document_id)
                chunk_counts_by_version = (
                    self._doc_repo.count_chunks_by_version_for_document(
                        conn, document_id
                    )
                )
                selected: dict[str, Any] | None = None
                if version_number is not None:
                    for v in versions:
                        if int(v.get("version_number") or 0) == int(version_number):
                            selected = v
                            break
                if selected is None:
                    for v in versions:
                        if v.get("is_active"):
                            selected = v
                            break
                if selected is None and versions:
                    selected = versions[-1]
                chunks_raw: list[dict[str, Any]] = []
                chunks_in_db = 0
                version_uuid: uuid.UUID | None = None
                if selected:
                    vid = selected.get("version_id")
                    if vid:
                        version_uuid = uuid.UUID(str(vid))
                        chunks_in_db = self._doc_repo.count_chunks_for_version(
                            conn, version_uuid
                        )
                        chunks_raw = self._doc_repo.list_chunks_for_version(
                            conn, version_uuid, limit=200
                        )
                timeline_rows = self._proc_repo.list_logs_for_document_filename(
                    conn,
                    filename=str(doc.get("source_filename") or ""),
                    limit=120,
                )
                conn.commit()
        except Exception as exc:
            return {"error": "load_failed", "message": str(exc)}

        path = Path(str(doc.get("storage_path") or ""))
        if not path.is_file():
            alt = self._documents_dir / str(doc.get("source_filename") or "")
            if alt.is_file():
                path = alt
        file_size_bytes: int | None = None
        try:
            if path.is_file():
                file_size_bytes = int(path.stat().st_size)
        except OSError:
            file_size_bytes = None
        text_preview = _read_kb_text_preview(path, 12000)
        declared = int((selected or {}).get("chunk_count") or 0)
        doc_id_str = str(doc.get("document_id") or "")
        chunk_sync_ok = True
        if selected and version_uuid:
            chunk_sync_ok = chunks_in_db == declared

        sel_vid_str = str(version_uuid) if version_uuid else None
        chunks_sync_diagnostic: str | None = None
        if selected and version_uuid:
            if chunks_in_db == 0 and declared > 0:
                parts = [
                    f"В document_versions заявлено {declared} чанков, но строк в "
                    f"document_chunks для version_id={sel_vid_str} не найдено "
                    f"(document_id={doc_id_str})."
                ]
                other_parts: list[str] = []
                for row in chunk_counts_by_version:
                    vid = str(row.get("version_id") or "")
                    if vid and vid != sel_vid_str:
                        other_parts.append(
                            f"{vid}: {int(row.get('row_count') or 0)}"
                        )
                if other_parts:
                    parts.append(
                        " Обнаружены строки у других версий этого документа: "
                        + ", ".join(other_parts)
                        + "."
                    )
                else:
                    parts.append(
                        " Действие: выполните «Переиндексировать документ» "
                        "(метаданные чанков записываются в document_chunks при индексации)."
                    )
                chunks_sync_diagnostic = "".join(parts)
            elif chunks_in_db > 0 and declared != chunks_in_db:
                chunks_sync_diagnostic = (
                    f"Заявлено в версии: {declared}; найдено в document_chunks: "
                    f"{chunks_in_db} (version_id={sel_vid_str}). "
                    "Рекомендуется переиндексировать документ."
                )

        active_row = next((v for v in versions if v.get("is_active")), None)
        active_out: dict[str, Any] | None = None
        if active_row:
            active_out = dict(active_row)
            ix = active_out.get("indexed_at")
            if isinstance(ix, datetime):
                active_out["indexed_at"] = ix.astimezone(timezone.utc).isoformat()

        last_err: str | None = None
        for ev in timeline_rows:
            st = str(ev.get("status") or "")
            et = ev.get("error_text")
            if st == "error" or et:
                t = str(et).strip() if et else None
                if t:
                    last_err = t
                elif st == "error":
                    last_err = "error (no message)"

        doc_out = dict(doc)
        for key in ("created_at", "updated_at"):
            v = doc_out.get(key)
            if isinstance(v, datetime):
                doc_out[key] = v.astimezone(timezone.utc).isoformat()

        versions_out = []
        for v in versions:
            vo = dict(v)
            ix = vo.get("indexed_at")
            if isinstance(ix, datetime):
                vo["indexed_at"] = ix.astimezone(timezone.utc).isoformat()
            versions_out.append(vo)
        sel_out = dict(selected) if selected else None
        if sel_out:
            ix = sel_out.get("indexed_at")
            if isinstance(ix, datetime):
                sel_out["indexed_at"] = ix.astimezone(timezone.utc).isoformat()

        chunks_out: list[dict[str, Any]] = []
        for c in chunks_raw:
            co = dict(c)
            ca = co.get("created_at")
            if isinstance(ca, datetime):
                co["created_at"] = ca.astimezone(timezone.utc).isoformat()
            chunks_out.append(co)

        cfg = self._config
        embed_model = getattr(cfg, "openai_embedding_model", None) or "—"

        cc_norm = [
            {
                "version_id": str(r.get("version_id") or ""),
                "row_count": int(r.get("row_count") or 0),
            }
            for r in chunk_counts_by_version
        ]

        return {
            "document": doc_out,
            "versions": versions_out,
            "selected_version": sel_out,
            "active_version": active_out,
            "selected_version_id": sel_vid_str,
            "chunks": chunks_out,
            "chunks_in_db": chunks_in_db,
            "chunk_count_declared": declared,
            "chunks_sync_ok": chunk_sync_ok,
            "chunks_sync_diagnostic": chunks_sync_diagnostic,
            "chunk_counts_by_version": cc_norm,
            "text_preview": text_preview,
            "preview_available": text_preview is not None,
            "embedding_model": embed_model,
            "file_size_bytes": file_size_bytes,
            "timeline_rows": timeline_rows,
            "last_error_message": last_err,
        }

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
        reindex_runs, sessions_total, by_status, by_stage, by_route, rag_quality.

        ``by_status`` contains only ``success`` and ``error`` (for the dashboard table).
        ``by_route`` counts only ``route_selected`` / ``processing_done`` with a known
        normalized route family (``rag``, ``text``, ``image_generation``, ``audio``).
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
            "sessions_total": 0,
            "by_status": {},
            "by_stage": {},
            "by_route": {
                "rag": 0,
                "text": 0,
                "image_generation": 0,
                "audio": 0,
            },
            "rag_quality": dict(empty_rq),
        }
        if not (os.getenv("DATABASE_URL") or "").strip():
            return empty
        try:
            with get_connection() as conn:
                total = self._proc_repo.count_events_since(conn, hours=h)
                sessions_total = self._proc_repo.count_unique_execution_ids_since(
                    conn, hours=h
                )
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
            "audio": int(by_route_raw.get("audio", 0)),
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
            "sessions_total": int(sessions_total),
            "by_status": by_status_dashboard,
            "by_stage": dict(by_stage),
            "by_route": by_route,
            "rag_quality": rag_quality,
        }

    def get_summary_payload(self, hours: int = 24) -> dict[str, Any]:
        """
        Compact aggregates for admin Summary (React). Reuses ``get_dashboard_stats``.

        Events: ``total`` = ``success`` + ``error`` + ``other`` (``other`` absorbs
        non-terminal / missing statuses vs raw row totals).

        Routes: session counts per normalized route family from ``count_routes_since``
        (distinct ``execution_id``); ``other_unknown`` reconciles against
        ``sessions_total`` from ``count_unique_execution_ids_since``.

        Telemetry: capped tail of ``processing_logs`` rows filtered into the window —
        row-level sample, not traffic share.
        """
        h = max(1, min(int(hours), 24 * 365))
        dash = self.get_dashboard_stats(hours=h)
        total_e = int(dash["total_events"])
        succ = int(dash["success_events"])
        err = int(dash["error_events"])
        other_e = max(0, total_e - succ - err)
        sessions_total = int(dash["sessions_total"])
        br = dash.get("by_route") or {}
        text_r = int(br.get("text", 0))
        rag_r = int(br.get("rag", 0))
        img_r = int(br.get("image_generation", 0))
        aud_r = int(br.get("audio", 0))
        routed_known = text_r + rag_r + img_r + aud_r
        other_unknown = max(0, sessions_total - routed_known)

        by_stage_raw = dash.get("by_stage") or {}
        by_stage = (
            {str(k): int(v) for k, v in by_stage_raw.items()}
            if isinstance(by_stage_raw, dict)
            else {}
        )
        lifecycle_rows: list[dict[str, Any]] = []
        for stage in SUMMARY_LIFECYCLE_STAGE_ORDER:
            c = int(by_stage.get(stage, 0))
            if c > 0:
                lifecycle_rows.append({"stage": stage, "events": c})

        voice_ev = sum(by_stage.get(s, 0) for s in _AUDIO_PIPELINE_STAGES)

        logs = self.get_recent_logs(limit=SUMMARY_LOG_SAMPLE_CAP)
        rows_win = _summary_filter_rows_since_hours(logs, hours=h)
        tel = _summary_telemetry_sample(rows_win)

        return {
            "hours": h,
            "events": {
                "total": total_e,
                "success": succ,
                "error": err,
                "other": other_e,
            },
            "sessions": {"unique_execution_ids": sessions_total},
            "routes": {
                "text": text_r,
                "rag": rag_r,
                "images": img_r,
                "audio_voice": aud_r,
                "other_unknown": other_unknown,
            },
            "lifecycle_events": lifecycle_rows,
            "telemetry_sample": {
                "scope": "recent_log_rows_tail_filtered_to_window",
                "cap": SUMMARY_LOG_SAMPLE_CAP,
                "rows_considered": len(logs),
                "rows_in_window": len(rows_win),
                **tel,
            },
            "admin_events": int(dash.get("admin_events", 0)),
            "reindex_starts": int(dash.get("reindex_runs", 0)),
            "audio_voice_counts": {
                "sessions_route_bucket": aud_r,
                "voice_pipeline_stage_events": voice_ev,
            },
        }
