function fmt(v: unknown): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "boolean") return v ? "true" : "false";
  return String(v);
}

function answerCacheValue(raw: unknown): string {
  const on = raw === true || raw === "true" || raw === 1 || raw === "1";
  return on ? "true · reserved" : "false · reserved";
}

function CacheEnvRow({ label, value, source }: { label: string; value: string; source?: string }) {
  return (
    <>
      <dt>
        {label}
        {source === "db" || source === "env" ? (
          <span className="retrieval-settings__src" title={source === "db" ? "PostgreSQL" : "Env"}>
            {source}
          </span>
        ) : null}
      </dt>
      <dd>
        <input readOnly className="retrieval-settings__ro" value={value} spellCheck={false} />
      </dd>
    </>
  );
}

type CacheSnapshot = Record<string, unknown>;

type Props = {
  cache: CacheSnapshot;
  databaseConfigured: boolean;
  cacheBusy: boolean;
  onSetRetrievalCache: (enabled: boolean) => void;
};

export function RetrievalCacheSettingsPanel({
  cache,
  databaseConfigured,
  cacheBusy,
  onSetRetrievalCache,
}: Props) {
  const enabled =
    cache.enable_retrieval_cache === true ||
    cache.enable_retrieval_cache === "true" ||
    cache.enable_retrieval_cache === 1;
  const source =
    cache.enable_retrieval_cache_source === "db"
      ? "db"
      : cache.enable_retrieval_cache_source === "env"
        ? "env"
        : undefined;
  const applyNote = fmt(cache.apply_note);

  return (
    <div className="retrieval-cache-panel">
      <dl className="retrieval-settings__kv retrieval-settings__kv--grid">
        <dt>
          ENABLE_RETRIEVAL_CACHE
          {source ? (
            <span className="retrieval-settings__src" title={source === "db" ? "PostgreSQL" : "Env"}>
              {source}
            </span>
          ) : null}
        </dt>
        <dd className="retrieval-cache-panel__toggle-cell">
          <div className="retrieval-cache-panel__toggle" role="group" aria-label="Retrieval cache">
            <button
              type="button"
              className={`retrieval-cache-panel__toggle-btn${!enabled ? " retrieval-cache-panel__toggle-btn--active" : ""}`}
              disabled={!databaseConfigured || cacheBusy || !enabled}
              onClick={() => void onSetRetrievalCache(false)}
            >
              OFF
            </button>
            <button
              type="button"
              className={`retrieval-cache-panel__toggle-btn${enabled ? " retrieval-cache-panel__toggle-btn--active" : ""}`}
              disabled={!databaseConfigured || cacheBusy || enabled}
              onClick={() => void onSetRetrievalCache(true)}
            >
              ON
            </button>
          </div>
          {!databaseConfigured ? (
            <span className="muted retrieval-settings__micro retrieval-cache-panel__toggle-hint">
              DATABASE_URL required
            </span>
          ) : null}
        </dd>
        <CacheEnvRow
          label="RETRIEVAL_CACHE_TTL_SECONDS"
          value={fmt(cache.retrieval_cache_ttl_seconds)}
        />
        <CacheEnvRow label="RAG_RETRIEVAL_GENERATION" value={fmt(cache.rag_retrieval_generation)} />
        <CacheEnvRow label="ENABLE_ANSWER_CACHE" value={answerCacheValue(cache.enable_answer_cache)} />
      </dl>
      {applyNote !== "—" ? (
        <p className="muted retrieval-settings__micro retrieval-cache-panel__foot">{applyNote}</p>
      ) : null}
      <details className="retrieval-settings__details retrieval-cache-panel__diag">
        <summary className="retrieval-settings__details-summary">Cache diagnostics</summary>
        <div className="retrieval-settings__details-body">
          <dl className="retrieval-settings__kv retrieval-settings__kv--grid retrieval-settings__kv--wide">
            <dt>NAMESPACE</dt>
            <dd>
              <input readOnly className="retrieval-settings__ro" value="retrieval" spellCheck={false} />
            </dd>
            <dt>EDITABLE_VIA_API</dt>
            <dd>
              <input
                readOnly
                className="retrieval-settings__ro"
                value={fmt(cache.editable_via_api)}
                spellCheck={false}
              />
            </dd>
          </dl>
        </div>
      </details>
    </div>
  );
}
