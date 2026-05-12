"""Admin UI / tooling: documents listing, vector index status, reindex, PostgreSQL logs."""

from __future__ import annotations

import os
import shutil
import time
import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from collections import defaultdict
from typing import Any, cast
import mimetypes

from repositories.connection import get_connection
from repositories.document_repository import DocumentRepository
from repositories.platform_settings_repository import (
    KEY_RETRIEVAL_TUNING,
    PlatformSettingsRepository,
)
from repositories.processing_logs_repository import ProcessingLogsRepository
from services.admin_knowledge_indexer import AdminKnowledgeIndexer, FileIndexOutcome
from services.asset_repository import AssetNotFoundError, AssetValidationError
from services.asset_repository_factory import create_asset_repository
from services.async_job_service import AsyncJob, AsyncJobService
from services.audio_browser_preview import ensure_mp3_browser_preview, needs_browser_mp3_preview
from providers.rag_embeddings import build_openai_embeddings
from services.rag_chroma_store import count_chroma_chunks
from services.rag_document_loader import iter_supported_files
from services.retrieval.faiss_backend import count_faiss_chunks_on_disk, resolve_faiss_index_dir
from services.retrieval.weaviate_backend import weaviate_collection_count_best_effort
from services.retrieval.retrieval_tuning import (
    TUNING_INDEXING_KEYS,
    TUNING_REQUIRES_REINDEX_KEYS,
    TUNING_RUNTIME_KEYS,
    apply_db_overrides_to_config,
    field_sources_from_db,
    load_retrieval_tuning_db,
    strip_db_keys_matching_env,
    tuning_effective_values,
    validate_and_normalize_patch,
)
from services.retrieval.retrieval_tuning_resolver import RetrievalTuningResolver
from services.retrieval.factory import (
    KNOWN_RAG_BACKENDS,
    build_retrieval_backend,
    effective_rag_backend_from_sources,
    normalize_rag_backend,
)
from services.preprocessing.preprocessing_service import PreprocessingService
from services.runtime_lifecycle_service import RuntimeLifecycleService
from utils.config import AppConfig, load_config

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_EFFECTIVE_RAG_BACKEND_CACHE_TTL_S = 2.5


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
    "image_received",
    "ocr_started",
    "ocr_done",
    "ocr_error",
    "ocr_response_sent",
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
    "admin_document_uploaded_raw",
    "document_preprocessing_started",
    "document_preprocessing_done",
    "document_preprocessing_error",
    "document_processed_artifact_saved",
    "document_compatibility_file_written",
    "document_indexing_started",
    "document_indexing_done",
    "document_indexing_error",
    "document_upload_pipeline_done",
    "admin_document_uploaded",
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


def _preprocessing_pipeline_component_names(ext: str) -> tuple[str, str, str]:
    """Stable machine-readable names for upload pipeline logs (Phase 1)."""
    if ext in (".html", ".htm"):
        return "HtmlExtractor", "html_cleaner + text_cleaner", "text_normalizer"
    return "TxtExtractor", "text_cleaner", "text_normalizer"


def _rag_extra_compatibility_write_roots(*, primary_root: Path) -> list[Path]:
    """
    Directories where cleaned ``{stem}.txt`` should be mirrored in addition to
    ``RAG_DOCUMENTS_DIR``.

    - ``RAG_DOCUMENTS_COMPATIBILITY_DIR`` when set and distinct from primary.
    - ``/app/data/documents`` when it exists (Docker compose bind mount) and
      differs from primary — fixes uploads when ``RAG_DOCUMENTS_DIR`` points
      outside the mounted corpus path.
    """
    primary_resolved = primary_root.resolve()
    seen: set[str] = {str(primary_resolved)}
    out: list[Path] = []
    env_raw = (os.getenv("RAG_DOCUMENTS_COMPATIBILITY_DIR") or "").strip()
    if env_raw:
        e = _resolve_dir(env_raw)
        key = str(e.resolve())
        if key not in seen:
            seen.add(key)
            out.append(e)
    docker_compat = Path("/app/data/documents")
    try:
        if docker_compat.is_dir():
            key = str(docker_compat.resolve())
            if key not in seen:
                seen.add(key)
                out.append(docker_compat)
    except OSError:
        pass
    return out


def _write_cleaned_rag_txt_everywhere(
    config: AppConfig, *, index_name: str, cleaned_bytes: bytes
) -> tuple[Path, list[Path]]:
    """Write canonical cleaned UTF-8 to primary ``RAG_DOCUMENTS_DIR`` and compatibility roots."""
    primary_root = _resolve_dir(config.rag_documents_dir)
    primary_root.mkdir(parents=True, exist_ok=True)
    primary = primary_root / index_name
    primary.write_bytes(cleaned_bytes)
    if not primary.is_file():
        raise RuntimeError(f"RAG primary write failed: {primary}")
    written: list[Path] = [primary]
    for root in _rag_extra_compatibility_write_roots(primary_root=primary_root):
        root.mkdir(parents=True, exist_ok=True)
        dest = root / index_name
        dest.write_bytes(cleaned_bytes)
        if not dest.is_file():
            raise RuntimeError(f"RAG compatibility mirror write failed: {dest}")
        written.append(dest)
    return primary, written


def _document_upload_log_snapshot_from_summary(us: dict[str, Any]) -> dict[str, Any]:
    """Common ``details`` shape for indexing / pipeline-done processing_logs rows."""
    pre = us.get("preprocessing")
    if not isinstance(pre, dict):
        pre = {}
    return {
        "upload_id": us.get("upload_id"),
        "execution_id": us.get("upload_id"),
        "original_upload_filename": us.get("original_upload_filename"),
        "indexed_target_filename": us.get("indexed_target_filename"),
        "raw_asset_ref": us.get("raw_asset_ref"),
        "processed_asset_ref": us.get("processed_asset_ref"),
        "cleaned_asset_ref": us.get("cleaned_asset_ref"),
        "compatibility_path": us.get("compatibility_path"),
        "compatibility_paths_written": us.get("compatibility_paths_written"),
        "preprocessing": pre,
        "original_size_bytes": us.get("original_bytes"),
        "cleaned_size_bytes": us.get("cleaned_bytes"),
        "extractor": us.get("extractor"),
        "cleaner": us.get("cleaner"),
        "normalizer": us.get("normalizer"),
    }


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
    active_retrieval_backend: str = "chroma"
    vector_index_chunk_count: int | None = None


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
        self._platform_repo = PlatformSettingsRepository()
        self._proc_repo = ProcessingLogsRepository()
        self._lifecycle = RuntimeLifecycleService()
        self._eff_rb_cache: str | None = None
        self._eff_rb_cache_ts: float = 0.0
        self._tuning_resolver: RetrievalTuningResolver | None = None

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

    @property
    def tuning_resolver(self) -> RetrievalTuningResolver:
        if self._tuning_resolver is None:
            self._tuning_resolver = RetrievalTuningResolver(self._config)
        return self._tuning_resolver

    def _invalidate_tuning_cache(self) -> None:
        if self._tuning_resolver is not None:
            self._tuning_resolver.invalidate()

    def _invalidate_effective_rag_backend_cache(self) -> None:
        self._eff_rb_cache = None

    def _effective_rag_backend_resolved(self) -> str:
        env_b = normalize_rag_backend(self._config.rag_backend)
        if not (self._config.database_url or "").strip():
            return env_b
        now = time.monotonic()
        if (
            self._eff_rb_cache is not None
            and (now - self._eff_rb_cache_ts) < _EFFECTIVE_RAG_BACKEND_CACHE_TTL_S
        ):
            return self._eff_rb_cache
        try:
            with get_connection() as conn:
                db_v = self._platform_repo.peek_active_rag_backend(conn)
            eff = effective_rag_backend_from_sources(
                env_backend=env_b,
                db_backend=db_v,
            )
        except Exception:
            eff = env_b
        self._eff_rb_cache = eff
        self._eff_rb_cache_ts = now
        return eff

    def _indexing_config(self) -> AppConfig:
        eff = self.tuning_resolver.effective_config()
        return replace(
            eff,
            rag_backend=self._effective_rag_backend_resolved(),
        )

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

    def save_uploaded_document(self, filename: str, data: bytes) -> tuple[Path, dict[str, Any]]:
        """
        Raw asset (immutable) → preprocessing → cleaned UTF-8 → RAG compatibility ``.txt``.

        Returns ``(index_path, upload_summary)`` where ``index_path`` is always
        ``RAG_DOCUMENTS_DIR / {stem}.txt`` (canonical input for chunking/indexing).

        Emits machine stages for observability (same ``execution_id`` / ``upload_id``
        for correlation). Cleaned bytes are also mirrored under
        ``/app/data/documents`` or ``RAG_DOCUMENTS_COMPATIBILITY_DIR`` when those
        paths differ from the resolved primary ``RAG_DOCUMENTS_DIR``.
        """
        safe = Path(filename).name
        ext = Path(safe).suffix.lower()
        if ext not in (".txt", ".html", ".htm"):
            raise ValueError("Only .txt, .html, .htm uploads are supported.")
        if not safe or safe in (".", ".."):
            raise ValueError("Invalid file name.")
        stem = Path(safe).stem
        if not stem:
            raise ValueError("Invalid file name (missing basename).")
        if not isinstance(data, (bytes, bytearray)) or len(data) == 0:
            raise ValueError("Uploaded file is empty.")

        pipeline_id = str(uuid.uuid4())
        index_name = f"{stem}.txt"
        extractor, cleaner, normalizer = _preprocessing_pipeline_component_names(ext)

        def _emit(
            stage: str,
            status: str,
            details: dict[str, Any],
            *,
            error_text: str | None = None,
        ) -> None:
            self._lifecycle.log_processing_event(
                execution_id=pipeline_id,
                intake_event_id=None,
                stage=stage,
                status=status,
                details=details,
                error_text=error_text,
            )

        raw_bytes = bytes(data)
        raw_ct = mimetypes.guess_type(safe)[0] or (
            "text/html" if ext in (".html", ".htm") else "text/plain"
        )
        raw_ref = self._asset_repository.save_bytes(
            raw_bytes,
            namespace="documents",
            filename=safe,
            content_type=raw_ct,
        )
        raw_src = self._asset_repository.resolve_path(raw_ref)
        if not raw_src.exists() or not raw_src.is_file():
            raise RuntimeError(f"AssetRepository raw asset not accessible: {raw_src}")

        base: dict[str, Any] = {
            "upload_id": pipeline_id,
            "execution_id": pipeline_id,
            "source": "admin_api",
            "filename": index_name,
            "source_filename": index_name,
            "original_upload_filename": safe,
            "indexed_target_filename": index_name,
            "raw_asset_ref": raw_ref.relative_path,
            "original_size_bytes": len(raw_bytes),
            "extractor": extractor,
            "cleaner": cleaner,
            "normalizer": normalizer,
            "rag_documents_dir_config": self._config.rag_documents_dir,
            "rag_documents_dir_resolved": str(_resolve_dir(self._config.rag_documents_dir)),
        }
        _emit(
            "admin_document_uploaded_raw",
            "success",
            {
                **base,
                "content_type": raw_ct,
                "asset_storage_path": str(raw_src),
                "asset_storage_exists": raw_src.exists(),
                "size_bytes": raw_ref.size_bytes,
                "sha256": raw_ref.sha256,
            },
        )

        _emit(
            "document_preprocessing_started",
            "started",
            {**base, "preprocessing": {"status": "started"}},
        )

        preprocessor = PreprocessingService()
        try:
            cleaned_text, diag = preprocessor.run(raw_bytes, original_filename=safe)
        except Exception as exc:
            fmt = "html" if ext in (".html", ".htm") else "txt"
            fail_diag = PreprocessingService.failure_diag(
                original_filename=safe,
                original_bytes=len(raw_bytes),
                err=str(exc),
                fmt=cast(Any, fmt),
            ).to_log_dict()
            _emit(
                "document_preprocessing_error",
                "error",
                {
                    **base,
                    "preprocessing": fail_diag,
                    "cleaned_size_bytes": 0,
                    "processed_asset_ref": None,
                    "cleaned_asset_ref": None,
                    "compatibility_path": None,
                    "compatibility_paths_written": [],
                },
                error_text=str(exc),
            )
            raise

        cleaned_bytes = cleaned_text.encode("utf-8")
        pre_block = diag.to_log_dict()
        _emit(
            "document_preprocessing_done",
            "success",
            {
                **base,
                "preprocessing": pre_block,
                "cleaned_size_bytes": len(cleaned_bytes),
            },
        )

        cleaned_fname = f"{stem}.cleaned.txt"
        cleaned_ref = self._asset_repository.save_bytes(
            cleaned_bytes,
            namespace="processed_documents",
            filename=cleaned_fname,
            content_type="text/plain",
        )
        cleaned_src = self._asset_repository.resolve_path(cleaned_ref)
        if not cleaned_src.exists() or not cleaned_src.is_file():
            raise RuntimeError(
                f"AssetRepository cleaned artifact not accessible: {cleaned_src}"
            )

        base["processed_asset_ref"] = cleaned_ref.relative_path
        base["cleaned_asset_ref"] = cleaned_ref.relative_path

        _emit(
            "document_processed_artifact_saved",
            "success",
            {
                **base,
                "preprocessing": pre_block,
                "cleaned_size_bytes": cleaned_ref.size_bytes,
                "cleaned_asset_path": str(cleaned_src),
            },
        )

        dest, all_written = _write_cleaned_rag_txt_everywhere(
            self._config, index_name=index_name, cleaned_bytes=cleaned_bytes
        )
        primary_root = _resolve_dir(self._config.rag_documents_dir)
        _emit(
            "document_compatibility_file_written",
            "success",
            {
                **base,
                "preprocessing": pre_block,
                "cleaned_size_bytes": cleaned_ref.size_bytes,
                "compatibility_path": str(dest),
                "compatibility_paths_written": [str(p) for p in all_written],
                "compatibility_primary_equals_config": str(dest.resolve())
                == str((primary_root / index_name).resolve()),
            },
        )

        upload_summary: dict[str, Any] = {
            "upload_id": pipeline_id,
            "original_upload_filename": safe,
            "indexed_target_filename": index_name,
            "preprocessing": pre_block,
            "raw_asset_ref": raw_ref.relative_path,
            "cleaned_asset_ref": cleaned_ref.relative_path,
            "processed_asset_ref": cleaned_ref.relative_path,
            "original_bytes": len(raw_bytes),
            "cleaned_bytes": len(cleaned_bytes),
            "compatibility_path": str(dest),
            "compatibility_paths_written": [str(p) for p in all_written],
            "extractor": extractor,
            "cleaner": cleaner,
            "normalizer": normalizer,
        }
        return dest, upload_summary

    def save_uploaded_txt(self, filename: str, data: bytes) -> Path:
        """Backward-compatible wrapper: same as ``save_uploaded_document`` but returns path only."""
        dest, _summary = self.save_uploaded_document(filename, data)
        return dest

    def get_collection_count(self) -> int:
        """Chunk count in the active vector index (Chroma, FAISS, or Weaviate), same semantics as CLI /stats."""
        rb = self._effective_rag_backend_resolved()
        if rb == "faiss":
            idx = resolve_faiss_index_dir(self._config, project_root=_PROJECT_ROOT)
            return count_faiss_chunks_on_disk(idx)
        if rb == "weaviate":
            try:
                embeddings = build_openai_embeddings(self._config)
            except Exception:
                return 0
            try:
                n = weaviate_collection_count_best_effort(
                    self._config, embeddings=embeddings
                )
                return int(n) if n is not None else 0
            except Exception:
                return 0
        return count_chroma_chunks(self._config, persist_path=self._chroma_dir)

    def get_knowledge_base_status(self) -> KnowledgeBaseStatus:
        vector_n = self.get_collection_count()
        rb = self._effective_rag_backend_resolved()
        db_url = (self._config.database_url or "").strip()
        if not db_url:
            return KnowledgeBaseStatus(
                collection_count=vector_n,
                postgres_documents=None,
                postgres_chunks_sum=None,
                postgres_available=False,
                active_retrieval_backend=rb,
                vector_index_chunk_count=vector_n,
            )
        try:
            with get_connection() as conn:
                doc_n = self._doc_repo.count_documents(conn)
                chunk_sum = self._doc_repo.sum_version_chunk_counts(conn)
                conn.commit()
            return KnowledgeBaseStatus(
                collection_count=vector_n,
                postgres_documents=doc_n,
                postgres_chunks_sum=chunk_sum,
                postgres_available=True,
                active_retrieval_backend=rb,
                vector_index_chunk_count=vector_n,
            )
        except Exception:
            return KnowledgeBaseStatus(
                collection_count=vector_n,
                postgres_documents=None,
                postgres_chunks_sum=None,
                postgres_available=False,
                active_retrieval_backend=rb,
                vector_index_chunk_count=vector_n,
            )

    def _probe_retrieval_backend_health(self, backend_name: str) -> dict[str, Any]:
        """Одноразовый health/collection snapshot для overview (независимо от active)."""
        name = normalize_rag_backend(backend_name)
        if name not in KNOWN_RAG_BACKENDS:
            return {
                "backend": name,
                "ok": False,
                "detail": "unknown_backend",
                "collection_count": None,
            }
        cfg = replace(self._config, rag_backend=name)
        try:
            emb = build_openai_embeddings(self._config)
        except ValueError as exc:
            return {
                "backend": name,
                "ok": False,
                "detail": str(exc),
                "collection_count": None,
            }
        be: Any = None
        try:
            if name == "chroma":
                from services.rag_chroma_store import ChromaRagStore
                from services.retrieval.chroma_backend import ChromaBackend

                cdir = self._chroma_dir
                if not cfg.chroma_use_http:
                    cdir.mkdir(parents=True, exist_ok=True)
                store = ChromaRagStore(cfg, emb, persist_directory=cdir)
                be = ChromaBackend(store)
            else:
                be = build_retrieval_backend(cfg, chroma_store=None, embeddings=emb)
            h = be.healthcheck()
            n = h.collection_count
            if n is None:
                try:
                    n = int(be.collection_count())
                except Exception:
                    n = None
            return {
                "backend": name,
                "ok": h.ok,
                "detail": h.detail,
                "collection_count": n,
            }
        except Exception as exc:
            return {
                "backend": name,
                "ok": False,
                "detail": f"{type(exc).__name__}: {exc}",
                "collection_count": None,
            }
        finally:
            if be is not None:
                closer = getattr(be, "close", None)
                if callable(closer):
                    try:
                        closer()
                    except Exception:
                        pass

    def get_retrieval_overview(self) -> dict[str, Any]:
        """Сводка для Admin API: env vs DB vs effective + health по каждому backend."""
        env_default = normalize_rag_backend(self._config.rag_backend)
        db_active: str | None = None
        degraded_detail: str | None = None
        if (self._config.database_url or "").strip():
            try:
                with get_connection() as conn:
                    db_active = self._platform_repo.peek_active_rag_backend(conn)
            except Exception as exc:
                degraded_detail = f"{type(exc).__name__}: {exc}"
        effective = effective_rag_backend_from_sources(
            env_backend=env_default,
            db_backend=db_active,
        )
        allowed = sorted(KNOWN_RAG_BACKENDS)
        backends = {b: self._probe_retrieval_backend_health(b) for b in allowed}
        active_h = backends.get(effective, {})
        warnings: list[str] = []
        if degraded_detail:
            warnings.append(f"postgres_read:{degraded_detail}")
        if not active_h.get("ok"):
            warnings.append(
                f"active_backend_health:{effective}:{active_h.get('detail')}"
            )
        out: dict[str, Any] = {
            "database_configured": bool((self._config.database_url or "").strip()),
            "env_default_backend": env_default,
            "db_active_backend": db_active,
            "effective_backend": effective,
            "allowed_backends": allowed,
            "degraded": degraded_detail is not None,
            "warnings": warnings,
            "backends": backends,
            "active_backend_health": active_h,
        }
        out.update(self._retrieval_settings_public_snapshot())
        return out

    def get_retrieval_platform_compact(self) -> dict[str, Any]:
        """
        High-level retrieval platform snapshot for Overview / Documents (no tuning matrix).
        Reuses ``get_retrieval_overview`` probes (multi-backend).
        """
        ro = self.get_retrieval_overview()
        active_h = ro.get("active_backend_health") or {}
        ok = bool(active_h.get("ok"))
        cnt_raw = active_h.get("collection_count")
        try:
            cnt_i = int(cnt_raw) if cnt_raw is not None else None
        except (TypeError, ValueError):
            cnt_i = None
        if not ok:
            readiness = "DOWN"
        elif cnt_i is None:
            readiness = "UNKNOWN"
        elif cnt_i == 0:
            readiness = "EMPTY"
        else:
            readiness = "READY"
        eff = str(ro.get("effective_backend") or "unknown").strip().lower()
        backends_compact: dict[str, Any] = {}
        for name, h in sorted((ro.get("backends") or {}).items()):
            bok = bool(h.get("ok"))
            bc = h.get("collection_count")
            try:
                bi = int(bc) if bc is not None else None
            except (TypeError, ValueError):
                bi = None
            if not bok:
                br = "DOWN"
            elif bi is None:
                br = "UNKNOWN"
            elif bi == 0:
                br = "EMPTY"
            else:
                br = "READY"
            backends_compact[name] = {"ok": bok, "count": bi, "readiness": br}
        reindex_recommended = (not ok) or (cnt_i is not None and cnt_i == 0)
        return {
            "effective_backend": eff,
            "active_readiness": readiness,
            "active_ok": ok,
            "active_collection_count": cnt_i,
            "backends_compact": backends_compact,
            "reindex_recommended": bool(reindex_recommended),
        }

    def _retrieval_settings_public_snapshot(self) -> dict[str, Any]:
        """Tuning/paths for Admin UI (no secrets). Effective tuning merges env + DB overrides."""
        c = self._config
        eff = self.tuning_resolver.effective_config()
        db: dict[str, Any] = {}
        if (c.database_url or "").strip():
            try:
                with get_connection() as conn:
                    db = load_retrieval_tuning_db(conn)
            except Exception:
                db = {}
        fs = field_sources_from_db(db)
        db_ok = bool((c.database_url or "").strip())
        return {
            "runtime_tuning": {
                "rag_top_k": eff.rag_top_k,
                "rag_max_distance": eff.rag_max_distance,
                "rag_answer_max_tokens": eff.rag_answer_max_tokens,
                "rag_retrieval_timeout": eff.rag_retrieval_timeout,
                "rag_embedding_request_timeout": eff.rag_embedding_request_timeout,
                "field_sources": {k: fs[k] for k in sorted(TUNING_RUNTIME_KEYS)},
                "editable_via_api": db_ok,
                "planned_note": (
                    "GET/PUT /api/retrieval/tuning when DATABASE_URL is set; "
                    "Telegram RAG picks up runtime fields within ~2.5s."
                ),
            },
            "indexing_tuning": {
                "rag_chunk_size": eff.rag_chunk_size,
                "rag_chunk_overlap": eff.rag_chunk_overlap,
                "field_sources": {k: fs[k] for k in sorted(TUNING_INDEXING_KEYS)},
                "editable_via_api": db_ok,
                "reindex_warning": (
                    "Changing chunk size/overlap requires full reindex of the active vector backend."
                ),
            },
            "cache": {
                "enable_retrieval_cache": c.enable_retrieval_cache,
                "enable_answer_cache": c.enable_answer_cache,
                "retrieval_cache_ttl_seconds": c.retrieval_cache_ttl_seconds,
                "answer_cache_ttl_seconds": c.answer_cache_ttl_seconds,
                "rag_retrieval_generation": (os.getenv("RAG_RETRIEVAL_GENERATION") or "").strip()
                or None,
                "cache_db_path": c.cache_db_path,
                "rag_retrieval_generation_hint": (
                    "Bump RAG_RETRIEVAL_GENERATION after corpus reindex when retrieval cache is enabled."
                ),
                "editable_via_api": False,
            },
            "paths": {
                "chroma_host": c.chroma_host,
                "chroma_port": c.chroma_port,
                "chroma_use_http": c.chroma_use_http,
                "chroma_persist_dir": c.chroma_persist_dir,
                "rag_documents_dir": c.rag_documents_dir,
                "faiss_index_dir": c.faiss_index_dir,
                "weaviate_url": (c.weaviate_url or "").strip() or None,
                "weaviate_host": c.weaviate_host,
                "weaviate_http_port": c.weaviate_http_port,
                "weaviate_grpc_port": c.weaviate_grpc_port,
                "cache_db_path": c.cache_db_path,
            },
        }

    def _retrieval_tuning_api_core(self) -> dict[str, Any]:
        base = self._config
        db: dict[str, Any] = {}
        if (base.database_url or "").strip():
            try:
                with get_connection() as conn:
                    db = load_retrieval_tuning_db(conn)
            except Exception:
                db = {}
        eff = apply_db_overrides_to_config(base, db)
        return {
            "effective": tuning_effective_values(eff),
            "env_defaults": tuning_effective_values(base),
            "db_overrides": dict(db),
            "requires_reindex_keys": sorted(TUNING_REQUIRES_REINDEX_KEYS),
            "runtime_keys": sorted(TUNING_RUNTIME_KEYS),
        }

    def get_retrieval_tuning(self) -> dict[str, Any]:
        """GET /api/retrieval/tuning — effective + env + DB overrides."""
        return self._retrieval_tuning_api_core()

    def put_retrieval_tuning(self, patch: dict[str, Any]) -> dict[str, Any]:
        """PUT /api/retrieval/tuning — partial merge, validate, strip keys matching env."""
        if not (self._config.database_url or "").strip():
            raise ValueError("DATABASE_URL not configured")
        with get_connection() as conn:
            db_existing = load_retrieval_tuning_db(conn)
            before_eff = apply_db_overrides_to_config(self._config, db_existing)
            normalized = validate_and_normalize_patch(self._config, db_existing, patch)
            merged = {**db_existing, **normalized}
            merged = strip_db_keys_matching_env(merged, self._config)
            if merged:
                self._platform_repo.set_setting(conn, KEY_RETRIEVAL_TUNING, merged)
            else:
                self._platform_repo.delete_setting(conn, KEY_RETRIEVAL_TUNING)
            conn.commit()
        self._invalidate_tuning_cache()
        after_eff = self.tuning_resolver.effective_config()
        reindex_required = any(
            getattr(before_eff, k) != getattr(after_eff, k) for k in TUNING_REQUIRES_REINDEX_KEYS
        )
        out = self._retrieval_tuning_api_core()
        out["reindex_required"] = reindex_required
        return out

    def delete_retrieval_tuning(self) -> dict[str, Any]:
        """DELETE /api/retrieval/tuning — clear all DB overrides."""
        if not (self._config.database_url or "").strip():
            raise ValueError("DATABASE_URL not configured")
        with get_connection() as conn:
            db_existing = load_retrieval_tuning_db(conn)
            before_eff = apply_db_overrides_to_config(self._config, db_existing)
            self._platform_repo.delete_setting(conn, KEY_RETRIEVAL_TUNING)
            conn.commit()
        self._invalidate_tuning_cache()
        after_eff = self.tuning_resolver.effective_config()
        reindex_required = any(
            getattr(before_eff, k) != getattr(after_eff, k) for k in TUNING_REQUIRES_REINDEX_KEYS
        )
        out = self._retrieval_tuning_api_core()
        out["reindex_required"] = reindex_required
        return out

    def set_active_retrieval_backend(self, backend: str) -> dict[str, Any]:
        """Persist active backend; allow switch with warnings if target health not ok."""
        name = normalize_rag_backend(backend)
        if name not in KNOWN_RAG_BACKENDS:
            raise ValueError(
                f"unsupported backend {name!r}; allowed: {', '.join(sorted(KNOWN_RAG_BACKENDS))}"
            )
        if not (self._config.database_url or "").strip():
            raise ValueError("DATABASE_URL not configured")
        warnings: list[str] = []
        snap = self._probe_retrieval_backend_health(name)
        if not snap.get("ok"):
            warnings.append(f"target_health_not_ok:{snap.get('detail')}")
        with get_connection() as conn:
            eff = self._platform_repo.set_active_rag_backend(conn, name)
            conn.commit()
        self._invalidate_effective_rag_backend_cache()
        return {
            "effective_backend": eff,
            "warnings": warnings,
            "target_health": snap,
        }

    def run_reindex(self) -> ReindexRunResult:
        """Full vector index reset + index from RAG_DOCUMENTS_DIR (same as admin CLI --reindex)."""
        execution_id = str(uuid.uuid4())
        rb = self._effective_rag_backend_resolved()
        try:
            doc_count_started = len(iter_supported_files(self._documents_dir))
        except FileNotFoundError:
            doc_count_started = 0

        started_details: dict[str, Any] = {
            "documents_count": doc_count_started,
            "chunks_count": 0,
            "retrieval_backend": rb,
        }
        if rb == "faiss":
            fdir = resolve_faiss_index_dir(self._config, project_root=_PROJECT_ROOT)
            started_details["backend_index_path"] = str(fdir)
            started_details["manifest_path"] = str(fdir / "manifest.json")

        self._lifecycle.log_processing_event(
            execution_id=execution_id,
            intake_event_id=None,
            stage="admin_reindex_started",
            status="started",
            details=started_details,
        )

        indexer = AdminKnowledgeIndexer(
            self._indexing_config(),
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
                    "retrieval_backend": self._effective_rag_backend_resolved(),
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

        details_done: dict[str, Any] = {
            "documents_count": report.files_found,
            "chunks_count": report.vector_index_chunk_count,
            "retrieval_backend": rb,
            "vector_count": report.vector_index_chunk_count,
        }
        if rb == "faiss":
            fdir = resolve_faiss_index_dir(self._config, project_root=_PROJECT_ROOT)
            details_done["backend_index_path"] = str(fdir)
            details_done["manifest_path"] = str(fdir / "manifest.json")
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
            collection_count=report.vector_index_chunk_count,
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
        if not (self._config.database_url or "").strip():
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
        if not (self._config.database_url or "").strip():
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
        if not (self._config.database_url or "").strip():
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
        if not (self._config.database_url or "").strip():
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
        if not (self._config.database_url or "").strip():
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
        if not (self._config.database_url or "").strip():
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
        if not (self._config.database_url or "").strip():
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
        if not (self._config.database_url or "").strip():
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
        if not (self._config.database_url or "").strip():
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
        if not (self._config.database_url or "").strip():
            return []
        try:
            with get_connection() as conn:
                rows = self._doc_repo.list_document_versions(conn, document_id)
                conn.commit()
            return rows
        except Exception:
            return []

    def upload_txt_and_index(self, filename: str, data: bytes) -> dict[str, Any]:
        """Save document via preprocessing pipeline, then index canonical ``.txt``."""
        dest, upload_summary = self.save_uploaded_document(filename, data)
        pipeline_id = str(upload_summary.get("upload_id") or uuid.uuid4())
        snap = _document_upload_log_snapshot_from_summary(upload_summary)
        self._lifecycle.log_processing_event(
            execution_id=pipeline_id,
            intake_event_id=None,
            stage="document_indexing_started",
            status="started",
            details={**snap, "index_path": str(dest)},
        )
        indexer = AdminKnowledgeIndexer(
            self._indexing_config(),
            documents_dir=self._documents_dir,
            chroma_dir=self._chroma_dir,
            use_postgres=True,
        )
        outcome: FileIndexOutcome | None = None
        try:
            outcome = indexer.index_single_file(dest)
        except Exception as exc:
            self._lifecycle.log_processing_event(
                execution_id=pipeline_id,
                intake_event_id=None,
                stage="document_indexing_error",
                status="error",
                details={**snap, "index_path": str(dest), "error": str(exc)},
                error_text=str(exc),
            )
            self._lifecycle.log_processing_event(
                execution_id=pipeline_id,
                intake_event_id=None,
                stage="document_upload_pipeline_done",
                status="error",
                details={
                    **snap,
                    "index_path": str(dest),
                    "success": False,
                    "error": str(exc),
                    "chunks": None,
                    "document_id": None,
                },
                error_text=str(exc),
            )
            return {
                "upload_id": pipeline_id,
                "filename": dest.name,
                "original_filename": upload_summary.get("original_upload_filename"),
                "path": str(dest),
                "success": False,
                "error": str(exc),
                "chunks": None,
                "document_id": None,
                "preprocessing": upload_summary.get("preprocessing"),
                "original_bytes": upload_summary.get("original_bytes"),
                "cleaned_bytes": upload_summary.get("cleaned_bytes"),
                "raw_asset_ref": upload_summary.get("raw_asset_ref"),
                "cleaned_asset_ref": upload_summary.get("cleaned_asset_ref"),
                "processed_asset_ref": upload_summary.get("processed_asset_ref"),
                "compatibility_path": upload_summary.get("compatibility_path"),
                "compatibility_paths_written": upload_summary.get(
                    "compatibility_paths_written"
                ),
            }

        assert outcome is not None
        doc_id = str(outcome.document_id) if outcome.document_id else None
        if outcome.error:
            self._lifecycle.log_processing_event(
                execution_id=pipeline_id,
                intake_event_id=None,
                stage="document_indexing_error",
                status="error",
                details={
                    **snap,
                    "index_path": str(dest),
                    "error": outcome.error,
                    "chunks": outcome.chunks,
                    "document_id": doc_id,
                },
                error_text=outcome.error,
            )
            self._lifecycle.log_processing_event(
                execution_id=pipeline_id,
                intake_event_id=None,
                stage="document_upload_pipeline_done",
                status="error",
                details={
                    **snap,
                    "index_path": str(dest),
                    "success": False,
                    "error": outcome.error,
                    "chunks": outcome.chunks,
                    "document_id": doc_id,
                },
                error_text=outcome.error,
            )
        else:
            self._lifecycle.log_processing_event(
                execution_id=pipeline_id,
                intake_event_id=None,
                stage="document_indexing_done",
                status="success",
                details={
                    **snap,
                    "index_path": str(dest),
                    "chunks": outcome.chunks,
                    "document_id": doc_id,
                },
            )
            self._lifecycle.log_processing_event(
                execution_id=pipeline_id,
                intake_event_id=None,
                stage="document_upload_pipeline_done",
                status="success",
                details={
                    **snap,
                    "index_path": str(dest),
                    "success": True,
                    "chunks": outcome.chunks,
                    "document_id": doc_id,
                },
            )

        return {
            "upload_id": pipeline_id,
            "filename": dest.name,
            "original_filename": upload_summary.get("original_upload_filename"),
            "path": str(dest),
            "success": outcome.error is None,
            "error": outcome.error,
            "chunks": outcome.chunks,
            "document_id": doc_id,
            "preprocessing": upload_summary.get("preprocessing"),
            "original_bytes": upload_summary.get("original_bytes"),
            "cleaned_bytes": upload_summary.get("cleaned_bytes"),
            "raw_asset_ref": upload_summary.get("raw_asset_ref"),
            "cleaned_asset_ref": upload_summary.get("cleaned_asset_ref"),
            "processed_asset_ref": upload_summary.get("processed_asset_ref"),
            "compatibility_path": upload_summary.get("compatibility_path"),
            "compatibility_paths_written": upload_summary.get(
                "compatibility_paths_written"
            ),
        }

    def reindex_document_file(self, document_id: uuid.UUID) -> dict[str, Any]:
        """Re-embed one on-disk document (no global Chroma reset)."""
        if not (self._config.database_url or "").strip():
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
        rb = self._effective_rag_backend_resolved()
        reindex_details: dict[str, Any] = {
            "document_id": str(document_id),
            "filename": source_fn or path.name,
            "path": str(path),
            "retrieval_backend": rb,
        }
        if rb == "faiss":
            fdir = resolve_faiss_index_dir(self._config, project_root=_PROJECT_ROOT)
            reindex_details["backend_index_path"] = str(fdir)
            reindex_details["manifest_path"] = str(fdir / "manifest.json")
        self._lifecycle.log_processing_event(
            execution_id=execution_id,
            intake_event_id=None,
            stage="admin_document_reindex_started",
            status="started",
            details=reindex_details,
        )
        indexer = AdminKnowledgeIndexer(
            self._indexing_config(),
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
        done_details: dict[str, Any] = {
            "document_id": str(document_id),
            "filename": source_fn or path.name,
            "chunks": outcome.chunks,
            "retrieval_backend": rb,
            "vector_count": self.get_collection_count(),
        }
        if rb == "faiss":
            fdir_done = resolve_faiss_index_dir(self._config, project_root=_PROJECT_ROOT)
            done_details["backend_index_path"] = str(fdir_done)
            done_details["manifest_path"] = str(fdir_done / "manifest.json")
        self._lifecycle.log_processing_event(
            execution_id=execution_id,
            intake_event_id=None,
            stage="admin_document_reindex_done",
            status="success",
            details=done_details,
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
        if not (self._config.database_url or "").strip():
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
        if not (self._config.database_url or "").strip():
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
                "document": 0,
            },
            "rag_quality": dict(empty_rq),
        }
        if not (self._config.database_url or "").strip():
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
            "document": int(by_route_raw.get("document", 0)),
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
        doc_r = int(br.get("document", 0))
        routed_known = text_r + rag_r + img_r + aud_r + doc_r
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
                "documents": doc_r,
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
