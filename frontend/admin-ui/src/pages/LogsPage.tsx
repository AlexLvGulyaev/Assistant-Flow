import { useEffect, useMemo, useRef, useState } from "react";
import { fetchRecentLogs, type LogItem } from "../api/client";
import { EmptyState } from "../components/EmptyState";
import { LoadingState } from "../components/LoadingState";
import { OperationalRefreshButton } from "../components/OperationalRefreshButton";
import { OperationalSessionEmptyHint } from "../components/OperationalSessionEmptyHint";
import { SessionJsonSnapshot } from "../components/SessionJsonSnapshot";
import { StatusBadge } from "../components/StatusBadge";
import {
  formatDurationMs,
  formatTimestampMsk,
  routeLabelRu,
  sessionAvgStepLatencyMs,
  sessionMaxStepLatencyMs,
  sessionWallDurationMs,
  stageToActionRu,
  statusLabelRu,
} from "../utils/operationalLabels";

const LOG_LIMIT_BY_WINDOW: Record<string, number> = {
  "24h": 400,
  "48h": 900,
  "7d": 1800,
};
/** ~один экран списка без длинного скролла внутри страницы */
const PAGE_SIZE = 10;
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
  routeKey: string;
  status: string;
  preview: string;
  providerModel: string | null;
  wallDurationMs: number | null;
  maxStageLatencyMs: number | null;
  avgStageLatencyMs: number | null;
  stageCount: number;
  pipelineSummary: string;
  userInput: string | null;
  transcript: string | null;
  assistantOutput: string | null;
  generatedPrompt: string | null;
  imageAnswer: string | null;
  ragAnswer: string | null;
  ragFallback: string | null;
}

export function LogsPage() {
  const [items, setItems] = useState<LogItem[]>([]);
  const [currentPage, setCurrentPage] = useState(0);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [routeFilter, setRouteFilter] = useState<RouteFilter>("all");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [windowLabel, setWindowLabel] = useState("24h");
  const [refreshNonce, setRefreshNonce] = useState(0);
  const [search, setSearch] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const listRef = useRef<HTMLDivElement | null>(null);
  /** Фокус на карточке только после явной навигации по списку (не при смене фильтра в поле ввода). */
  const pendingListFocusRef = useRef(false);
  const fetchLimit = LOG_LIMIT_BY_WINDOW[windowLabel] ?? LOG_LIMIT_BY_WINDOW["24h"];
  const sinceHours = windowLabelToHours(windowLabel);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const res = await fetchRecentLogs({
          limit: fetchLimit,
          sinceHours,
        });
        if (cancelled) return;
        const batch = res.items ?? [];
        setItems(batch);
      } catch (e) {
        if (!cancelled)
          setError(e instanceof Error ? e.message : "Не удалось загрузить логи");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [fetchLimit, sinceHours, refreshNonce]);

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
  const totalPagesRaw = Math.ceil(filtered.length / PAGE_SIZE);
  const pageIndex = Math.min(currentPage, Math.max(0, totalPagesRaw - 1));
  const pageSessions = useMemo(
    () =>
      filtered.slice(pageIndex * PAGE_SIZE, (pageIndex + 1) * PAGE_SIZE),
    [filtered, pageIndex]
  );

  useEffect(() => {
    setCurrentPage(0);
  }, [routeFilter, statusFilter, search, windowLabel]);

  useEffect(() => {
    if (currentPage !== pageIndex) {
      setCurrentPage(pageIndex);
    }
  }, [currentPage, pageIndex]);

  useEffect(() => {
    if (!pageSessions.length) {
      setSelectedId(null);
      return;
    }
    if (!selectedId || !filtered.some((s) => s.id === selectedId)) {
      setSelectedId(pageSessions[0].id);
      return;
    }
    if (!pageSessions.some((s) => s.id === selectedId)) {
      const idx = filtered.findIndex((s) => s.id === selectedId);
      if (idx >= 0) {
        setCurrentPage(Math.floor(idx / PAGE_SIZE));
        return;
      }
      setSelectedId(pageSessions[0].id);
    }
  }, [filtered, pageSessions, selectedId]);

  const selected =
    pageSessions.find((s) => s.id === selectedId) ?? filtered.find((s) => s.id === selectedId) ?? null;

  function resetPagination() {
    pendingListFocusRef.current = true;
    setCurrentPage(0);
    const first = filtered.slice(0, PAGE_SIZE)[0];
    if (first) setSelectedId(first.id);
  }

  const lastPageIndex = Math.max(0, totalPagesRaw - 1);

  function goPrevPage() {
    pendingListFocusRef.current = true;
    const np = Math.max(0, pageIndex - 1);
    setCurrentPage(np);
    const slice = filtered.slice(np * PAGE_SIZE, (np + 1) * PAGE_SIZE);
    const pick = slice[slice.length - 1] ?? slice[0];
    if (pick) setSelectedId(pick.id);
  }

  function goNextPage() {
    pendingListFocusRef.current = true;
    const np = Math.min(lastPageIndex, pageIndex + 1);
    setCurrentPage(np);
    const slice = filtered.slice(np * PAGE_SIZE, (np + 1) * PAGE_SIZE);
    if (slice[0]) setSelectedId(slice[0].id);
  }

  useEffect(() => {
    if (!selectedId) return;
    const list = listRef.current;
    if (!list) return;
    const safeId =
      typeof CSS !== "undefined" && typeof CSS.escape === "function"
        ? CSS.escape(selectedId)
        : selectedId.replace(/"/g, '\\"');
    const row = list.querySelector<HTMLButtonElement>(
      `[data-session-id="${safeId}"]`
    );
    if (!row) return;
    row.scrollIntoView({ block: "nearest" });
    const listHasFocus =
      document.activeElement instanceof Node && list.contains(document.activeElement);
    const shouldFocus = pendingListFocusRef.current || listHasFocus;
    pendingListFocusRef.current = false;
    if (!shouldFocus) return;
    const id = window.requestAnimationFrame(() => {
      row.focus({ preventScroll: true });
    });
    return () => window.cancelAnimationFrame(id);
  }, [selectedId, pageIndex]);

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
      const curIdx = selectedId
        ? filtered.findIndex((s) => s.id === selectedId)
        : pageIndex * PAGE_SIZE;
      if (curIdx < 0) return;
      const nextIdx =
        e.key === "ArrowDown"
          ? Math.min(filtered.length - 1, curIdx + 1)
          : Math.max(0, curIdx - 1);
      if (nextIdx === curIdx) return;
      e.preventDefault();
      const next = filtered[nextIdx];
      if (!next) return;
      pendingListFocusRef.current = true;
      setCurrentPage(Math.floor(nextIdx / PAGE_SIZE));
      setSelectedId(next.id);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [filtered, selectedId, pageIndex]);

  return (
    <div className="page logs-page">
      <h1 className="page__title">Логи</h1>
      <p className="page__lead logs-lead">
        ЖУРНАЛ EXECUTION-СЕССИЙ · <code>/api/logs/recent</code> · время: МСК
      </p>

      {error ? (
        <div className="panel panel--error page__mt" role="alert">
          {error}
        </div>
      ) : (
        <div className="logs-console">
          <section className="logs-left card">
            <div className="logs-filters">
              <div className="logs-filter-row">
                <select
                  className="logs-select"
                  value={windowLabel}
                  onChange={(e) => setWindowLabel(e.target.value)}
                  aria-label="Окно времени"
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
                  aria-label="Фильтр маршрута"
                >
                  <option value="all">все маршруты</option>
                  <option value="text">text</option>
                  <option value="rag">rag</option>
                  <option value="image">image</option>
                  <option value="audio">audio</option>
                  <option value="other">прочее</option>
                </select>
                <select
                  className="logs-select"
                  value={statusFilter}
                  onChange={(e) => setStatusFilter(e.target.value as StatusFilter)}
                  aria-label="Фильтр статуса"
                >
                  <option value="all">все статусы</option>
                  <option value="success">success</option>
                  <option value="error">error</option>
                  <option value="other">прочие</option>
                </select>
              </div>
              <input
                className="logs-search"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Поиск: execution_id, этап, текст…"
              />
              <div className="logs-filter-meta logs-filter-meta--with-refresh muted">
                <span>
                  Страница {filtered.length === 0 ? 0 : pageIndex + 1} из{" "}
                  {totalPagesRaw || 0} · всего сессий: {filtered.length} · показано:{" "}
                  {pageSessions.length}
                </span>
                <OperationalRefreshButton
                  loading={loading}
                  onClick={() => setRefreshNonce((n) => n + 1)}
                />
              </div>
              <div className="logs-page-controls">
                <button
                  type="button"
                  className="logs-page-btn"
                  onClick={goPrevPage}
                  disabled={pageIndex <= 0 || filtered.length === 0}
                >
                  ← Предыдущая
                </button>
                <button
                  type="button"
                  className="logs-page-btn"
                  onClick={goNextPage}
                  disabled={pageIndex >= lastPageIndex || filtered.length === 0}
                >
                  Следующая →
                </button>
                <button
                  type="button"
                  className="logs-page-btn logs-page-btn--muted"
                  onClick={resetPagination}
                  disabled={pageIndex === 0}
                >
                  Сброс
                </button>
              </div>
            </div>

            <div className="logs-list" ref={listRef}>
              {loading && items.length === 0 ? (
                <LoadingState label="Загрузка логов…" />
              ) : items.length === 0 ? (
                <OperationalSessionEmptyHint
                  title="За выбранный период события не найдены."
                  hint="Попробуйте увеличить период или изменить фильтры."
                  showExpand7d={windowLabel === "24h"}
                  onExpand7d={() => setWindowLabel("7d")}
                />
              ) : filtered.length === 0 ? (
                <div className="panel panel--muted">Нет сессий по текущим фильтрам или окну времени.</div>
              ) : (
                pageSessions.map((s) => (
                  <button
                    key={s.id}
                    type="button"
                    data-session-id={s.id}
                    className={`logs-item ${selectedId === s.id ? "logs-item--selected" : ""}`}
                    onClick={() => {
                      pendingListFocusRef.current = true;
                      setSelectedId(s.id);
                    }}
                  >
                    <div className="logs-item__row logs-item__row--tight">
                      <span className="mono logs-item__ts">
                        {formatTimestampMsk(s.lastAt)}
                      </span>
                      <span className="logs-item__route-status">
                        {routeLabelRu(s.routeKey).toUpperCase()} ·{" "}
                        {statusLabelRu(s.status).toUpperCase()}
                      </span>
                    </div>
                    <div className="logs-item__preview">{s.preview || "—"}</div>
                    <div className="logs-item__row logs-item__meta muted">
                      <span className="mono" title={s.id}>
                        {shortId(s.id)}
                      </span>
                      <span>этапов: {s.stageCount}</span>
                      <span title="Общая длительность (старт → конец)">
                        {formatDurationMs(s.wallDurationMs)}
                      </span>
                      <span title="Макс. длительность этапа из details">
                        макс. этап: {formatDurationMs(s.maxStageLatencyMs)}
                      </span>
                      <span className="mono truncate" title={s.providerModel ?? ""}>
                        {s.providerModel ?? "н/д"}
                      </span>
                    </div>
                  </button>
                ))
              )}
            </div>

          </section>

          <section className="logs-right card">
            {!selected ? (
              <EmptyState message="Выберите сессию для трассировки execution." />
            ) : (
              <div className="logs-detail">
                <div className="logs-detail__head">
                  <div>
                    <h2 className="card__title logs-detail__title">
                      Трассировка execution-сессии
                    </h2>
                    <p className="logs-detail__sub muted">Время: МСК</p>
                  </div>
                  <StatusBadge status={selected.status} />
                </div>

                <div className="logs-detail__route-line">
                  {routeLabelRu(selected.routeKey).toUpperCase()} ·{" "}
                  {statusLabelRu(selected.status).toUpperCase()}
                </div>

                <div className="logs-summary-grid">
                  <div className="logs-summary-col">
                    <dl className="kv logs-detail-kv">
                      <dt>execution_id</dt>
                      <dd className="mono break-all">{selected.id}</dd>
                      <dt>route</dt>
                      <dd className="mono">{selected.routeKey}</dd>
                      <dt>Статус</dt>
                      <dd>
                        <StatusBadge status={selected.status} />
                      </dd>
                      <dt>provider / model</dt>
                      <dd className="mono">{selected.providerModel ?? "н/д"}</dd>
                      <dt>Событий в трассе</dt>
                      <dd>{selected.stageCount}</dd>
                    </dl>
                  </div>
                  <div className="logs-summary-col">
                    <dl className="kv logs-detail-kv">
                      <dt>Начало</dt>
                      <dd className="mono">{formatTimestampMsk(selected.startedAt)}</dd>
                      <dt>Последняя активность</dt>
                      <dd className="mono">{formatTimestampMsk(selected.lastAt)}</dd>
                      <dt>Общая длительность</dt>
                      <dd>{formatDurationMs(selected.wallDurationMs)}</dd>
                      <dt>Макс. длительность этапа</dt>
                      <dd>{formatDurationMs(selected.maxStageLatencyMs)}</dd>
                      <dt>Средняя длительность этапа</dt>
                      <dd>{formatDurationMs(selected.avgStageLatencyMs)}</dd>
                    </dl>
                  </div>
                </div>

                <div className="logs-pipeline">
                  <div className="logs-pipeline__label muted">Цепочка этапов</div>
                  <div className="logs-pipeline__flow" title={selected.pipelineSummary}>
                    {selected.pipelineSummary || "—"}
                  </div>
                </div>

                <div className="logs-detail-grid page__mt logs-detail-grid--dense">
                  <div className="logs-detail-block">
                    <h3 className="logs-detail-block__title">
                      ЧТО СПРОСИЛ ПОЛЬЗОВАТЕЛЬ
                    </h3>
                    <pre className="logs-pre mono">{selected.userInput ?? "—"}</pre>
                    <details className="logs-details-inline">
                      <summary className="log-details__summary">
                        {detailLabels(selected.routeKey).left}
                      </summary>
                      <pre className="log-details__json mono">
                        {detailValue(selected, "left")}
                      </pre>
                    </details>
                  </div>
                  <div className="logs-detail-block">
                    <h3 className="logs-detail-block__title">
                      ЧТО ОТВЕТИЛА СИСТЕМА
                    </h3>
                    <pre className="logs-pre mono">
                      {detailValue(selected, "right")}
                    </pre>
                    <details className="logs-details-inline">
                      <summary className="log-details__summary">
                        {detailLabels(selected.routeKey).right}
                      </summary>
                      <pre className="log-details__json mono">
                        {detailValue(selected, "right")}
                      </pre>
                    </details>
                  </div>
                </div>

                <h3 className="logs-timeline-heading">Таймлайн pipeline</h3>
                <div className="logs-timeline">
                  {selected.rows.map((row, i) => {
                    const prev = i > 0 ? toTs(selected.rows[i - 1].created_at) : null;
                    const cur = toTs(row.created_at);
                    const delta =
                      prev != null && cur != null ? Math.max(0, cur - prev) : null;
                    const stageRaw = String(row.stage ?? "").trim();
                    const label = stageToActionRu(row.stage, row.details);
                    return (
                      <div
                        key={`${stageRaw}-${i}`}
                        className="logs-stage logs-stage--compact"
                        title={stageRaw ? `stage: ${stageRaw}` : undefined}
                      >
                        <div className="logs-stage__top">
                          <span className="mono logs-stage__time">
                            {formatTimestampMsk(row.created_at)}
                          </span>
                          <span className="logs-stage__label">{label}</span>
                          <StatusBadge status={row.status ?? "—"} />
                          {delta != null ? (
                            <span className="muted mono logs-stage__delta">
                              +{delta} мс
                            </span>
                          ) : null}
                        </div>
                        <details className="logs-stage__details">
                          <summary className="log-details__summary">
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

                <SessionJsonSnapshot
                  className="page__mt"
                  body={JSON.stringify(selected.rows, null, 2)}
                />
              </div>
            )}
          </section>
        </div>
      )}
    </div>
  );
}

function shortId(id: string | null | undefined): string {
  if (!id) return "—";
  return id.length > 12 ? id.slice(0, 8) + "…" : id;
}

function pickRouteKey(rows: LogItem[]): string {
  const f = pickRoute(rows);
  if (f === "image") return "image_generation";
  if (f === "audio") return "audio";
  if (f === "rag") return "rag";
  if (f === "text") return "text";
  if (f === "other") {
    for (const r of rows) {
      const det = r.details;
      if (det && typeof det === "object" && !Array.isArray(det)) {
        const rt = String((det as Record<string, unknown>).route ?? "")
          .trim()
          .toLowerCase();
        if (rt === "vision_ocr") return "text";
      }
    }
  }
  return "unknown";
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
    const ordered = [...chunk].sort(
      (a, b) => (toTs(a.created_at) ?? 0) - (toTs(b.created_at) ?? 0)
    );
    const latest = ordered[ordered.length - 1];
    const first = ordered[0];
    const detailsPool = ordered
      .map((r) => asRecord(r.details))
      .filter((d): d is Record<string, unknown> => d !== null);
    const route = pickRoute(ordered);
    const routeKey = pickRouteKey(ordered);
    const status = String(latest.status || "—");
    const providerModel = pickProviderModel(detailsPool);
    const userInput = pickText(detailsPool, [
      "list_user_preview",
      "user_input",
      "user_text",
      "query_preview",
      "query",
      "prompt",
      "input_text",
      "text",
    ]);
    const transcript = pickText(detailsPool, ["transcript_preview", "transcript"]);
    const assistantOutputBase = pickText(detailsPool, [
      "recognized_text_preview",
      "assistant_response",
      "response_text",
      "answer_preview",
      "answer",
      "answer_text",
      "output_text",
      "final_answer",
      "rag_answer",
    ]);
    const generatedPrompt = pickText(detailsPool, [
      "generated_prompt",
      "image_prompt",
      "prompt_enriched",
    ]);
    const imageAnswer = pickTextByPaths(detailsPool, [
      "enhanced_prompt",
      "image_prompt",
      "generated_prompt",
      "provider_prompt",
      "final_prompt",
      "prompt_enriched",
      "description",
      "answer",
      "response_text",
    ]);
    const ragAnswer = pickTextByPaths(detailsPool, [
      "answer",
      "answer_text",
      "response_text",
      "assistant_response",
      "output_text",
      "final_answer",
      "rag_answer",
      "details.answer",
      "details.answer_preview",
    ]);
    const ragFallback = buildRagFallback(detailsPool);
    const tsList = ordered
      .map((r) => toTs(r.created_at))
      .filter((t): t is number => t != null);
    const wallDurationMs = sessionWallDurationMs(tsList);
    const deltaStats = computeTimelineDeltaStats(ordered);
    const maxStageLatencyMs = sessionMaxStepLatencyMs(detailsPool) ?? deltaStats.max;
    const avgStageLatencyMs = sessionAvgStepLatencyMs(detailsPool) ?? deltaStats.avg;
    const pipelineSummary = ordered
      .map((r) => stageToActionRu(r.stage, r.details))
      .join(" → ");

    out.push({
      id,
      rows: ordered,
      startedAt: toTs(first.created_at) ?? 0,
      lastAt: toTs(latest.created_at) ?? 0,
      route,
      routeKey,
      status,
      preview: userInput || assistantOutputBase || imageAnswer || ragAnswer || previewSummary(latest.details),
      providerModel,
      wallDurationMs,
      maxStageLatencyMs,
      avgStageLatencyMs,
      stageCount: ordered.length,
      pipelineSummary,
      userInput,
      transcript,
      assistantOutput: assistantOutputBase,
      generatedPrompt,
      imageAnswer,
      ragAnswer,
      ragFallback,
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
      s.routeKey,
      s.status,
      s.preview,
      s.providerModel,
      s.userInput,
      s.assistantOutput,
      s.pipelineSummary,
      ...s.rows.map(
        (r) =>
          `${r.stage ?? ""} ${stageToActionRu(r.stage, r.details)} ${previewSummary(r.details)}`
      ),
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
  const ordered = [...rows].sort((a, b) => (toTs(a.created_at) ?? 0) - (toTs(b.created_at) ?? 0));
  for (let i = ordered.length - 1; i >= 0; i--) {
    const mr = String(ordered[i].modality_route ?? "")
      .trim()
      .toLowerCase();
    if (mr === "text" || mr === "rag" || mr === "image" || mr === "audio") {
      return mr;
    }
  }
  const vals = ordered
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
    if (v === "vision_ocr" || v === "ocr") return "text";
    if (v.includes("audio") || v.includes("voice")) return "audio";
    if (v === "image_generation" || v === "image_response" || v === "image") return "image";
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

function pickTextByPaths(
  detailsPool: Record<string, unknown>[],
  paths: string[]
): string | null {
  for (let i = detailsPool.length - 1; i >= 0; i--) {
    for (const p of paths) {
      const v = getPath(detailsPool[i], p);
      if (typeof v === "string" && v.trim()) {
        return v.trim().slice(0, 2400);
      }
    }
  }
  return null;
}

function getPath(obj: Record<string, unknown>, path: string): unknown {
  const parts = path.split(".");
  let cur: unknown = obj;
  for (const part of parts) {
    if (cur === null || typeof cur !== "object" || Array.isArray(cur)) {
      return undefined;
    }
    cur = (cur as Record<string, unknown>)[part];
  }
  return cur;
}

function computeTimelineDeltaStats(rows: LogItem[]): { max: number | null; avg: number | null } {
  const deltas: number[] = [];
  for (let i = 1; i < rows.length; i++) {
    const prev = toTs(rows[i - 1].created_at);
    const cur = toTs(rows[i].created_at);
    if (prev == null || cur == null) continue;
    deltas.push(Math.max(0, cur - prev));
  }
  if (!deltas.length) return { max: null, avg: null };
  const max = Math.round(Math.max(...deltas));
  const avg = Math.round(deltas.reduce((a, b) => a + b, 0) / deltas.length);
  return { max, avg };
}

function buildRagFallback(detailsPool: Record<string, unknown>[]): string | null {
  for (let i = detailsPool.length - 1; i >= 0; i--) {
    const d = detailsPool[i];
    const hasAny =
      d.retrieved_count != null ||
      d.context_chars != null ||
      d.fallback_reason != null;
    if (!hasAny) continue;
    const rc = d.retrieved_count ?? "н/д";
    const cc = d.context_chars ?? "н/д";
    const fr = d.fallback_reason ?? "нет";
    return `RAG-ответ построен; retrieved_count=${rc}, context_chars=${cc}, fallback_reason=${fr}`;
  }
  return null;
}

function pickText(
  detailsPool: Record<string, unknown>[],
  keys: string[]
): string | null {
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

function windowLabelToMs(label: string): number {
  return WINDOW_OPTIONS.find((x) => x.label === label)?.ms ?? WINDOW_OPTIONS[0].ms;
}

function windowLabelToHours(label: string): number {
  if (label === "48h") return 48;
  if (label === "7d") return 24 * 7;
  return 24;
}

function previewSummary(d: LogItem["details"]): string {
  if (d == null) return "пусто";
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

function detailLabels(routeKey: string): { left: string; right: string } {
  if (routeKey === "audio") {
    return {
      left: "Расшифровка речи (STT)",
      right: "Аудио-ответ / синтез речи (TTS)",
    };
  }
  if (routeKey === "image_generation") {
    return {
      left: "Промпт генерации",
      right: "Обогащённый промпт / описание изображения",
    };
  }
  if (routeKey === "rag") {
    return {
      left: "RAG-запрос",
      right: "RAG-ответ / контекст retrieval",
    };
  }
  return {
    left: "Текст запроса",
    right: "Ответ модели",
  };
}

function detailValue(
  session: SessionView,
  side: "left" | "right"
): string {
  if (session.routeKey === "audio") {
    if (side === "left") return session.transcript ?? session.userInput ?? "—";
    return session.assistantOutput ?? "н/д";
  }
  if (session.routeKey === "image_generation") {
    if (side === "left") return session.userInput ?? "—";
    return session.imageAnswer ?? session.generatedPrompt ?? session.assistantOutput ?? "н/д";
  }
  if (session.routeKey === "rag") {
    if (side === "left") return session.userInput ?? "—";
    return session.ragAnswer ?? session.ragFallback ?? session.assistantOutput ?? "н/д";
  }
  if (side === "left") return session.userInput ?? "—";
  return session.assistantOutput ?? "н/д";
}

