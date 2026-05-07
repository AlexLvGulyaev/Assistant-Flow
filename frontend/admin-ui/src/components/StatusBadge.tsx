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
    n === "configured" ||
    n === "available" ||
    n === "on" ||
    n === "yes"
  ) {
    tone = "ok";
  } else if (
    n === "degraded" ||
    n === "unreachable" ||
    n === "checking…" ||
    n === "started" ||
    n === "warning"
  ) {
    tone = "warn";
  } else if (
    n === "error" ||
    n.includes("fail") ||
    n === "err" ||
    n === "internal_error" ||
    n === "unavailable"
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

  return (
    <span className={`status-badge status-badge--${tone}`} title={status}>
      {status}
    </span>
  );
}
