interface StatusBadgeProps {
  status: string;
}

function normalizeStatus(s: string): string {
  return s.trim().toLowerCase();
}

export function StatusBadge({ status }: StatusBadgeProps) {
  const n = normalizeStatus(status);
  let tone: "ok" | "warn" | "err" | "muted" = "muted";
  if (n === "ok" || n === "configured") tone = "ok";
  else if (
    n === "degraded" ||
    n === "unreachable" ||
    n === "started" ||
    n === "warning"
  )
    tone = "warn";
  else if (
    n === "error" ||
    n.includes("fail") ||
    n === "err" ||
    n === "internal_error"
  )
    tone = "err";

  return (
    <span className={`status-badge status-badge--${tone}`} title={status}>
      {status}
    </span>
  );
}
