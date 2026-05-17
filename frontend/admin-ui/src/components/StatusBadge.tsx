interface StatusBadgeProps {
  status: string;
}

function normalizeStatus(s: string): string {
  return s.trim().toLowerCase();
}

export function StatusBadge({ status }: StatusBadgeProps) {
  const n = normalizeStatus(status);
  let tone: "ok" | "warn" | "err" | "muted" = "muted";
  if (
    n === "ok" ||
    n === "ready" ||
    n === "configured" ||
    n === "available" ||
    n === "on" ||
    n === "yes" ||
    n === "indexed"
  ) {
    tone = "ok";
  } else if (
    n === "degraded" ||
    n === "empty" ||
    n === "unreachable" ||
    n === "checking…" ||
    n === "started" ||
    n === "warning" ||
    n === "pending" ||
    n === "stale" ||
    n === "missing"
  ) {
    tone = "warn";
  } else if (
    n === "error" ||
    n === "down" ||
    n.includes("fail") ||
    n === "err" ||
    n === "internal_error" ||
    n === "unavailable" ||
    n === "unsupported"
  ) {
    tone = "err";
  } else if (
    n === "off" ||
    n === "not_configured" ||
    n === "no" ||
    n === "—"
  ) {
    tone = "muted";
  }

  const label =
    {
      ok: "норма",
      success: "успех",
      error: "ошибка",
      failed: "ошибка",
      available: "доступно",
      unavailable: "недоступно",
      configured: "настроено",
      not_configured: "не настроено",
      started: "запущено",
      running: "в работе",
      skipped: "пропущено",
      completed: "завершено",
      scored: "оценено",
      "not scored": "не оценено",
      degraded: "ограничено",
      empty: "EMPTY",
      ready: "READY",
      down: "DOWN",
      unknown: "неизвестно",
      unreachable: "недоступно",
      checking: "проверка",
      "checking…": "проверка",
      indexed: "проиндексирован",
      pending: "ожидание",
      missing: "нет в индексе",
      stale: "устарело",
      unsupported: "не поддерживается",
      on: "вкл",
      off: "выкл",
      yes: "да",
      no: "нет",
    }[n] ?? status;

  return (
    <span className={`status-badge status-badge--${tone}`} title={status}>
      {label}
    </span>
  );
}
