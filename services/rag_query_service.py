"""Read-only RAG: retrieve from Chroma and compose an answer via LLM."""

from __future__ import annotations

import concurrent.futures
import hashlib
import time
from typing import Sequence

from langchain_core.documents import Document

from providers.openai_chat_provider import OpenAIChatProvider
from services.rag_chroma_store import RAG_CHROMA_COLLECTION_NAME
from services.retrieval.base import RetrievalBackend
from services.retrieval.runtime_manager import RetrievalBackendManager
from services.retrieval.retrieval_tuning_resolver import RetrievalTuningResolver
from services.retrieval_security.context import RetrievalSecurityContext
from services.conversational_context_assembly import (
    RagConversationalContextAssembly,
    build_rag_conversational_context,
)
from services.rag_types import (
    RagQueryResult,
    RagRequestDiagnostics,
    RagRetrievedChunkDiagnostics,
    RagSourceChunk,
)
from utils.config import AppConfig

_LLM_TIMEOUT_SEC = 30
_QUERY_PREVIEW_MAX = 200
_CHUNK_PREVIEW_MAX = 500
_CHUNK_CARD_PREVIEW_MAX = 220
_CHUNK_FULL_TEXT_LOG_MAX = 12_000


def _chunk_text_fingerprint(text: object) -> str:
    """Short stable fingerprint for dedupe / logs (not cryptographic)."""
    s = " ".join(str(text or "").split())
    if not s:
        return ""
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


def _real_retrieval_vector_key(meta: dict[str, object], backend_label: str) -> str | None:
    """
    Stable backend object id when present and not synthetic (see ``chunk_metadata`` contract).
    Returns None if only synthetic / rank-based ids exist.
    """
    be = (backend_label or "unknown").strip().lower() or "unknown"
    cid = str(meta.get("chunk_id") or "").strip()
    synth_pfx = f"{be}-synthetic-rank-"
    if cid and not cid.startswith(synth_pfx):
        return f"id:{cid}"
    for k in ("chroma_id", "vector_id", "uuid"):
        v = meta.get(k)
        if v is not None and str(v).strip():
            return f"{k}:{str(v).strip()}"
    alt = meta.get("id")
    if alt is not None and str(alt).strip():
        return f"id:{str(alt).strip()}"
    return None


def _dedupe_retrieval_raw_results(
    items: list[tuple[Document, float]],
    *,
    backend_label: str,
) -> tuple[list[tuple[Document, float]], int, int]:
    """
    Drop duplicate hits before relevance filter / diagnostics / LLM context.

    Primary: identical normalized body under the same ``source`` — ``(source, text_fp)``.
    Secondary: same real vector / chunk id (defensive if the backend returns one object twice).

    Synthetic ``chunk_id`` values (``{backend}-synthetic-rank-N``) do **not** bypass text dedupe.
    """
    if not items:
        return [], 0, 0
    raw_len = len(items)
    seen_src_fp: set[str] = set()
    seen_real_id: set[str] = set()
    out: list[tuple[Document, float]] = []
    for pair in items:
        doc, score = pair
        meta = dict(getattr(doc, "metadata", None) or {})
        page = str(getattr(doc, "page_content", None) or "")
        h16 = _chunk_text_fingerprint(page) or "empty"
        src = str(meta.get("source") or "").strip() or "unknown"
        src_fp_key = f"srcfp:{src}:{h16}"

        if src_fp_key in seen_src_fp:
            continue

        rid = _real_retrieval_vector_key(meta, backend_label)
        if rid is not None and rid in seen_real_id:
            continue

        seen_src_fp.add(src_fp_key)
        if rid is not None:
            seen_real_id.add(rid)
        out.append(pair)
    return out, raw_len, raw_len - len(out)


def _chat_llm_usage_triplet(chat: OpenAIChatProvider) -> tuple[int | None, int | None, int | None]:
    """Map last OpenAI chat.usage into (input, output, total) token counts, if API returned them."""
    getter = getattr(chat, "get_last_llm_usage_for_log", None)
    if not callable(getter):
        return None, None, None
    raw = getter()
    if not isinstance(raw, dict):
        return None, None, None

    def _ix(key: str) -> int | None:
        v = raw.get(key)
        if v is None:
            return None
        try:
            n = int(v)
            return n if n >= 0 else None
        except (TypeError, ValueError):
            return None

    return _ix("prompt_tokens"), _ix("completion_tokens"), _ix("total_tokens")


def _query_preview_for_logs(query: str, max_len: int = _QUERY_PREVIEW_MAX) -> str:
    """Single-line preview for logs; truncated; no API key patterns (minimal redaction)."""
    t = " ".join((query or "").strip().split())
    if not t:
        return ""
    lower = t.lower()
    if "sk-" in lower or "api_key" in lower or "openai_api_key" in lower:
        return "[preview redacted: possible secret pattern]"
    if len(t) <= max_len:
        return t
    return t[: max_len - 3] + "..."


def _numeric_scores_only(filtered: Sequence[tuple[Document, float]]) -> tuple[float, ...]:
    out: list[float] = []
    for _, s in filtered:
        try:
            out.append(float(s))
        except (TypeError, ValueError):
            continue
    return tuple(out)


def _score_or_none(value: object) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _retrieval_diag_snapshot(
    be: RetrievalBackend,
) -> tuple[str, str, int | None, str]:
    """
    (active_backend_id, retrieval_backend_id, collection_count, readiness) for logs/UI.

    readiness: READY | EMPTY | DOWN | UNKNOWN
    """
    name = (be.backend_name or "").strip().lower() or "unknown"
    n: int | None = None
    readiness = "UNKNOWN"
    try:
        h = be.healthcheck()
        if h.collection_count is not None:
            try:
                n = int(h.collection_count)
            except (TypeError, ValueError):
                n = None
        if not h.ok:
            readiness = "DOWN"
        elif n is not None and n == 0:
            readiness = "EMPTY"
        elif n is not None:
            readiness = "READY"
        elif h.ok:
            readiness = "READY"
    except Exception:
        try:
            raw = be.collection_count()
            n = int(raw)
            readiness = "EMPTY" if n == 0 else "READY"
        except Exception:
            pass
    return name, name, n, readiness


def _routing_identity_for_logs(
    svc: "RagQueryService",
    active: RetrievalBackend,
    cache_probe: dict[str, object] | None,
) -> dict[str, object]:
    """Поля для diagnostics: фактический класс backend, пути, env vs DB, cache (поток worker)."""
    from services.retrieval.chroma_backend import ChromaBackend
    from services.retrieval.factory import normalize_rag_backend
    from services.retrieval.faiss_backend import FaissBackend

    out: dict[str, object] = {}
    out["backend_requested_env"] = normalize_rag_backend(svc._config.rag_backend)
    if svc._retrieval_manager is not None:
        try:
            out["backend_effective_resolved"] = svc._retrieval_manager.effective_backend_name()
        except Exception:
            pass
    out["backend_wrapper_class"] = type(active).__name__
    inner = getattr(active, "_inner", None)
    if inner is not None:
        out["backend_inner_class"] = type(inner).__name__
        concrete = inner
    else:
        concrete = active
    if isinstance(concrete, FaissBackend):
        out["faiss_index_path"] = str(concrete.index_dir)
        out["backend_storage_label"] = f"faiss:{concrete.index_dir}"
    elif isinstance(concrete, ChromaBackend):
        out["chroma_collection_name"] = RAG_CHROMA_COLLECTION_NAME
        out["backend_storage_label"] = f"chroma:{RAG_CHROMA_COLLECTION_NAME}"
    else:
        out["backend_storage_label"] = str(
            getattr(concrete, "backend_name", None) or "unknown"
        )
    if cache_probe:
        for k in (
            "retrieval_cache_hit",
            "retrieval_cache_key_hash_prefix",
            "retrieval_cache_fingerprint_backend",
            "retrieved_duplicate_count",
            "retrieval_vector_hits_raw",
            "retrieval_dedupe_applied",
        ):
            v = cache_probe.get(k)
            if v is not None:
                out[k] = v
    return out


def _text_preview_for_logs(text: object, max_len: int = _CHUNK_PREVIEW_MAX) -> str:
    normalized = " ".join(str(text or "").split())
    if not normalized:
        return ""
    lower = normalized.lower()
    if "sk-" in lower or "api_key" in lower or "openai_api_key" in lower:
        return "[preview redacted: possible secret pattern]"
    if len(normalized) <= max_len:
        return normalized
    return normalized[:max_len]


def _build_retrieved_chunks_diagnostics(
    raw: Sequence[tuple[Document, float]],
    *,
    max_distance: float,
    chunk_backend: str,
) -> tuple[RagRetrievedChunkDiagnostics, ...]:
    be_label = (chunk_backend or "").strip().lower() or "unknown"
    out: list[RagRetrievedChunkDiagnostics] = []
    for doc, score in raw:
        source_raw = doc.metadata.get("source")
        source = str(source_raw).strip() if source_raw is not None else ""
        if not source:
            source = "unknown"
        score_num = _score_or_none(score)
        passed_filter = score_num is None or score_num <= max_distance
        page = doc.page_content
        tfp = _chunk_text_fingerprint(page)
        out.append(
            RagRetrievedChunkDiagnostics(
                source=source,
                score=score_num,
                passed_filter=passed_filter,
                text_preview=_text_preview_for_logs(
                    page, max_len=_CHUNK_CARD_PREVIEW_MAX
                ),
                chunk_text_full=_text_preview_for_logs(
                    page, max_len=_CHUNK_FULL_TEXT_LOG_MAX
                ),
                text_fp=tfp,
                retrieval_backend=be_label,
                source_backend=be_label,
            )
        )
    return tuple(out)


def _filter_chunks_by_max_distance(
    raw: list[tuple[Document, float]],
    max_distance: float,
) -> tuple[list[tuple[Document, float]], int]:
    """
    Keep chunks with distance <= max_distance. Chunks without a numeric score are kept
    and counted as missing_score (caller logs in diagnostics).
    Returns (kept_chunks, chunks_missing_score).
    """
    missing = 0
    kept: list[tuple[Document, float]] = []
    for doc, score in raw:
        try:
            d = float(score)
        except (TypeError, ValueError):
            missing += 1
            kept.append((doc, score))
            continue
        if d <= max_distance:
            kept.append((doc, score))
    return kept, missing


def _assembly_diag_for_logs(
    assembly: RagConversationalContextAssembly,
    *,
    retrieval_chunks_used: int,
    retrieval_chars: int,
    system_context_chars: int,
    query: str,
) -> dict[str, object]:
    """Memory v1.1: safe sizes/flags for ``processing_logs.details`` (no prompt bodies)."""
    trim = assembly.history_trimming_messages or assembly.history_trimming_chars
    q = (query or "").strip()
    return {
        "followup_question_detected": assembly.followup_question_detected,
        "history_turns_used": assembly.history_turns_used,
        "history_messages_used": assembly.history_messages_used,
        "history_messages_loaded": assembly.history_messages_loaded,
        "history_chars": assembly.history_chars,
        "history_trimming_applied": trim,
        "conversational_context_size_chars": assembly.history_chars
        + len(q)
        + int(system_context_chars),
        "retrieval_chunks_used": int(retrieval_chunks_used),
        "retrieval_chars": int(retrieval_chars),
    }


def _build_diagnostics(
    *,
    query: str,
    top_k: int,
    raw: list[tuple[Document, float]],
    filtered: list[tuple[Document, float]],
    relevance_threshold: float,
    chunks_missing_score: int,
    context_chars: int,
    fallback_reason: str,
    retrieval_latency_ms: int | None = None,
    llm_latency_ms: int | None = None,
    rag_pipeline_wall_ms: int | None = None,
    llm_provider: str | None = None,
    llm_model: str | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    total_tokens: int | None = None,
    embedding_model: str | None = None,
    chroma_collection: str | None = None,
    active_backend: str | None = None,
    retrieval_backend: str | None = None,
    active_collection_count: int | None = None,
    retrieval_readiness: str | None = None,
    routing_extras: dict[str, object] | None = None,
    followup_question_detected: bool | None = None,
    history_turns_used: int | None = None,
    history_messages_used: int | None = None,
    history_messages_loaded: int | None = None,
    history_chars: int | None = None,
    history_trimming_applied: bool | None = None,
    conversational_context_size_chars: int | None = None,
    retrieval_chunks_used: int | None = None,
    retrieval_chars: int | None = None,
    retrieved_duplicate_count: int | None = None,
    retrieval_dedupe_applied: bool | None = None,
    retrieval_vector_hits_raw: int | None = None,
) -> RagRequestDiagnostics:
    scores = _numeric_scores_only(filtered)
    uniq = len(
        {str(doc.metadata.get("source", "Unknown")) for doc, _ in filtered}
    )
    chunk_be = (active_backend or retrieval_backend or "unknown").strip().lower()
    rx = routing_extras or {}
    return RagRequestDiagnostics(
        query_preview=_query_preview_for_logs(query),
        top_k=top_k,
        retrieved_count=len(raw),
        filtered_count=len(filtered),
        relevance_threshold=relevance_threshold,
        chunks_missing_score=chunks_missing_score,
        unique_sources_count=uniq,
        scores=scores,
        context_chars=context_chars,
        fallback_reason=fallback_reason,
        retrieved_chunks=_build_retrieved_chunks_diagnostics(
            raw,
            max_distance=relevance_threshold,
            chunk_backend=chunk_be,
        ),
        retrieval_latency_ms=retrieval_latency_ms,
        llm_latency_ms=llm_latency_ms,
        rag_pipeline_wall_ms=rag_pipeline_wall_ms,
        llm_provider=llm_provider,
        llm_model=llm_model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        embedding_model=embedding_model,
        chroma_collection=chroma_collection,
        active_backend=active_backend,
        retrieval_backend=retrieval_backend,
        active_collection_count=active_collection_count,
        retrieval_readiness=retrieval_readiness,
        backend_requested_env=rx.get("backend_requested_env"),  # type: ignore[arg-type]
        backend_effective_resolved=rx.get("backend_effective_resolved"),  # type: ignore[arg-type]
        backend_wrapper_class=rx.get("backend_wrapper_class"),  # type: ignore[arg-type]
        backend_inner_class=rx.get("backend_inner_class"),  # type: ignore[arg-type]
        backend_storage_label=rx.get("backend_storage_label"),  # type: ignore[arg-type]
        faiss_index_path=rx.get("faiss_index_path"),  # type: ignore[arg-type]
        chroma_collection_name=rx.get("chroma_collection_name"),  # type: ignore[arg-type]
        retrieval_cache_hit=rx.get("retrieval_cache_hit"),  # type: ignore[arg-type]
        retrieval_cache_key_hash_prefix=rx.get("retrieval_cache_key_hash_prefix"),  # type: ignore[arg-type]
        retrieval_cache_fingerprint_backend=rx.get("retrieval_cache_fingerprint_backend"),  # type: ignore[arg-type]
        followup_question_detected=followup_question_detected,
        history_turns_used=history_turns_used,
        history_messages_used=history_messages_used,
        history_messages_loaded=history_messages_loaded,
        history_chars=history_chars,
        history_trimming_applied=history_trimming_applied,
        conversational_context_size_chars=conversational_context_size_chars,
        retrieval_chunks_used=retrieval_chunks_used,
        retrieval_chars=retrieval_chars,
        retrieved_duplicate_count=rx.get("retrieved_duplicate_count"),  # type: ignore[arg-type]
        retrieval_dedupe_applied=rx.get("retrieval_dedupe_applied"),  # type: ignore[arg-type]
        retrieval_vector_hits_raw=rx.get("retrieval_vector_hits_raw"),  # type: ignore[arg-type]
    )


def _format_context(results: Sequence[tuple[Document, float]]) -> str:
    parts: list[str] = []
    for i, (doc, _score) in enumerate(results, 1):
        source = doc.metadata.get("source", "Unknown")
        content = (doc.page_content or "").strip()
        parts.append(f"[Источник {i}: {source}]\n{content}\n")
    return "\n".join(parts)


def _sources_from_results(
    results: Sequence[tuple[Document, float]],
) -> tuple[RagSourceChunk, ...]:
    out: list[RagSourceChunk] = []
    for doc, score in results:
        source = str(doc.metadata.get("source", "Unknown"))
        content = (doc.page_content or "").strip()
        try:
            sc: float | None = float(score)
        except (TypeError, ValueError):
            sc = None
        out.append(RagSourceChunk(source=source, content=content, score=sc))
    return tuple(out)


def _dedupe_sources_by_file(
    results: Sequence[tuple[Document, float]],
) -> tuple[RagSourceChunk, ...]:
    """
    One row per distinct metadata source path; keep the chunk with best (lowest) distance.
    Preserves first-seen order of unique sources. Missing numeric score ranks worse than any
    finite distance (tie-break: keep first seen with valid distance).
    """
    order: list[str] = []
    best_pair: dict[str, tuple[Document, object]] = {}
    best_rank: dict[str, float] = {}

    def _rank(s: object) -> float:
        try:
            return float(s)
        except (TypeError, ValueError):
            return float("inf")

    for doc, score in results:
        key = str(doc.metadata.get("source", "Unknown"))
        r = _rank(score)
        if key not in best_pair:
            order.append(key)
            best_pair[key] = (doc, score)
            best_rank[key] = r
            continue
        if r < best_rank[key]:
            best_pair[key] = (doc, score)
            best_rank[key] = r
    out: list[RagSourceChunk] = []
    for key in order:
        d, raw_sc = best_pair[key]
        content = (d.page_content or "").strip()
        try:
            sc_out: float | None = float(raw_sc)
        except (TypeError, ValueError):
            sc_out = None
        out.append(
            RagSourceChunk(
                source=key,
                content=content,
                score=sc_out,
            )
        )
    return tuple(out)


class RagQueryService:
    """
    Query persisted vector index; does not mutate the index.
    Used from Telegram in /mode rag (interfaces/telegram_bot.py) and from CLI smoke-test.

    P6.1: similarity search через RetrievalBackend.
    P6.9: опционально ``RetrievalBackendManager`` для refresh FAISS / смены backend без restart.
    """

    def __init__(
        self,
        retrieval: RetrievalBackend | RetrievalBackendManager,
        chat: OpenAIChatProvider,
        config: AppConfig,
        *,
        tuning_resolver: RetrievalTuningResolver | None = None,
    ) -> None:
        if isinstance(retrieval, RetrievalBackendManager):
            self._retrieval_manager = retrieval
            self._retrieval_static: RetrievalBackend | None = None
        else:
            self._retrieval_manager = None
            self._retrieval_static = retrieval
        self._chat = chat
        self._config = config
        self._tuning_resolver = tuning_resolver

    def _eff(self) -> AppConfig:
        """Effective tuning (DB overrides + env); never mutates frozen base config."""
        if self._tuning_resolver is not None:
            return self._tuning_resolver.effective_config()
        return self._config

    def _assemble_rag_conversation(
        self,
        query: str,
        conversation_history: list[dict[str, str]] | None,
    ) -> RagConversationalContextAssembly:
        cfg = self._eff()
        return build_rag_conversational_context(
            query=(query or "").strip(),
            conversation_history=conversation_history,
            max_history_messages=int(cfg.telegram_memory_max_llm_messages or 0),
            max_history_chars=int(cfg.rag_conversation_history_max_chars or 0),
        )

    def _history_tail_for_llm(self, history: list[dict[str, str]] | None) -> list[dict[str, str]]:
        """Tail for LLM; same caps as RAG answer path (message + char budgets)."""
        assy = self._assemble_rag_conversation("", history)
        return list(assy.history_for_llm)

    def _active_retrieval(self) -> RetrievalBackend:
        if self._retrieval_manager is not None:
            return self._retrieval_manager.get_retrieval()
        assert self._retrieval_static is not None
        return self._retrieval_static

    def _diagnostics_collection_label(self) -> str:
        be = self._active_retrieval()
        if be.backend_name == "chroma":
            return RAG_CHROMA_COLLECTION_NAME
        return be.backend_name

    def _complete_chat_with_timeout(self, messages: list[dict[str, str]]) -> str:
        """Run sync OpenAI chat in a worker thread with a hard timeout."""

        def run() -> str:
            return self._chat.complete_chat(
                messages, max_tokens=self._eff().rag_answer_max_tokens
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(run)
            try:
                return future.result(timeout=_LLM_TIMEOUT_SEC)
            except concurrent.futures.TimeoutError as exc:
                raise TimeoutError(
                    f"LLM request timed out after {_LLM_TIMEOUT_SEC} seconds"
                ) from exc

    def _similarity_search_with_timeout(
        self,
        query: str,
        k: int,
        *,
        security_context: RetrievalSecurityContext | None = None,
    ) -> tuple[list[tuple[Document, float]], dict[str, object]]:
        """Run vector retrieval in a worker thread (bounds local stalls)."""

        active = self._active_retrieval()
        backend_label = active.backend_name

        def run() -> tuple[list[tuple[Document, float]], dict[str, object]]:
            from services.cache.caching_retrieval_backend import (
                clear_retrieval_cache_thread_diag,
                take_retrieval_cache_thread_diag,
            )

            clear_retrieval_cache_thread_diag()
            try:
                results = active.search(
                    query, top_k=k, security_context=security_context
                )
                conv = [
                    (
                        Document(
                            page_content=r.chunk.page_content,
                            metadata=dict(r.chunk.metadata),
                        ),
                        r.score,
                    )
                    for r in results
                ]
                return conv, take_retrieval_cache_thread_diag()
            except Exception as exc:
                _ = take_retrieval_cache_thread_diag()
                print(
                    "[assistant-flow] rag retrieve: retrieval backend query failed "
                    f"({type(exc).__name__}: {exc})",
                    flush=True,
                )
                return [], {}

        timeout_sec = max(1, int(self._eff().rag_retrieval_timeout))
        t_vec0 = time.monotonic()
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(run)
            try:
                out, cache_probe = future.result(timeout=timeout_sec)
            except concurrent.futures.TimeoutError:
                wall_ms = int((time.monotonic() - t_vec0) * 1000)
                print(
                    "[assistant-flow] rag retrieval: "
                    f"backend={backend_label} top_k={k} retrieved_count=0 "
                    f"latency_ms={wall_ms} status=timeout",
                    flush=True,
                )
                print(
                    "[assistant-flow] rag retrieve: similarity_search timed out "
                    f"after {timeout_sec}s",
                    flush=True,
                )
                return [], {}
        wall_ms = int((time.monotonic() - t_vec0) * 1000)
        print(
            "[assistant-flow] rag retrieval: "
            f"backend={backend_label} top_k={k} retrieved_count={len(out)} "
            f"latency_ms={wall_ms}",
            flush=True,
        )
        return out, cache_probe

    def _retrieve_raw(
        self,
        query: str,
        k: int,
        *,
        security_context: RetrievalSecurityContext | None = None,
    ) -> tuple[list[tuple[Document, float]], dict[str, object]]:
        """Similarity search with diagnostics; empty list on timeout or empty query."""
        print("[assistant-flow] rag retrieve: start", flush=True)
        if not (query or "").strip():
            return [], {}
        q = query.strip()
        print(
            "[assistant-flow] rag retrieve: before vectorstore similarity_search",
            flush=True,
        )
        raw, cache_probe = self._similarity_search_with_timeout(
            q, k, security_context=security_context
        )
        print(
            "[assistant-flow] rag retrieve: after vectorstore similarity_search",
            flush=True,
        )
        active = self._active_retrieval()
        be_label = str(getattr(active, "backend_name", "") or "unknown").strip().lower()
        raw_list = list(raw)
        raw_deduped, raw_n, removed = _dedupe_retrieval_raw_results(
            raw_list, backend_label=be_label
        )
        cp: dict[str, object] = dict(cache_probe) if cache_probe else {}
        if removed > 0:
            cp["retrieved_duplicate_count"] = int(removed)
            cp["retrieval_vector_hits_raw"] = int(raw_n)
            cp["retrieval_dedupe_applied"] = True
        else:
            cp.setdefault("retrieval_dedupe_applied", False)
        return raw_deduped, cp

    def retrieve(
        self,
        query: str,
        *,
        top_k: int | None = None,
        security_context: RetrievalSecurityContext | None = None,
    ) -> tuple[RagSourceChunk, ...]:
        """Similarity search only (read-only)."""
        k = top_k if top_k is not None else self._eff().rag_top_k
        t0 = time.monotonic()
        raw, cache_probe = self._retrieve_raw(query, k, security_context=security_context)
        retrieval_ms = int((time.monotonic() - t0) * 1000)
        thr = float(self._eff().rag_max_distance)
        filtered, miss = _filter_chunks_by_max_distance(raw, thr)
        if not raw:
            fb = "empty_retrieval"
        elif not filtered:
            fb = "low_relevance"
        else:
            fb = "none"
        emb_model = (self._eff().openai_embedding_model or "").strip() or None
        llm_prov = str(getattr(self._chat, "provider_label", "") or "").strip() or None
        llm_mod = str(getattr(self._chat, "model_name", "") or "").strip() or None
        active = self._active_retrieval()
        ab, rb, acnt, rdy = _retrieval_diag_snapshot(active)
        routing = _routing_identity_for_logs(self, active, cache_probe)
        _build_diagnostics(
            query=query,
            top_k=k,
            raw=raw,
            filtered=filtered,
            relevance_threshold=thr,
            chunks_missing_score=miss,
            context_chars=0,
            fallback_reason=fb,
            retrieval_latency_ms=retrieval_ms,
            embedding_model=emb_model,
            chroma_collection=self._diagnostics_collection_label(),
            llm_provider=llm_prov,
            llm_model=llm_mod,
            active_backend=ab,
            retrieval_backend=rb,
            active_collection_count=acnt,
            retrieval_readiness=rdy,
            routing_extras=routing,
        ).emit_stdout()
        return _sources_from_results(filtered)

    def answer(
        self,
        query: str,
        *,
        top_k: int | None = None,
        conversation_history: list[dict[str, str]] | None = None,
        hybrid_session_id: str | None = None,
        hybrid_user_id: str | None = None,
        security_context: RetrievalSecurityContext | None = None,
    ) -> RagQueryResult:
        """
        Retrieve context, then generate an answer. Empty retrieval returns a static message
        (no LLM). LLM calls are bounded by a timeout.
        """
        print("[assistant-flow] rag answer: start", flush=True)
        normalized = (query or "").strip()
        if not normalized:
            raise ValueError("query must not be empty")

        t_answer0 = time.monotonic()

        def wall_ms() -> int:
            return int((time.monotonic() - t_answer0) * 1000)

        k = top_k if top_k is not None else self._eff().rag_top_k
        print("[assistant-flow] rag answer: before retrieval", flush=True)
        t_ret0 = time.monotonic()
        raw, cache_probe = self._retrieve_raw(
            normalized, k, security_context=security_context
        )
        retrieval_latency_ms = int((time.monotonic() - t_ret0) * 1000)
        print("[assistant-flow] rag answer: after retrieval", flush=True)

        thr = float(self._eff().rag_max_distance)
        filtered, miss = _filter_chunks_by_max_distance(raw, thr)

        emb_model = (self._eff().openai_embedding_model or "").strip() or None
        chroma_coll = self._diagnostics_collection_label()
        llm_prov = str(getattr(self._chat, "provider_label", "") or "").strip() or None
        llm_mod = str(getattr(self._chat, "model_name", "") or "").strip() or None
        active = self._active_retrieval()
        ab, rb, acnt, rdy = _retrieval_diag_snapshot(active)
        routing = _routing_identity_for_logs(self, active, cache_probe)
        assembly = self._assemble_rag_conversation(normalized, conversation_history)
        v11_diag_idle = _assembly_diag_for_logs(
            assembly,
            retrieval_chunks_used=0,
            retrieval_chars=0,
            system_context_chars=0,
            query=normalized,
        )

        if not raw:
            diagnostics = _build_diagnostics(
                query=normalized,
                top_k=k,
                raw=raw,
                filtered=[],
                relevance_threshold=thr,
                chunks_missing_score=0,
                context_chars=0,
                fallback_reason="empty_retrieval",
                retrieval_latency_ms=retrieval_latency_ms,
                rag_pipeline_wall_ms=wall_ms(),
                embedding_model=emb_model,
                chroma_collection=chroma_coll,
                llm_provider=llm_prov,
                llm_model=llm_mod,
                active_backend=ab,
                retrieval_backend=rb,
                active_collection_count=acnt,
                retrieval_readiness=rdy,
                routing_extras=routing,
                **v11_diag_idle,
            )
            diagnostics.emit_stdout()
            return RagQueryResult(
                answer="В базе знаний нет информации по этому запросу.",
                sources=(),
                used_fallback_without_context=True,
                diagnostics=diagnostics,
            )

        if not filtered:
            diagnostics = _build_diagnostics(
                query=normalized,
                top_k=k,
                raw=raw,
                filtered=[],
                relevance_threshold=thr,
                chunks_missing_score=miss,
                context_chars=0,
                fallback_reason="low_relevance",
                retrieval_latency_ms=retrieval_latency_ms,
                rag_pipeline_wall_ms=wall_ms(),
                embedding_model=emb_model,
                chroma_collection=chroma_coll,
                llm_provider=llm_prov,
                llm_model=llm_mod,
                active_backend=ab,
                retrieval_backend=rb,
                active_collection_count=acnt,
                retrieval_readiness=rdy,
                routing_extras=routing,
                **v11_diag_idle,
            )
            diagnostics.emit_stdout()
            return RagQueryResult(
                answer=(
                    "В базе знаний нет достаточно релевантной информации по этому запросу.\n\n"
                    "(Найденные фрагменты не прошли порог релевантности.)"
                ),
                sources=(),
                used_fallback_without_context=False,
                diagnostics=diagnostics,
            )

        kb_formatted = _format_context(filtered)
        retrieval_chars_kb = len(kb_formatted)
        context = kb_formatted
        memory_section_present = False
        if self._config.enable_hybrid_retrieval and hybrid_session_id:
            from services.hybrid_retrieval.hybrid_context_service import HybridContextService

            hsvc = HybridContextService()
            hr = hsvc.build(
                kb_chunks=filtered,
                session_id=hybrid_session_id,
                user_id=hybrid_user_id,
                include_memory=True,
            )
            context = hr.context_text
            memory_section_present = hr.hybrid_enabled and any(
                it.source_type == "memory" for it in hr.items
            )

        sources_unique = _dedupe_sources_by_file(filtered)
        ctx_len = len(context)
        fb_reason = "none"
        if not (context or "").strip():
            fb_reason = "empty_context"

        print("[assistant-flow] rag answer: before LLM call", flush=True)
        t_llm0 = time.monotonic()
        try:
            answer = self._rag_llm(
                normalized,
                context,
                history_for_llm=list(assembly.history_for_llm),
                followup_hint=assembly.followup_question_detected,
                memory_section_present=memory_section_present,
            )
        except Exception as exc:
            print(
                f"[assistant-flow] rag answer: LLM call failed: {type(exc).__name__}: {exc}",
                flush=True,
            )
            answer = "Не удалось получить ответ от модели. Попробуйте позже."
            fb_reason = "llm_error"
        llm_latency_ms = int((time.monotonic() - t_llm0) * 1000)
        print("[assistant-flow] rag answer: after LLM call", flush=True)

        inp_t, out_t, tot_t = _chat_llm_usage_triplet(self._chat)

        diagnostics = _build_diagnostics(
            query=normalized,
            top_k=k,
            raw=raw,
            filtered=filtered,
            relevance_threshold=thr,
            chunks_missing_score=miss,
            context_chars=ctx_len,
            fallback_reason=fb_reason,
            retrieval_latency_ms=retrieval_latency_ms,
            llm_latency_ms=llm_latency_ms,
            rag_pipeline_wall_ms=wall_ms(),
            llm_provider=llm_prov,
            llm_model=llm_mod,
            input_tokens=inp_t,
            output_tokens=out_t,
            total_tokens=tot_t,
            embedding_model=emb_model,
            chroma_collection=chroma_coll,
            active_backend=ab,
            retrieval_backend=rb,
            active_collection_count=acnt,
            retrieval_readiness=rdy,
            routing_extras=routing,
            **_assembly_diag_for_logs(
                assembly,
                retrieval_chunks_used=len(filtered),
                retrieval_chars=retrieval_chars_kb,
                system_context_chars=ctx_len,
                query=normalized,
            ),
        )
        diagnostics.emit_stdout()

        return RagQueryResult(
            answer=answer,
            sources=sources_unique,
            used_fallback_without_context=False,
            diagnostics=diagnostics,
        )

    def _rag_llm(
        self,
        query: str,
        context: str,
        *,
        history_for_llm: list[dict[str, str]],
        followup_hint: bool = False,
        memory_section_present: bool = False,
    ) -> str:
        followup_tail = ""
        if followup_hint and history_for_llm:
            followup_tail = (
                "\n\nУточнение: последний вопрос пользователя может быть кратким продолжением "
                "темы предыдущих реплик; используй историю только чтобы понять ссылку "
                "(например, «удалённо», «стажёр»), факты — только из базы знаний."
            )
        if memory_section_present:
            system_prompt = (
                "Ты отвечаешь на вопрос пользователя. Ниже КОНТЕКСТ: сначала блок из базы знаний "
                "(единственный допустимый источник фактов), затем при необходимости — краткая "
                "история диалога (только для понимания формулировки пользователя, не как "
                "источник фактов).\n\n"
                "Правила:\n"
                "1. Факты и утверждения по теме опирай ТОЛЬКО на блок базы знаний. Историю "
                "диалога не используй как доказательство фактов.\n"
                "2. Если в блоке базы знаний есть сведения по теме — дай связный ответ по-русски "
                "в 1–2 абзацах. Не пиши, что информации нет, если она есть в этом блоке.\n"
                "3. Фразу «в базе знаний нет информации» используй только если блок базы знаний "
                "пуст или явно не относится к вопросу.\n"
                "4. Не выдумывай факты, которых нет в блоке базы знаний.\n"
                "5. Не добавляй раздел «Источники» — список источников добавляется отдельно.\n"
                "6. Пиши нейтрально, ясно, по делу."
                f"{followup_tail}\n\n"
                f"КОНТЕКСТ:\n{context}"
            )
        else:
            system_prompt = (
                "Ты отвечаешь на вопрос пользователя, используя ТОЛЬКО приведённый ниже КОНТЕКСТ "
                "из базы знаний.\n\n"
                "Правила:\n"
                "1. Если контекст не пуст и содержит сведения по теме вопроса (полностью или "
                "частично) — ОБЯЗАТЕЛЬНО дай связный ответ по-русски в 1–2 абзацах, опираясь "
                "на эти сведения. Не пиши, что информации нет, если она присутствует в контексте.\n"
                "2. Фразу вида «в базе знаний нет информации» используй только если контекст "
                "пуст, либо он явно не относится к вопросу и не позволяет сформировать ответ.\n"
                "3. Не выдумывай факты, которых нет в контексте.\n"
                "4. Не добавляй раздел «Источники» и нумерацию файлов — список источников "
                "добавляется отдельно.\n"
                "5. Пиши нейтрально, ясно, по делу."
                f"{followup_tail}\n\n"
                f"КОНТЕКСТ:\n{context}"
            )
        messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
        messages.extend(history_for_llm)
        messages.append({"role": "user", "content": query})
        return self._complete_chat_with_timeout(messages)

    def _fallback_llm(
        self,
        query: str,
        *,
        history: list[dict[str, str]] | None,
    ) -> str:
        system_prompt = (
            "Ты — ассистент. В базе знаний не найдено релевантных фрагментов по запросу. "
            "Ответь по общим знаниям кратко и предупреди, что ответ не опирается на "
            "загруженные документы."
        )
        messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
        messages.extend(self._history_tail_for_llm(history))
        messages.append({"role": "user", "content": query})
        return self._complete_chat_with_timeout(messages)
