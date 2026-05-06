"""Minimal OpenAI chat completion for RAG answers (direct OpenAI only, sync)."""

from __future__ import annotations

from openai import OpenAI

from utils.config import AppConfig


class OpenAIChatProvider:
    """Single-call chat completion; same credentials pattern as embeddings."""

    def __init__(self, config: AppConfig) -> None:
        api_key = (config.openai_api_key or "").strip()
        if not api_key:
            raise ValueError("OpenAIChatProvider requires OPENAI_API_KEY (direct OpenAI only)")
        print("chat provider: openai_direct", flush=True)
        self._client = OpenAI(
            api_key=api_key,
            base_url=config.openai_base_url,
        )
        self._model = config.openai_model
        self._default_max_tokens = config.rag_answer_max_tokens

    def complete_chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.3,
        max_tokens: int | None = None,
    ) -> str:
        if not messages:
            raise ValueError("messages must not be empty")
        limit = max_tokens if max_tokens is not None else self._default_max_tokens
        response = self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            temperature=temperature,
            max_tokens=limit,
        )
        choice = response.choices[0].message
        text = (choice.content or "").strip()
        if not text:
            raise RuntimeError("LLM returned empty content")
        return text
