interface LoadingStateProps {
  label?: string;
}

export function LoadingState({ label = "Загрузка…" }: LoadingStateProps) {
  return (
    <div className="loading-state" role="status" aria-busy="true">
      <div className="loading-state__pulse" />
      <span className="loading-state__label muted">{label}</span>
    </div>
  );
}
