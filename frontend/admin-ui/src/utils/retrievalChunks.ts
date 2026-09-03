/** Shared retrieval chunk helpers for RAG + Evaluation consoles. */

export const CHUNK_PREVIEW_CHARS = 440;

export type SharedRetrievalChunk = {
  source: string;
  distance: number | null;
  passedFilter: boolean;
  preview: string;
  fullText: string;
  chunkIndex: number | null;
  backend: string | null;
  /** Fingerprint of the full chunk text (from rag diagnostics); enables full-text fetch from the vector store. */
  textFp?: string | null;
};

export function clipText(text: string | null | undefined, max: number): string | null {
  if (!text) return null;
  const t = text.trim();
  if (t.length <= max) return t;
  return `${t.slice(0, max - 1)}…`;
}

export function chunkPreviewText(chunk: SharedRetrievalChunk): string {
  const fromPreview = chunk.preview?.trim();
  if (fromPreview) {
    return clipText(fromPreview, CHUNK_PREVIEW_CHARS) ?? fromPreview;
  }
  const ft = chunk.fullText?.trim();
  if (ft) {
    return clipText(ft, CHUNK_PREVIEW_CHARS) ?? ft.slice(0, CHUNK_PREVIEW_CHARS);
  }
  return "—";
}

export function relevanceLabel(
  chunk: SharedRetrievalChunk,
  threshold: number | null
): string {
  if (chunk.distance == null) return "метрика расстояния недоступна";
  if (threshold != null && Number.isFinite(threshold)) {
    if (chunk.distance <= threshold) {
      return chunk.passedFilter
        ? "высокая релевантность (≤ порога)"
        : "в контексте / порог";
    }
    if (chunk.distance <= threshold * 1.35) return "средняя релевантность";
    return "низкая релевантность";
  }
  return chunk.passedFilter ? "включён в контекст" : "отфильтрован";
}

export function chunkFromEvalDiagnostic(
  raw: Record<string, unknown>,
  index: number
): SharedRetrievalChunk {
  const score = raw.score ?? raw.distance;
  let distance: number | null = null;
  if (typeof score === "number" && Number.isFinite(score)) distance = score;
  else if (typeof score === "string" && score.trim() !== "" && !Number.isNaN(Number(score))) {
    distance = Number(score);
  }
  const full = String(raw.chunk_text_full || raw.text_preview || "").trim();
  const preview = String(raw.text_preview || "").trim();
  const passed = raw.passed_filter;
  return {
    source: String(raw.source || raw.file || "—"),
    distance,
    passedFilter: passed !== false,
    preview: preview || full,
    fullText: full || preview,
    chunkIndex:
      raw.chunk_index != null
        ? Number(raw.chunk_index)
        : raw.ordinal != null
          ? Number(raw.ordinal)
          : index,
    backend: raw.backend ? String(raw.backend) : null,
  };
}

export function chunkFromRagSessionChunk(c: {
  source: string;
  distance: number | null;
  passedFilter: boolean;
  preview: string;
  fullText: string;
  chunkIndex: number | null;
  backend: string | null;
  textFp?: string | null;
}): SharedRetrievalChunk {
  return {
    source: c.source,
    distance: c.distance,
    passedFilter: c.passedFilter,
    preview: c.preview,
    fullText: c.fullText,
    chunkIndex: c.chunkIndex,
    backend: c.backend,
    textFp: c.textFp ?? null,
  };
}
