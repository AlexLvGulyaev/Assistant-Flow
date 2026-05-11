"""
Детерминированный fingerprint для retrieval cache (без молчаливого stale).

Включает: нормализованный query, backend, top_k, embedding model, retrieval generation,
флаг hybrid (влияет на downstream, не на сырой retrieval — но ключ должен различать конфиг).

``RAG_RETRIEVAL_GENERATION`` / knowledge_base_revision: пока placeholder через env;
без bump при reindex — риск устаревшего кэша (см. PROJECT_STATE §35).
"""

from __future__ import annotations

import hashlib
import os
from typing import TYPE_CHECKING

from services.retrieval.factory import normalize_rag_backend

if TYPE_CHECKING:
    from utils.config import AppConfig


def normalize_query_text(query: str) -> str:
    return " ".join((query or "").strip().split())


def build_retrieval_fingerprint(config: "AppConfig", *, query: str, top_k: int) -> str:
    gen = (os.getenv("RAG_RETRIEVAL_GENERATION") or "").strip() or "unset"
    parts = [
        normalize_query_text(query),
        normalize_rag_backend(config.rag_backend),
        str(int(top_k)),
        (config.openai_embedding_model or "").strip().lower(),
        gen,
        "1" if config.enable_hybrid_retrieval else "0",
    ]
    return "\n".join(parts)


def fingerprint_to_key_hash(fingerprint: str) -> str:
    return hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()
