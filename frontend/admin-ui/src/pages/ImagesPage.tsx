import { useEffect, useMemo, useState } from "react";
import {
  fetchRecentLogs,
  getAssetPreviewUrl,
  type LogItem,
} from "../api/client";
import { EmptyState } from "../components/EmptyState";
import { LoadingState } from "../components/LoadingState";
import { StatusBadge } from "../components/StatusBadge";

const INITIAL_LIMIT = 120;
const LIMIT_STEP = 80;

interface ImageSession {
  executionId: string;
  rows: LogItem[];
  startedAt: number;
  lastAt: number;
  status: string;
  prompt: string | null;
  enhancedPrompt: string | null;
  providerModel: string | null;
  latencyMs: number | null;
  assetRef: string | null;
  assetCount: number;
  preview: string;
}

export function ImagesPage() {
  const [limit, setLimit] = useState(INITIAL_LIMIT);
  const [items, setItems] = useState<LogItem[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState("all");
  const [providerFilter, setProviderFilter] = useState("all");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [imgFailed, setImgFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const res = await fetchRecentLogs(limit);
        if (!cancelled) setItems(res.items ?? []);
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : "Failed to load image logs");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [limit]);

  const sessions = useMemo(() => buildImageSessions(items), [items]);
  const providers = useMemo(
    () =>
      Array.from(
        new Set(
          sessions
            .map((s) => s.providerModel?.split(" / ")[0] ?? "")
            .filter(Boolean)
        )
      ).sort(),
    [sessions]
  );
  const filtered = useMemo(
    () =>
      sessions.filter((s) => {
        if (statusFilter !== "all" && normalizeStatus(s.status) !== statusFilter) {
          return false;
        }
        if (providerFilter !== "all") {
          const prov = (s.providerModel?.split(" / ")[0] || "—").toLowerCase();
          if (prov !== providerFilter) return false;
        }
        const q = search.trim().toLowerCase();
        if (!q) return true;
        return (
          s.executionId.toLowerCase().includes(q) ||
          (s.prompt || "").toLowerCase().includes(q) ||
          (s.enhancedPrompt || "").toLowerCase().includes(q) ||
          (s.providerModel || "").toLowerCase().includes(q) ||
          s.rows.some((r) =>
            `${r.stage ?? ""} ${previewSummary(r.details)}`.toLowerCase().includes(q)
          )
        );
      }),
    [providerFilter, search, sessions, statusFilter]
  );

  useEffect(() => {
    if (!filtered.length) {
      setSelectedId(null);
      return;
    }
    if (!selectedId || !filtered.some((s) => s.executionId === selectedId)) {
      setSelectedId(filtered[0].executionId);
    }
  }, [filtered, selectedId]);

  const selected =
    filtered.find((s) => s.executionId === selectedId) ??
    sessions.find((s) => s.executionId === selectedId) ??
    null;
  const canLoadMore = items.length >= limit;
  const previewUrl = selected?.assetRef ? getAssetPreviewUrl(selected.assetRef) : null;

  useEffect(() => {
    setImgFailed(false);
  }, [selectedId, previewUrl]);

  return (
    <div className="page logs-page">
      <h1 className="page__title">Images</h1>
      <p className="page__lead muted">
        Image generation sessions · <code>/api/logs/recent</code>
      </p>
      {loading ? (
        <LoadingState label="Loading image sessions…" />
      ) : error ? (
        <div className="panel panel--error page__mt" role="alert">
          {error}
        </div>
      ) : sessions.length === 0 ? (
        <section className="card">
          <EmptyState message="No image generation sessions in recent logs." />
        </section>
      ) : (
        <div className="logs-console images-console">
          <section className="logs-left card">
            <div className="logs-filters">
              <div className="logs-filter-row">
                <select
                  className="logs-select"
                  value={statusFilter}
                  onChange={(e) => setStatusFilter(e.target.value)}
                >
                  <option value="all">status: all</option>
                  <option value="success">success</option>
                  <option value="error">error</option>
                  <option value="other">other</option>
                </select>
                <select
                  className="logs-select"
                  value={providerFilter}
                  onChange={(e) => setProviderFilter(e.target.value)}
                >
                  <option value="all">provider: all</option>
                  {providers.map((p) => (
                    <option key={p} value={p.toLowerCase()}>
                      {p}
                    </option>
                  ))}
                </select>
                <button
                  type="button"
                  className="admin-shell__refresh"
                  onClick={() => setLimit(INITIAL_LIMIT)}
                >
                  reset
                </button>
              </div>
              <input
                className="logs-search"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="search prompt / execution / stage"
              />
              <div className="logs-filter-meta muted">
                sessions {filtered.length} / source rows {items.length}
              </div>
            </div>
            <div className="logs-list">
              {filtered.map((s) => (
                <button
                  key={s.executionId}
                  type="button"
                  className={`logs-item ${selectedId === s.executionId ? "logs-item--selected" : ""}`}
                  onClick={() => setSelectedId(s.executionId)}
                >
                  <div className="logs-item__row">
                    <span className="mono">{fmtTs(s.lastAt)}</span>
                    <span className="mini-badge">image</span>
                    <StatusBadge status={s.status} />
                  </div>
                  <div className="logs-item__preview">{s.preview}</div>
                  <div className="logs-item__row logs-item__meta muted">
                    <span className="mono">{shortId(s.executionId)}</span>
                    <span>{s.latencyMs != null ? `${s.latencyMs} ms` : "— ms"}</span>
                    <span>assets {s.assetCount}</span>
                    <span className="mono truncate">{s.providerModel ?? "—/—"}</span>
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
                  Load more (+{LIMIT_STEP})
                </button>
              </div>
            ) : null}
          </section>

          <section className="logs-right card">
            {!selected ? (
              <EmptyState message="Select generation session to inspect details." />
            ) : (
              <div className="logs-detail">
                <div className="logs-detail__head">
                  <h2 className="card__title">Session summary</h2>
                  <StatusBadge status={selected.status} />
                </div>
                <dl className="kv">
                  <dt>execution_id</dt>
                  <dd className="mono break-all">{selected.executionId}</dd>
                  <dt>started_at</dt>
                  <dd className="mono">{fmtTs(selected.startedAt)}</dd>
                  <dt>last_event_at</dt>
                  <dd className="mono">{fmtTs(selected.lastAt)}</dd>
                  <dt>provider/model</dt>
                  <dd className="mono">{selected.providerModel ?? "—"}</dd>
                  <dt>latency</dt>
                  <dd>{selected.latencyMs != null ? `${selected.latencyMs} ms` : "—"}</dd>
                  <dt>asset count</dt>
                  <dd>{selected.assetCount}</dd>
                </dl>

                <div className="logs-detail-grid page__mt">
                  <div className="logs-detail-block">
                    <h3 className="card__title">Original prompt</h3>
                    <pre className="logs-pre mono">{selected.prompt ?? "—"}</pre>
                  </div>
                  <div className="logs-detail-block">
                    <h3 className="card__title">Enhanced/provider prompt</h3>
                    <pre className="logs-pre mono">{selected.enhancedPrompt ?? "—"}</pre>
                  </div>
                </div>

                <div className="logs-detail-block page__mt">
                  <h3 className="card__title">Generated asset preview</h3>
                  {!previewUrl ? (
                    <div className="panel panel--muted">
                      No image asset reference found in this session.
                    </div>
                  ) : imgFailed ? (
                    <div className="panel panel--muted">
                      Image file is unavailable or not readable.
                    </div>
                  ) : (
                    <div className="image-preview-wrap">
                      <img
                        src={previewUrl}
                        alt="Generated result preview"
                        className="image-preview"
                        onError={() => setImgFailed(true)}
                      />
                    </div>
                  )}
                  {selected.assetRef ? (
                    <p className="muted mono page__mt-sm">asset_ref: {selected.assetRef}</p>
                  ) : null}
                </div>

                <h3 className="card__title page__mt">Timeline/events</h3>
                <div className="logs-timeline">
                  {selected.rows.map((row, i) => {
                    const prev = i > 0 ? toTs(selected.rows[i - 1].created_at) : null;
                    const cur = toTs(row.created_at);
                    const delta =
                      prev != null && cur != null ? Math.max(0, cur - prev) : null;
                    return (
                      <div key={`${row.stage ?? "unknown"}-${i}`} className="logs-stage">
                        <div className="logs-stage__top">
                          <span className="mono">{fmtTime(row.created_at)}</span>
                          <span className="mini-badge">{row.stage ?? "—"}</span>
                          <StatusBadge status={row.status ?? "—"} />
                          {delta != null ? (
                            <span className="muted mono">+{delta} ms</span>
                          ) : null}
                        </div>
                        <details>
                          <summary className="log-details__summary mono">
                            {previewSummary(row.details)}
                          </summary>
                          <pre className="log-details__json mono">
                            {formatDetailsJson(row.details)}
                          </pre>
                        </details>
                      </div>
                    );
                  })}
                </div>

                <details className="page__mt">
                  <summary className="log-details__summary mono">
                    raw session JSON ({selected.rows.length} rows)
                  </summary>
                  <pre className="log-details__json mono">
                    {JSON.stringify(selected.rows, null, 2)}
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

function buildImageSessions(rows: LogItem[]): ImageSession[] {
  const grouped = new Map<string, LogItem[]>();
  for (const row of rows) {
    const id = String(row.execution_id || "").trim();
    if (!id) continue;
    if (!isImageEvent(row)) continue;
    const bucket = grouped.get(id) ?? [];
    bucket.push(row);
    grouped.set(id, bucket);
  }
  const out: ImageSession[] = [];
  for (const [executionId, items] of grouped) {
    const ordered = [...items].sort((a, b) => (toTs(a.created_at) ?? 0) - (toTs(b.created_at) ?? 0));
    const detailsPool = ordered
      .map((r) => asRecord(r.details))
      .filter((d): d is Record<string, unknown> => d !== null);
    const latest = ordered[ordered.length - 1];
    const first = ordered[0];
    const assets = detailsPool
      .map((d) => strField(d, ["asset_ref", "image_asset_ref", "generated_asset_ref"]))
      .filter((x): x is string => Boolean(x));
    const prompt = pickText(detailsPool, [
      "prompt",
      "user_input",
      "query",
      "text",
      "input_text",
    ]);
    const enhancedPrompt = pickText(detailsPool, [
      "enhanced_prompt",
      "generated_prompt",
      "provider_prompt",
      "image_prompt",
      "prompt_enriched",
    ]);
    out.push({
      executionId,
      rows: ordered,
      startedAt: toTs(first.created_at) ?? 0,
      lastAt: toTs(latest.created_at) ?? 0,
      status: String(latest.status || "—"),
      prompt,
      enhancedPrompt,
      providerModel: pickProviderModel(detailsPool),
      latencyMs: pickLatency(detailsPool),
      assetRef: assets[assets.length - 1] ?? null,
      assetCount: assets.length,
      preview: (prompt || enhancedPrompt || previewSummary(latest.details)).slice(0, 160),
    });
  }
  return out.sort((a, b) => b.lastAt - a.lastAt);
}

function isImageEvent(row: LogItem): boolean {
  const route = String(row.route || "").trim().toLowerCase();
  const mode = String(row.mode || "").trim().toLowerCase();
  const stage = String(row.stage || "").trim().toLowerCase();
  const d = asRecord(row.details);
  const dRoute = String(d?.route || "").trim().toLowerCase();
  const dMode = String(d?.mode || "").trim().toLowerCase();
  if (stage === "audio_generation_done") return false;
  if (route === "image_generation" || route === "image") return true;
  if (dRoute === "image_generation" || dRoute === "image") return true;
  if (mode === "image" || dMode === "image") return true;
  return (
    stage === "image_generation_started" ||
    stage === "image_generation_done" ||
    stage === "image_generation_error" ||
    stage === "image_prompt_enhanced"
  );
}

function normalizeStatus(status: string): "success" | "error" | "other" {
  const n = status.trim().toLowerCase();
  if (n === "success") return "success";
  if (n === "error") return "error";
  return "other";
}

function pickProviderModel(detailsPool: Record<string, unknown>[]): string | null {
  for (let i = detailsPool.length - 1; i >= 0; i--) {
    const d = detailsPool[i];
    const p = strField(d, ["provider", "image_provider", "llm_provider"]);
    const m = strField(d, ["model", "image_model", "llm_model"]);
    if (p || m) return `${p || "—"} / ${m || "—"}`;
  }
  return null;
}

function pickLatency(detailsPool: Record<string, unknown>[]): number | null {
  for (let i = detailsPool.length - 1; i >= 0; i--) {
    const d = detailsPool[i];
    for (const key of ["latency_ms", "duration_ms", "elapsed_ms"]) {
      const v = Number(d[key]);
      if (Number.isFinite(v)) return Math.round(v);
    }
  }
  return null;
}

function pickText(detailsPool: Record<string, unknown>[], keys: string[]): string | null {
  for (let i = detailsPool.length - 1; i >= 0; i--) {
    const d = detailsPool[i];
    const val = strField(d, keys);
    if (val) return val.slice(0, 1600);
  }
  return null;
}

function strField(obj: Record<string, unknown>, keys: string[]): string | null {
  for (const key of keys) {
    const v = obj[key];
    if (typeof v === "string" && v.trim()) return v.trim();
  }
  return null;
}

function asRecord(v: unknown): Record<string, unknown> | null {
  if (v !== null && typeof v === "object" && !Array.isArray(v)) {
    return v as Record<string, unknown>;
  }
  return null;
}

function toTs(iso: string | null | undefined): number | null {
  if (!iso) return null;
  const n = new Date(iso).getTime();
  return Number.isFinite(n) ? n : null;
}

function fmtTs(ts: number): string {
  if (!Number.isFinite(ts) || ts <= 0) return "—";
  return new Date(ts).toISOString().replace("T", " ").slice(0, 19) + "Z";
}

function fmtTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    return d.toISOString().replace("T", " ").slice(0, 19) + "Z";
  } catch {
    return iso.slice(0, 19);
  }
}

function shortId(id: string | null | undefined): string {
  if (!id) return "—";
  return id.length > 12 ? `${id.slice(0, 8)}…` : id;
}

function previewSummary(d: LogItem["details"]): string {
  if (d == null) return "∅ empty";
  if (typeof d === "string") return d.length > 88 ? `${d.slice(0, 88)}…` : d;
  try {
    const s = JSON.stringify(d);
    return s.length > 88 ? `${s.slice(0, 88)}…` : s || "{}";
  } catch {
    return "?";
  }
}

function formatDetailsJson(d: LogItem["details"]): string {
  if (d == null) return "null";
  if (typeof d === "string") return d;
  try {
    return JSON.stringify(d, null, 2);
  } catch {
    return String(d);
  }
}

