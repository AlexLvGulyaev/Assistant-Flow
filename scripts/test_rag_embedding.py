"""
Smoke test: one embedding HTTP call (OpenAI-compatible API via LangChain).

Run from repository root:
  python scripts/test_rag_embedding.py

Requires OPENAI_API_KEY (direct OpenAI only). Optional OPENAI_BASE_URL for custom OpenAI-compatible endpoints.
Uses RAG_EMBEDDING_REQUEST_TIMEOUT from the environment (see utils.config.load_config).
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from providers.rag_embeddings import build_openai_embeddings  # noqa: E402
from utils.config import load_config  # noqa: E402


def main() -> None:
    config = load_config()
    emb = build_openai_embeddings(config)
    text = "test query"
    vec = emb.embed_query(text)
    print(f"[assistant-flow] rag embedding smoke: len(vector)={len(vec)}", flush=True)


if __name__ == "__main__":
    main()
