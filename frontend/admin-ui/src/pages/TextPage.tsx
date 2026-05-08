import { useEffect, useMemo, useState } from "react";
import { fetchRecentLogs, type LogItem } from "../api/client";
import { EmptyState } from "../components/EmptyState";
import { LoadingState } from "../components/LoadingState";
import { StatusBadge } from "../components/StatusBadge";

const INITIAL_LIMIT = 140;
const LIMIT_STEP = 80;

interface TextSession {
  executionId: string;
  rows: LogItem[];
  startedAt: number;
  lastAt: number;
  status: string;
  providerModel: string | null;
  latencyMs: number | null;
  userInput: string | null;
  assistantOutput: string | null;
}

export function TextPage() {
  const [limit, setLimit] = useState(INITIAL_LIMIT);
  const [items, setItems] = useState<LogItem[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState("all");
  const [providerFilter, setProviderFilter] = useState("all");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

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
          setError(e instanceof Error ? e.message : "Failed to load text logs");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [limit]);

  const sessions = useMemo(() => buildTextSessions(items), [items]);
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
          const p = (s.providerModel?.split(" / ")[0] || "").toLowerCase();
          if (p !== providerFilter) return false;
        }
        const q = search.trim().toLowerCase();
        if (!q) return true;
        return (
          s.executionId.toLowerCase().includes(q) ||
          (s.userInput || "").toLowerCase().includes(q) ||
          (s.assistantOutput || "").toLowerCase().includes(q) ||
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

  const selected = filtered.find((s) => s.executionId === selectedId) ?? null;
  const canLoadMore = items.length >= limit;

  return (
    <div className="page logs-page">
      <h1 className="page__title">Text</h1>
      <p className="page__lead muted">
        Text interactions operational view · <code>/api/logs/recent</code>
      </p>
      {loading ? (
        <LoadingState label="Loading text sessions…" />
      ) : error ? (
        <div className="panel panel--error page__mt" role="alert">
          {error}
        </div>
      ) : sessions.length === 0 ? (
        <section className="card">
          <EmptyState message="No text sessions found in recent logs." />
        </section>
      ) : (
        <div className="logs-console text-console">
          <section className="logs-left card">
            <div className="logs-filters">
              <div className="logs-filter-row text-filter-row">
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
                placeholder="search input / response / execution"
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
                    <span className="mini-badge">text</span>
                    <StatusBadge status={s.status} />
                  </div>
                  <div className="logs-item__preview">
                    {clip(s.userInput, 110) || clip(s.assistantOutput, 110) || "—"}
                  </div>
                  <div className="logs-item__row logs-item__meta muted">
                    <span className="mono">{shortId(s.executionId)}</span>
                    <span>{s.latencyMs != null ? `${s.latencyMs} ms` : "— ms"}</span>
                    <span>stages {s.rows.length}</span>
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
              <EmptyState message="Select text session to inspect details." />
            ) : (
              <div className="logs-detail">
                <div className="logs-detail__head">
                  <h2 className="card__title">Session summary</h2>
                  <StatusBadge status={selected.status} />
                </div>
                <dl className="kv">
                  <dt>execution_id</dt>
                  <dd className="mono break-all">{selected.executionId}</dd>
                  <dt>route</dt>
                  <dd>
                    <span className="mini-badge">text</span>
                  </dd>
                  <dt>provider/model</dt>
                  <dd className="mono">{selected.providerModel ?? "—"}</dd>
                  <dt>started_at</dt>
                  <dd className="mono">{fmtTs(selected.startedAt)}</dd>
                  <dt>latency</dt>
                  <dd>{selected.latencyMs != null ? `${selected.latencyMs} ms` : "—"}</dd>
                </dl>

                <div className="logs-detail-grid page__mt">
                  <div className="logs-detail-block">
                    <h3 className="card__title">User input</h3>
                    <pre className="logs-pre mono">{selected.userInput ?? "—"}</pre>
                  </div>
                  <div className="logs-detail-block">
                    <h3 className="card__title">Assistant response</h3>
                    <pre className="logs-pre mono">{selected.assistantOutput ?? "—"}</pre>
                  </div>
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
                            {formatJson(row.details)}
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

function buildTextSessions(rows: LogItem[]): TextSession[] {
  const grouped = new Map<string, LogItem[]>();
  for (const row of rows) {
    if (!isTextEvent(row)) continue;
    const id = String(row.execution_id || "").trim();
    if (!id) continue;
    const bucket = grouped.get(id) ?? [];
    bucket.push(row);
    grouped.set(id, bucket);
  }
  const out: TextSession[] = [];
  for (const [executionId, chunk] of grouped) {
    const ordered = [...chunk].sort((a, b) => (toTs(a.created_at) ?? 0) - (toTs(b.created_at) ?? 0));
    const detailsPool = ordered
      .map((r) => asRecord(r.details))
      .filter((d): d is Record<string, unknown> => d !== null);
    const latest = ordered[ordered.length - 1];
    const first = ordered[0];
    out.push({
      executionId,
      rows: ordered,
      startedAt: toTs(first.created_at) ?? 0,
      lastAt: toTs(latest.created_at) ?? 0,
      status: String(latest.status || "—"),
      providerModel: pickProviderModel(detailsPool),
      latencyMs: pickLatency(detailsPool),
      userInput: pickText(detailsPool, ["user_input", "query", "prompt", "input_text", "text"]),
      assistantOutput: pickText(detailsPool, [
        "assistant_response",
        "response_text",
        "answer",
        "answer_preview",
        "output_text",
      ]),
    });
  }
  return out.sort((a, b) => b.lastAt - a.lastAt);
}

function isTextEvent(row: LogItem): boolean {
  const route = String(row.route || "").trim().toLowerCase();
  const mode = String(row.mode || "").trim().toLowerCase();
  const stage = String(row.stage || "").trim().toLowerCase();
  const d = asRecord(row.details);
  const dRoute = String(d?.route || "").trim().toLowerCase();
  const dMode = String(d?.mode || "").trim().toLowerCase();
  const markers = [route, mode, dRoute, dMode, stage];
  if (
    markers.some(
      (v) =>
        v.includes("rag") ||
        v.includes("image") ||
        v.includes("audio") ||
        v.includes("voice")
    )
  ) {
    return false;
  }
  if (
    stage.startsWith("stt_") ||
    stage.startsWith("tts_") ||
    stage.startsWith("voice_processing_") ||
    stage.startsWith("image_generation_") ||
    stage.startsWith("rag_")
  ) {
    return false;
  }
  return (
    route === "text" ||
    mode === "text" ||
    dRoute === "text" ||
    dMode === "text" ||
    stage === "text_answer_done" ||
    stage === "route_selected" ||
    stage === "processing_done"
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
    const p = pickText([d], ["provider", "llm_provider"]);
    const m = pickText([d], ["model", "llm_model"]);
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
    for (const key of keys) {
      const v = d[key];
      if (typeof v === "string" && v.trim()) return v.trim();
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

function clip(value: string | null | undefined, max: number): string | null {
  if (!value) return null;
  return value.length > max ? `${value.slice(0, max)}…` : value;
}

function previewSummary(value: unknown): string {
  if (value == null) return "∅ empty";
  if (typeof value === "string") return clip(value, 88) ?? "?";
  try {
    const raw = JSON.stringify(value);
    return clip(raw, 88) ?? "{}";
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

