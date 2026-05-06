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

    def to_log_details(self) -> dict[str, object]:
        """Compact JSON-safe payload for ``processing_logs.details``."""
        return {
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
        }

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
