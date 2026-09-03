import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import {
  fetchRecentLogs,
  type LogItem,
} from "../api/client";
import { useAuthedAssetUrl } from "../hooks/useAuthedAssetUrl";
import { EmptyState } from "../components/EmptyState";
import { LoadingState } from "../components/LoadingState";
import { OperationalRefreshButton } from "../components/OperationalRefreshButton";
import { OperationalSessionEmptyHint } from "../components/OperationalSessionEmptyHint";
import { OperationalModalityBadge } from "../components/OperationalModalityBadge";
import { OperationalPipelineStageIcon } from "../components/OperationalPipelineStageIcon";
import { SessionJsonSnapshot } from "../components/SessionJsonSnapshot";
import { StatusBadge } from "../components/StatusBadge";
import {
  detailsJsonPreview,
  operationalModalityFromRouteKey,
  pipelineStageVariant,
} from "../utils/operationalConsoleUi";
import {
  extractLatencyMs,
  formatDurationMs,
  formatTimestampMsk,
  routeLabelRu,
  showLogsRouteLabelBesideModalityBadge,
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

interface AudioSession {
  executionId: string;
  rows: LogItem[];
  startedAt: number;
  lastAt: number;
  status: string;
  routeKey: string;
  /** Последний непустой route/mode из строк лога (сырой идентификатор). */
  routeDisplay: string;
  preview: string;
  pipelineSummary: string;
  modelTokens: string[];
  listProviderLine: string | null;
  userInput: string | null;
  transcript: string | null;
  assistantOutput: string | null;
  wallDurationMs: number | null;
  maxStageLatencyMs: number | null;
  sessionLatencyMs: number | null;
  pipelineLatencyMs: number | null;
  inputTokens: number | null;
  outputTokens: number | null;
  sttProvider: string | null;
  sttModel: string | null;
  sttLatencyMs: number | null;
  sttCostUsd: number | null;
  ttsProvider: string | null;
  ttsModel: string | null;
  ttsLatencyMs: number | null;
  ttsCostUsd: number | null;
  llmProvider: string | null;
  llmModel: string | null;
  inputAudioRef: string | null;
  outputAudioRef: string | null;
  /** Почему не строим preview URL (только telegram path / file_id и т.д.). */
  inputAudioPreviewBlockedReason: string | null;
  inputMeta: Record<string, string | null>;
  outputMeta: Record<string, string | null>;
  inputDurationMs: number | null;
  outputDurationMs: number | null;
}

export function AudioPage() {
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
  const [fullTextModal, setFullTextModal] = useState<{
    title: string;
    body: string;
    filename?: string | null;
    durationLabel?: string | null;
  } | null>(null);

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
          setError(e instanceof Error ? e.message : "Не удалось загрузить аудио-сессии");
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

  const sessions = useMemo(() => buildAudioSessions(items), [items]);

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
        s.transcript,
        s.userInput,
        s.assistantOutput,
        s.listProviderLine,
        s.pipelineSummary,
        s.sttProvider,
        s.sttModel,
        s.ttsProvider,
        s.ttsModel,
        s.llmProvider,
        s.llmModel,
        ...s.rows.map(
          (r) =>
            `${r.stage ?? ""} ${stageToActionRu(r.stage, r.details)} ${detailsJsonPreview(r.details)}`
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

  // Аудио грузим авторизованным blob-фетчем: <audio src=...> не несёт Bearer,
  // а 401 с WWW-Authenticate: Basic открывает нативный пароль-диалог.
  const inputAudio = useAuthedAssetUrl(selected?.inputAudioRef ?? null);
  const outputAudio = useAuthedAssetUrl(selected?.outputAudioRef ?? null);
  const inputAudioUrl = inputAudio.url;
  const outputAudioUrl = outputAudio.url;

  const inputPreviewBlockedReason = selected?.inputAudioPreviewBlockedReason ?? null;

  return (
    <div className="page logs-page audio-page">
      <h1 className="page__title">Аудио</h1>
      <p className="page__lead rag-page__lead muted">
        Операционная консоль voice / STT / TTS · <code>/api/logs/recent</code> · время: МСК
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
                  aria-label="Фильтр статуса"
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
                placeholder="Поиск: расшифровка, запрос, ответ, execution_id, модель, этап…"
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
                <LoadingState label="Загрузка аудио-сессий…" />
              ) : sessions.length === 0 ? (
                <OperationalSessionEmptyHint
                  title="За выбранный период аудио-сессии не найдены."
                  hint="Попробуйте увеличить период или изменить фильтры."
                  showExpand7d={windowLabel === "24h"}
                  onExpand7d={() => setWindowLabel("7d")}
                />
              ) : filtered.length === 0 ? (
                <div className="panel panel--muted">Нет сессий по текущим фильтрам или окну времени.</div>
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
                      <OperationalModalityBadge modality={operationalModalityFromRouteKey(s.routeKey)} />
                      <span className="logs-item__route-status">
                        {showLogsRouteLabelBesideModalityBadge(s.routeKey) ? (
                          <>
                            {routeLabelRu(s.routeKey).toUpperCase()} ·{" "}
                          </>
                        ) : null}
                        {statusLabelRu(s.status).toUpperCase()}
                      </span>
                    </div>
                    <div className="logs-item__preview">{s.preview || "—"}</div>
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
              <EmptyState message="Выберите аудио-сессию в списке слева." />
            ) : (
              <>
                <div className="logs-detail rag-modality-detail">
                  <div className="modality-card__head">
                    <h2 className="modality-card__title">СВОДКА АУДИО-СЕССИИ</h2>
                    <StatusBadge status={selected.status} />
                  </div>

                  <div className="modality-ops-panels modality-ops-panels--rag-split audio-ops-summary">
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
                            label="Задержка pipeline"
                            value={
                              hasNum(selected.pipelineLatencyMs) ? (
                                `${selected.pipelineLatencyMs} мс`
                              ) : (
                                <TelemetryGap kind="pipeline" />
                              )
                            }
                          />
                          <OpsRow
                            label="Провайдер / модель (ответ)"
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
                        </dl>
                      </div>
                    </div>
                    <div className="modality-ops-panels__rag-col modality-ops-panels__rag-col--session">
                      <div className="modality-ops-panel">
                        <div className="modality-ops-panel__name">Аудио pipeline</div>
                        <dl className="kv modality-ops-panel__kv">
                          <OpsRow
                            label="Маршрут"
                            value={<span className="mono">{selected.routeDisplay}</span>}
                          />
                          <OpsRow
                            label="STT провайдер / модель"
                            value={
                              sttLine(selected) ? (
                                <span className="mono">{sttLine(selected)}</span>
                              ) : (
                                <TelemetryGap kind="data" />
                              )
                            }
                          />
                          <OpsRow
                            label="TTS провайдер / модель"
                            value={
                              ttsLine(selected) ? (
                                <span className="mono">{ttsLine(selected)}</span>
                              ) : (
                                <TelemetryGap kind="data" />
                              )
                            }
                          />
                          <OpsRow
                            label="Задержка STT"
                            value={
                              hasNum(selected.sttLatencyMs) ? (
                                `${selected.sttLatencyMs} мс`
                              ) : (
                                <TelemetryGap kind="pipeline" />
                              )
                            }
                          />
                          <OpsRow
                            label="Задержка TTS"
                            value={
                              hasNum(selected.ttsLatencyMs) ? (
                                `${selected.ttsLatencyMs} мс`
                              ) : (
                                <TelemetryGap kind="pipeline" />
                              )
                            }
                          />
                          <OpsRow
                            label="Стоимость STT (оценка)"
                            value={
                              hasNum(selected.sttCostUsd) ? (
                                `~$${selected.sttCostUsd!.toFixed(4)}`
                              ) : (
                                <TelemetryGap kind="data" />
                              )
                            }
                          />
                          <OpsRow
                            label="Стоимость TTS (оценка)"
                            value={
                              hasNum(selected.ttsCostUsd) ? (
                                `~$${selected.ttsCostUsd!.toFixed(4)}`
                              ) : (
                                <TelemetryGap kind="data" />
                              )
                            }
                          />
                          <OpsRow
                            label="Длительность входного аудио"
                            value={formatDurationMs(selected.inputDurationMs)}
                          />
                          <OpsRow
                            label="Длительность выходного аудио"
                            value={formatDurationMs(selected.outputDurationMs)}
                          />
                        </dl>
                      </div>
                    </div>
                  </div>

                  <div className="logs-detail-grid logs-detail-grid--dense rag-io-grid audio-io-grid">
                    <div className="logs-detail-block">
                      <h3 className="logs-detail-block__title">ЧТО СПРОСИЛ ПОЛЬЗОВАТЕЛЬ</h3>
                      {inputPreviewBlockedReason ? (
                        <div className="panel panel--muted">{inputPreviewBlockedReason}</div>
                      ) : !inputAudioUrl ? (
                        <div className="panel panel--muted">
                          Нет preview для входного аудио: в логах нет сохранённого{" "}
                          <span className="mono">asset_ref</span> (AssetRepository).
                        </div>
                      ) : inputAudio.failed ? (
                        <div className="panel panel--muted">Не удалось воспроизвести входное аудио.</div>
                      ) : (
                        <audio
                          key={`in-${selected.executionId}-${selected.inputAudioRef}`}
                          controls
                          preload="none"
                          className="audio-player"
                        >
                          <source src={inputAudioUrl} />
                        </audio>
                      )}
                      <pre className="logs-pre logs-pre--compact mono">
                        {clipText(selected.transcript ?? selected.userInput, INLINE_PREVIEW_CHARS) ??
                          "Расшифровка или текст запроса не найдены в логах."}
                      </pre>
                      <header className="rag-chunk-card__header audio-io-cta-head">
                        <div className="rag-chunk-card__meta-row">
                          <div className="rag-chunk-card__meta-left mono">
                            <span
                              className="rag-chunk-card__filename"
                              title={selected.inputMeta.filename ?? ""}
                            >
                              {selected.inputMeta.filename?.trim()
                                ? selected.inputMeta.filename
                                : "файл не указан"}
                            </span>
                            <span className="muted">{formatMetaDuration(selected.inputMeta)}</span>
                          </div>
                          <button
                            type="button"
                            className="rag-chunk-card__fulltext-cta"
                            disabled={!(selected.transcript ?? selected.userInput)?.trim()}
                            onClick={() =>
                              setFullTextModal({
                                title: "Полный текст запроса",
                                body: (selected.transcript ?? selected.userInput ?? "").trim() || "—",
                                filename: selected.inputMeta.filename,
                                durationLabel: formatMetaDuration(selected.inputMeta),
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
                          "Текст ответа не найден в логах."}
                      </pre>
                      {!outputAudioUrl ? (
                        <div className="panel panel--muted page__mt-sm">Синтезированное аудио отсутствует.</div>
                      ) : outputAudio.failed ? (
                        <div className="panel panel--muted page__mt-sm">
                          Не удалось воспроизвести выходное аудио.
                        </div>
                      ) : (
                        <audio
                          key={`out-${selected.executionId}-${selected.outputAudioRef}`}
                          controls
                          preload="none"
                          className="audio-player page__mt-sm"
                        >
                          <source src={outputAudioUrl} />
                        </audio>
                      )}
                      <header className="rag-chunk-card__header audio-io-cta-head">
                        <div className="rag-chunk-card__meta-row">
                          <div className="rag-chunk-card__meta-left mono">
                            <span
                              className="rag-chunk-card__filename"
                              title={selected.outputMeta.filename ?? ""}
                            >
                              {selected.outputMeta.filename?.trim()
                                ? selected.outputMeta.filename
                                : "TTS файл не указан"}
                            </span>
                            <span className="muted">{formatMetaDuration(selected.outputMeta)}</span>
                            <span className="muted">
                              {selected.outputMeta.mimeType
                                ? ` · ${selected.outputMeta.mimeType}`
                                : ""}
                            </span>
                          </div>
                          <button
                            type="button"
                            className="rag-chunk-card__fulltext-cta"
                            disabled={!selected.assistantOutput?.trim()}
                            onClick={() =>
                              setFullTextModal({
                                title: "Полный текст ответа",
                                body: selected.assistantOutput?.trim() || "—",
                                filename: selected.outputMeta.filename,
                                durationLabel: formatMetaDuration(selected.outputMeta),
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
                      Диагностика asset preview
                    </summary>
                    <dl className="kv modality-ops-panel__kv page__mt-sm">
                      <dt>execution_id</dt>
                      <dd className="mono break-all">{selected.executionId}</dd>
                      <dt>inputAudioAssetRef</dt>
                      <dd className="mono break-all">{selected.inputAudioRef ?? "—"}</dd>
                      <dt>outputAudioAssetRef</dt>
                      <dd className="mono break-all">{selected.outputAudioRef ?? "—"}</dd>
                      <dt>inputAudioPreviewUrl</dt>
                      <dd className="mono break-all">{inputAudioUrl ?? "—"}</dd>
                      <dt>outputAudioPreviewUrl</dt>
                      <dd className="mono break-all">{outputAudioUrl ?? "—"}</dd>
                    </dl>
                  </details>

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
                              <span className="logs-stage__label af-logs-stage-label-with-icon">
                                <OperationalPipelineStageIcon
                                  variant={pipelineStageVariant(stageRaw, row.status)}
                                />
                                {label}
                              </span>
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
                                {detailsJsonPreview(row.details)}
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
                      <AudioFullTextModal {...fullTextModal} onClose={() => setFullTextModal(null)} />,
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

function AudioFullTextModal({
  title,
  body,
  filename,
  durationLabel,
  onClose,
}: {
  title: string;
  body: string;
  filename?: string | null;
  durationLabel?: string | null;
  onClose: () => void;
}) {
  return (
    <div className="rag-chunk-modal-backdrop" role="presentation" onClick={onClose}>
      <div
        className="rag-chunk-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="audio-fulltext-modal-title"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="rag-chunk-modal__head">
          <h2 id="audio-fulltext-modal-title" className="rag-chunk-modal__title">
            {title}
          </h2>
          <button type="button" className="rag-chunk-modal__close" onClick={onClose} aria-label="Закрыть">
            ×
          </button>
        </div>
        <dl className="kv rag-chunk-modal__meta modality-ops-panel__kv">
          {filename ? (
            <OpsRow label="Файл" value={<span className="mono break-all">{filename}</span>} />
          ) : null}
          {durationLabel ? (
            <OpsRow label="Длительность" value={<span className="mono">{durationLabel}</span>} />
          ) : null}
        </dl>
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



function hasNum(n: number | null | undefined): boolean {
  return n != null && Number.isFinite(n);
}

function llmLine(s: AudioSession): string | null {
  const p = s.llmProvider?.trim();
  const m = s.llmModel?.trim();
  if (!p && !m) return null;
  return `${p || "—"} / ${m || "—"}`;
}

function sttLine(s: AudioSession): string | null {
  const p = s.sttProvider?.trim();
  const m = s.sttModel?.trim();
  if (!p && !m) return null;
  return `${p || "—"} / ${m || "—"}`;
}

function ttsLine(s: AudioSession): string | null {
  const p = s.ttsProvider?.trim();
  const m = s.ttsModel?.trim();
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

function readSub(rec: Record<string, unknown>, key: string): Record<string, unknown> | null {
  return asRecord(rec[key]);
}

function numVal(v: unknown): number | null {
  if (v == null) return null;
  const n = typeof v === "number" ? v : Number(v);
  return Number.isFinite(n) ? n : null;
}

/** Collect distinct lowercase tokens for model/provider filter. */
function collectModelTokens(parts: Array<string | null | undefined>): string[] {
  const out = new Set<string>();
  for (const p of parts) {
    const t = (p || "").trim();
    if (t) out.add(t.toLowerCase());
  }
  return Array.from(out);
}

function pickSessionLatencyMs(detailsPool: Record<string, unknown>[]): number | null {
  let best: number | null = null;
  for (const d of detailsPool) {
    const lm = extractLatencyMs(d);
    if (lm == null) continue;
    best = best == null ? lm : Math.max(best, lm);
  }
  return best != null ? Math.round(best) : null;
}

function pickPipelineLatencyMs(detailsPool: Record<string, unknown>[]): number | null {
  for (let i = detailsPool.length - 1; i >= 0; i--) {
    const d = detailsPool[i];
    for (const key of [
      "voice_pipeline_ms",
      "pipeline_latency_ms",
      "pipeline_wall_ms",
      "total_pipeline_ms",
    ] as const) {
      const n = numVal(d[key]);
      if (n != null) return Math.round(n);
    }
  }
  return null;
}

function pickTokens(detailsPool: Record<string, unknown>[]): {
  input: number | null;
  output: number | null;
} {
  for (let i = detailsPool.length - 1; i >= 0; i--) {
    const d = detailsPool[i];
    const it = numVal(d.input_tokens ?? d.tokens_input);
    const ot = numVal(d.output_tokens ?? d.tokens_output);
    if (it != null || ot != null) return { input: it, output: ot };
  }
  return { input: null, output: null };
}

/** Только явные поля входа; без общего asset_ref (он задаётся ниже по доверенным stage). */
function extractInputAudioRefFromDetails(d: Record<string, unknown>): string | null {
  const keys = ["input_asset_ref", "audio_input_asset_ref", "voice_asset_ref"];
  for (const key of keys) {
    const v = d[key];
    if (typeof v === "string" && v.trim()) return v.trim();
  }
  const inNest = readSub(d, "input_audio");
  if (inNest) {
    const ar = inNest.asset_ref;
    if (typeof ar === "string" && ar.trim()) return ar.trim();
  }
  const audioNest = readSub(d, "audio");
  const audioIn = audioNest ? readSub(audioNest, "input") : null;
  if (audioIn) {
    const ar = audioIn.asset_ref;
    if (typeof ar === "string" && ar.trim()) return ar.trim();
  }
  return null;
}

function inputStageAllowsGenericAssetRef(stageRaw: string): boolean {
  const st = stageRaw.toLowerCase();
  return (
    st.includes("stt") ||
    st.includes("intake") ||
    st.includes("route") ||
    st === "voice_processing_done" ||
    st.includes("voice_processing")
  );
}

function extractInputFallbackAssetRef(d: Record<string, unknown>, stageRaw: string): string | null {
  if (!inputStageAllowsGenericAssetRef(stageRaw)) return null;
  const v = d.asset_ref;
  if (typeof v === "string" && v.trim()) return v.trim();
  return null;
}

function pickSessionInputAudioRef(ordered: LogItem[]): string | null {
  for (const row of ordered) {
    const d = asRecord(row.details);
    if (!d) continue;
    const ex = extractInputAudioRefFromDetails(d);
    if (ex) return ex;
  }
  for (const row of ordered) {
    const d = asRecord(row.details);
    if (!d) continue;
    const fb = extractInputFallbackAssetRef(d, String(row.stage || ""));
    if (fb) return fb;
  }
  return null;
}

/** Выходной TTS — только явные output-поля; asset_ref на строках voice не считается выходом. */
function extractOutputAudioRefFromDetails(d: Record<string, unknown>): string | null {
  const keys = ["tts_asset_ref", "output_asset_ref", "audio_output_asset_ref", "generated_audio_asset_ref"];
  for (const key of keys) {
    const v = d[key];
    if (typeof v === "string" && v.trim()) return v.trim();
  }
  const outNest = readSub(d, "output_audio");
  if (outNest) {
    const ar = outNest.asset_ref;
    if (typeof ar === "string" && ar.trim()) return ar.trim();
  }
  const ttsNest = readSub(d, "tts");
  if (ttsNest) {
    const ar = ttsNest.asset_ref;
    if (typeof ar === "string" && ar.trim()) return ar.trim();
  }
  return null;
}

function pickSessionOutputAudioRef(ordered: LogItem[]): string | null {
  const preferExactStages = new Set(["tts_completed", "tts_error"]);
  for (let i = ordered.length - 1; i >= 0; i--) {
    const row = ordered[i];
    const st = String(row.stage || "").trim().toLowerCase();
    if (!preferExactStages.has(st)) continue;
    const d = asRecord(row.details);
    if (!d) continue;
    const r = extractOutputAudioRefFromDetails(d);
    if (r) return r;
  }
  for (let i = ordered.length - 1; i >= 0; i--) {
    const row = ordered[i];
    const st = String(row.stage || "").trim().toLowerCase();
    if (st === "tts_started" || st === "tts_skipped") continue;
    const d = asRecord(row.details);
    if (!d) continue;
    const r = extractOutputAudioRefFromDetails(d);
    if (r) return r;
  }
  return null;
}

function resolveSessionInputAudio(ordered: LogItem[]): {
  ref: string | null;
  blockedReason: string | null;
} {
  const ref = pickSessionInputAudioRef(ordered);
  if (ref) return { ref, blockedReason: null };
  let telegramOnly = false;
  let pathOnly = false;
  for (const row of ordered) {
    const d = asRecord(row.details);
    if (!d) continue;
    const tid = d.telegram_file_id ?? d.file_id;
    if (typeof tid === "string" && tid.trim()) telegramOnly = true;
    const ap = d.audio_path ?? d.voice_file_path ?? d.local_path;
    if (typeof ap === "string" && ap.trim()) pathOnly = true;
  }
  if (telegramOnly) {
    return {
      ref: null,
      blockedReason:
        "Входное аудио: в логах есть только идентификатор Telegram / файл без сохранённого asset_ref — браузерный preview недоступен.",
    };
  }
  if (pathOnly) {
    return {
      ref: null,
      blockedReason:
        "Входное аудио: в логах указан только локальный путь без asset_ref — нельзя отдать через /api/assets/preview.",
    };
  }
  return { ref: null, blockedReason: null };
}

function pickNestedDurationMs(d: Record<string, unknown>, kind: "input" | "output"): number | null {
  const nestKey = kind === "input" ? "input_audio" : "output_audio";
  const nest = readSub(d, nestKey);
  const pool = nest ? [nest, d] : [d];
  for (const rec of pool) {
    const sec = numVal(rec.duration_sec);
    if (sec != null) return Math.round(sec * 1000);
    const ms = numVal(rec.duration_ms ?? rec.audio_duration_ms);
    if (ms != null) return Math.round(ms);
  }
  return null;
}

function pickDurationFromPool(pool: Record<string, unknown>[], kind: "input" | "output"): number | null {
  for (let i = pool.length - 1; i >= 0; i--) {
    const ms = pickNestedDurationMs(pool[i], kind);
    if (ms != null) return ms;
  }
  return null;
}

function pickInputMeta(detailsPool: Record<string, unknown>[]): Record<string, string | null> {
  return {
    filename: pickLastString(detailsPool, [
      "filename",
      "input_filename",
      "audio_filename",
    ]),
    mimeType: pickLastString(detailsPool, ["mime_type", "audio_mime_type", "content_type"]),
    size: pickLastString(detailsPool, ["size_bytes", "audio_size_bytes", "size"]),
    duration: pickLastString(detailsPool, ["duration_ms", "audio_duration_ms", "duration_sec"]),
  };
}

function pickOutputMeta(detailsPool: Record<string, unknown>[]): Record<string, string | null> {
  return {
    filename: pickLastString(detailsPool, [
      "output_filename",
      "tts_filename",
      "generated_audio_filename",
    ]),
    mimeType: pickLastString(detailsPool, [
      "output_mime_type",
      "tts_mime_type",
      "generated_audio_mime_type",
    ]),
    size: pickLastString(detailsPool, [
      "output_size_bytes",
      "tts_size_bytes",
      "generated_audio_size_bytes",
    ]),
    duration: pickLastString(detailsPool, [
      "output_duration_ms",
      "tts_duration_ms",
      "generated_audio_duration_ms",
    ]),
  };
}

function pickLastString(pool: Record<string, unknown>[], keys: string[]): string | null {
  for (let i = pool.length - 1; i >= 0; i--) {
    const d = pool[i];
    for (const key of keys) {
      const v = d[key];
      if (typeof v === "string" && v.trim()) return v.trim();
      if (typeof v === "number" && Number.isFinite(v)) return String(v);
    }
    const ia = readSub(d, "input_audio");
    const oa = readSub(d, "output_audio");
    for (const nest of [ia, oa].filter(Boolean) as Record<string, unknown>[]) {
      for (const key of keys) {
        const v = nest[key];
        if (typeof v === "string" && v.trim()) return v.trim();
      }
    }
  }
  return null;
}

function formatMetaDuration(meta: Record<string, string | null>): string {
  const raw = meta.duration?.trim();
  if (!raw) return "—";
  const n = Number(raw);
  if (!Number.isFinite(n) || n <= 0) return raw;
  if (n >= 500) return formatDurationMs(n);
  return `${n} с`;
}

function pmLine(p: string | null, m: string | null): string | null {
  const pp = p?.trim();
  const mm = m?.trim();
  if (!pp && !mm) return null;
  return `${pp || "—"} / ${mm || "—"}`;
}

function extractSttTtsLlm(
  detailsPool: Record<string, unknown>[],
  ordered: LogItem[]
): {
  sttProvider: string | null;
  sttModel: string | null;
  sttLatencyMs: number | null;
  sttCostUsd: number | null;
  ttsProvider: string | null;
  ttsModel: string | null;
  ttsLatencyMs: number | null;
  ttsCostUsd: number | null;
  llmProvider: string | null;
  llmModel: string | null;
} {
  let sttProvider: string | null = null;
  let sttModel: string | null = null;
  let sttLatencyMs: number | null = null;
  let sttCostUsd: number | null = null;
  let ttsProvider: string | null = null;
  let ttsModel: string | null = null;
  let ttsLatencyMs: number | null = null;
  let ttsCostUsd: number | null = null;
  let llmProvider: string | null = null;
  let llmModel: string | null = null;

  for (let i = detailsPool.length - 1; i >= 0; i--) {
    const d = detailsPool[i];
    const stt = readSub(d, "stt");
    if (stt) {
      if (!sttProvider && typeof stt.provider === "string") sttProvider = stt.provider.trim();
      if (!sttModel && typeof stt.model === "string") sttModel = stt.model.trim();
      if (sttLatencyMs == null) {
        const lm = numVal(stt.latency_ms);
        if (lm != null) sttLatencyMs = Math.round(lm);
      }
      if (sttCostUsd == null) {
        const c = numVal(stt.cost_usd) ?? numVal(d.cost_usd);
        if (c != null) sttCostUsd = c;
      }
    }
    const tts = readSub(d, "tts");
    if (tts) {
      if (!ttsProvider && typeof tts.provider === "string") ttsProvider = tts.provider.trim();
      if (!ttsModel && typeof tts.model === "string") ttsModel = tts.model.trim();
      if (ttsLatencyMs == null) {
        const lm = numVal(tts.latency_ms);
        if (lm != null) ttsLatencyMs = Math.round(lm);
      }
      if (ttsCostUsd == null) {
        const c = numVal(tts.cost_usd) ?? numVal(d.cost_usd);
        if (c != null) ttsCostUsd = c;
      }
    }
    const hasAnswer =
      typeof d.answer_text === "string" ||
      typeof d.answer_preview === "string" ||
      typeof d.generated_text === "string";
    if (hasAnswer && !llmProvider && typeof d.provider === "string") {
      llmProvider = d.provider.trim();
    }
    if (hasAnswer && !llmModel && typeof d.model === "string") {
      llmModel = d.model.trim();
    }
  }

  for (let i = ordered.length - 1; i >= 0; i--) {
    const row = ordered[i];
    const stage = String(row.stage || "").toLowerCase();
    const d = asRecord(row.details) ?? {};
    if (stage.includes("stt")) {
      if (!sttProvider && typeof d.provider === "string") sttProvider = d.provider.trim();
      if (!sttModel && typeof d.model === "string") sttModel = d.model.trim();
      if (sttLatencyMs == null) {
        const lm = extractLatencyMs(d);
        if (lm != null) sttLatencyMs = Math.round(lm);
      }
      if (sttCostUsd == null) {
        const c = numVal(d.cost_usd);
        if (c != null) sttCostUsd = c;
      }
    }
    if (stage.includes("tts")) {
      if (!ttsProvider && typeof d.provider === "string") ttsProvider = d.provider.trim();
      if (!ttsModel && typeof d.model === "string") ttsModel = d.model.trim();
      if (ttsLatencyMs == null) {
        const lm = extractLatencyMs(d);
        if (lm != null) ttsLatencyMs = Math.round(lm);
      }
      if (ttsCostUsd == null) {
        const c = numVal(d.cost_usd);
        if (c != null) ttsCostUsd = c;
      }
    }
  }

  if (!llmProvider || !llmModel) {
    for (let i = detailsPool.length - 1; i >= 0; i--) {
      const d = detailsPool[i];
      if (d.answer_text || d.answer_preview) {
        if (!llmProvider && typeof d.provider === "string") llmProvider = d.provider.trim();
        if (!llmModel && typeof d.model === "string") llmModel = d.model.trim();
        break;
      }
    }
  }

  return {
    sttProvider,
    sttModel,
    sttLatencyMs,
    sttCostUsd,
    ttsProvider,
    ttsModel,
    ttsLatencyMs,
    ttsCostUsd,
    llmProvider,
    llmModel,
  };
}

function buildListProviderLine(telem: {
  sttProvider: string | null;
  sttModel: string | null;
  ttsProvider: string | null;
  ttsModel: string | null;
  llmProvider: string | null;
  llmModel: string | null;
}): string | null {
  const parts: string[] = [];
  const stt = pmLine(telem.sttProvider, telem.sttModel);
  const tts = pmLine(telem.ttsProvider, telem.ttsModel);
  const llm = pmLine(telem.llmProvider, telem.llmModel);
  if (stt) parts.push(`STT ${stt}`);
  if (tts) parts.push(`TTS ${tts}`);
  if (llm) parts.push(`LLM ${llm}`);
  return parts.length ? parts.join(" · ") : null;
}

function isAudioEvent(row: LogItem): boolean {
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

function pickRouteKey(rows: LogItem[]): string {
  for (let i = rows.length - 1; i >= 0; i--) {
    const r = rows[i];
    const raw = String(r.route || r.mode || "").toLowerCase();
    if (raw.includes("voice") || raw.includes("audio")) return "audio";
    const d = asRecord(r.details);
    const dr = String(d?.route || d?.mode || "").toLowerCase();
    if (dr.includes("voice") || dr.includes("audio")) return "audio";
  }
  return "audio";
}

function pickRouteDisplay(ordered: LogItem[]): string {
  for (let i = ordered.length - 1; i >= 0; i--) {
    const row = ordered[i];
    const d = asRecord(row.details);
    const raw = String(d?.route || row.route || row.mode || "").trim();
    if (raw) return raw;
  }
  return "audio";
}

function buildAudioSessions(rows: LogItem[]): AudioSession[] {
  const grouped = new Map<string, LogItem[]>();
  for (const row of rows) {
    if (!isAudioEvent(row)) continue;
    const id = String(row.execution_id || "").trim();
    if (!id) continue;
    const bucket = grouped.get(id) ?? [];
    bucket.push(row);
    grouped.set(id, bucket);
  }
  const out: AudioSession[] = [];
  for (const [executionId, chunk] of grouped) {
    const ordered = [...chunk].sort((a, b) => (toTs(a.created_at) ?? 0) - (toTs(b.created_at) ?? 0));
    const detailsPool = ordered
      .map((r) => asRecord(r.details))
      .filter((d): d is Record<string, unknown> => d !== null);
    const latest = ordered[ordered.length - 1];
    const first = ordered[0];
    const routeKey = pickRouteKey(ordered);
    const routeDisplay = pickRouteDisplay(ordered);

    const telem = extractSttTtsLlm(detailsPool, ordered);
    const tokens = pickTokens(detailsPool);
    const tsList = ordered
      .map((r) => toTs(r.created_at))
      .filter((t): t is number => t != null);
    const wallDurationMs = sessionWallDurationMs(tsList);
    const maxStageLatencyMs = sessionMaxStepLatencyMs(detailsPool);

    const transcript = pickLastString(detailsPool, [
      "transcript",
      "transcript_text",
      "stt_text",
      "transcript_preview",
    ]);
    const userInput = pickLastString(detailsPool, [
      "query_preview",
      "user_input",
      "query",
      "prompt",
      "input_text",
      "text",
    ]);
    const assistantOutput = pickLastString(detailsPool, [
      "answer_text",
      "answer_preview",
      "assistant_response",
      "response_text",
      "output_text",
      "generated_text",
    ]);

    const inputResolved = resolveSessionInputAudio(ordered);
    const outputAudioRef = pickSessionOutputAudioRef(ordered);

    const inputDurationMs = pickDurationFromPool(detailsPool, "input");
    const outputDurationMs = pickDurationFromPool(detailsPool, "output");

    const modelTokens = collectModelTokens([
      telem.sttProvider,
      telem.sttModel,
      telem.ttsProvider,
      telem.ttsModel,
      telem.llmProvider,
      telem.llmModel,
    ]);

    const pipelineSummary = ordered
      .map((r) => stageToActionRu(r.stage, r.details))
      .join(" → ");

    const session: AudioSession = {
      executionId,
      rows: ordered,
      startedAt: toTs(first.created_at) ?? 0,
      lastAt: toTs(latest.created_at) ?? 0,
      status: String(latest.status || "—"),
      routeKey,
      routeDisplay,
      preview:
        clipText(transcript || userInput || assistantOutput, 200) ||
        clipText(detailsJsonPreview(latest.details), 120) ||
        "—",
      pipelineSummary,
      modelTokens,
      listProviderLine: buildListProviderLine(telem),
      userInput,
      transcript,
      assistantOutput,
      wallDurationMs,
      maxStageLatencyMs,
      sessionLatencyMs: pickSessionLatencyMs(detailsPool),
      pipelineLatencyMs: pickPipelineLatencyMs(detailsPool),
      inputTokens: tokens.input,
      outputTokens: tokens.output,
      ...telem,
      inputAudioRef: inputResolved.ref,
      outputAudioRef,
      inputAudioPreviewBlockedReason: inputResolved.blockedReason,
      inputMeta: pickInputMeta(detailsPool),
      outputMeta: pickOutputMeta(detailsPool),
      inputDurationMs,
      outputDurationMs,
    };

    out.push(session);
  }
  return out.sort((a, b) => b.lastAt - a.lastAt);
}
