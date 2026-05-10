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
        self._last_usage: dict[str, int] | None = None

    @property
    def provider_label(self) -> str:
        return "openai"

    @property
    def model_name(self) -> str:
        return self._model

    def get_last_llm_usage_for_log(self) -> dict[str, int] | None:
        """Token usage from the last ``complete_chat`` response, if the API returned usage."""
        if not self._last_usage:
            return None
        return dict(self._last_usage)

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
        self._last_usage = None
        response = self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            temperature=temperature,
            max_tokens=limit,
        )
        usage = getattr(response, "usage", None)
        if usage is not None:
            chunk: dict[str, int] = {}
            pt = getattr(usage, "prompt_tokens", None)
            ct = getattr(usage, "completion_tokens", None)
            tt = getattr(usage, "total_tokens", None)
            if pt is not None:
                chunk["prompt_tokens"] = int(pt)
            if ct is not None:
                chunk["completion_tokens"] = int(ct)
            if tt is not None:
                chunk["total_tokens"] = int(tt)
            self._last_usage = chunk if chunk else None
        choice = response.choices[0].message
        text = (choice.content or "").strip()
        if not text:
            raise RuntimeError("LLM returned empty content")
        return text
