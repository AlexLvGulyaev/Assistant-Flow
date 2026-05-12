"""Read-only RAG: retrieve from Chroma and compose an answer via LLM."""

from __future__ import annotations

import concurrent.futures
import time
from typing import Sequence

from langchain_core.documents import Document

from providers.openai_chat_provider import OpenAIChatProvider
from services.rag_chroma_store import RAG_CHROMA_COLLECTION_NAME
from services.retrieval.base import RetrievalBackend
from services.retrieval.runtime_manager import RetrievalBackendManager
from services.retrieval_security.context import RetrievalSecurityContext
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
) -> tuple[RagRetrievedChunkDiagnostics, ...]:
    out: list[RagRetrievedChunkDiagnostics] = []
    for doc, score in raw:
        source_raw = doc.metadata.get("source")
        source = str(source_raw).strip() if source_raw is not None else ""
        if not source:
            source = "unknown"
        score_num = _score_or_none(score)
        passed_filter = score_num is None or score_num <= max_distance
        out.append(
            RagRetrievedChunkDiagnostics(
                source=source,
                score=score_num,
                passed_filter=passed_filter,
                text_preview=_text_preview_for_logs(doc.page_content),
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
) -> RagRequestDiagnostics:
    scores = _numeric_scores_only(filtered)
    uniq = len(
        {str(doc.metadata.get("source", "Unknown")) for doc, _ in filtered}
    )
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
    ) -> None:
        if isinstance(retrieval, RetrievalBackendManager):
            self._retrieval_manager = retrieval
            self._retrieval_static: RetrievalBackend | None = None
        else:
            self._retrieval_manager = None
            self._retrieval_static = retrieval
        self._chat = chat
        self._config = config

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
                messages, max_tokens=self._config.rag_answer_max_tokens
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
    ) -> list[tuple[Document, float]]:
        """Run Chroma+embedding search in a worker thread (bounds local stalls)."""

        active = self._active_retrieval()
        backend_label = active.backend_name

        def run() -> list[tuple[Document, float]]:
            try:
                results = active.search(
                    query, top_k=k, security_context=security_context
                )
                return [
                    (
                        Document(
                            page_content=r.chunk.page_content,
                            metadata=dict(r.chunk.metadata),
                        ),
                        r.score,
                    )
                    for r in results
                ]
            except Exception as exc:
                print(
                    "[assistant-flow] rag retrieve: retrieval backend query failed "
                    f"({type(exc).__name__}: {exc})",
                    flush=True,
                )
                return []

        timeout_sec = max(1, int(self._config.rag_retrieval_timeout))
        t_vec0 = time.monotonic()
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(run)
            try:
                out = future.result(timeout=timeout_sec)
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
                return []
        wall_ms = int((time.monotonic() - t_vec0) * 1000)
        print(
            "[assistant-flow] rag retrieval: "
            f"backend={backend_label} top_k={k} retrieved_count={len(out)} "
            f"latency_ms={wall_ms}",
            flush=True,
        )
        return out

    def _retrieve_raw(
        self,
        query: str,
        k: int,
        *,
        security_context: RetrievalSecurityContext | None = None,
    ) -> list[tuple[Document, float]]:
        """Similarity search with diagnostics; empty list on timeout or empty query."""
        print("[assistant-flow] rag retrieve: start", flush=True)
        if not (query or "").strip():
            return []
        q = query.strip()
        print(
            "[assistant-flow] rag retrieve: before vectorstore similarity_search",
            flush=True,
        )
        raw = self._similarity_search_with_timeout(
            q, k, security_context=security_context
        )
        print(
            "[assistant-flow] rag retrieve: after vectorstore similarity_search",
            flush=True,
        )
        return raw

    def retrieve(
        self,
        query: str,
        *,
        top_k: int | None = None,
        security_context: RetrievalSecurityContext | None = None,
    ) -> tuple[RagSourceChunk, ...]:
        """Similarity search only (read-only)."""
        k = top_k if top_k is not None else self._config.rag_top_k
        t0 = time.monotonic()
        raw = self._retrieve_raw(query, k, security_context=security_context)
        retrieval_ms = int((time.monotonic() - t0) * 1000)
        thr = float(self._config.rag_max_distance)
        filtered, miss = _filter_chunks_by_max_distance(raw, thr)
        if not raw:
            fb = "empty_retrieval"
        elif not filtered:
            fb = "low_relevance"
        else:
            fb = "none"
        emb_model = (self._config.openai_embedding_model or "").strip() or None
        llm_prov = str(getattr(self._chat, "provider_label", "") or "").strip() or None
        llm_mod = str(getattr(self._chat, "model_name", "") or "").strip() or None
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

        k = top_k if top_k is not None else self._config.rag_top_k
        print("[assistant-flow] rag answer: before retrieval", flush=True)
        t_ret0 = time.monotonic()
        raw = self._retrieve_raw(
            normalized, k, security_context=security_context
        )
        retrieval_latency_ms = int((time.monotonic() - t_ret0) * 1000)
        print("[assistant-flow] rag answer: after retrieval", flush=True)

        thr = float(self._config.rag_max_distance)
        filtered, miss = _filter_chunks_by_max_distance(raw, thr)

        emb_model = (self._config.openai_embedding_model or "").strip() or None
        chroma_coll = self._diagnostics_collection_label()
        llm_prov = str(getattr(self._chat, "provider_label", "") or "").strip() or None
        llm_mod = str(getattr(self._chat, "model_name", "") or "").strip() or None

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

        context = _format_context(filtered)
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
                history=conversation_history,
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
        history: list[dict[str, str]] | None,
        memory_section_present: bool = False,
    ) -> str:
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
                "6. Пиши нейтрально, ясно, по делу.\n\n"
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
                "5. Пиши нейтрально, ясно, по делу.\n\n"
                f"КОНТЕКСТ:\n{context}"
            )
        messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
        if history:
            messages.extend(history[-6:])
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
        if history:
            messages.extend(history[-6:])
        messages.append({"role": "user", "content": query})
        return self._complete_chat_with_timeout(messages)
