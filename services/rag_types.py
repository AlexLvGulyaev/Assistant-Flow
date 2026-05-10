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

    def to_log_dict(self) -> dict[str, object]:
        return {
            "source": self.source,
            "score": self.score,
            "passed_filter": bool(self.passed_filter),
            "text_preview": self.text_preview,
        }


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
