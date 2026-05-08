import { useEffect, useMemo, useState } from "react";
import {
  fetchDocuments,
  type DocumentItem,
  type DocumentsResponse,
  type LogItem,
} from "../api/client";
import { EmptyState } from "../components/EmptyState";
import { LoadingState } from "../components/LoadingState";
import { StatusBadge } from "../components/StatusBadge";

const INITIAL_LIMIT = 200;
const LIMIT_STEP = 100;

export function DocumentsPage() {
  const [limit, setLimit] = useState(INITIAL_LIMIT);
  const [data, setData] = useState<DocumentsResponse | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState("all");
  const [extFilter, setExtFilter] = useState("all");
  const [search, setSearch] = useState("");
  const [indexedOnly, setIndexedOnly] = useState(false);
  const [errorsOnly, setErrorsOnly] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const res = await fetchDocuments(limit);
        if (!cancelled) setData(res);
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : "Не удалось загрузить документы");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [limit]);

  const items = data?.items ?? [];
  const observability = data?.observability ?? {};
  const extensions = useMemo(
    () => Array.from(new Set(items.map((d) => d.extension || "—"))).sort(),
    [items]
  );

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return items.filter((d) => {
      if (statusFilter !== "all" && d.status !== statusFilter) return false;
      if (extFilter !== "all" && d.extension !== extFilter) return false;
      if (indexedOnly && d.status !== "indexed") return false;
      if (errorsOnly && d.status !== "error") return false;
      if (!q) return true;
      const hay = [
        d.filename,
        d.extension,
        d.status,
        d.status_raw,
        d.path_category,
        String(d.chunk_count ?? ""),
      ]
        .join(" ")
        .toLowerCase();
      return hay.includes(q);
    });
  }, [errorsOnly, extFilter, indexedOnly, items, search, statusFilter]);

  useEffect(() => {
    if (!filtered.length) {
      setSelectedId(null);
      return;
    }
    if (!selectedId || !filtered.some((d) => d.document_id === selectedId)) {
      setSelectedId(filtered[0].document_id);
    }
  }, [filtered, selectedId]);

  const selected = filtered.find((d) => d.document_id === selectedId) ?? null;
  const canLoadMore = items.length >= limit;

  return (
    <div className="page logs-page">
      <h1 className="page__title">Документы</h1>
      <p className="page__lead muted">
        Document inventory & indexing observability · <code>/api/documents</code>
      </p>
      {loading ? (
        <LoadingState label="Загрузка документов…" />
      ) : error ? (
        <div className="panel panel--error page__mt" role="alert">
          {error}
        </div>
      ) : items.length === 0 ? (
        <section className="card">
          <EmptyState message="Нет documents returned by API." />
        </section>
      ) : (
        <div className="logs-console docs-console">
          <section className="logs-left card">
            <div className="logs-filters">
              <div className="logs-filter-row docs-filter-row">
                <select
                  className="logs-select"
                  value={statusFilter}
                  onChange={(e) => setStatusFilter(e.target.value)}
                >
                  <option value="all">статус: все</option>
                  <option value="indexed">indexed</option>
                  <option value="pending">pending</option>
                  <option value="error">error</option>
                  <option value="missing">missing</option>
                  <option value="unsupported">unsupported</option>
                  <option value="stale">stale</option>
                </select>
                <select
                  className="logs-select"
                  value={extFilter}
                  onChange={(e) => setExtFilter(e.target.value)}
                >
                  <option value="all">type: all</option>
                  {extensions.map((e) => (
                    <option key={e} value={e}>
                      {e}
                    </option>
                  ))}
                </select>
                <button
                  type="button"
                  className="admin-shell__refresh"
                  onClick={() => setLimit(INITIAL_LIMIT)}
                >
                  сброс
                </button>
              </div>
              <input
                className="logs-search"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="поиск filename / status / extension"
              />
              <div className="logs-quick-row">
                <button
                  type="button"
                  className={`logs-chip ${indexedOnly ? "logs-chip--active" : ""}`}
                  onClick={() => setIndexedOnly((v) => !v)}
                >
                  indexed only
                </button>
                <button
                  type="button"
                  className={`logs-chip ${errorsOnly ? "logs-chip--active" : ""}`}
                  onClick={() => setErrorsOnly((v) => !v)}
                >
                  errors only
                </button>
              </div>
              <div className="logs-filter-meta muted">
                docs {filtered.length} / payload {items.length}
              </div>
            </div>
            <div className="logs-list">
              {filtered.map((d) => (
                <button
                  key={d.document_id}
                  type="button"
                  className={`logs-item ${selectedId === d.document_id ? "logs-item--selected" : ""}`}
                  onClick={() => setSelectedId(d.document_id)}
                >
                  <div className="logs-item__row">
                    <span className="mini-badge mini-badge--docs">{d.extension || "—"}</span>
                    <StatusBadge status={d.status || "—"} />
                  </div>
                  <div className="logs-item__preview mono break-all">{d.filename || "—"}</div>
                  <div className="logs-item__row logs-item__meta muted">
                    <span>chunks {d.chunk_count ?? 0}</span>
                    <span>v{d.active_version ?? "—"}</span>
                    <span>{fmtTime(d.last_indexed_at)}</span>
                  </div>
                </button>
              ))}
            </div>
            {canLoadMore ? (
              <div className="logs-loadmore-wrap">
                <button
                  type="button"
                  className="admin-shell__refresh"
                  onClick={() => setLimit((v) => v + LIMIT_STEP)}
                >
                  Загрузить ещё (+{LIMIT_STEP})
                </button>
              </div>
            ) : null}
          </section>

          <section className="logs-right card">
            {!selected ? (
              <EmptyState message="Выберите document to inspect metadata and indexing history." />
            ) : (
              <div className="logs-detail">
                <div className="logs-detail__head">
                  <h2 className="card__title">Document summary</h2>
                  <StatusBadge status={selected.status || "—"} />
                </div>
                <dl className="kv">
                  <dt>filename</dt>
                  <dd className="mono break-all">{selected.filename || "—"}</dd>
                  <dt>path/category</dt>
                  <dd className="mono">{selected.path_category ?? "—"}</dd>
                  <dt>size</dt>
                  <dd>{selected.size_bytes != null ? `${selected.size_bytes} B` : "—"}</dd>
                  <dt>modified_at</dt>
                  <dd className="mono">{fmtTime(selected.modified_at)}</dd>
                  <dt>indexed status</dt>
                  <dd>
                    <StatusBadge status={selected.status_raw || selected.status || "—"} />
                  </dd>
                </dl>

                <div className="logs-detail-grid page__mt">
                  <div className="logs-detail-block">
                    <h3 className="card__title">Indexing metadata</h3>
                    <dl className="kv">
                      <dt>active version</dt>
                      <dd>{selected.active_version ?? "—"}</dd>
                      <dt>versions count</dt>
                      <dd>{selected.versions_count ?? 0}</dd>
                      <dt>chunk count</dt>
                      <dd>{selected.chunk_count ?? 0}</dd>
                      <dt>last indexed</dt>
                      <dd className="mono">{fmtTime(selected.last_indexed_at)}</dd>
                      <dt>collection info</dt>
                      <dd className="mono">—</dd>
                      <dt>provider/model</dt>
                      <dd className="mono">—</dd>
                    </dl>
                  </div>
                  <div className="logs-detail-block">
                    <h3 className="card__title">Last indexing activity</h3>
                    <dl className="kv">
                      <dt>last event stage</dt>
                      <dd className="mono">
                        {String(selected.last_indexing_event?.stage || "—")}
                      </dd>
                      <dt>last event time</dt>
                      <dd className="mono">
                        {fmtTime(selected.last_indexing_event?.created_at || null)}
                      </dd>
                      <dt>event status</dt>
                      <dd>
                        <StatusBadge
                          status={String(selected.last_indexing_event?.status || "—")}
                        />
                      </dd>
                      <dt>duration</dt>
                      <dd>—</dd>
                    </dl>
                  </div>
                </div>

                <h3 className="card__title page__mt">Related logs/events</h3>
                <div className="logs-timeline">
                  {(observability.timeline_events ?? [])
                    .filter((ev) => matchesDocEvent(ev, selected))
                    .slice(0, 30)
                    .map((ev, i) => (
                      <div key={`${ev.stage ?? "event"}-${i}`} className="logs-stage">
                        <div className="logs-stage__top">
                          <span className="mono">{fmtTime(ev.created_at)}</span>
                          <span className="mini-badge">{ev.stage ?? "—"}</span>
                          <StatusBadge status={ev.status ?? "—"} />
                        </div>
                        <details>
                          <summary className="log-details__summary mono">
                            {previewСводка(ev.details)}
                          </summary>
                          <pre className="log-details__json mono">
                            {formatJson(ev.details)}
                          </pre>
                        </details>
                      </div>
                    ))}
                </div>

                <h3 className="card__title page__mt">Reindex observability</h3>
                <div className="logs-detail-block">
                  <dl className="kv">
                    <dt>reindex capability</dt>
                    <dd>
                      {observability.reindex_available ? (
                        <StatusBadge status="available" />
                      ) : (
                        <StatusBadge status="unavailable" />
                      )}
                    </dd>
                    <dt>last reindex stage</dt>
                    <dd className="mono">
                      {String(observability.last_reindex_event?.stage || "—")}
                    </dd>
                    <dt>last reindex at</dt>
                    <dd className="mono">
                      {fmtTime(observability.last_reindex_event?.created_at || null)}
                    </dd>
                  </dl>
                </div>

                <details className="page__mt">
                  <summary className="log-details__summary mono">
                    raw metadata/details
                  </summary>
                  <pre className="log-details__json mono">
                    {JSON.stringify(
                      {
                        selected,
                        observability: {
                          last_reindex_event: observability.last_reindex_event,
                          admin_operations: (observability.admin_operations ?? []).slice(0, 20),
                        },
                      },
                      null,
                      2
                    )}
                  </pre>
                </details>
              </div>
            )}
          </section>
        </div>
      )}
    </div>
  );
}

function matchesDocEvent(ev: LogItem, doc: DocumentItem): boolean {
  const details =
    ev.details && typeof ev.details === "object" && !Array.isArray(ev.details)
      ? (ev.details as Record<string, unknown>)
      : {};
  const filename = String(details.filename || "").toLowerCase();
  return filename === String(doc.filename || "").toLowerCase();
}

function fmtTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return String(iso);
  return d.toISOString().replace("T", " ").slice(0, 19) + "Z";
}

function previewСводка(value: unknown): string {
  if (value == null) return "∅ empty";
  if (typeof value === "string") return value.length > 88 ? `${value.slice(0, 88)}…` : value;
  try {
    const raw = JSON.stringify(value);
    return raw.length > 88 ? `${raw.slice(0, 88)}…` : raw;
  } catch {
    return "?";
  }
}

function formatJson(value: unknown): string {
  if (value == null) return "null";
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

