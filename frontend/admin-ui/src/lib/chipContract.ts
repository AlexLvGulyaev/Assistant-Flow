/**
 * Эмодзи-SOT консоли (канон RF chipContract / AIC chipContract):
 * каждый статус-чип = эмодзи + лейбл; эмодзи заменяет точку тихого чипа
 * и повторяется в фильтрах и на экране «Справка → Обозначения».
 *
 * Один эмодзи — одно понятие во всём портфеле. Распределение понятий
 * зафиксировано референсами (RF: «🟢 остаётся за HEALTH, ✔︎/🔄/❌ — исход
 * события, ⏳ — pending, ✅ — indexed»); семьи скопированы с аналогий
 * AIC/RF, где аналогии нет — значки согласованы с владельцем 2026-09-03
 * (ocr 🔤, vision 👁️, test 🧪, bypass ⏭️, info ℹ️). Вариант задаёт цвет
 * текста тихого чипа (.ai-status* в globals.css, канон LQ).
 */

export interface ChipEntry {
  emoji: string;
  label: string;
  variant: string;
}

export const VARIANT = {
  MUTED: "ai-status--muted",
  ERROR: "ai-status--error",
  SUCCESS: "ai-status--success",
  WARNING: "ai-status--warning",
  INFO: "ai-status--info",
};

/* — Универсальные понятия (одна семья на все экраны консоли) — */

/** Исход события (канон AIC LIFECYCLE_STATUS / RF TRACE_STATUS). */
export const TRACE: Record<string, ChipEntry> = {
  success: { emoji: "✔︎", label: "успех", variant: VARIANT.SUCCESS },
  running: { emoji: "🔄", label: "в работе", variant: VARIANT.INFO },
  waiting: { emoji: "⏳", label: "ожидание", variant: VARIANT.MUTED },
  failed: { emoji: "❌", label: "ошибка", variant: VARIANT.ERROR },
  neutral: { emoji: "➖", label: "—", variant: VARIANT.MUTED },
};

/** Состояние компонента (канон AIC HEALTH). */
export const HEALTH: Record<string, ChipEntry> = {
  ok: { emoji: "🟢", label: "норма", variant: VARIANT.SUCCESS },
  warning: { emoji: "⚠️", label: "внимание", variant: VARIANT.WARNING },
  degraded: { emoji: "🟠", label: "деградация", variant: VARIANT.WARNING },
  disabled: { emoji: "🚫", label: "отключено", variant: VARIANT.MUTED },
  unknown: { emoji: "➖", label: "н/д", variant: VARIANT.MUTED },
  error: { emoji: "❌", label: "ошибка", variant: VARIANT.ERROR },
};

/** Жизненный цикл документа (канон AIC DOC_STATUS). */
export const DOC_STATUS: Record<string, ChipEntry> = {
  draft: { emoji: "📝", label: "черновик", variant: VARIANT.MUTED },
  pending: { emoji: "⏳", label: "в ожидании", variant: VARIANT.INFO },
  processing: { emoji: "🔄", label: "обработка", variant: VARIANT.INFO },
  indexed: { emoji: "✅", label: "индексирован", variant: VARIANT.SUCCESS },
  error: { emoji: "❌", label: "ошибка", variant: VARIANT.ERROR },
  archived: { emoji: "🗄️", label: "архив", variant: VARIANT.MUTED },
};

/** Активность записи/версии (канон RF ENTITY_ACTIVE / AIC SESSION_ACTIVE). */
export const SESSION_ACTIVE: Record<string, ChipEntry> = {
  active: { emoji: "⚡", label: "активна", variant: VARIANT.SUCCESS },
  inactive: { emoji: "⏸️", label: "в архиве", variant: VARIANT.MUTED },
};

/** Результат retrieval-кэша (канон AIC RETRIEVAL hit 🎯 / miss 💨;
 *  bypass ⏭️ согласован с владельцем — аналогии в референсах нет). */
export const RETRIEVAL: Record<string, ChipEntry> = {
  hit: { emoji: "🎯", label: "hit", variant: VARIANT.SUCCESS },
  miss: { emoji: "💨", label: "miss", variant: VARIANT.MUTED },
  bypass: { emoji: "⏭️", label: "bypass", variant: VARIANT.MUTED },
  off: { emoji: "🚫", label: "off", variant: VARIANT.WARNING },
  na: { emoji: "➖", label: "n/a", variant: VARIANT.MUTED },
};

/** Модальности (эмодзи меню, утверждены владельцем; ocr 🔤 / vision 👁️ /
 *  test 🧪 — согласованы с владельцем, аналогии в референсах нет). */
export const MODALITY: Record<string, ChipEntry> = {
  rag: { emoji: "🔎", label: "rag", variant: VARIANT.MUTED },
  mem: { emoji: "🧠", label: "mem", variant: VARIANT.MUTED },
  text: { emoji: "💬", label: "text", variant: VARIANT.MUTED },
  ocr: { emoji: "🔤", label: "ocr", variant: VARIANT.MUTED },
  vision: { emoji: "👁️", label: "vision", variant: VARIANT.MUTED },
  audio: { emoji: "🔊", label: "audio", variant: VARIANT.MUTED },
  image: { emoji: "🖼️", label: "image", variant: VARIANT.MUTED },
  test: { emoji: "🧪", label: "test", variant: VARIANT.MUTED },
  doc: { emoji: "📄", label: "doc", variant: VARIANT.MUTED },
  log: { emoji: "📜", label: "log", variant: VARIANT.MUTED },
};

/** Серьёзность security-события (critical по аналогии RF PRIORITY 🚨;
 *  info ℹ️ согласован с владельцем). */
export const SEVERITY: Record<string, ChipEntry> = {
  info: { emoji: "ℹ️", label: "INFO", variant: VARIANT.INFO },
  warning: { emoji: "⚠️", label: "WARN", variant: VARIANT.WARNING },
  error: { emoji: "❌", label: "ERROR", variant: VARIANT.ERROR },
  critical: { emoji: "🚨", label: "CRIT", variant: VARIANT.ERROR },
};

/** Универсальный резолвер статуса StatusBadge → понятие из референсов. */
const STATUS_ALLOCATION: Record<string, ChipEntry> = {
  // 🟢 HEALTH: состояние компонента/системы
  ok: HEALTH.ok,
  configured: { ...HEALTH.ok, label: "настроено" },
  available: { ...HEALTH.ok, label: "доступно" },
  on: { ...HEALTH.ok, label: "вкл" },
  ready: { ...HEALTH.ok, label: "готово" },
  degraded: HEALTH.degraded,
  off: HEALTH.disabled,
  not_configured: { ...HEALTH.disabled, label: "не настроено" },
  // ✔︎/🔄/⏳/❌ TRACE: исход операции
  success: TRACE.success,
  succeeded: { ...TRACE.success, label: "выполнено" },
  completed: { ...TRACE.success, label: "завершено" },
  scored: { ...TRACE.success, label: "оценено" },
  started: { ...TRACE.running, label: "запущено" },
  running: TRACE.running,
  checking: TRACE.running,
  "checking…": TRACE.running,
  queued: { ...TRACE.waiting, label: "в очереди" },
  pending: { ...TRACE.waiting, label: "ожидание" },
  // ⚠️ HEALTH.warning: ограничение/устаревание/повтор
  warning: HEALTH.warning,
  empty: { ...HEALTH.warning, label: "пусто" },
  unreachable: { ...HEALTH.warning, label: "недоступно" },
  stale: { ...HEALTH.warning, label: "устарело" },
  missing: { ...HEALTH.warning, label: "нет в индексе" },
  retry_scheduled: { ...HEALTH.warning, label: "повтор запланирован" },
  // ❌ HEALTH.error
  error: HEALTH.error,
  failed: HEALTH.error,
  down: HEALTH.error,
  err: HEALTH.error,
  internal_error: { ...HEALTH.error, label: "внутренняя ошибка" },
  unavailable: HEALTH.error,
  unsupported: { ...HEALTH.error, label: "не поддерживается" },
  // ⚡/⏸️ SESSION_ACTIVE
  yes: SESSION_ACTIVE.active,
  no: SESSION_ACTIVE.inactive,
  // ✅ DOC_STATUS.indexed
  indexed: DOC_STATUS.indexed,
  // ➖ нейтрально
  skipped: { ...TRACE.neutral, label: "пропущено" },
  unknown: { ...TRACE.neutral, label: "неизвестно" },
  "not scored": { ...TRACE.neutral, label: "не оценено" },
  "—": TRACE.neutral,
};

export function statusChip(status: string): ChipEntry {
  const key = status.trim().toLowerCase();
  return (
    STATUS_ALLOCATION[key] ??
    { emoji: "➖", label: status || "—", variant: VARIANT.MUTED }
  );
}