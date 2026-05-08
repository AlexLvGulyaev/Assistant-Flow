interface EmptyStateProps {
  title?: string;
  message: string;
}

export function EmptyState({
  title = "Пусто",
  message,
}: EmptyStateProps) {
  return (
    <div className="empty-state" role="status">
      <p className="empty-state__title">{title}</p>
      <p className="empty-state__msg muted">{message}</p>
    </div>
  );
}
