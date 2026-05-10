/**
 * Единый collapsible-блок сырого JSON сессии (модальные страницы Admin UI).
 */
export function SessionJsonSnapshot({
  body,
  className,
}: {
  body: string;
  className?: string;
}) {
  return (
    <details
      className={["session-json-snapshot", className].filter(Boolean).join(" ")}
    >
      <summary className="session-json-snapshot__summary">
        Технический снимок сессии (JSON)
      </summary>
      <pre className="session-json-snapshot__pre mono">{body}</pre>
    </details>
  );
}
