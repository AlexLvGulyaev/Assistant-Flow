import { useEffect, useMemo, useState } from "react";
import { fetchRecentLogs, type LogItem } from "../api/client";
import { EmptyState } from "../components/EmptyState";
import { LoadingState } from "../components/LoadingState";
import { StatusBadge } from "../components/StatusBadge";

const INITIAL_LIMIT = 180;
const LIMIT_STEP = 100;

interface RagChunk {
  source: string;
  score: number | null;
  preview: string;
  fullText: string;
}

interface RagSession {
  executionId: string;
  rows: LogItem[];
  startedAt: number;
  lastAt: number;
  status: string;
  query: string | null;
  answer: string | null;
  retrievedCount: number | null;
  filteredCount: number | null;
  contextChars: number | null;
  topK: number | null;
  uniqueSourcesCount: number | null;
  fallbackReason: string | null;
  scores: number[];
  chunks: RagChunk[];
}

export function RagPage() {
  const [limit, setLimit] = useState(INITIAL_LIMIT);
  const [items, setItems] = useState<LogItem[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState("all");
  const [fallbackFilter, setFallbackFilter] = useState("all");
  const [hasResultsOnly, setHasResultsOnly] = useState(false);
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
          setError(e instanceof Error ? e.message : "Не удалось загрузить RAG-логи");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [limit]);

  const sessions = useMemo(() => buildRagSessions(items), [items]);
  const fallbackOptions = useMemo(
    () =>
      Array.from(new Set(sessions.map((s) => s.fallbackReason || "").filter(Boolean))).sort(),
    [sessions]
  );
  const filtered = useMemo(
    () =>
      sessions.filter((s) => {
        if (statusFilter !== "all" && normalizeStatus(s.status) !== statusFilter) {
          return false;
        }
        if (fallbackFilter !== "all" && (s.fallbackReason || "none") !== fallbackFilter) {
          return false;
        }
        if (hasResultsOnly && !((s.retrievedCount ?? 0) > 0)) return false;
        const q = search.trim().toLowerCase();
        if (!q) return true;
        return (
          s.executionId.toLowerCase().includes(q) ||
          (s.query || "").toLowerCase().includes(q) ||
          (s.answer || "").toLowerCase().includes(q) ||
          (s.fallbackReason || "").toLowerCase().includes(q) ||
          s.chunks.some((c) => `${c.source} ${c.preview}`.toLowerCase().includes(q))
        );
      }),
    [fallbackFilter, hasResultsOnly, search, sessions, statusFilter]
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
      <h1 className="page__title">RAG</h1>
      <p className="page__lead muted">
        Retrieval diagnostics view · <code>/api/logs/recent</code>
      </p>
      {loading ? (
        <LoadingState label="Загрузка RAG-sessions…" />
      ) : error ? (
        <div className="panel panel--error page__mt" role="alert">
          {error}
        </div>
      ) : sessions.length === 0 ? (
        <section className="card">
          <EmptyState message="Нет RAG sessions in recent logs." />
        </section>
      ) : (
        <div className="logs-console rag-console">
          <section className="logs-left card">
            <div className="logs-filters">
              <div className="logs-filter-row rag-filter-row">
                <select
                  className="logs-select"
                  value={statusFilter}
                  onChange={(e) => setStatusFilter(e.target.value)}
                >
                  <option value="all">статус: все</option>
                  <option value="success">success</option>
                  <option value="error">error</option>
                  <option value="other">other</option>
                </select>
                <select
                  className="logs-select"
                  value={fallbackFilter}
                  onChange={(e) => setFallbackFilter(e.target.value)}
                >
                  <option value="all">fallback: all</option>
                  <option value="none">none</option>
                  {fallbackOptions.map((f) => (
                    <option key={f} value={f}>
                      {f}
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
                placeholder="поиск query / answer / source / fallback"
              />
              <div className="logs-quick-row">
                <button
                  type="button"
                  className={`logs-chip ${hasResultsOnly ? "logs-chip--active" : ""}`}
                  onClick={() => setHasResultsOnly((v) => !v)}
                >
                  has results
                </button>
              </div>
              <div className="logs-filter-meta muted">
                sessions {filtered.length} / исходных строк {items.length}
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
                    <span className="mini-badge mini-badge--rag">rag</span>
                    <StatusBadge status={s.status} />
                  </div>
                  <div className="logs-item__preview">{clip(s.query, 96) || "—"}</div>
                  <div className="logs-item__row logs-item__meta muted">
                    <span className="mono">{shortId(s.executionId)}</span>
                    <span>retr {s.retrievedCount ?? 0}</span>
                    <span>ctx {s.contextChars ?? 0}</span>
                    <span className="truncate">{s.fallbackReason ?? "none"}</span>
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
              <EmptyState message="Выберите RAG session to inspect diagnostics." />
            ) : (
              <div className="logs-detail">
                <div className="logs-detail__head">
                  <h2 className="card__title">Сводка сессии</h2>
                  <StatusBadge status={selected.status} />
                </div>
                <dl className="kv">
                  <dt>execution_id</dt>
                  <dd className="mono break-all">{selected.executionId}</dd>
                  <dt>route</dt>
                  <dd>
                    <span className="mini-badge mini-badge--rag">rag</span>
                  </dd>
                  <dt>started_at</dt>
                  <dd className="mono">{fmtTs(selected.startedAt)}</dd>
                  <dt>fallback_reason</dt>
                  <dd>{selected.fallbackReason ?? "none"}</dd>
                </dl>

                <div className="logs-detail-grid page__mt">
                  <div className="logs-detail-block">
                    <h3 className="card__title">User query</h3>
                    <pre className="logs-pre mono">{selected.query ?? "—"}</pre>
                  </div>
                  <div className="logs-detail-block">
                    <h3 className="card__title">Assistant answer</h3>
                    <pre className="logs-pre mono">{selected.answer ?? "—"}</pre>
                  </div>
                </div>

                <div className="logs-detail-block page__mt">
                  <h3 className="card__title">Retrieval diagnostics</h3>
                  <dl className="kv">
                    <dt>top_k</dt>
                    <dd>{selected.topK ?? "—"}</dd>
                    <dt>retrieved_count</dt>
                    <dd>{selected.retrievedCount ?? "—"}</dd>
                    <dt>filtered_count</dt>
                    <dd>{selected.filteredCount ?? "—"}</dd>
                    <dt>scores</dt>
                    <dd className="mono">
                      {selected.scores.length ? selected.scores.join(", ") : "—"}
                    </dd>
                    <dt>unique_sources_count</dt>
                    <dd>{selected.uniqueSourcesCount ?? "—"}</dd>
                    <dt>context_chars</dt>
                    <dd>{selected.contextChars ?? "—"}</dd>
                    <dt>fallback_reason</dt>
                    <dd>{selected.fallbackReason ?? "none"}</dd>
                  </dl>
                </div>

                <h3 className="card__title page__mt">Retrieved chunks</h3>
                <div className="logs-timeline">
                  {selected.chunks.length === 0 ? (
                    <div className="panel panel--muted">Нет chunk diagnostics in logs.</div>
                  ) : (
                    selected.chunks.map((chunk, i) => (
                      <div key={`${chunk.source}-${i}`} className="logs-stage">
                        <div className="logs-stage__top">
                          <span className="mini-badge mini-badge--rag">chunk</span>
                          <span className="mono truncate" title={chunk.source}>
                            {chunk.source || "unknown"}
                          </span>
                          <span className="muted mono">
                            {chunk.score != null ? `score ${chunk.score}` : "score —"}
                          </span>
                        </div>
                        <pre className="logs-pre mono page__mt-sm">{chunk.preview}</pre>
                        <details className="page__mt-sm">
                          <summary className="log-details__summary mono">full text</summary>
                          <pre className="log-details__json mono">{chunk.fullText}</pre>
                        </details>
                      </div>
                    ))
                  )}
                </div>

                <h3 className="card__title page__mt">Таймлайн / события</h3>
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
                            {previewСводка(row.details)}
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
                    raw JSON сессии ({selected.rows.length} rows)
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

function buildRagSessions(rows: LogItem[]): RagSession[] {
  const grouped = new Map<string, LogItem[]>();
  for (const row of rows) {
    if (!isRagEvent(row)) continue;
    const id = String(row.execution_id || "").trim();
    if (!id) continue;
    const bucket = grouped.get(id) ?? [];
    bucket.push(row);
    grouped.set(id, bucket);
  }
  const out: RagSession[] = [];
  for (const [executionId, chunk] of grouped) {
    const ordered = [...chunk].sort((a, b) => (toTs(a.created_at) ?? 0) - (toTs(b.created_at) ?? 0));
    const detailsPool = ordered
      .map((r) => asRecord(r.details))
      .filter((d): d is Record<string, unknown> => d !== null);
    const latest = ordered[ordered.length - 1];
    const first = ordered[0];
    const scores = collectScores(detailsPool);
    const chunks = extractChunks(detailsPool);
    out.push({
      executionId,
      rows: ordered,
      startedAt: toTs(first.created_at) ?? 0,
      lastAt: toTs(latest.created_at) ?? 0,
      status: String(latest.status || "—"),
      query: pickТекст(detailsPool, ["user_input", "query_preview", "query", "prompt"]),
      answer: pickТекст(detailsPool, [
        "assistant_response",
        "response_text",
        "answer_preview",
        "answer",
      ]),
      retrievedCount: pickNumber(detailsPool, ["retrieved_count"]),
      filteredCount: pickNumber(detailsPool, ["filtered_count"]),
      contextChars: pickNumber(detailsPool, ["context_chars"]),
      topK: pickNumber(detailsPool, ["top_k"]),
      uniqueSourcesCount: pickNumber(detailsPool, ["unique_sources_count"]),
      fallbackReason: pickТекст(detailsPool, ["fallback_reason"]),
      scores,
      chunks,
    });
  }
  return out.sort((a, b) => b.lastAt - a.lastAt);
}

function isRagEvent(row: LogItem): boolean {
  const route = String(row.route || "").trim().toLowerCase();
  const mode = String(row.mode || "").trim().toLowerCase();
  const stage = String(row.stage || "").trim().toLowerCase();
  const d = asRecord(row.details);
  const dRoute = String(d?.route || "").trim().toLowerCase();
  const dMode = String(d?.mode || "").trim().toLowerCase();
  return (
    route === "rag" ||
    mode === "rag" ||
    dRoute === "rag" ||
    dMode === "rag" ||
    stage.startsWith("rag_")
  );
}

function normalizeStatus(status: string): "success" | "error" | "other" {
  const n = status.trim().toLowerCase();
  if (n === "success") return "success";
  if (n === "error") return "error";
  return "other";
}

function pickТекст(detailsPool: Record<string, unknown>[], keys: string[]): string | null {
  for (let i = detailsPool.length - 1; i >= 0; i--) {
    const d = detailsPool[i];
    for (const key of keys) {
      const v = d[key];
      if (typeof v === "string" && v.trim()) return v.trim();
    }
  }
  return null;
}

function pickNumber(detailsPool: Record<string, unknown>[], keys: string[]): number | null {
  for (let i = detailsPool.length - 1; i >= 0; i--) {
    const d = detailsPool[i];
    for (const key of keys) {
      const n = Number(d[key]);
      if (Number.isFinite(n)) return n;
    }
  }
  return null;
}

function collectScores(detailsPool: Record<string, unknown>[]): number[] {
  for (let i = detailsPool.length - 1; i >= 0; i--) {
    const d = detailsPool[i];
    const sc = d.scores;
    if (Array.isArray(sc)) {
      const vals = sc
        .map((x) => Number(x))
        .filter((n) => Number.isFinite(n))
        .slice(0, 8);
      if (vals.length) return vals;
    }
  }
  return [];
}

function extractChunks(detailsPool: Record<string, unknown>[]): RagChunk[] {
  for (let i = detailsPool.length - 1; i >= 0; i--) {
    const d = detailsPool[i];
    const raw = d.retrieved_chunks;
    if (!Array.isArray(raw)) continue;
    const out: RagChunk[] = [];
    for (const row of raw.slice(0, 10)) {
      if (!row || typeof row !== "object" || Array.isArray(row)) continue;
      const item = row as Record<string, unknown>;
      const source = String(item.source || item.filename || item.path || "unknown");
      const text = String(item.preview || item.text || item.content || "");
      const score = Number(item.score);
      out.push({
        source,
        score: Number.isFinite(score) ? score : null,
        preview: clip(text, 180) || "—",
        fullText: text || "—",
      });
    }
    if (out.length) return out;
  }
  return [];
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

function previewСводка(value: unknown): string {
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

