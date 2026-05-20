/**
 * Единый collapsible-блок сырого JSON сессии (модальные страницы Admin UI).
 */
export function SessionJsonSnapshot({
  body,
  className,
  summaryLabel = "Технический снимок сессии (JSON)",
}: {
  body: string;
  className?: string;
  summaryLabel?: string;
}) {
  return (
    <details
      className={["session-json-snapshot", className].filter(Boolean).join(" ")}
    >
      <summary className="session-json-snapshot__summary">{summaryLabel}</summary>
      <pre className="session-json-snapshot__pre mono">{body}</pre>
    </details>
  );
}
