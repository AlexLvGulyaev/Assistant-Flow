/** Компактная кнопка обновления данных списка (единый стиль operational console). */
export function OperationalRefreshButton({
  loading,
  onClick,
  className,
}: {
  loading?: boolean;
  onClick: () => void;
  /** Дополнительные классы (например стили тулбара документов). */
  className?: string;
}) {
  return (
    <button
      type="button"
      className={["ops-refresh-btn", className].filter(Boolean).join(" ")}
      onClick={onClick}
      disabled={!!loading}
      aria-busy={loading || undefined}
    >
      {loading ? "Обновление…" : "Обновить"}
    </button>
  );
}
