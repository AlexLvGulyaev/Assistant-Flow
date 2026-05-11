"""
Сборка hybrid context: KB chunks + recent dialog memory (без semantic retrieval).
"""

from __future__ import annotations

import time
from typing import Any

from langchain_core.documents import Document

from services.hybrid_retrieval.base import (
    HybridContextItem,
    HybridContextResult,
    HybridRetrievalPolicy,
)
from services.memory.base import ConversationMemoryRecord, MemoryBudgetPolicy
from services.memory.conversation_memory_service import ConversationMemoryService


def _trim(s: str, max_len: int) -> str:
    if max_len <= 0:
        return ""
    t = (s or "").strip()
    return t if len(t) <= max_len else t[:max_len]


class HybridContextService:
    """
    Context assembly: KB (уже отфильтрованные чанки) + optional dialog memory.

    Не вызывает retrieval сам; не смешивает scores KB и memory.
    """

    def build(
        self,
        *,
        kb_chunks: list[tuple[Document, float]],
        session_id: str | None,
        user_id: str | None,
        include_memory: bool,
        policy: HybridRetrievalPolicy | None = None,
    ) -> HybridContextResult:
        """
        :param kb_chunks: уже отфильтрованные по релевантности пары (Document, score).
        :param include_memory: из config ``enable_hybrid_retrieval``; без ``session_id`` memory не грузится.
        :param user_id: зарезервирован для будущих проверок / correlation; на P6.4 не обязателен.
        """
        _ = user_id
        pol = policy or HybridRetrievalPolicy()
        t0 = time.monotonic()

        kb_budget = min(int(pol.max_kb_chars), int(pol.max_context_chars))
        kb_items, kb_text, kb_used, kb_trunc = self._assemble_kb(
            kb_chunks, pol.max_kb_chunks, kb_budget
        )

        memory_items: tuple[HybridContextItem, ...] = ()
        memory_text = ""
        memory_trunc = False
        hybrid_on = False

        room_global = max(0, int(pol.max_context_chars) - kb_used)
        memory_cap = min(int(pol.max_memory_chars), room_global)

        if include_memory and session_id and memory_cap > 0:
            hybrid_on = True
            mem_pol = MemoryBudgetPolicy(
                max_recent_messages=max(1, int(pol.max_memory_messages)),
                max_message_chars=8_000,
                total_memory_chars_budget=max(1, memory_cap),
            )
            mem_svc = ConversationMemoryService(policy=mem_pol)
            records = mem_svc.get_recent_messages(session_id, limit=pol.max_memory_messages)
            memory_items, memory_text, memory_trunc = self._records_to_memory_items(
                records,
                session_id,
                hard_char_cap=memory_cap,
            )

        if memory_text.strip():
            context_text = self._join_context_blocks(kb_text, memory_text)
        else:
            context_text = kb_text
        budget_applied = kb_trunc or memory_trunc
        max_ctx = int(pol.max_context_chars)
        if len(context_text) > max_ctx:
            context_text = context_text[:max_ctx]
            budget_applied = True
        total_chars = len(context_text)

        latency_ms = int((time.monotonic() - t0) * 1000)
        print(
            "[assistant-flow] hybrid: "
            f"hybrid_enabled={'true' if hybrid_on else 'false'} "
            f"kb_items_count={len(kb_items)} memory_items_count={len(memory_items)} "
            f"total_context_chars={total_chars} "
            f"budget_applied={'true' if budget_applied else 'false'} "
            f"memory_truncated={'true' if memory_trunc else 'false'} "
            f"kb_truncated={'true' if kb_trunc else 'false'} "
            f"latency_ms={latency_ms}",
            flush=True,
        )

        all_items: list[HybridContextItem] = list(kb_items) + list(memory_items)
        return HybridContextResult(
            items=tuple(all_items),
            context_text=context_text,
            hybrid_enabled=hybrid_on,
            budget_applied=budget_applied,
            memory_truncated=memory_trunc,
            kb_truncated=kb_trunc,
            total_context_chars=total_chars,
        )

    def _assemble_kb(
        self,
        kb_chunks: list[tuple[Document, float]],
        max_chunks: int,
        kb_char_budget: int,
    ) -> tuple[list[HybridContextItem], str, int, bool]:
        items: list[HybridContextItem] = []
        parts: list[str] = []
        used = 0
        truncated = False
        for i, (doc, score) in enumerate(kb_chunks[: max(0, int(max_chunks))], 1):
            source = str(doc.metadata.get("source", "Unknown"))
            raw = (doc.page_content or "").strip()
            room = kb_char_budget - used
            if room <= 0:
                truncated = True
                break
            piece = raw if len(raw) <= room else raw[:room]
            if len(raw) > len(piece):
                truncated = True
            meta: dict[str, Any] = {
                "kb_index": i,
                "source": source,
            }
            try:
                meta["score"] = float(score)
            except (TypeError, ValueError):
                meta["score"] = None
            items.append(
                HybridContextItem(
                    source_type="kb",
                    content=piece,
                    role=None,
                    created_at=None,
                    session_id=None,
                    metadata=meta,
                )
            )
            parts.append(f"[Источник {i}: {source}]\n{piece}\n")
            used += len(piece)
        kb_text = "\n".join(parts).strip()
        return items, kb_text, used, truncated

    def _records_to_memory_items(
        self,
        records: list[ConversationMemoryRecord],
        session_id: str,
        *,
        hard_char_cap: int,
    ) -> tuple[tuple[HybridContextItem, ...], str, bool]:
        lines: list[str] = []
        items: list[HybridContextItem] = []
        used = 0
        truncated = False
        for r in records:
            role = str(r.role or "")
            body = _trim(str(r.content or ""), 8000)
            ts = r.created_at
            ts_s = ts.isoformat() if ts is not None else ""
            line = f"[{ts_s} {role}] {body}"
            room = hard_char_cap - used
            if room <= 0:
                truncated = True
                break
            if len(line) > room:
                line = line[:room]
                truncated = True
            items.append(
                HybridContextItem(
                    source_type="memory",
                    content=body,
                    role=role,
                    created_at=r.created_at,
                    session_id=session_id,
                    metadata={
                        "memory_layer": r.metadata.get("memory_layer", "dialog_history"),
                        "display_line": line,
                    },
                )
            )
            lines.append(line)
            used += len(line)
        text = "\n".join(lines).strip()
        return tuple(items), text, truncated

    @staticmethod
    def _join_context_blocks(kb_text: str, memory_text: str) -> str:
        kb_block = (kb_text or "").strip()
        mem_block = (memory_text or "").strip()
        if not mem_block:
            return kb_block
        return (
            "=== БАЗА ЗНАНИЙ (источник фактов) ===\n"
            f"{kb_block}\n\n"
            "=== ИСТОРИЯ ДИАЛОГА (не источник фактов, только контекст формулировки) ===\n"
            f"{mem_block}"
        )
