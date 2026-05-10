import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
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
  sessionMaxStepLatencyMs,
  sessionWallDurationMs,
  stageToActionRu,
  statusLabelRu,
} from "../utils/operationalLabels";

const PAGE_SIZE = 10;
const LOG_LIMIT_BY_WINDOW: Record<string, number> = {
  "24h": 400,
  "48h": 900,
  "7d": 1800,
};
const WINDOW_OPTIONS: Array<{ label: string; ms: number }> = [
  { label: "24h", ms: 24 * 60 * 60 * 1000 },
  { label: "48h", ms: 48 * 60 * 60 * 1000 },
  { label: "7d", ms: 7 * 24 * 60 * 60 * 1000 },
];
const INLINE_PREVIEW_CHARS = 280;

type StatusFilter = "all" | "success" | "error" | "other";

type TelemetryGapKind = "log" | "pipeline" | "data";

function telemetryGapText(kind: TelemetryGapKind): string {
  switch (kind) {
    case "pipeline":
      return "н/с";
    case "data":
      return "н/д";
    default:
      return "н/л";
  }
}

function TelemetryGap({ kind }: { kind: TelemetryGapKind }) {
  return <span className="telemetry-gap muted">{telemetryGapText(kind)}</span>;
}

interface TextSession {
  executionId: string;
  rows: LogItem[];
  startedAt: number;
  lastAt: number;
  status: string;
  routeDisplay: string | null;
  preview: string;
  pipelineSummary: string;
  modelTokens: string[];
  listProviderLine: string | null;
  userInput: string | null;
  assistantOutput: string | null;
  wallDurationMs: number | null;
  maxStageLatencyMs: number | null;
  /** latency_ms из processing_done (если есть). */
  processingLatencyMs: number | null;
  /** Универсальная задержка для блока «Параметры сессии»: processing → ответ LLM → макс. этап. */
  summaryLatencyMs: number | null;
  inputTokens: number | null;
  outputTokens: number | null;
  totalTokens: number | null;
  llmProvider: string | null;
  llmModel: string | null;
  responseLatencyMs: number | null;
  inputChars: number | null;
  outputChars: number | null;
  pipelineError: string | null;
}

/**
 * Одна карточка Text page = сессия только text-mode.
 * Не включаем execution, где встречаются чужие маршруты/стадии (RAG, image, voice, …),
 * даже если есть текстовые поля или processing_done.
 */
export function isTextExecutionSession(rows: LogItem[]): boolean {
  if (!rows.length) return false;
  const ordered = [...rows].sort((a, b) => (toTs(a.created_at) ?? 0) - (toTs(b.created_at) ?? 0));

  for (const row of ordered) {
    for (const raw of [row.route, row.mode]) {
      if (isForeignRouteOrMode(String(raw))) return false;
    }
    const d = asRecord(row.details);
    if (d) {
      for (const raw of [d.route, d.mode]) {
        if (isForeignRouteOrMode(String(raw))) return false;
      }
    }
  }

  for (const row of ordered) {
    if (isForeignStage(String(row.stage ?? ""))) return false;
  }

  if (ordered.some((row) => isExplicitTextRouteOrMode(String(row.route ?? "")))) return true;
  if (ordered.some((row) => isExplicitTextRouteOrMode(String(row.mode ?? "")))) return true;
  for (const row of ordered) {
    const d = asRecord(row.details);
    if (!d) continue;
    if (
      isExplicitTextRouteOrMode(String(d.route ?? "")) ||
      isExplicitTextRouteOrMode(String(d.mode ?? ""))
    ) {
      return true;
    }
  }

  if (ordered.some((row) => String(row.stage || "").trim().toLowerCase() === "text_answer_done")) {
    return true;
  }

  return false;
}

export function TextPage() {
  const [items, setItems] = useState<LogItem[]>([]);
  const [currentPage, setCurrentPage] = useState(0);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [windowLabel, setWindowLabel] = useState("24h");
  const [refreshNonce, setRefreshNonce] = useState(0);
  const [modelFilter, setModelFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const listRef = useRef<HTMLDivElement | null>(null);
  const pendingListFocusRef = useRef(false);
  const [fullTextModal, setFullTextModal] = useState<{ title: string; body: string } | null>(null);

  const fetchLimit = LOG_LIMIT_BY_WINDOW[windowLabel] ?? LOG_LIMIT_BY_WINDOW["24h"];
  const sinceHours = windowLabel === "48h" ? 48 : windowLabel === "7d" ? 24 * 7 : 24;

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const res = await fetchRecentLogs({ limit: fetchLimit, sinceHours });
        if (!cancelled) setItems(res.items ?? []);
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : "Не удалось загрузить текстовые сессии");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [fetchLimit, sinceHours, refreshNonce]);

  useEffect(() => {
    setFullTextModal(null);
  }, [selectedId]);

  useEffect(() => {
    if (!fullTextModal) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setFullTextModal(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [fullTextModal]);

  const sessions = useMemo(() => buildTextSessions(items), [items]);

  const modelOptions = useMemo(() => {
    const m = new Map<string, string>();
    for (const s of sessions) {
      for (const tok of s.modelTokens) {
        const low = tok.toLowerCase();
        if (!m.has(low)) m.set(low, tok);
      }
    }
    return Array.from(m.entries())
      .sort((a, b) => a[1].localeCompare(b[1], "ru"))
      .map(([low, label]) => ({ value: low, label }));
  }, [sessions]);

  const filtered = useMemo(() => {
    const now = Date.now();
    const windowMs = WINDOW_OPTIONS.find((x) => x.label === windowLabel)?.ms ?? WINDOW_OPTIONS[0].ms;
    const q = search.trim().toLowerCase();
    return sessions.filter((s) => {
      if (windowMs > 0 && now - s.lastAt > windowMs) return false;
      if (statusFilter !== "all" && normalizeStatusFilter(s.status) !== statusFilter) return false;
      if (modelFilter !== "all") {
        const mf = modelFilter.toLowerCase();
        if (!s.modelTokens.some((t) => t === mf)) return false;
      }
      if (!q) return true;
      const hay = [
        s.executionId,
        s.userInput,
        s.assistantOutput,
        s.listProviderLine,
        s.routeDisplay,
        s.pipelineSummary,
        s.llmProvider,
        s.llmModel,
        ...s.rows.map(
          (r) =>
            `${r.stage ?? ""} ${stageToActionRu(r.stage, r.details)} ${previewSummary(r.details)}`
        ),
      ]
        .join(" ")
        .toLowerCase();
      return hay.includes(q);
    });
  }, [modelFilter, search, sessions, statusFilter, windowLabel]);

  const totalPagesRaw = Math.ceil(filtered.length / PAGE_SIZE);
  const pageIndex = Math.min(currentPage, Math.max(0, totalPagesRaw - 1));
  const pageSessions = useMemo(
    () => filtered.slice(pageIndex * PAGE_SIZE, (pageIndex + 1) * PAGE_SIZE),
    [filtered, pageIndex]
  );
  const lastPageIndex = Math.max(0, totalPagesRaw - 1);

  useEffect(() => {
    setCurrentPage(0);
  }, [statusFilter, modelFilter, search, windowLabel]);

  useEffect(() => {
    if (currentPage !== pageIndex) setCurrentPage(pageIndex);
  }, [currentPage, pageIndex]);

  useEffect(() => {
    if (!pageSessions.length) {
      setSelectedId(null);
      return;
    }
    if (!selectedId || !filtered.some((s) => s.executionId === selectedId)) {
      setSelectedId(pageSessions[0].executionId);
      return;
    }
    if (!pageSessions.some((s) => s.executionId === selectedId)) {
      const idx = filtered.findIndex((s) => s.executionId === selectedId);
      if (idx >= 0) {
        setCurrentPage(Math.floor(idx / PAGE_SIZE));
        return;
      }
      setSelectedId(pageSessions[0].executionId);
    }
  }, [filtered, pageSessions, selectedId]);

  const selected =
    pageSessions.find((s) => s.executionId === selectedId) ??
    filtered.find((s) => s.executionId === selectedId) ??
    null;

  function resetPagination() {
    pendingListFocusRef.current = true;
    setCurrentPage(0);
    const first = filtered.slice(0, PAGE_SIZE)[0];
    if (first) setSelectedId(first.executionId);
  }

  function goPrevPage() {
    pendingListFocusRef.current = true;
    const np = Math.max(0, pageIndex - 1);
    setCurrentPage(np);
    const slice = filtered.slice(np * PAGE_SIZE, (np + 1) * PAGE_SIZE);
    const pick = slice[slice.length - 1] ?? slice[0];
    if (pick) setSelectedId(pick.executionId);
  }

  function goNextPage() {
    pendingListFocusRef.current = true;
    const np = Math.min(lastPageIndex, pageIndex + 1);
    setCurrentPage(np);
    const slice = filtered.slice(np * PAGE_SIZE, (np + 1) * PAGE_SIZE);
    if (slice[0]) setSelectedId(slice[0].executionId);
  }

  useEffect(() => {
    if (!selectedId) return;
    const list = listRef.current;
    if (!list) return;
    const safeId =
      typeof CSS !== "undefined" && typeof CSS.escape === "function"
        ? CSS.escape(selectedId)
        : selectedId.replace(/"/g, '\\"');
    const row = list.querySelector<HTMLButtonElement>(`[data-session-id="${safeId}"]`);
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
        ? filtered.findIndex((s) => s.executionId === selectedId)
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
      setSelectedId(next.executionId);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [filtered, selectedId, pageIndex]);

  return (
    <div className="page logs-page text-page">
      <h1 className="page__title">Текст</h1>
      <p className="page__lead rag-page__lead muted">
        Операционная консоль текстовых ответов · <code>/api/logs/recent</code> · время: МСК
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
                  value={modelFilter}
                  onChange={(e) => setModelFilter(e.target.value)}
                  aria-label="Фильтр по модели или провайдеру"
                >
                  <option value="all">все модели</option>
                  {modelOptions.map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                </select>
                <select
                  className="logs-select"
                  value={statusFilter}
                  onChange={(e) => setStatusFilter(e.target.value as StatusFilter)}
                  aria-label="Статус"
                >
                  <option value="all">все статусы</option>
                  <option value="success">успех</option>
                  <option value="error">ошибка</option>
                  <option value="other">прочие</option>
                </select>
              </div>
              <input
                className="logs-search"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Поиск: execution_id, запрос, ответ, модель, этап…"
              />
              <div className="logs-filter-meta logs-filter-meta--with-refresh muted">
                <span>
                  Страница {filtered.length === 0 ? 0 : pageIndex + 1} из {totalPagesRaw || 0} · всего
                  сессий: {filtered.length} · показано: {pageSessions.length}
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
                <LoadingState label="Загрузка текстовых сессий…" />
              ) : sessions.length === 0 ? (
                <OperationalSessionEmptyHint
                  title="За выбранный период text-сессии не найдены."
                  hint="Попробуйте увеличить период или изменить фильтры."
                  showExpand7d={windowLabel === "24h"}
                  onExpand7d={() => setWindowLabel("7d")}
                />
              ) : filtered.length === 0 ? (
                <div className="panel panel--muted">
                  <p>Нет сессий по текущим фильтрам или окну времени.</p>
                  {windowLabel === "24h" ? (
                    <p className="muted page__mt-sm">
                      Попробуйте период 48h или 7d — сессии могли быть раньше.
                    </p>
                  ) : null}
                </div>
              ) : (
                pageSessions.map((s) => (
                  <button
                    key={s.executionId}
                    type="button"
                    data-session-id={s.executionId}
                    className={`logs-item ${selectedId === s.executionId ? "logs-item--selected" : ""}`}
                    onClick={() => {
                      pendingListFocusRef.current = true;
                      setSelectedId(s.executionId);
                    }}
                  >
                    <div className="logs-item__row logs-item__row--tight">
                      <span className="mono logs-item__ts">{formatTimestampMsk(s.lastAt)}</span>
                      <span className="logs-item__route-status">
                        TEXT · {statusLabelRu(s.status).toUpperCase()}
                      </span>
                    </div>
                    <div className="logs-item__preview">{s.preview}</div>
                    <div className="logs-item__row logs-item__meta muted">
                      <span className="mono" title={s.executionId}>
                        {shortId(s.executionId)}
                      </span>
                      <span>этапов: {s.rows.length}</span>
                      <span title="Общая длительность (старт → конец)">
                        {formatDurationMs(s.wallDurationMs)}
                      </span>
                      <span title="Макс. длительность этапа из details">
                        макс. этап: {formatDurationMs(s.maxStageLatencyMs)}
                      </span>
                      <span className="mono truncate" title={s.listProviderLine ?? ""}>
                        {s.listProviderLine ?? "н/д"}
                      </span>
                    </div>
                  </button>
                ))
              )}
            </div>
          </section>

          <section className="logs-right card">
            {!selected ? (
              <EmptyState message="Выберите текстовую сессию в списке слева." />
            ) : (
              <>
                <div className="logs-detail rag-modality-detail">
                  <div className="modality-card__head">
                    <h2 className="modality-card__title">СВОДКА TEXT-СЕССИИ</h2>
                    <span
                      className={`modality-card__status status-badge status-badge--${textTitleStatusTone(selected.status)}`}
                      title={selected.status}
                    >
                      {textTitleStatusText(selected.status)}
                    </span>
                  </div>

                  <div className="modality-ops-panels modality-ops-panels--rag-split text-ops-summary">
                    <div className="modality-ops-panels__rag-col modality-ops-panels__rag-col--session">
                      <div className="modality-ops-panel">
                        <div className="modality-ops-panel__name">Параметры сессии</div>
                        <dl className="kv modality-ops-panel__kv">
                          <OpsRow
                            label="execution_id"
                            value={
                              selected.executionId?.trim() ? (
                                <span className="mono rag-ops-execution-id">{selected.executionId}</span>
                              ) : (
                                <TelemetryGap kind="log" />
                              )
                            }
                          />
                          <OpsRow
                            label="Начало"
                            value={
                              selected.startedAt > 0 ? (
                                <span className="mono rag-ops-timestamp-value">
                                  {formatTimestampMsk(selected.startedAt)}
                                </span>
                              ) : (
                                <TelemetryGap kind="log" />
                              )
                            }
                          />
                          <OpsRow
                            label="Длительность"
                            value={
                              hasNum(selected.wallDurationMs) ? (
                                formatDurationMs(selected.wallDurationMs)
                              ) : (
                                <TelemetryGap kind="log" />
                              )
                            }
                          />
                          <OpsRow
                            label="Задержка"
                            value={
                              hasNum(selected.summaryLatencyMs) ? (
                                `${selected.summaryLatencyMs} мс`
                              ) : (
                                <TelemetryGap kind="log" />
                              )
                            }
                          />
                          <OpsRow
                            label="Провайдер / модель"
                            value={
                              llmLine(selected) ? (
                                <span className="mono">{llmLine(selected)}</span>
                              ) : (
                                <TelemetryGap kind="pipeline" />
                              )
                            }
                          />
                          <OpsRow
                            label="Входные токены"
                            value={
                              hasNum(selected.inputTokens) ? (
                                String(selected.inputTokens)
                              ) : (
                                <TelemetryGap kind="pipeline" />
                              )
                            }
                          />
                          <OpsRow
                            label="Выходные токены"
                            value={
                              hasNum(selected.outputTokens) ? (
                                String(selected.outputTokens)
                              ) : (
                                <TelemetryGap kind="pipeline" />
                              )
                            }
                          />
                          <OpsRow
                            label="Всего токенов"
                            value={
                              hasNum(selected.totalTokens) ? (
                                String(selected.totalTokens)
                              ) : (
                                <TelemetryGap kind="pipeline" />
                              )
                            }
                          />
                        </dl>
                      </div>
                    </div>
                    <div className="modality-ops-panels__rag-col modality-ops-panels__rag-col--session">
                      <div className="modality-ops-panel">
                        <div className="modality-ops-panel__name">Текстовый пайплайн</div>
                        <dl className="kv modality-ops-panel__kv">
                          <OpsRow
                            label="Маршрут"
                            value={
                              selected.routeDisplay?.trim() ? (
                                <span className="mono">{selected.routeDisplay}</span>
                              ) : (
                                <TelemetryGap kind="log" />
                              )
                            }
                          />
                          <OpsRow
                            label="LLM провайдер"
                            value={
                              selected.llmProvider?.trim() ? (
                                <span className="mono">{selected.llmProvider}</span>
                              ) : (
                                <TelemetryGap kind="pipeline" />
                              )
                            }
                          />
                          <OpsRow
                            label="LLM модель"
                            value={
                              selected.llmModel?.trim() ? (
                                <span className="mono">{selected.llmModel}</span>
                              ) : (
                                <TelemetryGap kind="pipeline" />
                              )
                            }
                          />
                          <OpsRow
                            label="Задержка ответа"
                            value={
                              hasNum(selected.responseLatencyMs) ? (
                                `${selected.responseLatencyMs} мс`
                              ) : (
                                <TelemetryGap kind="pipeline" />
                              )
                            }
                          />
                          <OpsRow
                            label="Символов запроса"
                            value={
                              hasNum(selected.inputChars) ? (
                                String(selected.inputChars)
                              ) : (
                                <TelemetryGap kind="data" />
                              )
                            }
                          />
                          <OpsRow
                            label="Символов ответа"
                            value={
                              hasNum(selected.outputChars) ? (
                                String(selected.outputChars)
                              ) : (
                                <TelemetryGap kind="data" />
                              )
                            }
                          />
                          <OpsRow
                            label="Ошибка / fallback"
                            value={
                              selected.pipelineError?.trim() ? (
                                <span className="mono">{selected.pipelineError}</span>
                              ) : (
                                <TelemetryGap kind="data" />
                              )
                            }
                          />
                        </dl>
                      </div>
                    </div>
                  </div>

                  <div className="logs-detail-grid logs-detail-grid--dense rag-io-grid">
                    <div className="logs-detail-block">
                      <h3 className="logs-detail-block__title">ЧТО СПРОСИЛ ПОЛЬЗОВАТЕЛЬ</h3>
                      <pre className="logs-pre logs-pre--compact mono">
                        {clipText(selected.userInput, INLINE_PREVIEW_CHARS) ??
                          "Текст запроса не найден в логах."}
                      </pre>
                      <header className="rag-chunk-card__header audio-io-cta-head">
                        <div className="rag-chunk-card__meta-row">
                          <span className="muted mono">пользовательский ввод</span>
                          <button
                            type="button"
                            className="rag-chunk-card__fulltext-cta"
                            disabled={!selected.userInput?.trim()}
                            onClick={() =>
                              setFullTextModal({
                                title: "Полный текст запроса",
                                body: selected.userInput?.trim() || "—",
                              })
                            }
                          >
                            показать полный текст
                          </button>
                        </div>
                      </header>
                    </div>
                    <div className="logs-detail-block">
                      <h3 className="logs-detail-block__title">ЧТО ОТВЕТИЛА СИСТЕМА</h3>
                      <pre className="logs-pre logs-pre--compact mono">
                        {clipText(selected.assistantOutput, INLINE_PREVIEW_CHARS) ??
                          "Ответ не найден в логах."}
                      </pre>
                      <header className="rag-chunk-card__header audio-io-cta-head">
                        <div className="rag-chunk-card__meta-row">
                          <span className="muted mono">ответ ассистента</span>
                          <button
                            type="button"
                            className="rag-chunk-card__fulltext-cta"
                            disabled={!selected.assistantOutput?.trim()}
                            onClick={() =>
                              setFullTextModal({
                                title: "Полный текст ответа",
                                body: selected.assistantOutput?.trim() || "—",
                              })
                            }
                          >
                            показать полный текст
                          </button>
                        </div>
                      </header>
                    </div>
                  </div>

                  <details className="rag-diagnostics-fold page__mt">
                    <summary className="rag-diagnostics-fold__summary">
                      Таймлайн pipeline ({selected.rows.length})
                    </summary>
                    <div className="logs-timeline page__mt-sm">
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
                                <span className="muted mono logs-stage__delta">+{delta} мс</span>
                              ) : null}
                            </div>
                            {row.error_text ? (
                              <div className="logs-stage__details mono">{row.error_text}</div>
                            ) : null}
                            <details className="logs-stage__details">
                              <summary className="log-details__summary">
                                {previewSummary(row.details)}
                              </summary>
                              <pre className="log-details__json mono">{formatDetailsJson(row.details)}</pre>
                            </details>
                          </div>
                        );
                      })}
                    </div>
                  </details>

                  <SessionJsonSnapshot
                    className="page__mt"
                    body={JSON.stringify(selected.rows, null, 2)}
                  />
                </div>

                {typeof document !== "undefined" && fullTextModal
                  ? createPortal(
                      <TextFullTextModal {...fullTextModal} onClose={() => setFullTextModal(null)} />,
                      document.body
                    )
                  : null}
              </>
            )}
          </section>
        </div>
      )}
    </div>
  );
}

function OpsRow({ label, value }: { label: string; value: ReactNode }) {
  return (
    <>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </>
  );
}

function TextFullTextModal({
  title,
  body,
  onClose,
}: {
  title: string;
  body: string;
  onClose: () => void;
}) {
  return (
    <div className="rag-chunk-modal-backdrop" role="presentation" onClick={onClose}>
      <div
        className="rag-chunk-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="text-fulltext-modal-title"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="rag-chunk-modal__head">
          <h2 id="text-fulltext-modal-title" className="rag-chunk-modal__title">
            {title}
          </h2>
          <button type="button" className="rag-chunk-modal__close" onClick={onClose} aria-label="Закрыть">
            ×
          </button>
        </div>
        <pre className="mono rag-chunk-modal__body">{body}</pre>
        <div className="rag-chunk-modal__foot">
          <button type="button" className="rag-chunk-modal__done" onClick={onClose}>
            Закрыть
          </button>
        </div>
      </div>
    </div>
  );
}

function textTitleStatusTone(status: string): "ok" | "warn" | "err" | "muted" {
  const n = status.trim().toLowerCase();
  if (n === "success") return "ok";
  if (n === "error" || n === "failed" || n.includes("fail")) return "err";
  if (n === "warning" || n === "degraded" || n === "skipped") return "warn";
  return "muted";
}

function textTitleStatusText(status: string): string {
  const n = status.trim().toLowerCase();
  if (n === "success") return "УСПЕХ";
  if (n === "error" || n === "failed") return "ОШИБКА";
  return statusLabelRu(status).toUpperCase();
}

function hasNum(n: number | null | undefined): boolean {
  return n != null && Number.isFinite(n);
}

function llmLine(s: TextSession): string | null {
  const p = s.llmProvider?.trim();
  const m = s.llmModel?.trim();
  if (!p && !m) return null;
  return `${p || "—"} / ${m || "—"}`;
}

function normalizeStatusFilter(status: string): StatusFilter {
  const n = status.trim().toLowerCase();
  if (n === "success") return "success";
  if (n === "error") return "error";
  return "other";
}

function shortId(id: string | null | undefined): string {
  if (!id) return "—";
  return id.length > 12 ? `${id.slice(0, 8)}…` : id;
}

function clipText(value: string | null | undefined, max: number): string | null {
  if (!value?.trim()) return null;
  const t = value.trim();
  return t.length > max ? `${t.slice(0, max)}…` : t;
}

function previewSummary(d: LogItem["details"]): string {
  if (d == null) return "пусто";
  if (typeof d === "string") return d.length > 56 ? `${d.slice(0, 56)}…` : d;
  try {
    const s = JSON.stringify(d);
    return s.length > 56 ? `${s.slice(0, 56)}…` : s || "{}";
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

function toTs(iso: string | null | undefined): number | null {
  if (!iso) return null;
  const n = new Date(iso).getTime();
  return Number.isFinite(n) ? n : null;
}

function asRecord(v: unknown): Record<string, unknown> | null {
  if (v !== null && typeof v === "object" && !Array.isArray(v)) {
    return v as Record<string, unknown>;
  }
  return null;
}

function isExplicitTextRouteOrMode(v: string): boolean {
  const t = v.trim().toLowerCase();
  if (!t) return false;
  return t === "text" || t === "text_response" || t.startsWith("text_");
}

/** Чужие маршруты/режимы: RAG, изображения, голос, документы админки и т.д. */
function isForeignRouteOrMode(raw: string): boolean {
  const t = raw.trim().toLowerCase();
  if (!t) return false;
  if (t === "rag" || t.startsWith("rag_")) return true;
  if (t.includes("image")) return true;
  if (t === "audio" || t === "voice" || t.startsWith("voice_") || t.startsWith("audio_")) return true;
  if (t === "stt" || t === "tts" || t.startsWith("stt_") || t.startsWith("tts_")) return true;
  if (t === "document" || t === "documents") return true;
  if (t.includes("reindex")) return true;
  if (t.includes("upload") && (t.includes("admin") || t.includes("document"))) return true;
  return false;
}

function isForeignStage(stageRaw: string): boolean {
  const s = stageRaw.trim().toLowerCase();
  if (!s) return false;
  if (s.startsWith("rag_")) return true;
  if (s.startsWith("image_")) return true;
  if (s.startsWith("stt_") || s.startsWith("tts_")) return true;
  if (s.startsWith("voice_")) return true;
  if (s.startsWith("audio_generation")) return true;
  if (s.startsWith("admin_document") || s.startsWith("admin_reindex")) return true;
  return false;
}

function findLatestDetailsByStage(
  ordered: LogItem[],
  stageNeedle: string
): Record<string, unknown> | null {
  const sn = stageNeedle.toLowerCase();
  for (let i = ordered.length - 1; i >= 0; i--) {
    if (String(ordered[i].stage || "").toLowerCase() === sn) {
      return asRecord(ordered[i].details);
    }
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

function numField(obj: Record<string, unknown>, keys: string[]): number | null {
  for (const key of keys) {
    const v = obj[key];
    const n = typeof v === "number" ? v : Number(v);
    if (Number.isFinite(n)) return n;
  }
  return null;
}

function pickUserInput(ordered: LogItem[], detailsPool: Record<string, unknown>[]): string | null {
  for (const row of ordered) {
    if (String(row.stage || "").toLowerCase() !== "intake_received") continue;
    const d = asRecord(row.details);
    if (!d) continue;
    const u = strField(d, ["user_text"]);
    if (u) return u;
    const q = strField(d, ["query_preview"]);
    if (q) return q;
  }
  return strFieldFromPool(detailsPool, [
    "user_text",
    "query_preview",
    "user_input",
    "query",
    "prompt",
    "input_text",
    "text",
  ]);
}

function strFieldFromPool(pool: Record<string, unknown>[], keys: string[]): string | null {
  for (let i = pool.length - 1; i >= 0; i--) {
    const s = strField(pool[i], keys);
    if (s) return s;
  }
  return null;
}

function pickAssistantOutput(detailsPool: Record<string, unknown>[]): string | null {
  return strFieldFromPool(detailsPool, [
    "answer_text",
    "assistant_response",
    "response_text",
    "answer",
    "answer_preview",
    "output_text",
    "generated_text",
  ]);
}

function pickRouteDisplay(ordered: LogItem[]): string | null {
  for (let i = ordered.length - 1; i >= 0; i--) {
    const row = ordered[i];
    const raw = String(row.route || row.mode || "").trim();
    if (raw) return raw;
    const d = asRecord(row.details);
    const dr = d ? String(d.route || d.mode || "").trim() : "";
    if (dr) return dr;
  }
  return null;
}

function pickLlmFromPool(detailsPool: Record<string, unknown>[]): {
  provider: string | null;
  model: string | null;
} {
  for (let i = detailsPool.length - 1; i >= 0; i--) {
    const d = detailsPool[i];
    const p = strField(d, ["provider", "llm_provider"]);
    const m = strField(d, ["model", "llm_model"]);
    if (p || m) return { provider: p, model: m };
  }
  return { provider: null, model: null };
}

function pickProcessingDone(ordered: LogItem[]): {
  latencyMs: number | null;
  inputTokens: number | null;
  outputTokens: number | null;
  totalTokens: number | null;
} {
  const d = findLatestDetailsByStage(ordered, "processing_done");
  if (!d) {
    return { latencyMs: null, inputTokens: null, outputTokens: null, totalTokens: null };
  }
  return {
    latencyMs: numField(d, ["latency_ms"]),
    inputTokens: numField(d, ["input_tokens"]),
    outputTokens: numField(d, ["output_tokens"]),
    totalTokens: numField(d, ["total_tokens"]),
  };
}

/** Токены и nested usage из одной записи details (как в text_answer_done / processing_done). */
function extractTokensFromDetails(d: Record<string, unknown>): {
  inputTokens: number | null;
  outputTokens: number | null;
  totalTokens: number | null;
} {
  let it = numField(d, ["input_tokens", "prompt_tokens", "tokens_input"]);
  let ot = numField(d, ["output_tokens", "completion_tokens", "tokens_output"]);
  let tt = numField(d, ["total_tokens", "tokens_total", "token_count_total"]);
  const u = d.usage;
  if (u !== null && typeof u === "object" && !Array.isArray(u)) {
    const o = u as Record<string, unknown>;
    const pit = Number(o.prompt_tokens ?? o.input_tokens);
    const pot = Number(o.completion_tokens ?? o.output_tokens);
    const ptt = Number(o.total_tokens);
    if (it == null && Number.isFinite(pit)) it = pit;
    if (ot == null && Number.isFinite(pot)) ot = pot;
    if (tt == null && Number.isFinite(ptt)) tt = ptt;
  }
  if (tt == null && it != null && ot != null && Number.isFinite(it + ot)) {
    tt = it + ot;
  }
  return {
    inputTokens: it != null && Number.isFinite(it) ? Math.round(it) : null,
    outputTokens: ot != null && Number.isFinite(ot) ? Math.round(ot) : null,
    totalTokens: tt != null && Number.isFinite(tt) ? Math.round(tt) : null,
  };
}

/**
 * Токены из первой подходящей стадии (сервер чаще кладёт их в text_answer_done, не в processing_done).
 */
function pickAggregatedTokens(ordered: LogItem[], detailsPool: Record<string, unknown>[]): {
  inputTokens: number | null;
  outputTokens: number | null;
  totalTokens: number | null;
} {
  const stages = [
    "processing_done",
    "text_answer_done",
    "response_generated",
    "text_response",
  ];
  for (const st of stages) {
    const d = findLatestDetailsByStage(ordered, st);
    if (!d) continue;
    const t = extractTokensFromDetails(d);
    if (t.inputTokens != null || t.outputTokens != null || t.totalTokens != null) {
      return t;
    }
  }
  for (let i = detailsPool.length - 1; i >= 0; i--) {
    const t = extractTokensFromDetails(detailsPool[i]);
    if (t.inputTokens != null || t.outputTokens != null || t.totalTokens != null) {
      return t;
    }
  }
  return { inputTokens: null, outputTokens: null, totalTokens: null };
}

const TEXT_LATENCY_STAGES = [
  "text_answer_done",
  "response_generated",
  "text_response",
] as const;

function pickResponseLatencyMs(ordered: LogItem[], detailsPool: Record<string, unknown>[]): number | null {
  for (const stage of TEXT_LATENCY_STAGES) {
    const d = findLatestDetailsByStage(ordered, stage);
    if (!d) continue;
    const lm = numField(d, [
      "response_latency_ms",
      "latency_ms",
      "duration_ms",
      "elapsed_ms",
      "llm_latency_ms",
    ]);
    if (lm != null) return Math.round(lm);
  }
  for (let i = detailsPool.length - 1; i >= 0; i--) {
    const d = detailsPool[i];
    const lm = numField(d, ["response_latency_ms", "llm_latency_ms"]);
    if (lm != null) return Math.round(lm);
  }
  return null;
}

function pickSummaryLatencyMs(
  processingMs: number | null,
  responseMs: number | null,
  maxStageMs: number | null
): number | null {
  if (processingMs != null && Number.isFinite(processingMs)) return Math.round(processingMs);
  if (responseMs != null && Number.isFinite(responseMs)) return Math.round(responseMs);
  if (maxStageMs != null && Number.isFinite(maxStageMs)) return Math.round(maxStageMs);
  return null;
}

function collectModelTokens(provider: string | null, model: string | null): string[] {
  const out = new Set<string>();
  for (const p of [provider, model]) {
    const t = (p || "").trim().toLowerCase();
    if (t) out.add(t);
  }
  return Array.from(out);
}

function pickPipelineError(ordered: LogItem[]): string | null {
  for (let i = ordered.length - 1; i >= 0; i--) {
    const row = ordered[i];
    if (row.error_text?.trim()) return row.error_text.trim();
    const st = String(row.status || "").toLowerCase();
    if (st === "error") {
      const d = asRecord(row.details);
      const msg = d && strField(d, ["error", "error_message", "message", "fallback_reason"]);
      if (msg) return msg;
    }
  }
  return null;
}

function buildTextSessions(rows: LogItem[]): TextSession[] {
  const grouped = new Map<string, LogItem[]>();
  for (const row of rows) {
    const id = String(row.execution_id || "").trim();
    if (!id) continue;
    const bucket = grouped.get(id) ?? [];
    bucket.push(row);
    grouped.set(id, bucket);
  }
  const out: TextSession[] = [];
  for (const [executionId, chunk] of grouped) {
    if (!isTextExecutionSession(chunk)) continue;
    const ordered = [...chunk].sort((a, b) => (toTs(a.created_at) ?? 0) - (toTs(b.created_at) ?? 0));
    const detailsPool = ordered
      .map((r) => asRecord(r.details))
      .filter((d): d is Record<string, unknown> => d !== null);
    const latest = ordered[ordered.length - 1];
    const first = ordered[0];
    const tsList = ordered
      .map((r) => toTs(r.created_at))
      .filter((t): t is number => t != null);
    const wallDurationMs = sessionWallDurationMs(tsList);
    const maxStageLatencyMs = sessionMaxStepLatencyMs(detailsPool);

    const userInput = pickUserInput(ordered, detailsPool);
    const assistantOutput = pickAssistantOutput(detailsPool);
    const { provider, model } = pickLlmFromPool(detailsPool);
    const proc = pickProcessingDone(ordered);
    const responseLatencyMs = pickResponseLatencyMs(ordered, detailsPool);
    const tok = pickAggregatedTokens(ordered, detailsPool);
    const procLat =
      proc.latencyMs != null && Number.isFinite(proc.latencyMs) ? Math.round(proc.latencyMs) : null;
    const summaryLatencyMs = pickSummaryLatencyMs(procLat, responseLatencyMs, maxStageLatencyMs);
    const listLine = provider || model ? `${provider || "—"} / ${model || "—"}` : null;

    const inputChars =
      userInput?.length != null && userInput.length > 0
        ? userInput.length
        : numFieldFromPool(detailsPool, ["input_chars", "query_chars", "prompt_chars"]);
    const outputChars =
      assistantOutput?.length != null && assistantOutput.length > 0
        ? assistantOutput.length
        : numFieldFromPool(detailsPool, ["output_chars", "answer_chars", "response_chars"]);

    const preview =
      clipText(userInput, 200) ||
      clipText(assistantOutput, 200) ||
      clipText(previewSummary(latest.details), 120) ||
      "—";

    out.push({
      executionId,
      rows: ordered,
      startedAt: toTs(first.created_at) ?? 0,
      lastAt: toTs(latest.created_at) ?? 0,
      status: String(latest.status || "—"),
      routeDisplay: pickRouteDisplay(ordered),
      preview,
      pipelineSummary: ordered.map((r) => stageToActionRu(r.stage, r.details)).join(" → "),
      modelTokens: collectModelTokens(provider, model),
      listProviderLine: listLine,
      userInput,
      assistantOutput,
      wallDurationMs,
      maxStageLatencyMs,
      processingLatencyMs: procLat,
      summaryLatencyMs,
      inputTokens: tok.inputTokens,
      outputTokens: tok.outputTokens,
      totalTokens: tok.totalTokens,
      llmProvider: provider,
      llmModel: model,
      responseLatencyMs,
      inputChars,
      outputChars,
      pipelineError: pickPipelineError(ordered),
    });
  }
  return out.sort((a, b) => b.lastAt - a.lastAt);
}

function numFieldFromPool(pool: Record<string, unknown>[], keys: string[]): number | null {
  for (let i = pool.length - 1; i >= 0; i--) {
    const n = numField(pool[i], keys);
    if (n != null) return Math.round(n);
  }
  return null;
}
