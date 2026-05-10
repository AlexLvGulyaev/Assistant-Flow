import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { fetchRecentLogs, type LogItem } from "../api/client";
import { EmptyState } from "../components/EmptyState";
import { LoadingState } from "../components/LoadingState";
import { StatusBadge } from "../components/StatusBadge";
import {
  formatDurationMs,
  formatTimestampMsk,
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
const CHUNK_PREVIEW_CHARS = 440;

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

interface RagChunk {
  source: string;
  distance: number | null;
  passedFilter: boolean;
  preview: string;
  fullText: string;
  chromaId: string | null;
  version: string | null;
  chunkIndex: number | null;
  tokenCount: number | null;
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
  uniqueSourcesCount: number | null;
  fallbackReason: string | null;
  relevanceThreshold: number | null;
  usedInContextCount: number | null;
  topK: number | null;
  wallDurationMs: number | null;
  sessionLatencyMs: number | null;
  llmProvider: string | null;
  llmModel: string | null;
  inputTokens: number | null;
  outputTokens: number | null;
  totalTokens: number | null;
  embeddingModel: string | null;
  retrievalProvider: string | null;
  collectionName: string | null;
  scores: number[];
  chunks: RagChunk[];
  /** From rag_answer_done diagnostics (server-measured). */
  retrievalLatencyMs: number | null;
  llmLatencyMs: number | null;
  ragPipelineWallMs: number | null;
  /** When logged in details; complements chunk-derived best distance. */
  loggedBestDistance: number | null;
}

export function RagPage() {
  const [items, setItems] = useState<LogItem[]>([]);
  const [currentPage, setCurrentPage] = useState(0);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState("all");
  const [fallbackFilter, setFallbackFilter] = useState("all");
  const [hasResultsOnly, setHasResultsOnly] = useState(false);
  const [search, setSearch] = useState("");
  const [windowLabel, setWindowLabel] = useState("24h");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const listRef = useRef<HTMLDivElement | null>(null);
  const pendingListFocusRef = useRef(false);
  const [chunkFullTextModal, setChunkFullTextModal] = useState<{
    chunk: RagChunk;
    displayIndex: number;
    relevanceLabel: string;
  } | null>(null);

  const fetchLimit = LOG_LIMIT_BY_WINDOW[windowLabel] ?? LOG_LIMIT_BY_WINDOW["24h"];
  const sinceHours = windowLabel === "48h" ? 48 : windowLabel === "7d" ? 24 * 7 : 24;

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      setCurrentPage(0);
      try {
        const res = await fetchRecentLogs({ limit: fetchLimit, sinceHours });
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
  }, [fetchLimit, sinceHours]);

  useEffect(() => {
    setChunkFullTextModal(null);
  }, [selectedId]);

  useEffect(() => {
    if (!chunkFullTextModal) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setChunkFullTextModal(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [chunkFullTextModal]);

  const sessions = useMemo(() => buildRagSessions(items), [items]);
  const fallbackOptions = useMemo(
    () =>
      Array.from(new Set(sessions.map((s) => s.fallbackReason || "").filter(Boolean))).sort(),
    [sessions]
  );

  const filtered = useMemo(() => {
    const now = Date.now();
    const windowMs = WINDOW_OPTIONS.find((x) => x.label === windowLabel)?.ms ?? WINDOW_OPTIONS[0].ms;
    const q = search.trim().toLowerCase();
    return sessions.filter((s) => {
      if (windowMs > 0 && now - s.lastAt > windowMs) return false;
      if (statusFilter !== "all" && normalizeStatus(s.status) !== statusFilter) return false;
      if (fallbackFilter !== "all" && (s.fallbackReason || "none") !== fallbackFilter) return false;
      if (hasResultsOnly && !((s.retrievedCount ?? 0) > 0)) return false;
      if (!q) return true;
      return (
        s.executionId.toLowerCase().includes(q) ||
        (s.query || "").toLowerCase().includes(q) ||
        (s.answer || "").toLowerCase().includes(q) ||
        (s.fallbackReason || "").toLowerCase().includes(q) ||
        s.chunks.some((c) => `${c.source} ${c.preview}`.toLowerCase().includes(q))
      );
    });
  }, [fallbackFilter, hasResultsOnly, search, sessions, statusFilter, windowLabel]);

  const totalPagesRaw = Math.ceil(filtered.length / PAGE_SIZE);
  const pageIndex = Math.min(currentPage, Math.max(0, totalPagesRaw - 1));
  const pageSessions = useMemo(
    () => filtered.slice(pageIndex * PAGE_SIZE, (pageIndex + 1) * PAGE_SIZE),
    [filtered, pageIndex]
  );
  const lastPageIndex = Math.max(0, totalPagesRaw - 1);

  useEffect(() => {
    setCurrentPage(0);
  }, [statusFilter, fallbackFilter, search, hasResultsOnly, windowLabel]);

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
      setSelectedId(pageSessions[0].executionId);
    }
  }, [filtered, pageSessions, selectedId]);

  const selected = pageSessions.find((s) => s.executionId === selectedId) ?? null;

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
    const row = list.querySelector<HTMLButtonElement>(`[data-rag-id="${safeId}"]`);
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
    <div className="page logs-page rag-page">
      <h1 className="page__title">RAG</h1>
      <p className="page__lead rag-page__lead muted">
        Операционная диагностика retrieval · <code>/api/logs/recent</code> · время: МСК
      </p>
      {loading ? (
        <LoadingState label="Загрузка RAG-сессий…" />
      ) : error ? (
        <div className="panel panel--error page__mt" role="alert">
          {error}
        </div>
      ) : sessions.length === 0 ? (
        <section className="card">
          <EmptyState message="В выборке нет RAG-сессий (маршрут rag в логах)." />
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
                  value={statusFilter}
                  onChange={(e) => setStatusFilter(e.target.value)}
                  aria-label="Статус"
                >
                  <option value="all">все статусы</option>
                  <option value="success">успех</option>
                  <option value="error">ошибка</option>
                  <option value="other">прочие</option>
                </select>
                <select
                  className="logs-select"
                  value={fallbackFilter}
                  onChange={(e) => setFallbackFilter(e.target.value)}
                  aria-label="Причина fallback"
                >
                  <option value="all">все причины fallback</option>
                  <option value="none">нет</option>
                  {fallbackOptions.map((f) => (
                    <option key={f} value={f}>
                      {fallbackReasonRuShort(f)}
                    </option>
                  ))}
                </select>
              </div>
              <input
                className="logs-search"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Поиск: execution_id, запрос, ответ, источник, fallback…"
              />
              <div className="logs-quick-row">
                <button
                  type="button"
                  className={`logs-chip ${hasResultsOnly ? "logs-chip--active" : ""}`}
                  onClick={() => setHasResultsOnly((v) => !v)}
                >
                  Только с результатами retrieval
                </button>
              </div>
              <div className="logs-filter-meta muted">
                Страница {filtered.length === 0 ? 0 : pageIndex + 1} из {totalPagesRaw || 0} ·
                сессий: {filtered.length} · показано: {pageSessions.length}
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
                  disabled={
                    pageIndex === 0 &&
                    !search.trim() &&
                    statusFilter === "all" &&
                    fallbackFilter === "all" &&
                    !hasResultsOnly &&
                    windowLabel === "24h"
                  }
                >
                  Сброс
                </button>
              </div>
            </div>
            <div className="logs-list" ref={listRef}>
              {filtered.length === 0 ? (
                <div className="panel panel--muted">Нет сессий по фильтрам.</div>
              ) : (
                pageSessions.map((s) => (
                  <button
                    key={s.executionId}
                    type="button"
                    data-rag-id={s.executionId}
                    className={`logs-item ${selectedId === s.executionId ? "logs-item--selected" : ""}`}
                    onClick={() => {
                      pendingListFocusRef.current = true;
                      setSelectedId(s.executionId);
                    }}
                  >
                    <div className="logs-item__row logs-item__row--tight">
                      <span className="mono logs-item__ts">
                        {formatTimestampMsk(s.lastAt)}
                      </span>
                      <span className="mini-badge mini-badge--rag">rag</span>
                      <StatusBadge status={s.status} />
                    </div>
                    <div className="logs-item__preview">{clipText(s.query, 96) || "запрос не найден в логах"}</div>
                    <div className="logs-item__row logs-item__meta muted">
                      <span className="mono truncate" title={s.executionId}>
                        {shortId(s.executionId)}
                      </span>
                      <span>
                        {[
                          hasNum(s.retrievedCount) ? `найдено: ${s.retrievedCount}` : null,
                          hasNum(s.usedInContextCount) ? `в контексте: ${s.usedInContextCount}` : null,
                          hasMeaningfulFallback(s.fallbackReason)
                            ? `fallback: ${fallbackReasonRuShort(s.fallbackReason)}`
                            : null,
                        ]
                          .filter(Boolean)
                          .join(" · ") || "—"}
                      </span>
                    </div>
                  </button>
                ))
              )}
            </div>
          </section>

          <section className="logs-right card">
            {!selected ? (
              <EmptyState message="Выберите RAG-сессию в списке слева." />
            ) : (
              <>
                <div className="logs-detail rag-modality-detail">
                <div className="modality-card__head">
                  <h2 className="modality-card__title">СВОДКА RAG-СЕССИИ</h2>
                  <span
                    className={`modality-card__status status-badge status-badge--${ragTitleStatusTone(selected.status)}`}
                    title={selected.status}
                  >
                    {ragTitleStatusText(selected.status)}
                  </span>
                </div>

                <div className="modality-ops-panels modality-ops-panels--rag-split">
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
                          hasNum(selected.sessionLatencyMs) ? (
                            `${selected.sessionLatencyMs} мс`
                          ) : (
                            <TelemetryGap kind="log" />
                          )
                        }
                      />
                      <OpsRow
                        label="Задержка retrieval (сервер), мс"
                        value={
                          hasNum(selected.retrievalLatencyMs) ? (
                            String(selected.retrievalLatencyMs)
                          ) : (
                            <TelemetryGap kind="log" />
                          )
                        }
                      />
                      <OpsRow
                        label="Задержка LLM (сервер), мс"
                        value={
                          hasNum(selected.llmLatencyMs) ? (
                            String(selected.llmLatencyMs)
                          ) : (
                            <TelemetryGap kind="log" />
                          )
                        }
                      />
                      <OpsRow
                        label="Длительность RAG pipeline (сервер), мс"
                        value={
                          hasNum(selected.ragPipelineWallMs) ? (
                            String(selected.ragPipelineWallMs)
                          ) : (
                            <TelemetryGap kind="log" />
                          )
                        }
                      />
                      <OpsRow
                        label="Провайдер / модель"
                        value={
                          sessionProviderModelLine(selected) ? (
                            <span className="mono">{sessionProviderModelLine(selected)}</span>
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
                  <div className="modality-ops-panels__rag-col modality-ops-panels__rag-col--stack">
                    <div className="modality-ops-panel">
                      <div className="modality-ops-panel__name">Качество</div>
                      <dl className="kv modality-ops-panel__kv">
                        <OpsRow
                          label="Лучший distance"
                          value={
                            displayedBestDistance(selected) != null ? (
                              formatDisplayedBestDistance(selected)
                            ) : (
                              <TelemetryGap kind="log" />
                            )
                          }
                        />
                        <OpsRow
                          label="Порог"
                          value={
                            hasNum(selected.relevanceThreshold) ? (
                              formatThresholdValue(selected.relevanceThreshold)
                            ) : (
                              <TelemetryGap kind="log" />
                            )
                          }
                        />
                        <OpsRow label="Релевантность" value={sessionRelevanceVerdict(selected)} />
                        <OpsRow
                          label="fallback"
                          value={
                            hasMeaningfulFallback(selected.fallbackReason) ? (
                              <span title={fallbackReasonRuLong(selected.fallbackReason)}>
                                {fallbackReasonRuLong(selected.fallbackReason)}
                              </span>
                            ) : (
                              <TelemetryGap kind="data" />
                            )
                          }
                        />
                      </dl>
                    </div>
                    <div className="modality-ops-panel">
                      <div className="modality-ops-panel__name">Retrieval</div>
                      <dl className="kv modality-ops-panel__kv">
                        <OpsRow
                          label="top_k"
                          value={
                            hasNum(selected.topK) ? String(selected.topK) : <TelemetryGap kind="log" />
                          }
                        />
                        <OpsRow
                          label="Найдено"
                          value={
                            hasNum(selected.retrievedCount) ? (
                              String(selected.retrievedCount)
                            ) : (
                              <TelemetryGap kind="log" />
                            )
                          }
                        />
                        <OpsRow
                          label="В контексте"
                          value={
                            hasNum(selected.usedInContextCount) ? (
                              String(selected.usedInContextCount)
                            ) : (
                              <TelemetryGap kind="log" />
                            )
                          }
                        />
                        <OpsRow
                          label="Отфильтровано"
                          value={
                            hasNum(selected.filteredCount) ? (
                              String(selected.filteredCount)
                            ) : (
                              <TelemetryGap kind="log" />
                            )
                          }
                        />
                        <OpsRow
                          label="Источников"
                          value={
                            hasNum(selected.uniqueSourcesCount) ? (
                              String(selected.uniqueSourcesCount)
                            ) : (
                              <TelemetryGap kind="log" />
                            )
                          }
                        />
                        <OpsRow
                          label="Символов контекста"
                          value={
                            hasNum(selected.contextChars) ? (
                              String(selected.contextChars)
                            ) : (
                              <TelemetryGap kind="log" />
                            )
                          }
                        />
                        <OpsRow
                          label="Модель embeddings"
                          value={
                            selected.embeddingModel?.trim() ? (
                              <span className="mono">{selected.embeddingModel}</span>
                            ) : (
                              <TelemetryGap kind="log" />
                            )
                          }
                        />
                        <OpsRow
                          label="Коллекция Chroma"
                          value={
                            selected.collectionName?.trim() ? (
                              <span className="mono">{selected.collectionName}</span>
                            ) : (
                              <TelemetryGap kind="log" />
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
                    <pre className="logs-pre logs-pre--compact mono">{selected.query ?? "Запрос не найден в логах."}</pre>
                    <p className="rag-io-foot muted">RAG-запрос</p>
                  </div>
                  <div className="logs-detail-block">
                    <h3 className="logs-detail-block__title">ЧТО ОТВЕТИЛА СИСТЕМА</h3>
                    <pre className="logs-pre logs-pre--compact mono">{ragAnswerBlockText(selected)}</pre>
                    <p className="rag-io-foot muted">RAG-ответ</p>
                  </div>
                </div>

                <section className="rag-chunks-primary" aria-label="Найденные чанки">
                  <h3 className="logs-timeline-heading rag-chunks-primary__title">Найденные чанки</h3>
                  {selected.chunks.length === 0 ? (
                    <div className="panel panel--muted rag-chunks-empty">
                      Чанки не переданы в логах или retrieval пустой.
                    </div>
                  ) : (
                    selected.chunks.map((chunk, i) => {
                      const idx = chunk.chunkIndex ?? i;
                      return (
                        <article key={`${chunk.source}-${i}`} className="rag-chunk-card">
                          <header className="rag-chunk-card__header">
                            <div className="rag-chunk-card__meta-row">
                              <div className="rag-chunk-card__meta-left mono">
                                <span className="rag-chunk-card__filename" title={chunk.source}>
                                  {chunk.source || "неизвестный файл"}
                                </span>
                                <span className="rag-chunk-card__chunk-no">#{idx}</span>
                                <span className="rag-chunk-card__distance">
                                  {chunk.distance != null ? (
                                    <span title="distance в Chroma (меньше — ближе к запросу)">
                                      {chunk.distance.toFixed(4)}
                                    </span>
                                  ) : (
                                    <span className="muted">—</span>
                                  )}
                                </span>
                              </div>
                              <button
                                type="button"
                                className="rag-chunk-card__fulltext-cta"
                                onClick={() =>
                                  setChunkFullTextModal({
                                    chunk,
                                    displayIndex: idx,
                                    relevanceLabel: relevanceLabel(chunk, selected.relevanceThreshold),
                                  })
                                }
                              >
                                показать полный текст
                              </button>
                              <div className="rag-chunk-card__meta-right">
                                <span className="rag-chunk-card__relevance">
                                  {relevanceLabel(chunk, selected.relevanceThreshold)}
                                </span>
                              </div>
                            </div>
                          </header>
                          <div className="rag-chunk-card__body">
                            <p className="rag-chunk-card__preview mono">{chunkPreviewText(chunk)}</p>
                          </div>
                        </article>
                      );
                    })
                  )}
                </section>

                <details className="rag-diagnostics-fold page__mt">
                  <summary className="rag-diagnostics-fold__summary">
                    Таймлайн pipeline ({selected.rows.length})
                  </summary>
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
                              <span className="muted mono logs-stage__delta">+{delta} мс</span>
                            ) : null}
                          </div>
                          {row.error_text ? (
                            <div className="logs-stage__details mono">{row.error_text}</div>
                          ) : null}
                          <details className="logs-stage__details">
                            <summary className="log-details__summary">{previewSummary(row.details)}</summary>
                            <pre className="log-details__json mono">{formatDetailsJson(row.details)}</pre>
                          </details>
                        </div>
                      );
                    })}
                  </div>
                </details>

                <details className="logs-raw-session page__mt">
                  <summary className="logs-raw-session__summary">
                    Технический снимок сессии (JSON) · {selected.rows.length} строк
                  </summary>
                  <pre className="log-details__json mono logs-raw-session__body">
                    {JSON.stringify(selected.rows, null, 2)}
                  </pre>
                </details>
                </div>
                {typeof document !== "undefined" && chunkFullTextModal
                  ? createPortal(
                      <RagChunkFullTextModal
                        chunk={chunkFullTextModal.chunk}
                        displayIndex={chunkFullTextModal.displayIndex}
                        relevanceLabel={chunkFullTextModal.relevanceLabel}
                        onClose={() => setChunkFullTextModal(null)}
                      />,
                      document.body,
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

function formatThresholdValue(t: number | null): string {
  if (t == null || !Number.isFinite(t)) return "";
  return String(t);
}

function hasNum(n: number | null | undefined): boolean {
  return n != null && Number.isFinite(n);
}

function hasMeaningfulFallback(s: string | null | undefined): boolean {
  const t = (s || "").trim().toLowerCase();
  return t.length > 0 && t !== "none";
}

function ragTitleStatusTone(status: string): "ok" | "warn" | "err" | "muted" {
  const n = status.trim().toLowerCase();
  if (n === "success") return "ok";
  if (n === "error" || n === "failed" || n.includes("fail")) return "err";
  if (n === "warning" || n === "degraded") return "warn";
  return "muted";
}

function ragTitleStatusText(status: string): string {
  const n = status.trim().toLowerCase();
  if (n === "success") return "УСПЕХ";
  if (n === "error" || n === "failed") return "ОШИБКА";
  return statusLabelRu(status).toUpperCase();
}

function sessionProviderModelLine(s: RagSession): string | null {
  const p = s.llmProvider?.trim();
  const m = s.llmModel?.trim();
  if (!p && !m) return null;
  return [p || null, m || null].filter(Boolean).join(" / ");
}

function fallbackReasonRuShort(raw: string | null): string {
  if (!raw || raw === "none") return "нет";
  return fallbackReasonRuLong(raw);
}

function fallbackReasonRuLong(raw: string | null): string {
  const s = (raw || "").trim().toLowerCase();
  if (!s || s === "none") return "нет";
  if (s === "low_relevance") return "низкая релевантность";
  if (s === "empty_retrieval") return "пустой retrieval";
  if (s === "empty_context") return "контекст не построен";
  if (s === "llm_error") return "ошибка LLM";
  return raw ?? "";
}

function relevanceLabel(chunk: RagChunk, threshold: number | null): string {
  if (chunk.distance == null) return "метрика расстояния недоступна";
  if (threshold != null && Number.isFinite(threshold)) {
    if (chunk.distance <= threshold) {
      return chunk.passedFilter ? "высокая релевантность (≤ порога)" : "в контексте / порог";
    }
    if (chunk.distance <= threshold * 1.35) return "средняя релевантность";
    return "низкая релевантность";
  }
  return chunk.passedFilter ? "включён в контекст" : "отфильтрован";
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

function formatDetailsJson(d: unknown): string {
  if (d == null) return "null";
  if (typeof d === "string") return d;
  try {
    return JSON.stringify(d, null, 2);
  } catch {
    return String(d);
  }
}

function ragAnswerBlockText(s: RagSession): string {
  if (s.answer?.trim()) return s.answer;
  const lines = [
    "Ответ отсутствует в логах.",
    "",
    `Поиск по корпусу: ${
      (s.retrievedCount ?? 0) === 0
        ? "0 фрагментов."
        : `найдено ${s.retrievedCount} фрагментов.`
    }${(s.contextChars ?? 0) === 0 ? " Контекст не собран." : ""}`,
    `Причина fallback: ${fallbackReasonRuLong(s.fallbackReason) || "нет"}`,
  ];
  return lines.join("\n");
}

function bestDistance(s: RagSession): number | null {
  const fromChunks = s.chunks
    .map((c) => c.distance)
    .filter((n): n is number => n != null && Number.isFinite(n));
  if (fromChunks.length) return Math.min(...fromChunks);
  const sc = s.scores.filter((n) => Number.isFinite(n));
  if (sc.length) return Math.min(...sc);
  return null;
}

/** Prefer explicit best_distance from rag diagnostics when present. */
function displayedBestDistance(s: RagSession): number | null {
  if (hasNum(s.loggedBestDistance)) return s.loggedBestDistance;
  return bestDistance(s);
}

function formatDisplayedBestDistance(s: RagSession): string {
  const d = displayedBestDistance(s);
  if (d == null) return "";
  return d.toFixed(4);
}

function sessionRelevanceVerdict(s: RagSession): string {
  const ref =
    s.chunks.find((c) => c.distance != null && Number.isFinite(c.distance)) ?? s.chunks[0];
  if (ref && ref.distance != null) return relevanceLabel(ref, s.relevanceThreshold);
  const bd = displayedBestDistance(s);
  if (bd == null) return "метрика в логах недоступна";
  if (s.relevanceThreshold != null && Number.isFinite(s.relevanceThreshold)) {
    return bd <= s.relevanceThreshold ? "лучший фрагмент в пределах порога" : "лучший фрагмент выше порога";
  }
  return "оценка без порога в логах";
}

function OpsRow({ label, value }: { label: string; value: ReactNode }) {
  return (
    <>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </>
  );
}

function RagChunkFullTextModal({
  chunk,
  displayIndex,
  relevanceLabel,
  onClose,
}: {
  chunk: RagChunk;
  displayIndex: number;
  relevanceLabel: string;
  onClose: () => void;
}) {
  const full = chunk.fullText?.trim()
    ? chunk.fullText
    : "Текст чанка не передан в логах.";
  return (
    <div className="rag-chunk-modal-backdrop" role="presentation" onClick={onClose}>
      <div
        className="rag-chunk-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="rag-chunk-modal-title"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="rag-chunk-modal__head">
          <h2 id="rag-chunk-modal-title" className="rag-chunk-modal__title">
            Полный текст чанка
          </h2>
          <button
            type="button"
            className="rag-chunk-modal__close"
            onClick={onClose}
            aria-label="Закрыть"
          >
            ×
          </button>
        </div>
        <dl className="kv rag-chunk-modal__meta modality-ops-panel__kv">
          <OpsRow
            label="Файл"
            value={<span className="mono break-all">{chunk.source || "неизвестный файл"}</span>}
          />
          <OpsRow label="Индекс чанка" value={<span className="mono">#{displayIndex}</span>} />
          <OpsRow
            label="distance"
            value={
              chunk.distance != null && Number.isFinite(chunk.distance) ? (
                <span className="mono">{chunk.distance.toFixed(4)}</span>
              ) : (
                <TelemetryGap kind="log" />
              )
            }
          />
          <OpsRow label="Релевантность" value={relevanceLabel} />
        </dl>
        <pre className="mono rag-chunk-modal__body">{full}</pre>
        <div className="rag-chunk-modal__foot">
          <button type="button" className="rag-chunk-modal__done" onClick={onClose}>
            Закрыть
          </button>
        </div>
      </div>
    </div>
  );
}

function pickSessionLatencyMs(detailsPool: Record<string, unknown>[]): number | null {
  let best: number | null = null;
  for (const d of detailsPool) {
    for (const key of ["latency_ms", "duration_ms", "elapsed_ms"] as const) {
      const n = Number(d[key]);
      if (Number.isFinite(n)) best = best == null ? n : Math.max(best, n);
    }
  }
  return best != null ? Math.round(best) : null;
}

function chunkPreviewText(chunk: RagChunk): string {
  const fromPreview = chunk.preview?.trim();
  if (fromPreview) {
    const clipped = clipText(fromPreview, CHUNK_PREVIEW_CHARS);
    return clipped ?? fromPreview;
  }
  const ft = chunk.fullText?.trim();
  if (ft) {
    const clipped = clipText(ft, CHUNK_PREVIEW_CHARS);
    return clipped ?? ft.slice(0, CHUNK_PREVIEW_CHARS);
  }
  return "Текст превью в логах не передан.";
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
    const usedInContext =
      pickNumber(detailsPool, ["used_chunks_count"]) ?? chunks.filter((c) => c.passedFilter).length;
    const filteredCount = pickNumber(detailsPool, ["filtered_count"]);
    const usageTok = pickUsageTokens(detailsPool);
    const inputTokens =
      pickNumber(detailsPool, ["input_tokens", "prompt_tokens", "prompt_token_count"]) ?? usageTok.input;
    const outputTokens =
      pickNumber(detailsPool, ["output_tokens", "completion_tokens", "completion_token_count"]) ??
      usageTok.output;
    let totalTokens =
      pickNumber(detailsPool, ["total_tokens", "tokens_total", "token_count_total"]) ?? usageTok.total;
    if (
      totalTokens == null &&
      inputTokens != null &&
      outputTokens != null &&
      Number.isFinite(inputTokens + outputTokens)
    ) {
      totalTokens = inputTokens + outputTokens;
    }
    const tsList = ordered
      .map((r) => toTs(r.created_at))
      .filter((t): t is number => t != null);
    const wallDurationMs = sessionWallDurationMs(tsList);

    out.push({
      executionId,
      rows: ordered,
      startedAt: toTs(first.created_at) ?? 0,
      lastAt: toTs(latest.created_at) ?? 0,
      status: String(latest.status || "нет данных"),
      query: pickText(detailsPool, ["user_input", "query_preview", "query", "prompt", "query_text"]),
      answer: extractRagAnswer(ordered, detailsPool),
      retrievedCount: pickNumber(detailsPool, ["retrieved_count"]),
      filteredCount,
      contextChars: pickNumber(detailsPool, ["context_chars"]),
      uniqueSourcesCount: pickNumber(detailsPool, ["unique_sources_count"]),
      fallbackReason: pickText(detailsPool, ["fallback_reason"]),
      relevanceThreshold: pickFloat(detailsPool, ["relevance_threshold"]),
      usedInContextCount: usedInContext,
      topK: pickNumber(detailsPool, ["top_k"]),
      wallDurationMs,
      sessionLatencyMs: pickSessionLatencyMs(detailsPool),
      llmProvider: pickText(detailsPool, ["llm_provider", "provider", "llm_provider_name"]),
      llmModel: pickText(detailsPool, ["llm_model", "model", "llm_model_name"]),
      inputTokens,
      outputTokens,
      totalTokens,
      embeddingModel: pickText(detailsPool, [
        "embedding_model",
        "embed_model",
        "embeddingModel",
        "embeddings_model",
        "vector_embedding_model",
      ]),
      retrievalProvider: pickText(detailsPool, [
        "retrieval_provider",
        "vector_provider",
        "chroma_provider",
        "embed_provider",
      ]),
      collectionName: pickText(detailsPool, [
        "collection",
        "collection_name",
        "chroma_collection",
        "vector_collection",
      ]),
      scores,
      chunks,
      retrievalLatencyMs: pickNumber(detailsPool, ["retrieval_latency_ms"]),
      llmLatencyMs: pickNumber(detailsPool, ["llm_latency_ms"]),
      ragPipelineWallMs: pickNumber(detailsPool, ["rag_pipeline_wall_ms"]),
      loggedBestDistance: pickFloat(detailsPool, ["best_distance"]),
    });
  }
  return out.sort((a, b) => b.lastAt - a.lastAt);
}

function extractRagAnswer(rows: LogItem[], detailsPool: Record<string, unknown>[]): string | null {
  const paths = [
    "answer",
    "answer_text",
    "response_text",
    "assistant_response",
    "assistant_response_text",
    "output_text",
    "final_answer",
    "rag_answer",
    "details.answer",
    "details.answer_preview",
  ];
  const fromPaths = pickTextByPaths(detailsPool, paths);
  if (fromPaths) return fromPaths;
  for (const row of rows) {
    const found = deepFindAnswerString(row.details, 0);
    if (found) return found;
  }
  return null;
}

function deepFindAnswerString(v: unknown, depth: number): string | null {
  if (depth > 5 || v == null) return null;
  if (typeof v === "string") {
    const t = v.trim();
    if (t.length < 2) return null;
    return t;
  }
  if (Array.isArray(v)) {
    for (const item of v) {
      const f = deepFindAnswerString(item, depth + 1);
      if (f && f.length > 2) return f;
    }
    return null;
  }
  if (typeof v === "object") {
    const o = v as Record<string, unknown>;
    for (const [k, val] of Object.entries(o)) {
      const kl = k.toLowerCase();
      if (
        kl === "answer" ||
        kl === "answer_text" ||
        kl === "response_text" ||
        kl === "assistant_response" ||
        kl === "output_text" ||
        kl === "final_answer" ||
        kl === "rag_answer"
      ) {
        if (typeof val === "string" && val.trim()) return val.trim();
        if (typeof val === "object" && val !== null) {
          const nested = deepFindAnswerString(val, depth + 1);
          if (nested) return nested;
        }
      }
    }
    for (const val of Object.values(o)) {
      const nested = deepFindAnswerString(val, depth + 1);
      if (nested && nested.length > 2) return nested;
    }
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
        return v.trim().slice(0, 24000);
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

function pickFloat(detailsPool: Record<string, unknown>[], keys: string[]): number | null {
  for (let i = detailsPool.length - 1; i >= 0; i--) {
    const d = detailsPool[i];
    for (const key of keys) {
      const n = Number(d[key]);
      if (Number.isFinite(n)) return n;
    }
  }
  return null;
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

/** OpenAI-style nested `usage` in log details. */
function pickUsageTokens(detailsPool: Record<string, unknown>[]): {
  input: number | null;
  output: number | null;
  total: number | null;
} {
  for (let i = detailsPool.length - 1; i >= 0; i--) {
    const u = detailsPool[i].usage;
    if (u !== null && typeof u === "object" && !Array.isArray(u)) {
      const o = u as Record<string, unknown>;
      const pt = Number(o.prompt_tokens ?? o.input_tokens);
      const ct = Number(o.completion_tokens ?? o.output_tokens);
      const tt = Number(o.total_tokens);
      return {
        input: Number.isFinite(pt) ? pt : null,
        output: Number.isFinite(ct) ? ct : null,
        total: Number.isFinite(tt) ? tt : null,
      };
    }
  }
  return { input: null, output: null, total: null };
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
    let idx = 0;
    for (const row of raw.slice(0, 24)) {
      if (!row || typeof row !== "object" || Array.isArray(row)) continue;
      const item = row as Record<string, unknown>;
      const source = String(item.source || item.filename || item.path || "unknown");
      const textRaw = String(item.text_preview || item.preview || item.text || item.content || "");
      const dist = Number(item.score ?? item.distance);
      const passed =
        typeof item.passed_filter === "boolean"
          ? item.passed_filter
          : Number.isFinite(dist) && typeof d.relevance_threshold === "number"
            ? dist <= Number(d.relevance_threshold)
            : false;
      const chromaRaw = item.chroma_id ?? item.id ?? item.chunk_id;
      const ver = item.version ?? item.version_number ?? item.document_version;
      const tok = item.token_count ?? item.tokens;
      out.push({
        source,
        distance: Number.isFinite(dist) ? dist : null,
        passedFilter: passed,
        preview: clipText(textRaw, CHUNK_PREVIEW_CHARS) ?? textRaw.slice(0, CHUNK_PREVIEW_CHARS),
        fullText: textRaw || "нет текста в логах",
        chromaId: chromaRaw != null ? String(chromaRaw) : null,
        version: ver != null ? String(ver) : null,
        chunkIndex: typeof item.chunk_index === "number" ? item.chunk_index : idx,
        tokenCount: typeof tok === "number" && Number.isFinite(tok) ? tok : null,
      });
      idx += 1;
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

function shortId(id: string | null | undefined): string {
  if (!id) return "нет данных";
  return id.length > 12 ? `${id.slice(0, 8)}…` : id;
}

function clipText(value: string | null | undefined, max: number): string | null {
  if (!value) return null;
  return value.length > max ? `${value.slice(0, max)}…` : value;
}

