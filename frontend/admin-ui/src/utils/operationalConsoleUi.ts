/**
 * Shared operational-console UI contract (Assistant Flow admin-ui).
 * Used by RAG, Text, Images, Audio, Logs, Memory and future modality pages.
 */

export type OperationalModality =
  | "rag"
  | "mem"
  | "text"
  | "ocr"
  | "vision"
  | "audio"
  | "image"
  | "test"
  | "doc"
  | "log";

/** Colored pipeline marker (CSS), aligned across consoles. */
export type AfPipelineStageVariant =
  | "success"
  | "loading"
  | "processing"
  | "reset"
  | "warning"
  | "error"
  | "muted";

const MODALITY_ORDER: OperationalModality[] = [
  "rag",
  "mem",
  "text",
  "ocr",
  "vision",
  "audio",
  "image",
  "test",
  "doc",
  "log",
];

/** Short label inside list mini-badge. */
export const OPERATIONAL_MODALITY_LABEL: Record<OperationalModality, string> = {
  rag: "rag",
  mem: "mem",
  text: "text",
  ocr: "ocr",
  vision: "vision",
  audio: "audio",
  image: "image",
  test: "test",
  doc: "doc",
  log: "log",
};

/** CSS suffix after `mini-badge--af-` (see globals.css). */
export function operationalModalityBadgeClassList(mod: OperationalModality): string {
  return `mini-badge mini-badge--af mini-badge--af-${mod}`;
}

export function normalizeOperationalModality(raw: string): OperationalModality {
  const k = raw.trim().toLowerCase();
  if (MODALITY_ORDER.includes(k as OperationalModality)) return k as OperationalModality;
  if (k === "memory" || k === "mem") return "mem";
  if (k === "img" || k === "images") return "image";
  if (k === "voice") return "audio";
  if (k === "document" || k === "documents") return "doc";
  return "log";
}

/** Map execution route keys (and common aliases) to list-badge modality. */
export function operationalModalityFromRouteKey(routeKey: string): OperationalModality {
  const r = (routeKey || "").trim().toLowerCase();
  if (!r) return "log";
  if (r === "document" || r === "documents") return "doc";
  if (r === "rag" || r === "rag_response") return "rag";
  if (r === "text") return "text";
  if (r === "vision_ocr" || r === "ocr") return "ocr";
  if (r.includes("vision") || r === "image_analysis") return "vision";
  if (r.includes("audio") || r.includes("voice") || r.includes("stt") || r.includes("tts"))
    return "audio";
  if (r.includes("image") || r === "image_generation") return "image";
  if (r === "test" || r.includes("smoke")) return "test";
  return "log";
}

const MEMORY_LIFECYCLE_LABEL: Record<string, string> = {
  memory_load_started: "Загрузка памяти…",
  memory_load_done: "Память загружена",
  memory_append_done: "Ответ сохранён",
  memory_session_cleared: "Сессия сброшена",
  memory_error: "Ошибка памяти",
};

/** Human label for memory lifecycle stages (Memory detail timeline). */
export function memoryLifecycleStageLabel(stage: string): string {
  const low = stage.trim().toLowerCase();
  if (MEMORY_LIFECYCLE_LABEL[low]) return MEMORY_LIFECYCLE_LABEL[low];
  if (low.startsWith("memory_meta")) return "Meta intent";
  const tail = low.replace(/^memory_/, "");
  return tail ? tail.replace(/_/g, " ") : "—";
}

/**
 * JSON one-line preview for `<details>` summary (same contract as Logs `previewSummary`).
 */
export function detailsJsonPreview(d: unknown): string {
  if (d == null) return "пусто";
  if (typeof d === "string") return d.length > 56 ? `${d.slice(0, 56)}…` : d;
  try {
    const s = JSON.stringify(d);
    return s.length > 56 ? `${s.slice(0, 56)}…` : s || "{}";
  } catch {
    return "?";
  }
}

/**
 * Heuristic stage marker color from machine stage name (+ optional status).
 * Applies to pipeline timelines across modalities.
 */
export function pipelineStageVariant(
  stage: string,
  status?: string | null
): AfPipelineStageVariant {
  const s = (stage || "").toLowerCase();
  const st = (status || "").trim().toLowerCase();
  if (
    st === "error" ||
    st === "failed" ||
    s.includes("error") ||
    s.endsWith("_error") ||
    s.includes("failure")
  ) {
    return "error";
  }
  if (st === "warning" || s.includes("warn")) return "warning";
  if (s.includes("clear") || s.includes("reset") || s.includes("cleared")) return "reset";
  if (
    s.includes("_started") ||
    s.endsWith("started") ||
    s.includes("loading") ||
    s.includes("queued") ||
    s.includes("pending")
  ) {
    return "loading";
  }
  if (
    s.includes("_done") ||
    s.includes("completed") ||
    s.includes("success") ||
    st === "success" ||
    st === "ok"
  ) {
    return "success";
  }
  if (
    s.includes("processing") ||
    s.includes("append") ||
    s.includes("retrieve") ||
    s.includes("embedding") ||
    s.startsWith("memory_meta")
  ) {
    return "processing";
  }
  return "muted";
}

/**
 * Canonical layout class names (React admin-ui). Prefer these over ad-hoc strings in new code.
 */
export const AF_OPERATIONAL_LAYOUT_CLASSES = {
  console: "logs-console",
  leftCard: "logs-left card",
  rightCard: "logs-right card",
  filters: "logs-filters",
  filterRow: "logs-filter-row",
  search: "logs-search",
  list: "logs-list",
  detail: "logs-detail",
  modalityDetail: "rag-modality-detail",
  opsPanelsTriple: "memory-memory-top-panels--triple",
  opsPanelsRagBalanced: "modality-ops-panels--rag-balanced",
  opsPanelsRagSplit: "modality-ops-panels--rag-split",
  logsTimeline: "logs-timeline",
  logsStage: "logs-stage logs-stage--compact",
  stageLabelWithIcon: "af-logs-stage-label-with-icon",
} as const;
