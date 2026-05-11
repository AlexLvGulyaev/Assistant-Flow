"""
Детерминированный paragraph-aware chunker (P6.3).

Без semantic/LLM chunking. Идеи адаптированы из legacy PEr03/PEr08, без копипасты монолитов.

TODO (будущее): token_budget / token-aware границы поверх этого слоя (см. PROJECT_STATE §30).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from services.chunking.base import (
    ChunkMetadata,
    ChunkingDocument,
    ChunkingResult,
    ChunkingTelemetry,
)
from utils.config import AppConfig

if TYPE_CHECKING:
    from langchain_core.documents import Document

_STRATEGY = "smart_paragraph_v1"
_MAX_CHUNKS_WARN = 3000
_MIN_CHUNK_CHARS = 40
_MIN_PARAGRAPH_MERGE = 80


@dataclass(frozen=True)
class SmartChunkingConfig:
    """Параметры: target/max/overlap в символах (approximation под будущие токены)."""

    target_chunk_size: int
    max_chunk_size: int
    overlap_size: int

    @classmethod
    def from_app_config(cls, config: AppConfig) -> SmartChunkingConfig:
        target = max(200, int(config.rag_chunk_size))
        raw_overlap = int(config.rag_chunk_overlap)
        overlap = max(0, min(raw_overlap, target - 1, target // 2))
        # max чуть выше target, но ограничен (нет giant chunks)
        max_c = min(max(int(target * 1.3), target + 200), 8000)
        max_c = max(max_c, target)
        return cls(
            target_chunk_size=target,
            max_chunk_size=max_c,
            overlap_size=overlap,
        )


class SmartChunker:
    """Paragraph-first packing + bounded overlap; fallback для очень длинных абзацев."""

    def __init__(self, cfg: SmartChunkingConfig) -> None:
        self._cfg = cfg

    @classmethod
    def from_app_config(cls, config: AppConfig) -> SmartChunker:
        return cls(SmartChunkingConfig.from_app_config(config))

    def chunk_text(self, document: ChunkingDocument) -> list[ChunkingResult]:
        text = document.text or ""
        base = dict(document.metadata)
        raw_parts = self._build_raw_chunks(text.strip() if text else "")
        overlaid = self._apply_overlap(raw_parts, self._cfg.overlap_size)
        n = len(overlaid)
        if n == 0:
            return []

        source = str(base.get("source") or "unknown")
        doc_id = base.get("document_id")
        ver_id = base.get("version_id")
        doc_id_s = str(doc_id) if doc_id is not None else None
        ver_id_s = str(ver_id) if ver_id is not None else None

        out: list[ChunkingResult] = []
        for i, chunk_text in enumerate(overlaid):
            meta = ChunkMetadata(
                source=source,
                chunk_index=i,
                total_chunks=n,
                chunking_strategy=_STRATEGY,
                approximate_size=len(chunk_text),
                document_id=doc_id_s,
                version_id=ver_id_s,
            )
            out.append(ChunkingResult(text=chunk_text, metadata=meta))

        self._log_telemetry(out)
        return out

    def split_langchain_documents(self, docs: list[Any]) -> list[Any]:
        """Тонкий adapter: список Document → плоский список chunked Document (как RecursiveCharacterTextSplitter)."""
        from langchain_core.documents import Document  # noqa: PLC0415

        result: list[Any] = []
        for doc in docs:
            cd = ChunkingDocument(text=doc.page_content or "", metadata=dict(doc.metadata))
            for cr in self.chunk_text(cd):
                meta = cr.to_langchain_metadata(dict(doc.metadata))
                result.append(Document(page_content=cr.text, metadata=meta))
        return result

    def _log_telemetry(self, chunks: list[ChunkingResult]) -> None:
        n = len(chunks)
        if n == 0:
            return
        sizes = [len(c.text) for c in chunks]
        avg = sum(sizes) // n
        mx = max(sizes)
        tel = ChunkingTelemetry(
            strategy=_STRATEGY,
            chunks_created=n,
            avg_chunk_size=avg,
            max_chunk_size=mx,
        )
        print(
            "[assistant-flow] chunking: "
            f"strategy={tel.strategy} chunks_created={tel.chunks_created} "
            f"avg_chunk_size={tel.avg_chunk_size} max_chunk_size={tel.max_chunk_size}",
            flush=True,
        )
        if n > _MAX_CHUNKS_WARN:
            print(
                f"[assistant-flow] chunking: WARNING chunk_count={n} "
                f"exceeds warn_threshold={_MAX_CHUNKS_WARN} — проверьте документ и параметры",
                flush=True,
            )

    def _paragraph_units(self, text: str) -> list[str]:
        if not text.strip():
            return []
        parts = re.split(r"\n\s*\n+", text.strip())
        units: list[str] = []
        for p in parts:
            s = p.strip()
            if not s:
                continue
            if units and len(units[-1]) < _MIN_PARAGRAPH_MERGE:
                units[-1] = units[-1] + "\n\n" + s
            else:
                units.append(s)
        if not units:
            return [text.strip()]
        return units

    def _split_oversized(self, block: str) -> list[str]:
        """Длинный абзац: предложения, иначе жёсткая нарезка по max (fallback)."""
        if len(block) <= self._cfg.max_chunk_size:
            return [block]
        sentences = re.split(r"(?<=[.!?])\s+", block)
        sentences = [s.strip() for s in sentences if s and s.strip()]
        if len(sentences) <= 1:
            return self._hard_split(block, self._cfg.max_chunk_size)

        out: list[str] = []
        buf = ""
        for sent in sentences:
            if len(buf) + len(sent) + 1 <= self._cfg.target_chunk_size:
                buf = (buf + " " + sent).strip() if buf else sent
            else:
                if buf:
                    out.append(buf)
                if len(sent) > self._cfg.max_chunk_size:
                    out.extend(self._hard_split(sent, self._cfg.max_chunk_size))
                    buf = ""
                else:
                    buf = sent
        if buf:
            out.append(buf)
        return [x for x in out if x.strip()]

    def _hard_split(self, s: str, max_chunk: int) -> list[str]:
        if len(s) <= max_chunk:
            return [s]
        step = max(1, max_chunk - min(self._cfg.overlap_size, max_chunk // 4))
        out: list[str] = []
        i = 0
        while i < len(s):
            out.append(s[i : i + max_chunk])
            i += step
        return out

    def _pack_units(self, units: list[str]) -> list[str]:
        target = self._cfg.target_chunk_size
        max_c = self._cfg.max_chunk_size
        chunks: list[str] = []
        buf = ""
        for u in units:
            if len(u) > max_c:
                if buf:
                    chunks.append(buf)
                    buf = ""
                chunks.extend(self._split_oversized(u))
                continue
            sep = "\n\n" if buf else ""
            if len(buf) + len(sep) + len(u) <= target:
                buf = (buf + sep + u) if buf else u
            else:
                if buf:
                    chunks.append(buf)
                if len(u) <= target:
                    buf = u
                else:
                    chunks.extend(self._split_oversized(u))
                    buf = ""
        if buf:
            chunks.append(buf)
        merged: list[str] = []
        for c in chunks:
            if len(c) < _MIN_CHUNK_CHARS and merged:
                cand = merged[-1] + "\n\n" + c
                if len(cand) <= self._cfg.max_chunk_size:
                    merged[-1] = cand
                else:
                    merged.append(c)
            else:
                merged.append(c)
        return [m for m in merged if m.strip()]

    def _build_raw_chunks(self, text: str) -> list[str]:
        if not text:
            return []
        if len(text) <= self._cfg.target_chunk_size:
            return [text]
        units = self._paragraph_units(text)
        raw = self._pack_units(units)
        return [r for r in raw if r.strip()]

    def _apply_overlap(self, parts: list[str], overlap: int) -> list[str]:
        if not parts or overlap <= 0:
            return parts
        out: list[str] = [parts[0]]
        for i in range(1, len(parts)):
            prev = out[-1]
            take = min(overlap, len(prev), len(parts[i]))
            prefix = prev[-take:] if take > 0 else ""
            out.append(prefix + parts[i])
        return out
