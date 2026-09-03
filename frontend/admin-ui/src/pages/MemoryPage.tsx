import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { OperationalModalityBadge } from "../components/OperationalModalityBadge";
import { OperationalPipelineStageIcon } from "../components/OperationalPipelineStageIcon";
import { formatTimestampMsk } from "../utils/operationalLabels";
import {
  detailsJsonPreview,
  memoryLifecycleStageLabel,
  pipelineStageVariant,
} from "../utils/operationalConsoleUi";
import {
  fetchMemorySessionDetail,
  fetchMemorySessionsList,
  type MemorySessionDetailResponse,
  type MemorySessionListItem,
  type MemorySessionsListResponse,
} from "../api/client";
import { EmptyState } from "../components/EmptyState";
import { LoadingState } from "../components/LoadingState";
import { OperationalRefreshButton } from "../components/OperationalRefreshButton";
import { StatusBadge } from "../components/StatusBadge";

const LIST_FETCH_LIMIT = 200;
const PAGE_SIZE = 10;

type MemoryWindowLabel = "24h" | "48h" | "7d";

const MEMORY_WINDOW_OPTIONS: Array<{ label: MemoryWindowLabel; ms: number }> = [
  { label: "24h", ms: 24 * 60 * 60 * 1000 },
  { label: "48h", ms: 48 * 60 * 60 * 1000 },
  { label: "7d", ms: 7 * 24 * 60 * 60 * 1000 },
];

function memoryListRowTimeMs(row: MemorySessionListItem): number | null {
  const raw = row.updated_at;
  if (raw == null || typeof raw !== "string") return null;
  const ms = new Date(raw).getTime();
  return Number.isFinite(ms) ? ms : null;
}

function shortId(id: string | undefined, n = 8): string {
  if (!id) return "—";
  return id.length <= n ? id : `${id.slice(0, n)}…`;
}

function parseNumericId(raw: string | undefined): bigint | null {
  const t = (raw ?? "").trim();
  if (!t || !/^-?\d+$/.test(t)) return null;
  try {
    return BigInt(t);
  } catch {
    return null;
  }
}

function isSyntheticTelegramUserId(raw: string | undefined): boolean {
  const n = parseNumericId(raw);
  if (n === null) return false;
  if (n < -900_000_000_000_000n) return true;
  if (n >= 9_000_000_000_000n && n <= 9_999_999_999_999n) return true;
  return false;
}

function isSyntheticSessionRow(row: MemorySessionListItem): boolean {
  if (isSyntheticTelegramUserId(row.telegram_user_id)) return true;
  const label = (row.user_label || "").toLowerCase();
  if (label.includes("hello smoke")) return true;
  return false;
}

function isSyntheticDetail(d: MemorySessionDetailResponse): boolean {
  if (isSyntheticTelegramUserId(d.telegram_user_id)) return true;
  for (const t of d.recent_turns ?? []) {
    const p = (t.preview || "").toLowerCase();
    if (
      p.includes("hello smoke") ||
      p.includes("world smoke") ||
      /lim-u\d/.test(p) ||
      /lim-a\d/.test(p) ||
      /ord-u\d/.test(p) ||
      /ord-a\d/.test(p)
    ) {
      return true;
    }
  }
  return false;
}

function asRecord(v: unknown): Record<string, unknown> | undefined {
  if (!v || typeof v !== "object" || Array.isArray(v)) return undefined;
  return v as Record<string, unknown>;
}

function parseDetailNum(d: Record<string, unknown> | undefined, key: string): number | null {
  if (!d) return null;
  const v = d[key];
  if (typeof v === "number" && Number.isFinite(v)) return v;
  if (typeof v === "string" && v.trim() !== "" && !Number.isNaN(Number(v))) return Number(v);
  return null;
}

type LifecycleRow = {
  stage?: string;
  created_at?: string;
  status?: string;
  details?: Record<string, unknown>;
};

function lifecycleTimelineMeta(events: LifecycleRow[]): { rag: boolean; meta: boolean } {
  let rag = false;
  let meta = false;
  for (const ev of events) {
    const r = String(asRecord(ev.details)?.route || "")
      .trim()
      .toLowerCase();
    if (r === "rag" || r === "rag_response") rag = true;
    if (r === "memory_meta") meta = true;
    const st = String(ev.stage || "").toLowerCase();
    if (st.startsWith("memory_meta")) meta = true;
  }
  return { rag, meta };
}

function formatMemoryDetailsJson(d: unknown): string {
  if (d == null) return "null";
  if (typeof d === "string") return d;
  try {
    return JSON.stringify(d, null, 2);
  } catch {
    return String(d);
  }
}

/** ISO или число из корня события / details (lifecycle payload). */
function lifecycleEventTimestamp(ev: LifecycleRow): string | undefined {
  const ca = ev.created_at;
  if (typeof ca === "string" && ca.trim()) return ca.trim();
  const d = asRecord(ev.details);
  if (!d) return undefined;
  for (const k of ["created_at", "timestamp", "ts", "time"]) {
    const v = d[k];
    if (typeof v === "string" && v.trim()) return v.trim();
    if (typeof v === "number" && Number.isFinite(v)) return new Date(v).toISOString();
  }
  return undefined;
}

function parseLifecycleLatencyMs(ev: LifecycleRow): number | null {
  return parseDetailNum(asRecord(ev.details), "latency_ms");
}

type ModeFilter = "all" | "rag" | "text" | "other";

function sessionModeBucket(mode: string | undefined): Exclude<ModeFilter, "all"> {
  const m = (mode || "").trim().toLowerCase();
  if (!m) return "other";
  if (m.includes("rag")) return "rag";
  if (m === "text" || m.includes("text")) return "text";
  return "other";
}

function OpsRow({ label, value }: { label: string; value: ReactNode }) {
  return (
    <>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </>
  );
}

/** Парные строки user/assistant по хронологии (диагностическая таблица). */
function pairDialogRows(
  turns: { role: string; preview: string }[]
): { user: string | null; assistant: string | null }[] {
  const rows: { user: string | null; assistant: string | null }[] = [];
  let pendingUser: string | null = null;
  for (const t of turns) {
    const r = (t.role || "").trim().toLowerCase();
    if (r === "user") {
      if (pendingUser != null) {
        rows.push({ user: pendingUser, assistant: null });
      }
      pendingUser = t.preview || "";
    } else if (r === "assistant") {
      rows.push({ user: pendingUser, assistant: t.preview || "" });
      pendingUser = null;
    }
  }
  if (pendingUser != null) rows.push({ user: pendingUser, assistant: null });
  return rows;
}

function sourceLabel(src: string | undefined): string {
  if (src === "pg") return "PostgreSQL";
  if (src === "fallback_in_memory") return "in-memory fallback";
  return src || "—";
}

function MemorySessionDetailPanel({
  detail,
  detailId,
  listRow,
}: {
  detail: MemorySessionDetailResponse;
  detailId: string;
  listRow: MemorySessionListItem | null;
}) {
  const budget = detail.budget;
  const dialogMsgs = budget?.dialog_messages_in_session ?? 0;
  const loaded = budget?.last_load_messages_loaded;
  const maxLlm = budget?.max_llm_messages ?? 0;
  const trimmed = Boolean(budget?.trimmed);
  const lifecycle = (detail.memory_lifecycle_recent ?? []) as LifecycleRow[];
  const chronological = useMemo(() => [...lifecycle].reverse(), [lifecycle]);
  const { rag, meta } = useMemo(() => lifecycleTimelineMeta(lifecycle), [lifecycle]);

  const sentToLlm =
    loaded != null
      ? loaded
      : maxLlm > 0
        ? Math.min(dialogMsgs, maxLlm)
        : dialogMsgs;

  const turnsApprox =
    dialogMsgs > 0 ? Math.round((dialogMsgs / 2) * 10) / 10 : 0;

  const dialogRows = useMemo(
    () => pairDialogRows(detail.recent_turns ?? []),
    [detail.recent_turns]
  );

  const trimLine =
    trimmed && dialogMsgs > 0 ? `${sentToLlm} / ${dialogMsgs}` : trimmed ? "да" : "нет";

  const rtLen = detail.recent_turns?.length ?? 0;
  const truncatedNote =
    dialogMsgs > rtLen
      ? `В выгрузке ${rtLen} диалоговых сообщений из ${dialogMsgs} в сессии (лимит выборки API).`
      : null;

  return (
    <div className="logs-detail rag-modality-detail memory-detail-panel">
        <div className="modality-card__head">
          <h2 className="modality-card__title">СВОДКА MEMORY-СЕССИИ</h2>
          {isSyntheticDetail(detail) ? (
            <OperationalModalityBadge modality="test" title="Synthetic (эвристика UI)" />
          ) : (
            <StatusBadge status={detail.is_active ? "yes" : "no"} />
          )}
        </div>

        <div className="modality-ops-panels memory-memory-top-panels memory-memory-top-panels--triple">
          <div className="modality-ops-panel">
            <div className="modality-ops-panel__name">Параметры сессии</div>
            <dl className="kv modality-ops-panel__kv">
              <OpsRow
                label="session_id"
                value={
                  detailId ? (
                    <span className="mono rag-ops-execution-id">{detailId}</span>
                  ) : (
                    "—"
                  )
                }
              />
              <OpsRow
                label="Пользователь"
                value={
                  listRow?.user_label ? (
                    <span title={listRow.user_label}>{listRow.user_label}</span>
                  ) : (
                    <span className="mono">{detail.telegram_user_id || "—"}</span>
                  )
                }
              />
              <OpsRow label="Режим" value={<span className="mono">{detail.mode || "—"}</span>} />
              <OpsRow
                label="Активна"
                value={<StatusBadge status={detail.is_active ? "yes" : "no"} />}
              />
              <OpsRow label="Сообщений" value={String(detail.messages_count ?? 0)} />
              <OpsRow label="Turns~" value={String(turnsApprox)} />
              <OpsRow
                label="Обновлена"
                value={
                  detail.updated_at ? (
                    <span className="mono">
                      {detail.updated_at.slice(0, 19).replace("T", " ")}
                    </span>
                  ) : (
                    "—"
                  )
                }
              />
            </dl>
          </div>
          <div className="modality-ops-panel">
            <div className="modality-ops-panel__name">Runtime memory context</div>
            <dl className="kv modality-ops-panel__kv">
              <OpsRow
                label="Загружено из PG"
                value={loaded != null ? String(loaded) : "—"}
              />
              <OpsRow label="После trim" value={trimLine} />
              <OpsRow label="В LLM" value={String(sentToLlm)} />
              <OpsRow
                label="budget"
                value={
                  <span className="mono">
                    {loaded ?? "—"} / {maxLlm || "—"}
                  </span>
                }
              />
              <OpsRow label="RAG" value={rag ? "да" : "нет"} />
              <OpsRow label="META" value={meta ? "да" : "нет"} />
            </dl>
          </div>
          <div className="modality-ops-panel">
            <div className="modality-ops-panel__name">Memory policy / limits</div>
            <dl className="kv modality-ops-panel__kv">
              <OpsRow
                label="limit pairs"
                value={
                  <span className="mono">
                    {String(budget?.last_load_limit_pairs ?? "—")} / {budget?.max_turn_pairs ?? "—"}
                  </span>
                }
              />
              <OpsRow label="cap messages" value={String(budget?.max_llm_messages ?? "—")} />
              <OpsRow
                label="trimmed"
                value={<StatusBadge status={trimmed ? "yes" : "no"} />}
              />
              <OpsRow
                label="source"
                value={<span className="mono">{sourceLabel(detail.memory_source)}</span>}
              />
            </dl>
          </div>
        </div>

        <div className="memory-dialog-panel page__mt-sm">
          <h3 className="logs-detail-block__title">Диалог сессии</h3>
          <p className="muted memory-dialog-panel__lead">
            Парные реплики по времени; при неполном turn пустая ячейка.
          </p>
          {truncatedNote ? <p className="muted memory-dialog-panel__note">{truncatedNote}</p> : null}
          <div className="memory-dialog-table-wrap">
            <table className="memory-dialog-table">
              <thead>
                <tr>
                  <th>Что спросил пользователь</th>
                  <th>Что ответила система</th>
                </tr>
              </thead>
              <tbody>
                {dialogRows.length ? (
                  dialogRows.map((row, i) => (
                    <tr key={i}>
                      <td className="memory-dialog-table__cell memory-dialog-table__cell--user">
                        {row.user ?? "—"}
                      </td>
                      <td className="memory-dialog-table__cell memory-dialog-table__cell--assistant">
                        {row.assistant ?? "—"}
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={2} className="muted memory-dialog-table__empty">
                      Нет user/assistant сообщений.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        <details className="rag-diagnostics-fold page__mt">
          <summary className="rag-diagnostics-fold__summary">
            Таймлайн memory pipeline ({chronological.length})
          </summary>
          <div className="logs-timeline memory-timeline--in-fold">
            {chronological.map((ev, i) => {
              const st = String(ev.stage || "");
              const title = memoryLifecycleStageLabel(st);
              const variant = pipelineStageVariant(st, ev.status);
              const tsRaw = lifecycleEventTimestamp(ev);
              const formattedTs = tsRaw ? formatTimestampMsk(tsRaw) : "—";
              const tsLabel = !tsRaw || formattedTs === "—" ? "timestamp: n/a" : formattedTs;
              const lat = parseLifecycleLatencyMs(ev);
              const statusRaw = String(ev.status ?? "").trim() || "—";
              const detailPayload = {
                stage: ev.stage,
                created_at: ev.created_at,
                status: ev.status,
                details: ev.details ?? null,
              };
              return (
                <div
                  key={`${st}-${i}-${tsRaw ?? "x"}`}
                  className="logs-stage logs-stage--compact memory-pipeline-stage"
                  title={st ? `stage: ${st}` : undefined}
                >
                  <div className="logs-stage__top">
                    <span className="mono logs-stage__time" title="timestamp (МСК или n/a)">
                      {tsLabel}
                    </span>
                    <span className="logs-stage__label af-logs-stage-label-with-icon">
                      <OperationalPipelineStageIcon variant={variant} />
                      <span>{title}</span>
                    </span>
                    <StatusBadge status={statusRaw} />
                    {lat != null ? (
                      <span className="muted mono logs-stage__delta">{lat} ms</span>
                    ) : null}
                  </div>
                  <details className="logs-stage__details">
                    <summary className="log-details__summary">
                      {detailsJsonPreview(ev.details ?? null)}
                    </summary>
                    <pre className="log-details__json mono">
                      {formatMemoryDetailsJson(detailPayload)}
                    </pre>
                  </details>
                </div>
              );
            })}
          </div>
        </details>

        <details className="rag-diagnostics-fold page__mt">
          <summary className="rag-diagnostics-fold__summary">
            Технический снимок memory session (JSON)
          </summary>
          <div className="memory-advanced__body memory-advanced__body--in-fold">
            <dl className="memory-advanced__dl">
              <dt>user_id</dt>
              <dd>
                <code>{detail.user_id}</code>
              </dd>
              <dt>telegram_user_id</dt>
              <dd>
                <code>{detail.telegram_user_id}</code>
              </dd>
            </dl>
            <p className="muted memory-advanced__label">last_memory_load</p>
            <pre className="memory-advanced__pre">
              {JSON.stringify(detail.last_memory_load ?? null, null, 2)}
            </pre>
            <p className="muted memory-advanced__label">last_memory_append</p>
            <pre className="memory-advanced__pre">
              {JSON.stringify(detail.last_memory_append ?? null, null, 2)}
            </pre>
            <p className="muted memory-advanced__label">last_clear_event</p>
            <pre className="memory-advanced__pre">
              {JSON.stringify(detail.last_clear_event ?? null, null, 2)}
            </pre>
            <p className="muted memory-advanced__label">budget</p>
            <pre className="memory-advanced__pre">
              {JSON.stringify(detail.budget ?? null, null, 2)}
            </pre>
            <p className="muted memory-advanced__label">memory_lifecycle_recent</p>
            <pre className="memory-advanced__pre">
              {JSON.stringify(detail.memory_lifecycle_recent ?? [], null, 2)}
            </pre>
          </div>
        </details>
    </div>
  );
}

export function MemoryPage() {
  const [list, setList] = useState<MemorySessionsListResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshNonce, setRefreshNonce] = useState(0);
  const [windowLabel, setWindowLabel] = useState<MemoryWindowLabel>("24h");
  const [activeFilter, setActiveFilter] = useState<"all" | "active" | "inactive">("all");
  const [modeFilter, setModeFilter] = useState<ModeFilter>("all");
  const [hideSynthetic, setHideSynthetic] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [pageIndex, setPageIndex] = useState(0);
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);
  const [detail, setDetail] = useState<MemorySessionDetailResponse | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  const listRef = useRef<HTMLDivElement | null>(null);
  const pendingListFocusRef = useRef(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const l = await fetchMemorySessionsList({
        activeOnly: activeFilter === "active",
        limit: LIST_FETCH_LIMIT,
        offset: 0,
      });
      setList(l);
    } catch (e) {
      setList(null);
      setError(e instanceof Error ? e.message : "Ошибка загрузки");
    } finally {
      setLoading(false);
    }
  }, [activeFilter, refreshNonce]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    setPageIndex(0);
  }, [searchQuery, hideSynthetic, activeFilter, modeFilter, windowLabel, refreshNonce]);

  useEffect(() => {
    if (!selectedSessionId) {
      setDetail(null);
      setDetailError(null);
      setDetailLoading(false);
      return;
    }
    let cancelled = false;
    setDetail(null);
    setDetailLoading(true);
    setDetailError(null);
    void fetchMemorySessionDetail(selectedSessionId)
      .then((d) => {
        if (!cancelled) setDetail(d);
      })
      .catch((e) => {
        if (!cancelled)
          setDetailError(e instanceof Error ? e.message : "detail error");
      })
      .finally(() => {
        if (!cancelled) setDetailLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedSessionId]);

  const filtered = useMemo(() => {
    const items = list?.items ?? [];
    const base = hideSynthetic ? items.filter((r) => !isSyntheticSessionRow(r)) : items;
    let rows =
      activeFilter === "inactive"
        ? base.filter((r) => r.is_active === false)
        : activeFilter === "active"
          ? base.filter((r) => r.is_active === true)
          : [...base];
    if (modeFilter !== "all") {
      rows = rows.filter((r) => sessionModeBucket(r.mode) === modeFilter);
    }
    const windowMs =
      MEMORY_WINDOW_OPTIONS.find((w) => w.label === windowLabel)?.ms ?? MEMORY_WINDOW_OPTIONS[0].ms;
    const cutoff = Date.now() - windowMs;
    rows = rows.filter((r) => {
      const t = memoryListRowTimeMs(r);
      if (t == null) return false;
      return t >= cutoff;
    });
    const q = searchQuery.trim().toLowerCase();
    if (!q) return rows;
    return rows.filter((r) => {
      const sid = (r.session_id || "").toLowerCase();
      const ul = (r.user_label || "").toLowerCase();
      const mode = (r.mode || "").toLowerCase();
      const tid = (r.telegram_user_id || "").toLowerCase();
      return sid.includes(q) || ul.includes(q) || mode.includes(q) || tid.includes(q);
    });
  }, [list, hideSynthetic, searchQuery, activeFilter, modeFilter, windowLabel]);

  const totalFiltered = filtered.length;
  const totalPages = Math.max(1, Math.ceil(totalFiltered / PAGE_SIZE));
  const safePageIdx = useMemo(
    () => Math.min(pageIndex, Math.max(0, totalPages - 1)),
    [pageIndex, totalPages]
  );

  useEffect(() => {
    if (pageIndex !== safePageIdx) setPageIndex(safePageIdx);
  }, [pageIndex, safePageIdx]);

  const pageSessions = useMemo(() => {
    const start = safePageIdx * PAGE_SIZE;
    return filtered.slice(start, start + PAGE_SIZE);
  }, [filtered, safePageIdx]);

  useEffect(() => {
    if (loading || error) return;
    if (totalFiltered === 0) {
      if (selectedSessionId) setSelectedSessionId(null);
      return;
    }
    const inFiltered = selectedSessionId
      ? filtered.some((r) => r.session_id === selectedSessionId)
      : false;
    const onCurrentPage = selectedSessionId
      ? pageSessions.some((r) => r.session_id === selectedSessionId)
      : false;

    if (!selectedSessionId || !inFiltered) {
      setSelectedSessionId(pageSessions[0]?.session_id ?? filtered[0]?.session_id ?? null);
      return;
    }
    if (!onCurrentPage) {
      setSelectedSessionId(pageSessions[0]?.session_id ?? null);
    }
  }, [
    loading,
    error,
    totalFiltered,
    filtered,
    pageSessions,
    selectedSessionId,
  ]);

  useEffect(() => {
    if (!selectedSessionId) return;
    const listEl = listRef.current;
    if (!listEl) return;
    const safeId =
      typeof CSS !== "undefined" && typeof CSS.escape === "function"
        ? CSS.escape(selectedSessionId)
        : selectedSessionId.replace(/"/g, '\\"');
    const row = listEl.querySelector<HTMLButtonElement>(`[data-memory-session-id="${safeId}"]`);
    if (!row) return;
    row.scrollIntoView({ block: "nearest" });
    const listHasFocus =
      document.activeElement instanceof Node && listEl.contains(document.activeElement);
    const shouldFocus = pendingListFocusRef.current || listHasFocus;
    pendingListFocusRef.current = false;
    if (!shouldFocus) return;
    const id = window.requestAnimationFrame(() => {
      row.focus({ preventScroll: true });
    });
    return () => window.cancelAnimationFrame(id);
  }, [selectedSessionId, safePageIdx]);

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
      const t = e.target as HTMLElement | null;
      if (
        t &&
        (t.closest("input") ||
          t.closest("textarea") ||
          t.closest("select") ||
          t.isContentEditable)
      ) {
        return;
      }
      if (!filtered.length) return;
      const curIdx = selectedSessionId
        ? filtered.findIndex((s) => s.session_id === selectedSessionId)
        : safePageIdx * PAGE_SIZE;
      if (curIdx < 0) return;
      const nextIdx =
        e.key === "ArrowDown"
          ? Math.min(filtered.length - 1, curIdx + 1)
          : Math.max(0, curIdx - 1);
      if (nextIdx === curIdx) return;
      e.preventDefault();
      const next = filtered[nextIdx];
      if (!next?.session_id) return;
      pendingListFocusRef.current = true;
      setPageIndex(Math.floor(nextIdx / PAGE_SIZE));
      setSelectedSessionId(next.session_id);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [filtered, selectedSessionId, safePageIdx]);

  const selectedListRow = useMemo(() => {
    if (!selectedSessionId) return null;
    return filtered.find((r) => r.session_id === selectedSessionId) ?? null;
  }, [filtered, selectedSessionId]);

  const goPrevPage = () => {
    pendingListFocusRef.current = true;
    const np = Math.max(0, safePageIdx - 1);
    setPageIndex(np);
    const pick = filtered[np * PAGE_SIZE]?.session_id ?? null;
    if (pick) setSelectedSessionId(pick);
  };

  const goNextPage = () => {
    pendingListFocusRef.current = true;
    const np = Math.min(totalPages - 1, safePageIdx + 1);
    setPageIndex(np);
    const pick = filtered[np * PAGE_SIZE]?.session_id ?? null;
    if (pick) setSelectedSessionId(pick);
  };

  const resetPagination = () => {
    setPageIndex(0);
    setSearchQuery("");
    setHideSynthetic(false);
    setActiveFilter("all");
    setModeFilter("all");
    setWindowLabel("24h");
  };

  const listMetaLine = useMemo(() => {
    const p = safePageIdx + 1;
    const shown = pageSessions.length;
    return `Страница ${p} из ${totalPages} · сессий: ${totalFiltered} · показано: ${shown}`;
  }, [safePageIdx, totalPages, totalFiltered, pageSessions.length]);

  if (loading && !list) {
    return (
      <div className="page logs-page memory-console-page">
        <h1 className="page__title">Memory</h1>
        <p className="page__lead rag-page__lead muted">
          Операционная консоль runtime memory/session diagnostics
        </p>
        <LoadingState label="Загрузка списка сессий…" />
      </div>
    );
  }

  const listEmpty = !loading && totalFiltered === 0;
  const rawEmpty = !(list?.items?.length ?? 0);

  return (
    <div className="page logs-page memory-console-page">
      <h1 className="page__title">Memory</h1>
      <p className="page__lead rag-page__lead muted">
        Операционная консоль runtime memory/session diagnostics
      </p>

      {error ? (
        <div className="panel panel--error page__mt" role="alert">
          {error}
        </div>
      ) : (
        <div className="logs-console memory-logs-console">
          <section className="logs-left card">
            <div className="logs-filters">
              <div className="logs-filter-row memory-logs-filter-row memory-logs-filter-row--three-selects">
                <select
                  className="logs-select"
                  value={windowLabel}
                  onChange={(e) => setWindowLabel(e.target.value as MemoryWindowLabel)}
                  aria-label="Окно времени (по updated_at сессии)"
                >
                  {MEMORY_WINDOW_OPTIONS.map((w) => (
                    <option key={w.label} value={w.label}>
                      {w.label}
                    </option>
                  ))}
                </select>
                <select
                  className="logs-select"
                  value={modeFilter}
                  onChange={(e) => setModeFilter(e.target.value as ModeFilter)}
                  aria-label="Режим сессии"
                >
                  <option value="all">все режимы</option>
                  <option value="rag">RAG</option>
                  <option value="text">текст</option>
                  <option value="other">прочие</option>
                </select>
                <select
                  className="logs-select"
                  value={activeFilter}
                  onChange={(e) =>
                    setActiveFilter(e.target.value as "all" | "active" | "inactive")
                  }
                  aria-label="Статус активности"
                >
                  <option value="all">все статусы</option>
                  <option value="active">активные</option>
                  <option value="inactive">неактивные</option>
                </select>
              </div>
              <input
                className="logs-search memory-logs-search"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Поиск: session_id, пользователь, mode, telegram id…"
                aria-label="Поиск сессий"
              />
              <div className="memory-filter-synthetic-row">
                <label
                  className="memory-filter-synthetic"
                  title="Эвристика UI: synthetic telegram id, smoke-метки в списке."
                >
                  <input
                    type="checkbox"
                    checked={hideSynthetic}
                    onChange={(e) => setHideSynthetic(e.target.checked)}
                  />
                  <span>скрыть тестовые / synthetic-сессии</span>
                </label>
              </div>
              <div className="logs-filter-meta logs-filter-meta--with-refresh muted memory-logs-filters__row">
                <span>{listMetaLine}</span>
                <OperationalRefreshButton
                  loading={loading}
                  onClick={() => setRefreshNonce((n) => n + 1)}
                />
              </div>
              <div className="logs-page-controls memory-page-controls--compact">
                <button
                  type="button"
                  className="logs-page-btn"
                  onClick={goPrevPage}
                  disabled={safePageIdx <= 0 || totalFiltered === 0}
                >
                  ← Предыдущая
                </button>
                <button
                  type="button"
                  className="logs-page-btn"
                  onClick={goNextPage}
                  disabled={safePageIdx >= totalPages - 1 || totalFiltered === 0}
                >
                  Следующая →
                </button>
                <button
                  type="button"
                  className="logs-page-btn logs-page-btn--muted"
                  onClick={resetPagination}
                  disabled={
                    safePageIdx === 0 &&
                    !searchQuery.trim() &&
                    !hideSynthetic &&
                    activeFilter === "all" &&
                    modeFilter === "all" &&
                    windowLabel === "24h"
                  }
                >
                  Сброс
                </button>
              </div>
              {list?.memory_runtime_source ? (
                <p className="memory-api-micro muted" title="Источник данных списка">
                  <code>{list.memory_runtime_source}</code> · API ≤ {LIST_FETCH_LIMIT} сессий · окно по{" "}
                  <code>updated_at</code>
                </p>
              ) : null}
            </div>
            <div className="logs-list" ref={listRef}>
              {loading && !list?.items?.length ? (
                <LoadingState label="Загрузка списка…" />
              ) : listEmpty ? (
                <EmptyState
                  title={rawEmpty ? "Нет сессий" : "Нет сессий в фильтре"}
                  message={
                    rawEmpty
                      ? "При пустой БД список пуст."
                      : "Измените поиск или снимите фильтры."
                  }
                />
              ) : (
                pageSessions.map((row: MemorySessionListItem) => {
                  const sid = row.session_id ?? "";
                  return (
                    <button
                      key={sid}
                      type="button"
                      data-memory-session-id={sid}
                      className={`logs-item memory-logs-item ${selectedSessionId === sid ? "logs-item--selected" : ""}`}
                      onClick={() => {
                        pendingListFocusRef.current = true;
                        setSelectedSessionId(sid || null);
                      }}
                    >
                      <div className="logs-item__row logs-item__row--tight">
                        <span className="mono logs-item__ts">
                          {row.updated_at
                            ? row.updated_at.slice(0, 19).replace("T", " ")
                            : "—"}
                        </span>
                        <OperationalModalityBadge modality="mem" />
                        <StatusBadge status={row.is_active ? "yes" : "no"} />
                        {row.recent_clear_badge ? (
                          <span className="memory-badge-clear">clear</span>
                        ) : null}
                      </div>
                      <div className="logs-item__preview memory-logs-item__user" title={row.user_label}>
                        {row.user_label}
                        {isSyntheticSessionRow(row) ? (
                          <OperationalModalityBadge modality="test" title="Synthetic (эвристика UI)" />
                        ) : null}
                      </div>
                      <div className="logs-item__row logs-item__meta muted">
                        <span className="mono truncate" title={sid}>
                          {shortId(sid, 12)}
                        </span>
                        <span>{row.mode}</span>
                        <span>msg {row.messages_count ?? 0}</span>
                        <span>turns~ {row.turns_approx ?? 0}</span>
                      </div>
                    </button>
                  );
                })
              )}
            </div>
          </section>

          <section className="logs-right card">
            {listEmpty ? (
              <EmptyState
                title={rawEmpty ? "Нет сессий" : "Нет сессий в фильтре"}
                message={
                  rawEmpty
                    ? "Выберите другой фильтр или дождитесь данных."
                    : "Сузьте поиск или снимите «скрыть synthetic»."
                }
              />
            ) : detailLoading && !detail ? (
              <LoadingState label="Загрузка сессии…" />
            ) : detailError ? (
              <div className="panel panel--error" role="alert">
                {detailError}
              </div>
            ) : detail && selectedSessionId ? (
              <MemorySessionDetailPanel
                detail={detail}
                detailId={selectedSessionId}
                listRow={selectedListRow}
              />
            ) : null}
          </section>
        </div>
      )}
    </div>
  );
}
