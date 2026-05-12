/**
 * Operational display labels for logs / lifecycle.
 * Mirrors `admin_ui/app.py`: `_EVENT_TYPE_ALIASES`, `_EVENT_TYPE_RU`,
 * `_ROUTE_ALIASES`, `_ROUTE_LABEL_RU`, `_STATUS_RU`, `_stage_to_action`.
 * Unknown stages must not leak raw internal names in UI — use a generic label
 * and expose technical id via DOM title where needed.
 */

export const MSK_TIMEZONE = "Europe/Moscow";

const EVENT_TYPE_ALIASES: Record<string, string> = {
  text_answer_done: "processing_done",
  rag_answer_done: "processing_done",
  image_answer_done: "processing_done",
  rag_response: "processing_done",
};

const EVENT_TYPE_RU: Record<string, string> = {
  intake_received: "Получен запрос",
  route_selected: "Определён тип запроса",
  processing_done: "Обработка завершена",
  processing_error: "Ошибка обработки",
  image_received: "Получено изображение",
  ocr_started: "OCR запущен",
  ocr_done: "OCR завершён",
  ocr_error: "Ошибка OCR",
  vision_ocr_started: "OCR запущен",
  vision_ocr_done: "OCR завершён",
  vision_ocr_error: "Ошибка OCR",
  ocr_response_sent: "OCR-ответ отправлен",
  database_schema: "Служебное событие схемы БД",
  admin_document_uploaded: "Документ загружен",
  admin_reindex_started: "Переиндексация (полная) запущена",
  admin_reindex_done: "Переиндексация завершена",
  admin_reindex_error: "Ошибка переиндексации",
  admin_document_reindex_started: "Переиндексация документа запущена",
  admin_document_reindex_done: "Переиндексация документа завершена",
  admin_document_reindex_error: "Ошибка переиндексации документа",
  image_generation_started: "Генерация изображения запущена",
  image_text_enhancement_done: "Уточнение промпта (текст) завершено",
  image_prompt_refinement_done: "Подготовка image prompt завершена",
  image_provider_done: "Изображение получено от провайдера",
  image_assets_persisted: "Файлы изображения сохранены",
  stt_started: "STT запущен",
  stt_completed: "STT завершён",
  tts_started: "TTS запущен",
  tts_completed: "TTS завершён",
  tts_skipped: "TTS пропущен",
  tts_error: "Ошибка TTS",
  voice_processing_done: "Voice-обработка завершена",
  voice_processing_error: "Ошибка voice-обработки",
  audio_generation_done: "Генерация аудио завершена",
  audio_generation_error: "Ошибка генерации аудио",
  rag_unavailable: "RAG недоступен",
  system_degraded: "Деградация системы",
};

/** OCR lifecycle machine names → operator RU (React primary UI). */
const OCR_STAGE_LABEL_RU: Record<string, string> = {
  image_received: "Получено изображение",
  ocr_started: "OCR запущен",
  ocr_done: "OCR завершён",
  ocr_error: "Ошибка OCR",
  ocr_response_sent: "OCR-ответ отправлен",
  vision_ocr_started: "OCR запущен",
  vision_ocr_done: "OCR завершён",
  vision_ocr_error: "Ошибка OCR",
};

const ROUTE_ALIASES: Record<string, string> = {
  text_response: "text",
  text_answer_done: "text",
  text_query: "text",
  rag_response: "rag",
  rag_answer_done: "rag",
  vision_ocr: "text",
  image: "image_generation",
  image_response: "image_generation",
  audio: "audio",
  voice: "audio",
  voice_response: "audio",
};

export const ROUTE_LABEL_RU: Record<string, string> = {
  rag: "RAG",
  text: "Текст",
  image_generation: "Генерация изображений",
  audio: "Аудио",
  unknown: "Прочее",
};

const STATUS_RU: Record<string, string> = {
  success: "успешно",
  error: "ошибка",
  skipped: "пропущено",
  retry: "повтор",
  started: "запущено",
  warning: "предупреждение",
  failed: "ошибка",
};

export type NormalizedRouteKey =
  | "rag"
  | "text"
  | "image_generation"
  | "audio"
  | "unknown";

/** Normalize lifecycle ``stage`` / machine ids (trim, BOM, NFKC, collapse spaces → _). */
export function normalizeMachineStage(stage: string | null | undefined): string {
  let s = String(stage ?? "").trim();
  if (!s) return "";
  s = s.replace(/\uFEFF/g, "").replace(/[\u200B-\u200D]/g, "");
  try {
    s = s.normalize("NFKC");
  } catch {
    /* ignore */
  }
  return s.toLowerCase().replace(/\s+/g, "_");
}

export function normalizeRouteKey(route: string | null | undefined): NormalizedRouteKey {
  const raw = (route || "").trim().toLowerCase();
  if (!raw) return "unknown";
  const norm = ROUTE_ALIASES[raw] ?? raw;
  if (norm === "rag") return "rag";
  if (norm === "text") return "text";
  if (norm === "image_generation") return "image_generation";
  if (norm === "audio") return "audio";
  return "unknown";
}

export function normalizeEventType(eventType: string | null | undefined): string {
  const raw = normalizeMachineStage(eventType);
  if (!raw) return "";
  if (raw in OCR_STAGE_LABEL_RU) return raw;
  return EVENT_TYPE_ALIASES[raw] ?? raw;
}

export function routeLabelRu(route: string | null | undefined): string {
  const norm = normalizeRouteKey(route);
  return ROUTE_LABEL_RU[norm] ?? norm;
}

export function statusLabelRu(raw: string | null | undefined): string {
  if (!raw) return "—";
  return STATUS_RU[raw.trim().toLowerCase()] ?? raw;
}

/** Streamlit `_stage_to_action` + safe fallback (no raw English leakage). */
export function stageToActionRu(
  stage: string | null | undefined,
  details: unknown
): string {
  const raw = (stage || "").trim();
  if (!raw) return "—";
  const rawKey = normalizeMachineStage(raw);
  const ocrLbl = OCR_STAGE_LABEL_RU[rawKey];
  if (ocrLbl) return ocrLbl;
  if (rawKey === "text_answer_done") return "Текстовый ответ построен";
  if (rawKey === "rag_answer_done") return "RAG-ответ построен";
  if (rawKey === "processing_done") {
    const dd = isRecord(details) ? details : {};
    const rr = String(dd.downstream_route ?? dd.route ?? "")
      .trim()
      .toLowerCase();
    if (rr === "vision_ocr") {
      return "Обработка OCR завершена";
    }
    if (normalizeRouteKey(String(dd.route ?? "")) === "image_generation") {
      if (dd.generation_completed) return "Генерация завершена";
      return "Обработка завершена (изображение)";
    }
  }
  const norm = normalizeEventType(rawKey);
  if (!norm) return "—";
  const mapped = EVENT_TYPE_RU[norm];
  if (mapped) return mapped;
  return "Нестандартный этап";
}

export function formatTimestampMsk(
  isoOrMs: string | number | null | undefined
): string {
  if (isoOrMs == null) return "—";
  const ms =
    typeof isoOrMs === "number" ? isoOrMs : new Date(isoOrMs).getTime();
  if (!Number.isFinite(ms)) return "—";
  return new Intl.DateTimeFormat("ru-RU", {
    timeZone: MSK_TIMEZONE,
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  })
    .format(new Date(ms))
    .replace(",", "");
}

/** Compact calendar stamp for dense lists (e.g. document versions). DD.MM.YY, МСК. */
export function formatShortDateMsk(
  isoOrMs: string | number | null | undefined
): string {
  if (isoOrMs == null) return "—";
  const ms =
    typeof isoOrMs === "number" ? isoOrMs : new Date(isoOrMs).getTime();
  if (!Number.isFinite(ms)) return "—";
  return new Intl.DateTimeFormat("ru-RU", {
    timeZone: MSK_TIMEZONE,
    day: "2-digit",
    month: "2-digit",
    year: "2-digit",
  })
    .format(new Date(ms))
    .replace(/\//g, ".");
}

/** Like `_logs_format_duration_ms` in Streamlit. */
export function formatDurationMs(ms: number | null | undefined): string {
  if (ms == null || !Number.isFinite(ms)) return "—";
  if (ms < 1000) return `${Math.round(ms)} мс`;
  return `${(ms / 1000).toFixed(2)} с`;
}

export function extractLatencyMs(
  details: Record<string, unknown> | null
): number | null {
  if (!details) return null;
  for (const key of ["latency_ms", "duration_ms", "elapsed_ms"] as const) {
    const v = details[key];
    if (v == null) continue;
    const n = Number(v);
    if (Number.isFinite(n)) return n;
  }
  return null;
}

/** Wall clock span of session: min(created_at) → max(created_at). */
export function sessionWallDurationMs(
  timestampsMs: number[]
): number | null {
  const finite = timestampsMs.filter((t) => Number.isFinite(t));
  if (finite.length < 2) return null;
  const t0 = Math.min(...finite);
  const t1 = Math.max(...finite);
  return Math.max(0, t1 - t0);
}

export function sessionMaxStepLatencyMs(
  detailsList: Array<Record<string, unknown> | null>
): number | null {
  let best: number | null = null;
  for (const d of detailsList) {
    const lm = extractLatencyMs(d);
    if (lm == null) continue;
    best = best == null ? lm : Math.max(best, lm);
  }
  return best != null ? Math.round(best) : null;
}

export function sessionAvgStepLatencyMs(
  detailsList: Array<Record<string, unknown> | null>
): number | null {
  const vals: number[] = [];
  for (const d of detailsList) {
    const lm = extractLatencyMs(d);
    if (lm != null) vals.push(lm);
  }
  if (!vals.length) return null;
  return Math.round(vals.reduce((a, b) => a + b, 0) / vals.length);
}

/** Короткое имя retrieval backend (chroma | faiss | weaviate) для операторского UI. */
export function formatRetrievalBackendTitle(id: string | undefined | null): string {
  if (!id?.trim()) return "—";
  const t = id.trim().toLowerCase();
  return t.length ? t.charAt(0).toUpperCase() + t.slice(1) : "—";
}

/**
 * Maps compact retrieval readiness to StatusBadge `status` tokens (see StatusBadge.tsx).
 */
export function retrievalReadinessForStatusBadge(
  readiness: string | undefined | null,
  activeOk?: boolean | null
): string {
  if (activeOk === false) return "down";
  const r = (readiness || "").trim().toUpperCase();
  if (r === "READY") return "ready";
  if (r === "EMPTY") return "empty";
  if (r === "DOWN") return "down";
  return "unknown";
}

function isRecord(v: unknown): v is Record<string, unknown> {
  return v !== null && typeof v === "object" && !Array.isArray(v);
}
