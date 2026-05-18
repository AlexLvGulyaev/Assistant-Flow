"""Shared types for RAG query results (read path)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class RagRetrievedChunkDiagnostics:
    """One retrieved chunk snapshot for explainability logs/UI."""

    source: str
    score: float | None
    passed_filter: bool
    text_preview: str
    chunk_text_full: str = ""
    text_fp: str = ""
    retrieval_backend: str | None = None
    source_backend: str | None = None

    def to_log_dict(self) -> dict[str, object]:
        out: dict[str, object] = {
            "source": self.source,
            "score": self.score,
            "passed_filter": bool(self.passed_filter),
            "text_preview": self.text_preview,
        }
        fp = (self.text_fp or "").strip()
        if fp:
            out["text_fp"] = fp
        full = (self.chunk_text_full or "").strip()
        if full:
            out["chunk_text_full"] = full
        rb0 = self.retrieval_backend
        sb0 = self.source_backend
        if rb0 or sb0:
            rb = (rb0 or sb0 or "").strip().lower()
            sb = (sb0 or rb0 or rb).strip().lower()
            if rb:
                out["retrieval_backend"] = rb
                out["source_backend"] = sb
        return out


@dataclass(frozen=True)
class RagRequestDiagnostics:
    """Per-request RAG retrieval/answer metrics (safe for stdout; no secrets)."""

    query_preview: str
    top_k: int
    retrieved_count: int
    filtered_count: int
    relevance_threshold: float
    chunks_missing_score: int
    unique_sources_count: int
    scores: tuple[float, ...]
    context_chars: int
    fallback_reason: str
    retrieved_chunks: tuple[RagRetrievedChunkDiagnostics, ...] = field(
        default_factory=tuple
    )
    # Optional telemetry (all persisted inside processing_logs.details JSON; no DB migration).
    retrieval_latency_ms: int | None = None
    llm_latency_ms: int | None = None
    rag_pipeline_wall_ms: int | None = None
    llm_provider: str | None = None
    llm_model: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    embedding_model: str | None = None
    chroma_collection: str | None = None
    active_backend: str | None = None
    retrieval_backend: str | None = None
    active_collection_count: int | None = None
    retrieval_readiness: str | None = None
    # Routing / identity (P6 retrieval audit; JSON in processing_logs.details, no DB migration).
    backend_requested_env: str | None = None
    backend_effective_resolved: str | None = None
    backend_wrapper_class: str | None = None
    backend_inner_class: str | None = None
    backend_storage_label: str | None = None
    faiss_index_path: str | None = None
    chroma_collection_name: str | None = None
    retrieval_cache_hit: bool | None = None
    retrieval_cache_miss: bool | None = None
    retrieval_cache_disabled: bool | None = None
    cache_layer: str | None = None
    cache_latency_ms: int | None = None
    retrieval_cache_generation: str | None = None
    retrieval_cache_backend: str | None = None
    retrieval_cache_key_hash_prefix: str | None = None
    retrieval_cache_fingerprint_backend: str | None = None
    # Memory v1.1: conversational assembly (counts/flags only; no full prompts).
    followup_question_detected: bool | None = None
    history_turns_used: int | None = None
    history_messages_used: int | None = None
    history_messages_loaded: int | None = None
    history_chars: int | None = None
    history_trimming_applied: bool | None = None
    conversational_context_size_chars: int | None = None
    retrieval_chunks_used: int | None = None
    retrieval_chars: int | None = None
    # Dedup: duplicate vector hits removed before distance filter / LLM (counts only).
    retrieved_duplicate_count: int | None = None
    retrieval_dedupe_applied: bool | None = None
    retrieval_vector_hits_raw: int | None = None
    #: Exact query string passed to retrieval (embed + vector search), after any future
    #: rewrite/expansion; today typically equals the normalized user message. Not a preview.
    retrieval_ready_query: str | None = None

    def to_log_details(self) -> dict[str, object]:
        """Compact JSON-safe payload for ``processing_logs.details``."""
        out: dict[str, object] = {
            "query_preview": self.query_preview,
            "top_k": int(self.top_k),
            "retrieved_count": int(self.retrieved_count),
            "filtered_count": int(self.filtered_count),
            "relevance_threshold": float(self.relevance_threshold),
            "chunks_missing_score": int(self.chunks_missing_score),
            "unique_sources_count": int(self.unique_sources_count),
            "scores": [float(s) for s in self.scores],
            "context_chars": int(self.context_chars),
            "fallback_reason": self.fallback_reason,
            "retrieved_chunks": [c.to_log_dict() for c in self.retrieved_chunks],
            "used_chunks_count": int(self.filtered_count),
        }
        if self.scores:
            out["best_distance"] = float(min(self.scores))
        if self.retrieval_latency_ms is not None:
            out["retrieval_latency_ms"] = int(self.retrieval_latency_ms)
        if self.llm_latency_ms is not None:
            out["llm_latency_ms"] = int(self.llm_latency_ms)
        if self.rag_pipeline_wall_ms is not None:
            out["rag_pipeline_wall_ms"] = int(self.rag_pipeline_wall_ms)
        if self.llm_provider:
            out["llm_provider"] = self.llm_provider
        if self.llm_model:
            out["llm_model"] = self.llm_model
        if self.input_tokens is not None:
            out["input_tokens"] = int(self.input_tokens)
        if self.output_tokens is not None:
            out["output_tokens"] = int(self.output_tokens)
        if self.total_tokens is not None:
            out["total_tokens"] = int(self.total_tokens)
        if self.embedding_model:
            out["embedding_model"] = self.embedding_model
        if self.chroma_collection:
            out["chroma_collection"] = self.chroma_collection
        if self.active_backend:
            out["active_backend"] = self.active_backend
        if self.retrieval_backend:
            out["retrieval_backend"] = self.retrieval_backend
        if self.active_collection_count is not None:
            out["active_collection_count"] = int(self.active_collection_count)
        if self.retrieval_readiness:
            out["retrieval_readiness"] = self.retrieval_readiness
        if self.backend_requested_env:
            out["backend_requested_env"] = self.backend_requested_env
        if self.backend_effective_resolved:
            out["backend_effective_resolved"] = self.backend_effective_resolved
        if self.backend_wrapper_class:
            out["backend_wrapper_class"] = self.backend_wrapper_class
        if self.backend_inner_class:
            out["backend_inner_class"] = self.backend_inner_class
        if self.backend_storage_label:
            out["backend_storage_label"] = self.backend_storage_label
        if self.faiss_index_path:
            out["faiss_index_path"] = self.faiss_index_path
        if self.chroma_collection_name:
            out["chroma_collection_name"] = self.chroma_collection_name
        if self.retrieval_cache_hit is not None:
            out["retrieval_cache_hit"] = bool(self.retrieval_cache_hit)
        if self.retrieval_cache_miss is not None:
            out["retrieval_cache_miss"] = bool(self.retrieval_cache_miss)
        if self.retrieval_cache_disabled is not None:
            out["retrieval_cache_disabled"] = bool(self.retrieval_cache_disabled)
        if self.cache_layer:
            out["cache_layer"] = self.cache_layer
        if self.cache_latency_ms is not None:
            out["cache_latency_ms"] = int(self.cache_latency_ms)
        if self.retrieval_cache_generation:
            out["retrieval_cache_generation"] = self.retrieval_cache_generation
        if self.retrieval_cache_backend:
            out["retrieval_cache_backend"] = self.retrieval_cache_backend
        if self.retrieval_cache_key_hash_prefix:
            out["retrieval_cache_key_hash_prefix"] = self.retrieval_cache_key_hash_prefix
        if self.retrieval_cache_fingerprint_backend:
            out["retrieval_cache_fingerprint_backend"] = self.retrieval_cache_fingerprint_backend
        if self.followup_question_detected is not None:
            out["followup_question_detected"] = bool(self.followup_question_detected)
        if self.history_turns_used is not None:
            out["history_turns_used"] = int(self.history_turns_used)
        if self.history_messages_used is not None:
            out["history_messages_used"] = int(self.history_messages_used)
        if self.history_messages_loaded is not None:
            out["history_messages_loaded"] = int(self.history_messages_loaded)
        if self.history_chars is not None:
            out["history_chars"] = int(self.history_chars)
        if self.history_trimming_applied is not None:
            out["history_trimming_applied"] = bool(self.history_trimming_applied)
        if self.conversational_context_size_chars is not None:
            out["conversational_context_size_chars"] = int(
                self.conversational_context_size_chars
            )
        if self.retrieval_chunks_used is not None:
            out["retrieval_chunks_used"] = int(self.retrieval_chunks_used)
        if self.retrieval_chars is not None:
            out["retrieval_chars"] = int(self.retrieval_chars)
        if self.retrieved_duplicate_count is not None:
            out["retrieved_duplicate_count"] = int(self.retrieved_duplicate_count)
        if self.retrieval_dedupe_applied is not None:
            out["retrieval_dedupe_applied"] = bool(self.retrieval_dedupe_applied)
        if self.retrieval_vector_hits_raw is not None:
            out["retrieval_vector_hits_raw"] = int(self.retrieval_vector_hits_raw)
        rq = (self.retrieval_ready_query or "").strip()
        if rq:
            out["retrieval_ready_query"] = rq
        return out

    def emit_stdout(self) -> None:
        """Log one block of rag diagnostics lines to stdout."""
        scores_str = "[" + ", ".join(f"{s:.4f}" for s in self.scores) + "]"
        print(
            f"[assistant-flow] rag diagnostics: query_preview={self.query_preview!r}",
            flush=True,
        )
        print(f"[assistant-flow] rag diagnostics: top_k={self.top_k}", flush=True)
        print(
            f"[assistant-flow] rag diagnostics: retrieved_count={self.retrieved_count}",
            flush=True,
        )
        print(
            f"[assistant-flow] rag diagnostics: filtered_count={self.filtered_count}",
            flush=True,
        )
        print(
            f"[assistant-flow] rag diagnostics: relevance_threshold={self.relevance_threshold}",
            flush=True,
        )
        print(
            f"[assistant-flow] rag diagnostics: chunks_missing_score="
            f"{self.chunks_missing_score}",
            flush=True,
        )
        print(
            f"[assistant-flow] rag diagnostics: unique_sources_count="
            f"{self.unique_sources_count}",
            flush=True,
        )
        print(f"[assistant-flow] rag diagnostics: scores={scores_str}", flush=True)
        print(
            f"[assistant-flow] rag diagnostics: context_chars={self.context_chars}",
            flush=True,
        )
        print(
            f"[assistant-flow] rag diagnostics: fallback_reason={self.fallback_reason}",
            flush=True,
        )
        print(
            "[assistant-flow] rag diagnostics: retrieved_chunks="
            f"{len(self.retrieved_chunks)}",
            flush=True,
        )
        if self.retrieval_latency_ms is not None:
            print(
                f"[assistant-flow] rag diagnostics: retrieval_latency_ms="
                f"{self.retrieval_latency_ms}",
                flush=True,
            )
        if self.llm_latency_ms is not None:
            print(
                f"[assistant-flow] rag diagnostics: llm_latency_ms={self.llm_latency_ms}",
                flush=True,
            )
        if self.rag_pipeline_wall_ms is not None:
            print(
                f"[assistant-flow] rag diagnostics: rag_pipeline_wall_ms="
                f"{self.rag_pipeline_wall_ms}",
                flush=True,
            )
        if self.backend_wrapper_class:
            print(
                f"[assistant-flow] rag diagnostics: backend_wrapper_class="
                f"{self.backend_wrapper_class}",
                flush=True,
            )
        if self.backend_inner_class:
            print(
                f"[assistant-flow] rag diagnostics: backend_inner_class="
                f"{self.backend_inner_class}",
                flush=True,
            )
        if self.backend_storage_label:
            print(
                f"[assistant-flow] rag diagnostics: backend_storage_label="
                f"{self.backend_storage_label!r}",
                flush=True,
            )
        if self.retrieval_cache_hit is not None:
            print(
                f"[assistant-flow] rag diagnostics: retrieval_cache_hit="
                f"{self.retrieval_cache_hit}",
                flush=True,
            )
        if self.retrieval_cache_miss is not None:
            print(
                f"[assistant-flow] rag diagnostics: retrieval_cache_miss="
                f"{self.retrieval_cache_miss}",
                flush=True,
            )
        if self.cache_layer:
            print(
                f"[assistant-flow] rag diagnostics: cache_layer={self.cache_layer!r}",
                flush=True,
            )
        if self.cache_latency_ms is not None:
            print(
                f"[assistant-flow] rag diagnostics: cache_latency_ms={self.cache_latency_ms}",
                flush=True,
            )
        if self.retrieval_cache_generation:
            print(
                "[assistant-flow] rag diagnostics: retrieval_cache_generation="
                f"{self.retrieval_cache_generation!r}",
                flush=True,
            )
        if self.retrieval_cache_backend:
            print(
                "[assistant-flow] rag diagnostics: retrieval_cache_backend="
                f"{self.retrieval_cache_backend!r}",
                flush=True,
            )
        if self.retrieval_cache_fingerprint_backend:
            print(
                "[assistant-flow] rag diagnostics: retrieval_cache_fingerprint_backend="
                f"{self.retrieval_cache_fingerprint_backend!r}",
                flush=True,
            )
        if self.followup_question_detected is not None:
            print(
                "[assistant-flow] rag diagnostics: followup_question_detected="
                f"{self.followup_question_detected}",
                flush=True,
            )
        if self.history_turns_used is not None:
            print(
                f"[assistant-flow] rag diagnostics: history_turns_used={self.history_turns_used}",
                flush=True,
            )
        if self.history_trimming_applied is not None:
            print(
                "[assistant-flow] rag diagnostics: history_trimming_applied="
                f"{self.history_trimming_applied}",
                flush=True,
            )
        if self.conversational_context_size_chars is not None:
            print(
                "[assistant-flow] rag diagnostics: conversational_context_size_chars="
                f"{self.conversational_context_size_chars}",
                flush=True,
            )
        if self.retrieval_dedupe_applied is not None:
            print(
                "[assistant-flow] rag diagnostics: retrieval_dedupe_applied="
                f"{self.retrieval_dedupe_applied}",
                flush=True,
            )
        if self.retrieved_duplicate_count is not None:
            print(
                "[assistant-flow] rag diagnostics: retrieved_duplicate_count="
                f"{self.retrieved_duplicate_count}",
                flush=True,
            )
        if self.retrieval_vector_hits_raw is not None:
            print(
                "[assistant-flow] rag diagnostics: retrieval_vector_hits_raw="
                f"{self.retrieval_vector_hits_raw}",
                flush=True,
            )
        rq = (self.retrieval_ready_query or "").strip()
        if rq:
            preview = rq if len(rq) <= 240 else rq[:237] + "…"
            print(
                "[assistant-flow] rag diagnostics: retrieval_ready_query_len="
                f"{len(rq)} preview={preview!r}",
                flush=True,
            )


@dataclass(frozen=True)
class RagSourceChunk:
    """One retrieved chunk with optional vector distance/score."""

    source: str
    content: str
    score: float | None = None


@dataclass(frozen=True)
class RagQueryResult:
    """Answer text plus retrieved evidence."""

    answer: str
    sources: tuple[RagSourceChunk, ...] = field(default_factory=tuple)
    used_fallback_without_context: bool = False
    diagnostics: RagRequestDiagnostics | None = None
