import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  deleteRetrievalTuning,
  fetchRetrievalOverview,
  fetchRetrievalTuning,
  putRetrievalTuning,
  setActiveRetrievalBackend,
  type RetrievalBackendHealthRow,
  type RetrievalOverviewResponse,
  type RetrievalTuningResponse,
} from "../api/client";
import { EmptyState } from "../components/EmptyState";
import { LoadingState } from "../components/LoadingState";
import { OperationalRefreshButton } from "../components/OperationalRefreshButton";
import { SectionCard } from "../components/SectionCard";
import { RetrievalCacheSettingsPanel } from "../components/RetrievalCacheSettingsPanel";

function Badge({
  text,
  tone,
}: {
  text: string;
  tone: "ok" | "warn" | "err" | "muted";
}) {
  return <span className={`status-badge status-badge--${tone}`}>{text}</span>;
}

const BACKEND_ORDER = ["chroma", "faiss", "weaviate"] as const;

const RUNTIME_TUNING_KEYS = [
  "rag_top_k",
  "rag_max_distance",
  "rag_answer_max_tokens",
  "rag_retrieval_timeout",
  "rag_embedding_request_timeout",
] as const;

const INDEXING_TUNING_KEYS = ["rag_chunk_size", "rag_chunk_overlap"] as const;

const ALL_TUNING_KEYS = [...RUNTIME_TUNING_KEYS, ...INDEXING_TUNING_KEYS] as const;

function fmt(v: unknown): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "boolean") return v ? "true" : "false";
  return String(v);
}

function draftFromTuning(t: RetrievalTuningResponse): Record<string, string> {
  const o: Record<string, string> = {};
  for (const k of ALL_TUNING_KEYS) {
    const v = t.effective[k as string];
    o[k as string] = typeof v === "number" && Number.isFinite(v) ? String(v) : "";
  }
  return o;
}

function draftParseError(d: Record<string, string>): string | null {
  for (const k of ALL_TUNING_KEYS) {
    const s = String(d[k as string] ?? "").trim();
    if (s === "") return `${k}: empty`;
    const n = Number(s);
    if (!Number.isFinite(n)) return `${k}: not a valid number`;
  }
  return null;
}

function buildTuningPatch(
  draft: Record<string, string>,
  saved: RetrievalTuningResponse
): Record<string, number> {
  const patch: Record<string, number> = {};
  for (const k of ALL_TUNING_KEYS) {
    const parsed = Number(String(draft[k as string] ?? "").trim());
    const prev = saved.effective[k as string];
    if (typeof prev !== "number" || !Number.isFinite(prev)) {
      patch[k as string] = parsed;
      continue;
    }
    if (Math.abs(parsed - prev) > 1e-9) {
      patch[k as string] = parsed;
    }
  }
  return patch;
}

function readinessBadge(row: RetrievalBackendHealthRow | undefined): {
  label: string;
  tone: "ok" | "warn" | "err";
} {
  if (!row) return { label: "unknown", tone: "warn" };
  if (!row.ok) return { label: "not ready", tone: "err" };
  const n = row.collection_count;
  if (n === 0) return { label: "empty index", tone: "warn" };
  return { label: "ready", tone: "ok" };
}

function SourceChip({ source }: { source?: string }) {
  if (source !== "db" && source !== "env") return null;
  return (
    <span className="retrieval-settings__src" title={source === "db" ? "PostgreSQL override" : "Env default"}>
      {source}
    </span>
  );
}

export function RetrievalSettingsPage() {
  const [data, setData] = useState<RetrievalOverviewResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [switching, setSwitching] = useState(false);
  const [selected, setSelected] = useState<string>("chroma");
  const [lastSwitchWarnings, setLastSwitchWarnings] = useState<string[] | null>(null);
  const [refreshNonce, setRefreshNonce] = useState(0);

  const [tuning, setTuning] = useState<RetrievalTuningResponse | null>(null);
  const [tuningLoadError, setTuningLoadError] = useState<string | null>(null);
  const [tuningDraft, setTuningDraft] = useState<Record<string, string>>({});
  const [tuningBusy, setTuningBusy] = useState(false);
  const [cacheBusy, setCacheBusy] = useState(false);
  const [tuningSaveError, setTuningSaveError] = useState<string | null>(null);
  const [lastTuneReindex, setLastTuneReindex] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    setTuningLoadError(null);
    setTuningSaveError(null);
    try {
      const o = await fetchRetrievalOverview();
      setData(o);
      const eff = (o.effective_backend || "chroma").toLowerCase();
      if (BACKEND_ORDER.includes(eff as (typeof BACKEND_ORDER)[number])) {
        setSelected(eff);
      }
      try {
        const t = await fetchRetrievalTuning();
        setTuning(t);
        setTuningDraft(draftFromTuning(t));
        setLastTuneReindex(false);
      } catch (e) {
        setTuning(null);
        setTuningDraft({});
        setTuningLoadError(e instanceof Error ? e.message : "Failed to load /api/retrieval/tuning");
      }
    } catch (e) {
      setData(null);
      setTuning(null);
      setTuningDraft({});
      setError(e instanceof Error ? e.message : "Failed to load retrieval overview");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load, refreshNonce]);

  const activeHealth = data?.active_backend_health;
  const reindexHint = useMemo(() => {
    if (!data?.effective_backend) return false;
    const h = data.active_backend_health;
    if (!h?.ok) return true;
    const n = h.collection_count;
    return n === 0 || n === null;
  }, [data]);

  const onApply = async () => {
    setSwitching(true);
    setLastSwitchWarnings(null);
    setError(null);
    try {
      const res = await setActiveRetrievalBackend(selected);
      setLastSwitchWarnings(res.warnings ?? []);
      setRefreshNonce((n) => n + 1);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Switch failed");
    } finally {
      setSwitching(false);
    }
  };

  const backendRows = useMemo(() => {
    const raw = data?.backends ?? {};
    const keys = new Set([...BACKEND_ORDER, ...Object.keys(raw)]);
    return [...keys].sort();
  }, [data]);

  const rt = data?.runtime_tuning ?? {};
  const it = data?.indexing_tuning ?? {};
  const cache = data?.cache ?? {};
  const paths = data?.paths ?? {};

  const rtSources = (rt.field_sources ?? {}) as Record<string, string>;
  const itSources = (it.field_sources ?? {}) as Record<string, string>;

  const tuningDirty = useMemo(() => {
    if (!tuning) return false;
    const pe = draftParseError(tuningDraft);
    if (pe) return true;
    return Object.keys(buildTuningPatch(tuningDraft, tuning)).length > 0;
  }, [tuning, tuningDraft]);

  const tuningSaveDisabled = useMemo(() => {
    if (!data?.database_configured || !tuning || tuningBusy) return true;
    if (draftParseError(tuningDraft)) return true;
    return Object.keys(buildTuningPatch(tuningDraft, tuning)).length === 0;
  }, [data?.database_configured, tuning, tuningBusy, tuningDraft]);

  const onSaveTuning = async () => {
    if (!tuning || tuningSaveDisabled) return;
    setTuningBusy(true);
    setTuningSaveError(null);
    try {
      const patch = buildTuningPatch(tuningDraft, tuning);
      const res = await putRetrievalTuning(patch);
      setTuning(res);
      setTuningDraft(draftFromTuning(res));
      setLastTuneReindex(Boolean(res.reindex_required));
      setRefreshNonce((n) => n + 1);
    } catch (e) {
      setTuningSaveError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setTuningBusy(false);
    }
  };

  const onSetRetrievalCache = async (enabled: boolean) => {
    if (!data?.database_configured || cacheBusy) return;
    setCacheBusy(true);
    setTuningSaveError(null);
    try {
      const res = await putRetrievalTuning({
        enable_retrieval_cache: enabled === true,
      });
      setTuning(res);
      setTuningDraft(draftFromTuning(res));
      setRefreshNonce((n) => n + 1);
    } catch (e) {
      setTuningSaveError(e instanceof Error ? e.message : "Cache toggle failed");
    } finally {
      setCacheBusy(false);
    }
  };

  const onClearTuning = async () => {
    if (!data?.database_configured || tuningBusy) return;
    setTuningBusy(true);
    setTuningSaveError(null);
    try {
      const res = await deleteRetrievalTuning();
      setTuning(res);
      setTuningDraft(draftFromTuning(res));
      setLastTuneReindex(Boolean(res.reindex_required));
      setRefreshNonce((n) => n + 1);
    } catch (e) {
      setTuningSaveError(e instanceof Error ? e.message : "Clear failed");
    } finally {
      setTuningBusy(false);
    }
  };

  const head = (
    <div className="retrieval-settings__head">
      <div>
        <h1 className="page__title">Retrieval Settings</h1>
        <p className="page__lead muted">
          Active vector backend (DB + env), health matrix, RAG/indexing tuning via{" "}
          <code>platform_settings</code> when <code>DATABASE_URL</code> is set. No silent fallback to
          Chroma — unhealthy backends stay visible.
        </p>
      </div>
      <OperationalRefreshButton
        loading={loading}
        onClick={() => setRefreshNonce((n) => n + 1)}
      />
    </div>
  );

  if (loading && !data) {
    return (
      <div className="retrieval-settings page">
        {head}
        <LoadingState label="Загрузка /api/retrieval/overview и /api/retrieval/tuning…" />
      </div>
    );
  }

  if (error && !data) {
    return (
      <div className="retrieval-settings page">
        {head}
        <EmptyState title="Ошибка" message={error} />
      </div>
    );
  }

  return (
    <div className="retrieval-settings page">
      {head}

      {data?.degraded ? (
        <div className="retrieval-settings__alert retrieval-settings__alert--warn" role="status">
          <strong>Degraded:</strong> could not read PostgreSQL for{" "}
          <code>platform_settings</code> (using env default for effective backend). Check{" "}
          <code>DATABASE_URL</code> and migrations.
        </div>
      ) : null}

      {error ? (
        <div className="retrieval-settings__alert retrieval-settings__alert--bad" role="alert">
          {error}
        </div>
      ) : null}

      {tuningLoadError ? (
        <div className="retrieval-settings__alert retrieval-settings__alert--warn" role="status">
          <strong>Tuning API:</strong> {tuningLoadError} (values below from overview snapshot only).
        </div>
      ) : null}

      {tuningSaveError ? (
        <div className="retrieval-settings__alert retrieval-settings__alert--bad" role="alert">
          {tuningSaveError}
        </div>
      ) : null}

      {lastTuneReindex ? (
        <div className="retrieval-settings__alert retrieval-settings__alert--warn" role="status">
          <strong>Reindex required:</strong> chunk settings changed. Run a{" "}
          <strong>full reindex</strong> on the active vector backend from{" "}
          <Link to="/documents" className="retrieval-settings__link">
            Documents
          </Link>{" "}
          before relying on new chunk boundaries.
        </div>
      ) : null}

      {lastSwitchWarnings && lastSwitchWarnings.length > 0 ? (
        <div className="retrieval-settings__alert retrieval-settings__alert--warn" role="status">
          <strong>Switch warnings:</strong>
          <ul className="retrieval-settings__warn-list">
            {lastSwitchWarnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
          <p className="muted retrieval-settings__alert-foot">
            Full reindex on the <strong>Documents</strong> page may be required or recommended after
            changing backend or corpus.
          </p>
        </div>
      ) : null}

      {reindexHint ? (
        <div className="retrieval-settings__alert retrieval-settings__alert--info" role="note">
          <strong>Reindex recommended:</strong> active backend health is not OK or collection count is
          zero. Use{" "}
          <Link to="/documents" className="retrieval-settings__link">
            Documents
          </Link>{" "}
          → full reindex when the target index is ready.
        </div>
      ) : null}

      <div className="retrieval-settings__grid2">
        <div className="retrieval-settings__panel">
          <SectionCard
            title="Active backend"
            description="DB row when valid, else env RAG_BACKEND. Switch → platform_settings (needs DATABASE_URL)."
          >
            <dl className="retrieval-settings__kv">
              <dt>Effective</dt>
              <dd>
                <code>{fmt(data?.effective_backend)}</code>{" "}
                {activeHealth ? (
                  <Badge
                    text={activeHealth.ok ? "health ok" : "health not ok"}
                    tone={activeHealth.ok ? "ok" : "err"}
                  />
                ) : null}
              </dd>
              <dt>Env default</dt>
              <dd>
                <code>{fmt(data?.env_default_backend)}</code>
              </dd>
              <dt>DB active</dt>
              <dd>
                {data?.db_active_backend == null ? (
                  <span className="muted">(no row — env default in use)</span>
                ) : (
                  <code>{data.db_active_backend}</code>
                )}
              </dd>
              <dt>Postgres</dt>
              <dd>
                {data?.database_configured ? (
                  <Badge text="DATABASE_URL configured" tone="ok" />
                ) : (
                  <Badge text="DATABASE_URL missing" tone="err" />
                )}
              </dd>
            </dl>

            <div className="retrieval-settings__switch-row">
              <label className="retrieval-settings__label" htmlFor="retrieval-backend-select">
                Target backend
              </label>
              <select
                id="retrieval-backend-select"
                className="retrieval-settings__select"
                value={selected}
                onChange={(e) => setSelected(e.target.value)}
                disabled={switching || !data?.database_configured}
              >
                {(data?.allowed_backends ?? [...BACKEND_ORDER]).map((b) => (
                  <option key={b} value={b}>
                    {b}
                  </option>
                ))}
              </select>
              <button
                type="button"
                className="retrieval-settings__apply"
                onClick={() => void onApply()}
                disabled={
                  switching ||
                  !data?.database_configured ||
                  !selected ||
                  selected === data?.effective_backend
                }
              >
                {switching ? "Applying…" : "Apply switch"}
              </button>
            </div>
            {!data?.database_configured ? (
              <p className="muted retrieval-settings__hint">
                Backend switch is disabled until <code>DATABASE_URL</code> is set for the Admin API
                process.
              </p>
            ) : (
              <p className="muted retrieval-settings__hint">
                Unhealthy targets are still allowed — warnings appear above. Telegram RAG picks up the
                new effective backend shortly (manager cache); run reindex for the chosen store.
              </p>
            )}
            {data?.warnings && data.warnings.length > 0 ? (
              <div className="retrieval-settings__subwarn">
                <strong>Overview warnings</strong>
                <ul>
                  {data.warnings.map((w) => (
                    <li key={w}>{w}</li>
                  ))}
                </ul>
              </div>
            ) : null}
          </SectionCard>
        </div>

        <div className="retrieval-settings__panel">
          <SectionCard
            title="Backend health matrix"
            description="Per-backend probe (OpenAI embeddings for non-Chroma)."
          >
            <div className="retrieval-settings__table-wrap">
              <table className="retrieval-settings__table">
                <thead>
                  <tr>
                    <th>Backend</th>
                    <th>OK</th>
                    <th>Collection</th>
                    <th>Readiness</th>
                    <th>Detail / warnings</th>
                  </tr>
                </thead>
                <tbody>
                  {backendRows.map((key) => {
                    const row = data?.backends?.[key];
                    const rb = readinessBadge(row);
                    const isActive = key === data?.effective_backend;
                    return (
                      <tr key={key} className={isActive ? "retrieval-settings__row--active" : undefined}>
                        <td>
                          <code>{key}</code>
                          {isActive ? <span className="retrieval-settings__pill">active</span> : null}
                        </td>
                        <td>
                          {row ? (
                            <Badge text={row.ok ? "yes" : "no"} tone={row.ok ? "ok" : "err"} />
                          ) : (
                            "—"
                          )}
                        </td>
                        <td>{row?.collection_count ?? "—"}</td>
                        <td>
                          <Badge text={rb.label} tone={rb.tone} />
                        </td>
                        <td className="retrieval-settings__cell-detail">
                          {!row?.ok && row?.detail ? (
                            <span className="retrieval-settings__detail-err">{row.detail}</span>
                          ) : null}
                          {row?.ok && (row.collection_count === 0 || row.collection_count == null) ? (
                            <span className="retrieval-settings__detail-warn">
                              Empty or unknown count — consider reindex.
                            </span>
                          ) : null}
                          {row?.ok && row.collection_count != null && row.collection_count > 0 ? (
                            <span className="muted">—</span>
                          ) : null}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </SectionCard>
        </div>
      </div>

      <div className="retrieval-settings__grid2">
        <div className="retrieval-settings__panel">
          <SectionCard
            title="Runtime tuning / RAG query"
            description="Overrides in PostgreSQL; runtime fields apply within ~2.5s (no container rebuild)."
          >
            <dl className="retrieval-settings__kv retrieval-settings__kv--grid">
              {RUNTIME_TUNING_KEYS.map((k) => (
                <FragmentRow
                  key={k}
                  label={k.toUpperCase()}
                  source={rtSources[k] ?? (k in (tuning?.db_overrides ?? {}) ? "db" : "env")}
                  value={tuning ? tuningDraft[k] : fmt(rt[k])}
                  disabled={!tuning || tuningBusy || !data?.database_configured}
                  onChange={(v) => setTuningDraft((d) => ({ ...d, [k]: v }))}
                />
              ))}
            </dl>
            <div className="retrieval-settings__tuning-actions">
              <button
                type="button"
                className="retrieval-settings__apply"
                disabled={tuningSaveDisabled}
                onClick={() => void onSaveTuning()}
              >
                {tuningBusy ? "Saving…" : "Save runtime"}
              </button>
              <button
                type="button"
                className="retrieval-settings__btn-quiet"
                disabled={!data?.database_configured || tuningBusy || !tuning}
                onClick={() => void onClearTuning()}
              >
                Clear DB overrides
              </button>
              {tuningDirty ? (
                <span className="retrieval-settings__dirty muted">unsaved</span>
              ) : (
                <span className="muted retrieval-settings__micro">saved</span>
              )}
            </div>
            {draftParseError(tuningDraft) && tuning ? (
              <p className="retrieval-settings__detail-err retrieval-settings__micro">
                {draftParseError(tuningDraft)}
              </p>
            ) : null}
            <p className="muted retrieval-settings__micro">{fmt(rt.planned_note)}</p>
          </SectionCard>
        </div>

        <div className="retrieval-settings__panel">
          <SectionCard
            title="Indexing tuning / chunking"
            description="Applies on next reindex / upload indexing only."
          >
            <div className="retrieval-settings__alert retrieval-settings__alert--warn retrieval-settings__micro-alert">
              {fmt(it.reindex_warning)}
            </div>
            <dl className="retrieval-settings__kv retrieval-settings__kv--grid">
              {INDEXING_TUNING_KEYS.map((k) => (
                <FragmentRow
                  key={k}
                  label={k.toUpperCase()}
                  source={itSources[k] ?? (k in (tuning?.db_overrides ?? {}) ? "db" : "env")}
                  value={tuning ? tuningDraft[k] : fmt(it[k])}
                  disabled={!tuning || tuningBusy || !data?.database_configured}
                  onChange={(v) => setTuningDraft((d) => ({ ...d, [k]: v }))}
                />
              ))}
            </dl>
            <div className="retrieval-settings__tuning-actions">
              <button
                type="button"
                className="retrieval-settings__apply"
                disabled={tuningSaveDisabled}
                onClick={() => void onSaveTuning()}
              >
                {tuningBusy ? "Saving…" : "Save indexing"}
              </button>
              <button
                type="button"
                className="retrieval-settings__btn-quiet"
                disabled={!data?.database_configured || tuningBusy || !tuning}
                onClick={() => void onClearTuning()}
              >
                Clear DB overrides
              </button>
            </div>
          </SectionCard>
        </div>
      </div>

      <SectionCard
        title="Retrieval cache"
        description="ENABLE_RETRIEVAL_CACHE via tuning API (~2.5s). Hit/miss on RAG page."
      >
        <RetrievalCacheSettingsPanel
          cache={cache}
          databaseConfigured={Boolean(data?.database_configured)}
          cacheBusy={cacheBusy}
          onSetRetrievalCache={(v) => void onSetRetrievalCache(v)}
        />
      </SectionCard>


      <details className="retrieval-settings__details">
        <summary className="retrieval-settings__details-summary">Системные пути и подключения</summary>
        <div className="retrieval-settings__details-body">
          <p className="muted retrieval-settings__micro">
            Только чтение: пути и подключения из env / AppConfig (для инфраструктурной проверки).
          </p>
          <dl className="retrieval-settings__kv retrieval-settings__kv--grid retrieval-settings__kv--wide">
            <dt>CHROMA_HOST</dt>
            <dd>
              <input readOnly className="retrieval-settings__ro" value={fmt(paths.chroma_host)} />
            </dd>
            <dt>CHROMA_PORT</dt>
            <dd>
              <input readOnly className="retrieval-settings__ro" value={fmt(paths.chroma_port)} />
            </dd>
            <dt>CHROMA_USE_HTTP</dt>
            <dd>
              <input readOnly className="retrieval-settings__ro" value={fmt(paths.chroma_use_http)} />
            </dd>
            <dt>CHROMA_PERSIST_DIR</dt>
            <dd>
              <input readOnly className="retrieval-settings__ro" value={fmt(paths.chroma_persist_dir)} />
            </dd>
            <dt>RAG_DOCUMENTS_DIR</dt>
            <dd>
              <input readOnly className="retrieval-settings__ro" value={fmt(paths.rag_documents_dir)} />
            </dd>
            <dt>FAISS_INDEX_DIR</dt>
            <dd>
              <input readOnly className="retrieval-settings__ro" value={fmt(paths.faiss_index_dir)} />
            </dd>
            <dt>WEAVIATE_HOST</dt>
            <dd>
              <input readOnly className="retrieval-settings__ro" value={fmt(paths.weaviate_host)} />
            </dd>
            <dt>WEAVIATE_HTTP_PORT</dt>
            <dd>
              <input readOnly className="retrieval-settings__ro" value={fmt(paths.weaviate_http_port)} />
            </dd>
            <dt>WEAVIATE_URL</dt>
            <dd>
              <input readOnly className="retrieval-settings__ro" value={fmt(paths.weaviate_url)} />
            </dd>
            <dt>CACHE_DB_PATH</dt>
            <dd>
              <input readOnly className="retrieval-settings__ro" value={fmt(paths.cache_db_path)} />
            </dd>
          </dl>
        </div>
      </details>
    </div>
  );
}

function FragmentRow({
  label,
  source,
  value,
  disabled,
  onChange,
}: {
  label: string;
  source: string;
  value: string;
  disabled: boolean;
  onChange: (v: string) => void;
}) {
  return (
    <>
      <dt>
        {label}
        <SourceChip source={source} />
      </dt>
      <dd>
        <input
          className={disabled ? "retrieval-settings__ro" : "retrieval-settings__in"}
          readOnly={disabled}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          spellCheck={false}
        />
      </dd>
    </>
  );
}
