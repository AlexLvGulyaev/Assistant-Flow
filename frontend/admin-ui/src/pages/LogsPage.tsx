import { useEffect, useMemo, useState } from "react";
import { fetchRecentLogs, type LogItem } from "../api/client";
import { EmptyState } from "../components/EmptyState";
import { LoadingState } from "../components/LoadingState";
import { StatusBadge } from "../components/StatusBadge";

const INITIAL_LIMIT = 120;
const LIMIT_STEP = 120;
const WINDOW_OPTIONS: Array<{ label: string; ms: number }> = [
  { label: "24h", ms: 24 * 60 * 60 * 1000 },
  { label: "48h", ms: 48 * 60 * 60 * 1000 },
  { label: "7d", ms: 7 * 24 * 60 * 60 * 1000 },
];

type RouteFilter = "all" | "text" | "rag" | "image" | "audio" | "other";
type StatusFilter = "all" | "success" | "error" | "other";

interface SessionView {
  id: string;
  rows: LogItem[];
  startedAt: number;
  lastAt: number;
  route: RouteFilter;
  status: string;
  preview: string;
  providerModel: string | null;
  latencyMs: number | null;
  stageCount: number;
  userInput: string | null;
  transcript: string | null;
  assistantOutput: string | null;
  generatedPrompt: string | null;
}

export function LogsPage() {
  const [limit, setLimit] = useState(INITIAL_LIMIT);
  const [items, setItems] = useState<LogItem[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [routeFilter, setRouteFilter] = useState<RouteFilter>("all");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [windowLabel, setWindowLabel] = useState("24h");
  const [search, setSearch] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const res = await fetchRecentLogs(limit);
        if (!cancelled) setItems(res.items ?? []);
      } catch (e) {
        if (!cancelled)
          setError(e instanceof Error ? e.message : "Failed to load logs");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [limit]);

  const sessions = useMemo(() => buildSessions(items), [items]);
  const filtered = useMemo(
    () =>
      filterSessions(
        sessions,
        routeFilter,
        statusFilter,
        search,
        windowLabelToMs(windowLabel)
      ),
    [routeFilter, search, sessions, statusFilter, windowLabel]
  );

  useEffect(() => {
    if (!filtered.length) {
      setSelectedId(null);
      return;
    }
    if (!selectedId || !filtered.some((s) => s.id === selectedId)) {
      setSelectedId(filtered[0].id);
    }
  }, [filtered, selectedId]);

  const selected = filtered.find((s) => s.id === selectedId) ?? null;
  const canLoadMore = items.length >= limit;

  return (
    <div className="page logs-page">
      <h1 className="page__title">Logs</h1>
      <p className="page__lead muted">
        Operational trace console · <code>/api/logs/recent</code>
      </p>

      {loading ? (
        <LoadingState label="Loading log entries…" />
      ) : error ? (
        <div className="panel panel--error page__mt" role="alert">
          {error}
        </div>
      ) : items.length === 0 ? (
        <section className="card">
          <EmptyState message="No log entries returned for this request." />
        </section>
      ) : (
        <div className="logs-console">
          <section className="logs-left card">
            <div className="logs-filters">
              <div className="logs-filter-row">
                <select
                  className="logs-select"
                  value={windowLabel}
                  onChange={(e) => setWindowLabel(e.target.value)}
                >
                  {WINDOW_OPTIONS.map((w) => (
                    <option key={w.label} value={w.label}>
                      {w.label}
                    </option>
                  ))}
                </select>
                <select
                  className="logs-select"
                  value={routeFilter}
                  onChange={(e) => setRouteFilter(e.target.value as RouteFilter)}
                >
                  <option value="all">route: all</option>
                  <option value="text">text</option>
                  <option value="rag">rag</option>
                  <option value="image">image</option>
                  <option value="audio">audio</option>
                  <option value="other">other</option>
                </select>
                <select
                  className="logs-select"
                  value={statusFilter}
                  onChange={(e) => setStatusFilter(e.target.value as StatusFilter)}
                >
                  <option value="all">status: all</option>
                  <option value="success">success</option>
                  <option value="error">error</option>
                  <option value="other">other</option>
                </select>
              </div>
              <input
                className="logs-search"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="search execution_id / stage / text"
              />
              <div className="logs-quick-row">
                {(["audio", "image", "rag"] as const).map((r) => (
                  <button
                    key={r}
                    type="button"
                    className={`logs-chip ${routeFilter === r ? "logs-chip--active" : ""}`}
                    onClick={() =>
                      setRouteFilter((cur) => (cur === r ? "all" : r))
                    }
                  >
                    {r}
                  </button>
                ))}
              </div>
              <div className="logs-filter-meta muted">
                sessions {filtered.length} / source rows {items.length}
              </div>
            </div>

            <div className="logs-list">
              {filtered.length === 0 ? (
                <div className="panel panel--muted">No sessions match filters.</div>
              ) : (
                filtered.map((s) => (
                  <button
                    key={s.id}
                    type="button"
                    className={`logs-item ${selectedId === s.id ? "logs-item--selected" : ""}`}
                    onClick={() => setSelectedId(s.id)}
                  >
                    <div className="logs-item__row">
                      <span className="mono">{fmtTs(s.lastAt)}</span>
                      <span className="mini-badge">{s.route}</span>
                      <StatusBadge status={s.status} />
                    </div>
                    <div className="logs-item__preview">{s.preview || "—"}</div>
                    <div className="logs-item__row logs-item__meta muted">
                      <span className="mono">{shortId(s.id)}</span>
                      <span>stages {s.stageCount}</span>
                      <span>{s.latencyMs != null ? `${s.latencyMs} ms` : "— ms"}</span>
                      <span className="mono truncate">{s.providerModel ?? "—/—"}</span>
                    </div>
                  </button>
                ))
              )}
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
              <EmptyState message="Select a session to inspect execution trace." />
            ) : (
              <div className="logs-detail">
                <div className="logs-detail__head">
                  <h2 className="card__title">Session summary</h2>
                  <StatusBadge status={selected.status} />
                </div>
                <dl className="kv">
                  <dt>execution_id</dt>
                  <dd className="mono break-all">{selected.id}</dd>
                  <dt>route</dt>
                  <dd>
                    <span className="mini-badge">{selected.route}</span>
                  </dd>
                  <dt>started_at</dt>
                  <dd className="mono">{fmtTs(selected.startedAt)}</dd>
                  <dt>latency</dt>
                  <dd>{selected.latencyMs != null ? `${selected.latencyMs} ms` : "—"}</dd>
                  <dt>provider/model</dt>
                  <dd className="mono">{selected.providerModel ?? "—"}</dd>
                </dl>

                <div className="logs-detail-grid page__mt">
                  <div className="logs-detail-block">
                    <h3 className="card__title">User input</h3>
                    <pre className="logs-pre mono">{selected.userInput ?? "—"}</pre>
                    <details className="page__mt-sm">
                      <summary className="log-details__summary mono">
                        transcript preview
                      </summary>
                      <pre className="log-details__json mono">
                        {selected.transcript ?? "—"}
                      </pre>
                    </details>
                  </div>
                  <div className="logs-detail-block">
                    <h3 className="card__title">Assistant output</h3>
                    <pre className="logs-pre mono">
                      {selected.assistantOutput ?? "—"}
                    </pre>
                    <details className="page__mt-sm">
                      <summary className="log-details__summary mono">
                        generated image prompt
                      </summary>
                      <pre className="log-details__json mono">
                        {selected.generatedPrompt ?? "—"}
                      </pre>
                    </details>
                  </div>
                </div>

                <h3 className="card__title page__mt">Timeline</h3>
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
  return id.length > 12 ? id.slice(0, 8) + "…" : id;
}

function buildSessions(rows: LogItem[]): SessionView[] {
  const grouped = new Map<string, LogItem[]>();
  for (const row of rows) {
    const id = (row.execution_id || "").trim();
    if (!id) continue;
    const bucket = grouped.get(id) ?? [];
    bucket.push(row);
    grouped.set(id, bucket);
  }
  const out: SessionView[] = [];
  for (const [id, chunk] of grouped) {
    const ordered = [...chunk].sort((a, b) => (toTs(a.created_at) ?? 0) - (toTs(b.created_at) ?? 0));
    const latest = ordered[ordered.length - 1];
    const first = ordered[0];
    const detailsPool = ordered
      .map((r) => asRecord(r.details))
      .filter((d): d is Record<string, unknown> => d !== null);
    const route = pickRoute(ordered);
    const status = String(latest.status || "—");
    const providerModel = pickProviderModel(detailsPool);
    const userInput = pickText(detailsPool, [
      "user_input",
      "query_preview",
      "query",
      "prompt",
      "input_text",
      "text",
    ]);
    const transcript = pickText(detailsPool, ["transcript_preview", "transcript"]);
    const assistantOutput = pickText(detailsPool, [
      "assistant_response",
      "response_text",
      "answer_preview",
      "answer",
      "output_text",
    ]);
    const generatedPrompt = pickText(detailsPool, [
      "generated_prompt",
      "image_prompt",
      "prompt_enriched",
    ]);
    out.push({
      id,
      rows: ordered,
      startedAt: toTs(first.created_at) ?? 0,
      lastAt: toTs(latest.created_at) ?? 0,
      route,
      status,
      preview: userInput || assistantOutput || previewSummary(latest.details),
      providerModel,
      latencyMs: pickLatency(detailsPool),
      stageCount: ordered.length,
      userInput,
      transcript,
      assistantOutput,
      generatedPrompt,
    });
  }
  return out.sort((a, b) => b.lastAt - a.lastAt);
}

function filterSessions(
  sessions: SessionView[],
  routeFilter: RouteFilter,
  statusFilter: StatusFilter,
  search: string,
  windowMs: number
): SessionView[] {
  const now = Date.now();
  const q = search.trim().toLowerCase();
  return sessions.filter((s) => {
    if (windowMs > 0 && now - s.lastAt > windowMs) return false;
    if (routeFilter !== "all" && s.route !== routeFilter) return false;
    if (statusFilter !== "all") {
      const st = normalizeStatus(s.status);
      if (statusFilter === "success" && st !== "success") return false;
      if (statusFilter === "error" && st !== "error") return false;
      if (statusFilter === "other" && (st === "success" || st === "error")) return false;
    }
    if (!q) return true;
    const searchHay = [
      s.id,
      s.route,
      s.status,
      s.preview,
      s.providerModel,
      s.userInput,
      s.assistantOutput,
      ...s.rows.map((r) => `${r.stage ?? ""} ${previewSummary(r.details)}`),
    ]
      .join(" ")
      .toLowerCase();
    return searchHay.includes(q);
  });
}

function normalizeStatus(s: string): string {
  return s.trim().toLowerCase();
}

function pickRoute(rows: LogItem[]): RouteFilter {
  const vals = rows
    .flatMap((r) => {
      const d = asRecord(r.details);
      return [
        String(r.route || ""),
        String(r.mode || ""),
        String(d?.route || ""),
        String(d?.mode || ""),
      ];
    })
    .map((v) => v.trim().toLowerCase())
    .filter(Boolean);
  for (const v of vals.reverse()) {
    if (v.includes("rag")) return "rag";
    if (v.includes("audio") || v.includes("voice")) return "audio";
    if (v.includes("image")) return "image";
    if (v.includes("text")) return "text";
  }
  return "other";
}

function pickProviderModel(detailsPool: Record<string, unknown>[]): string | null {
  for (let i = detailsPool.length - 1; i >= 0; i--) {
    const d = detailsPool[i];
    const p = String(d.provider || d.llm_provider || "").trim();
    const m = String(d.model || d.llm_model || "").trim();
    if (p || m) return `${p || "—"} / ${m || "—"}`;
  }
  return null;
}

function pickLatency(detailsPool: Record<string, unknown>[]): number | null {
  for (let i = detailsPool.length - 1; i >= 0; i--) {
    const d = detailsPool[i];
    for (const k of ["latency_ms", "duration_ms", "elapsed_ms"]) {
      const v = Number(d[k]);
      if (Number.isFinite(v)) return Math.round(v);
    }
  }
  return null;
}

function pickText(detailsPool: Record<string, unknown>[], keys: string[]): string | null {
  for (let i = detailsPool.length - 1; i >= 0; i--) {
    const d = detailsPool[i];
    for (const k of keys) {
      const v = d[k];
      if (typeof v === "string" && v.trim()) {
        return v.trim().slice(0, 1200);
      }
    }
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

function windowLabelToMs(label: string): number {
  return WINDOW_OPTIONS.find((x) => x.label === label)?.ms ?? WINDOW_OPTIONS[0].ms;
}

function previewSummary(d: LogItem["details"]): string {
  if (d == null) return "∅ empty";
  if (typeof d === "string") return d.length > 56 ? d.slice(0, 56) + "…" : d;
  try {
    const s = JSON.stringify(d);
    return s.length > 56 ? s.slice(0, 56) + "…" : s || "{}";
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
