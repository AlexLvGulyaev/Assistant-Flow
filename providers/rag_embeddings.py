"""OpenAI-compatible embeddings for Chroma (no global singletons).

Embeddings always use direct OpenAI with ``OPENAI_API_KEY`` only (never ProxyAPI).

HTTP timeouts: LangChain ``OpenAIEmbeddings`` uses ``request_timeout`` from
``RAG_EMBEDDING_REQUEST_TIMEOUT`` → ``AppConfig.rag_embedding_request_timeout``.
Chroma local queries are bounded separately by ``RAG_RETRIEVAL_TIMEOUT`` in
``RagQueryService``.
"""

from __future__ import annotations

from langchain_openai import OpenAIEmbeddings

from utils.config import AppConfig


def build_openai_embeddings(config: AppConfig) -> OpenAIEmbeddings:
    """Build LangChain OpenAIEmbeddings: direct OpenAI only (``OPENAI_API_KEY``)."""
    openai_key = (config.openai_api_key or "").strip()
    if not openai_key:
        raise ValueError("RAG embeddings require OPENAI_API_KEY (direct OpenAI only)")

    print("embeddings provider: openai_direct", flush=True)
    kwargs = {
        "model": config.openai_embedding_model,
        "openai_api_key": openai_key,
        "request_timeout": float(config.rag_embedding_request_timeout),
    }
    return OpenAIEmbeddings(**kwargs)
