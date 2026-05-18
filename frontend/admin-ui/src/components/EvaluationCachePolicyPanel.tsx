type Props = {
  retrievalDiag?: Record<string, unknown> | null;
  className?: string;
};

function readBypass(rd: Record<string, unknown>): boolean | null {
  const v = rd.evaluation_cache_bypass;
  if (v === true || v === false) return v;
  if (v === 1) return true;
  if (v === 0) return false;
  return null;
}

function readPolicy(rd: Record<string, unknown>): string | null {
  const p = rd.evaluation_cache_policy;
  return typeof p === "string" && p.trim() ? p.trim() : null;
}

export function EvaluationCachePolicyPanel({ retrievalDiag, className = "" }: Props) {
  const rd = retrievalDiag ?? {};
  const bypass = readBypass(rd);
  const policy = readPolicy(rd);

  return (
    <div className={`cache-obs-policy panel page__mt-sm${className ? ` ${className}` : ""}`}>
      <div className="cache-obs-policy__title">Политика кэша</div>
      {bypass === true ? (
        <>
          <p className="cache-obs-policy__badge">
            <span className="cache-obs-badge cache-obs-badge--bypass">BYPASS</span>
            <span className="cache-obs-policy__text">
              Кэш retrieval отключён для воспроизводимости оценки.
            </span>
          </p>
          {policy ? (
            <p className="muted cache-obs-policy__meta mono">
              evaluation_cache_policy: {policy}
            </p>
          ) : null}
        </>
      ) : (
        <p className="muted cache-obs-policy__text">
          Политика кэша не зафиксирована в данных.
        </p>
      )}
    </div>
  );
}
