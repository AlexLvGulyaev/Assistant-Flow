import { useEffect, useMemo, useState } from "react";
import {
  fetchRecentLogs,
  getAssetPreviewUrl,
  type LogItem,
} from "../api/client";
import { EmptyState } from "../components/EmptyState";
import { LoadingState } from "../components/LoadingState";
import { StatusBadge } from "../components/StatusBadge";

const INITIAL_LIMIT = 140;
const LIMIT_STEP = 80;

interface АудиоSession {
  executionId: string;
  rows: LogItem[];
  startedAt: number;
  lastAt: number;
  status: string;
  route: "audio" | "voice";
  providerModel: string | null;
  latencyMs: number | null;
  stageCount: number;
  transcript: string | null;
  responseТекст: string | null;
  inputАудиоRef: string | null;
  outputАудиоRef: string | null;
  inputMeta: Record<string, string | null>;
  outputMeta: Record<string, string | null>;
  preview: string;
}

export function AudioPage() {
  const [limit, setLimit] = useState(INITIAL_LIMIT);
  const [items, setItems] = useState<LogItem[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState("all");
  const [providerFilter, setProviderFilter] = useState("all");
  const [quickFilter, setQuickFilter] = useState<"all" | "audio" | "stt" | "tts">(
    "all"
  );
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [inАудиоFailed, setInАудиоFailed] = useState(false);
  const [outАудиоFailed, setOutАудиоFailed] = useState(false);

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
          setError(e instanceof Error ? e.message : "Не удалось загрузить логи аудио");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [limit]);

  const sessions = useMemo(() => buildАудиоSessions(items), [items]);
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
        if (quickFilter !== "all" && !matchesQuickFilter(s.rows, quickFilter)) {
          return false;
        }
        const q = search.trim().toLowerCase();
        if (!q) return true;
        return (
          s.executionId.toLowerCase().includes(q) ||
          (s.transcript || "").toLowerCase().includes(q) ||
          (s.responseТекст || "").toLowerCase().includes(q) ||
          (s.providerModel || "").toLowerCase().includes(q) ||
          s.rows.some((r) =>
            `${r.stage ?? ""} ${previewСводка(r.details)}`.toLowerCase().includes(q)
          )
        );
      }),
    [providerFilter, quickFilter, search, sessions, statusFilter]
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

  const inputАудиоUrl =
    selected?.inputАудиоRef ? getAssetPreviewUrl(selected.inputАудиоRef) : null;
  const outputАудиоUrl =
    selected?.outputАудиоRef ? getAssetPreviewUrl(selected.outputАудиоRef) : null;

  useEffect(() => {
    setInАудиоFailed(false);
    setOutАудиоFailed(false);
  }, [selectedId, inputАудиоUrl, outputАудиоUrl]);

  return (
    <div className="page logs-page">
      <h1 className="page__title">Аудио</h1>
      <p className="page__lead muted">
        Voice/STT/TTS operational sessions · <code>/api/logs/recent</code>
      </p>
      {loading ? (
        <LoadingState label="Загрузка аудио-sessions…" />
      ) : error ? (
        <div className="panel panel--error page__mt" role="alert">
          {error}
        </div>
      ) : sessions.length === 0 ? (
        <section className="card">
          <EmptyState message="Нет audio sessions in recent logs." />
        </section>
      ) : (
        <div className="logs-console audio-console">
          <section className="logs-left card">
            <div className="logs-filters">
              <div className="logs-filter-row audio-filter-row">
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
                  value={providerFilter}
                  onChange={(e) => setProviderFilter(e.target.value)}
                >
                  <option value="all">провайдер: все</option>
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
                  сброс
                </button>
              </div>
              <input
                className="logs-search"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="поиск transcript / response / execution"
              />
              <div className="logs-quick-row">
                {(["audio", "stt", "tts"] as const).map((k) => (
                  <button
                    key={k}
                    type="button"
                    className={`logs-chip ${quickFilter === k ? "logs-chip--active" : ""}`}
                    onClick={() => setQuickFilter((cur) => (cur === k ? "all" : k))}
                  >
                    {k}
                  </button>
                ))}
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
                    <span className="mini-badge mini-badge--audio">{s.route}</span>
                    <StatusBadge status={s.status} />
                  </div>
                  <div className="logs-item__preview">{s.preview}</div>
                  <div className="logs-item__row logs-item__meta muted">
                    <span className="mono">{shortId(s.executionId)}</span>
                    <span>stages {s.stageCount}</span>
                    <span>{s.latencyMs != null ? `${s.latencyMs} ms` : "— ms"}</span>
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
                  Загрузить ещё (+{LIMIT_STEP})
                </button>
              </div>
            ) : null}
          </section>

          <section className="logs-right card">
            {!selected ? (
              <EmptyState message="Выберите audio session to inspect details." />
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
                    <span className="mini-badge mini-badge--audio">{selected.route}</span>
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
                    <h3 className="card__title">Original audio metadata</h3>
                    <dl className="kv">
                      <dt>filename</dt>
                      <dd className="mono break-all">
                        {selected.inputMeta.filename ?? "—"}
                      </dd>
                      <dt>mime_type</dt>
                      <dd className="mono">{selected.inputMeta.mimeType ?? "—"}</dd>
                      <dt>size</dt>
                      <dd className="mono">{selected.inputMeta.size ?? "—"}</dd>
                      <dt>duration</dt>
                      <dd className="mono">{selected.inputMeta.duration ?? "—"}</dd>
                      <dt>asset_ref</dt>
                      <dd className="mono break-all">
                        {selected.inputАудиоRef ?? "—"}
                      </dd>
                    </dl>
                  </div>
                  <div className="logs-detail-block">
                    <h3 className="card__title">TTS/output audio metadata</h3>
                    <dl className="kv">
                      <dt>filename</dt>
                      <dd className="mono break-all">
                        {selected.outputMeta.filename ?? "—"}
                      </dd>
                      <dt>mime_type</dt>
                      <dd className="mono">{selected.outputMeta.mimeType ?? "—"}</dd>
                      <dt>size</dt>
                      <dd className="mono">{selected.outputMeta.size ?? "—"}</dd>
                      <dt>duration</dt>
                      <dd className="mono">{selected.outputMeta.duration ?? "—"}</dd>
                      <dt>asset_ref</dt>
                      <dd className="mono break-all">
                        {selected.outputАудиоRef ?? "—"}
                      </dd>
                    </dl>
                  </div>
                </div>

                <div className="logs-detail-grid page__mt">
                  <div className="logs-detail-block">
                    <h3 className="card__title">STT transcript</h3>
                    <pre className="logs-pre mono">
                      {clip(selected.transcript, 420) ?? "—"}
                    </pre>
                    <details className="page__mt-sm">
                      <summary className="log-details__summary mono">
                        full transcript
                      </summary>
                      <pre className="log-details__json mono">
                        {selected.transcript ?? "—"}
                      </pre>
                    </details>
                  </div>
                  <div className="logs-detail-block">
                    <h3 className="card__title">Assistant response</h3>
                    <pre className="logs-pre mono">
                      {clip(selected.responseТекст, 420) ?? "—"}
                    </pre>
                    <details className="page__mt-sm">
                      <summary className="log-details__summary mono">
                        full response text
                      </summary>
                      <pre className="log-details__json mono">
                        {selected.responseТекст ?? "—"}
                      </pre>
                    </details>
                  </div>
                </div>

                <div className="logs-detail-grid page__mt">
                  <div className="logs-detail-block">
                    <h3 className="card__title">Input audio preview</h3>
                    {!inputАудиоUrl ? (
                      <div className="panel panel--muted">Нет input audio asset.</div>
                    ) : inАудиоFailed ? (
                      <div className="panel panel--muted">
                        Input audio is unavailable or unreadable.
                      </div>
                    ) : (
                      <audio
                        controls
                        preload="none"
                        className="audio-player"
                        onError={() => setInАудиоFailed(true)}
                      >
                        <source src={inputАудиоUrl} />
                      </audio>
                    )}
                  </div>
                  <div className="logs-detail-block">
                    <h3 className="card__title">TTS/output audio preview</h3>
                    {!outputАудиоUrl ? (
                      <div className="panel panel--muted">Нет output audio asset.</div>
                    ) : outАудиоFailed ? (
                      <div className="panel panel--muted">
                        Output audio is unavailable or unreadable.
                      </div>
                    ) : (
                      <audio
                        controls
                        preload="none"
                        className="audio-player"
                        onError={() => setOutАудиоFailed(true)}
                      >
                        <source src={outputАудиоUrl} />
                      </audio>
                    )}
                  </div>
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
                            {formatDetailsJson(row.details)}
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

function buildАудиоSessions(rows: LogItem[]): АудиоSession[] {
  const grouped = new Map<string, LogItem[]>();
  for (const row of rows) {
    if (!isАудиоEvent(row)) continue;
    const id = String(row.execution_id || "").trim();
    if (!id) continue;
    const bucket = grouped.get(id) ?? [];
    bucket.push(row);
    grouped.set(id, bucket);
  }
  const out: АудиоSession[] = [];
  for (const [executionId, chunk] of grouped) {
    const ordered = [...chunk].sort((a, b) => (toTs(a.created_at) ?? 0) - (toTs(b.created_at) ?? 0));
    const detailsPool = ordered
      .map((r) => asRecord(r.details))
      .filter((d): d is Record<string, unknown> => d !== null);
    const latest = ordered[ordered.length - 1];
    const first = ordered[0];
    const inputАудиоRef = pickТекст(detailsPool, [
      "input_audio_asset_ref",
      "audio_asset_ref",
      "input_asset_ref",
      "source_audio_asset_ref",
      "asset_ref",
    ]);
    const outputАудиоRef = pickТекст(detailsPool, [
      "output_audio_asset_ref",
      "tts_asset_ref",
      "generated_audio_asset_ref",
      "audio_output_asset_ref",
    ]);
    const transcript = pickТекст(detailsPool, [
      "transcript",
      "transcript_text",
      "stt_text",
      "transcript_preview",
    ]);
    const responseТекст = pickТекст(detailsPool, [
      "assistant_response",
      "response_text",
      "answer",
      "answer_preview",
      "output_text",
    ]);
    out.push({
      executionId,
      rows: ordered,
      startedAt: toTs(first.created_at) ?? 0,
      lastAt: toTs(latest.created_at) ?? 0,
      status: String(latest.status || "—"),
      route: pickАудиоRoute(ordered),
      providerModel: pickProviderModel(detailsPool),
      latencyMs: pickLatency(detailsPool),
      stageCount: ordered.length,
      transcript,
      responseТекст,
      inputАудиоRef,
      outputАудиоRef,
      inputMeta: pickInputАудиоMeta(detailsPool),
      outputMeta: pickOutputАудиоMeta(detailsPool),
      preview: clip(transcript || responseТекст || previewСводка(latest.details), 120) || "—",
    });
  }
  return out.sort((a, b) => b.lastAt - a.lastAt);
}

function isАудиоEvent(row: LogItem): boolean {
  const route = String(row.route || "").trim().toLowerCase();
  const mode = String(row.mode || "").trim().toLowerCase();
  const stage = String(row.stage || "").trim().toLowerCase();
  const d = asRecord(row.details);
  const dRoute = String(d?.route || "").trim().toLowerCase();
  const dMode = String(d?.mode || "").trim().toLowerCase();
  if (route === "audio" || route === "voice" || mode === "audio" || mode === "voice") {
    return true;
  }
  if (dRoute === "audio" || dRoute === "voice" || dMode === "audio" || dMode === "voice") {
    return true;
  }
  return [
    "stt_started",
    "stt_completed",
    "tts_started",
    "tts_completed",
    "tts_skipped",
    "tts_error",
    "voice_processing_done",
    "voice_processing_error",
    "audio_generation_done",
  ].includes(stage);
}

function pickАудиоRoute(rows: LogItem[]): "audio" | "voice" {
  for (let i = rows.length - 1; i >= 0; i--) {
    const route = String(rows[i].route || rows[i].mode || "").toLowerCase();
    if (route.includes("audio")) return "audio";
    if (route.includes("voice")) return "voice";
  }
  return "audio";
}

function normalizeStatus(status: string): "success" | "error" | "other" {
  const n = status.trim().toLowerCase();
  if (n === "success") return "success";
  if (n === "error") return "error";
  return "other";
}

function matchesQuickFilter(rows: LogItem[], quick: "audio" | "stt" | "tts"): boolean {
  const stages = rows.map((r) => String(r.stage || "").toLowerCase());
  if (quick === "audio") return true;
  if (quick === "stt") return stages.some((s) => s.startsWith("stt_"));
  return stages.some((s) => s.startsWith("tts_"));
}

function pickProviderModel(detailsPool: Record<string, unknown>[]): string | null {
  for (let i = detailsPool.length - 1; i >= 0; i--) {
    const d = detailsPool[i];
    const p = pickТекст([d], ["provider", "stt_provider", "tts_provider", "llm_provider"]);
    const m = pickТекст([d], ["model", "stt_model", "tts_model", "llm_model"]);
    if (p || m) return `${p || "—"} / ${m || "—"}`;
  }
  return null;
}

function pickInputАудиоMeta(detailsPool: Record<string, unknown>[]): Record<string, string | null> {
  return {
    filename: pickТекст(detailsPool, ["filename", "input_filename", "audio_filename"]),
    mimeType: pickТекст(detailsPool, ["mime_type", "audio_mime_type", "content_type"]),
    size: pickТекст(detailsPool, ["size_bytes", "audio_size_bytes", "size"]),
    duration: pickТекст(detailsPool, ["duration_ms", "audio_duration_ms", "duration_sec"]),
  };
}

function pickOutputАудиоMeta(
  detailsPool: Record<string, unknown>[]
): Record<string, string | null> {
  return {
    filename: pickТекст(detailsPool, [
      "output_filename",
      "tts_filename",
      "generated_audio_filename",
    ]),
    mimeType: pickТекст(detailsPool, [
      "output_mime_type",
      "tts_mime_type",
      "generated_audio_mime_type",
      "content_type",
    ]),
    size: pickТекст(detailsPool, [
      "output_size_bytes",
      "tts_size_bytes",
      "generated_audio_size_bytes",
      "size_bytes",
    ]),
    duration: pickТекст(detailsPool, [
      "output_duration_ms",
      "tts_duration_ms",
      "generated_audio_duration_ms",
    ]),
  };
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

function pickТекст(detailsPool: Record<string, unknown>[], keys: string[]): string | null {
  for (let i = detailsPool.length - 1; i >= 0; i--) {
    const d = detailsPool[i];
    for (const key of keys) {
      const v = d[key];
      if (typeof v === "string" && v.trim()) return v.trim();
      if (typeof v === "number" && Number.isFinite(v)) return String(v);
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

function previewСводка(d: LogItem["details"]): string {
  if (d == null) return "∅ empty";
  if (typeof d === "string") return clip(d, 88) ?? "?";
  try {
    const s = JSON.stringify(d);
    return clip(s, 88) ?? "{}";
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

