/** List pagination controls (RAG / Logs / Evaluation consoles). */

export function OperationalListPagination({
  pageIndex,
  totalPages,
  totalItems,
  pageSize,
  onPrev,
  onNext,
  disabled,
}: {
  pageIndex: number;
  totalPages: number;
  totalItems: number;
  pageSize: number;
  onPrev: () => void;
  onNext: () => void;
  disabled?: boolean;
}) {
  const shown = totalItems === 0 ? 0 : Math.min(pageSize, totalItems - pageIndex * pageSize);
  const pageNum = totalItems === 0 ? 0 : pageIndex + 1;
  const pages = Math.max(0, totalPages);

  return (
    <>
      <div className="logs-filter-meta muted">
        <span>
          Страница {pageNum} из {pages || 0} · всего: {totalItems}
          {totalItems > 0 ? ` · показано: ${shown}` : ""}
        </span>
      </div>
      <div className="logs-page-controls">
        <button
          type="button"
          className="logs-page-btn"
          onClick={onPrev}
          disabled={disabled || pageIndex <= 0 || totalItems === 0}
        >
          ← Предыдущая
        </button>
        <button
          type="button"
          className="logs-page-btn"
          onClick={onNext}
          disabled={disabled || pageIndex >= pages - 1 || totalItems === 0}
        >
          Следующая →
        </button>
      </div>
    </>
  );
}
