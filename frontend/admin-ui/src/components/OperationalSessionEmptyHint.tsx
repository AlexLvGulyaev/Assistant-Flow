/** Подсказка при отсутствии сессий за период (не «модальность отсутствует»). */
export function OperationalSessionEmptyHint({
  title,
  hint,
  showExpand7d,
  onExpand7d,
}: {
  title: string;
  hint: string;
  showExpand7d?: boolean;
  onExpand7d?: () => void;
}) {
  return (
    <div className="panel panel--muted ops-session-empty-hint">
      <p className="ops-session-empty-hint__title">{title}</p>
      <p className="ops-session-empty-hint__sub muted">{hint}</p>
      {showExpand7d && onExpand7d ? (
        <button type="button" className="logs-page-btn page__mt-sm" onClick={onExpand7d}>
          Показать за 7 дней
        </button>
      ) : null}
    </div>
  );
}
