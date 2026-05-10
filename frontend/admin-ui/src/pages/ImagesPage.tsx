import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import {
  fetchRecentLogs,
  getAssetPreviewUrl,
  type LogItem,
} from "../api/client";
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
const INLINE_PROMPT_PREVIEW = 320;

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

/** Промежуточный или финальный этап цепочки промптов (отдельные токены/latency). */
interface ImagePromptChainStage {
  text: string | null;
  provider: string | null;
  model: string | null;
  inputTokens: number | null;
  outputTokens: number | null;
  totalTokens: number | null;
  latencyMs: number | null;
}

interface OutputImageMeta {
  assetRef: string | null;
  filename: string | null;
  sizeBytes: number | null;
  provider: string | null;
  model: string | null;
}

interface ImageSession {
  executionId: string;
  rows: LogItem[];
  startedAt: number;
  lastAt: number;
  status: string;
  /** Исходный запрос (intake и др.). */
  originalUserPrompt: string | null;
  /** Уточнение текста (GigaChat), stage image_text_enhancement_done. */
  textEnhancement: ImagePromptChainStage | null;
  /** Финальный prompt для image provider, stage image_prompt_refinement_done. */
  finalImagePrompt: ImagePromptChainStage | null;
  /** Компактная строка для карточки списка, если original пуст. */
  listPreviewFallback: string | null;
  /** Провайдер / модель генерации изображения (image_provider_done) для списка. */
  providerModel: string | null;
  /** Токен фильтра по провайдеру image provider. */
  providerFilterToken: string | null;
  /** Задержка из processing_done.details.latency_ms (итог сессии). */
  processingLatencyMs: number | null;
  wallDurationMs: number | null;
  processingInputTokens: number | null;
  processingOutputTokens: number | null;
  processingTotalTokens: number | null;
  assetRefs: string[];
  /** Метаданные из output_images (по индексу; слияние с assetRefs при отображении). */
  outputImageMeta: OutputImageMeta[];
  pipelineSummary: string;
  imageGenProvider: string | null;
  imageGenModel: string | null;
  imageGenDurationMs: number | null;
  pipelineError: string | null;
}

export function ImagesPage() {
  const [items, setItems] = useState<LogItem[]>([]);
  const [currentPage, setCurrentPage] = useState(0);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selectedAssetIdx, setSelectedAssetIdx] = useState(0);
  const [windowLabel, setWindowLabel] = useState("24h");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [providerFilter, setProviderFilter] = useState("all");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const listRef = useRef<HTMLDivElement | null>(null);
  const pendingListFocusRef = useRef(false);
  const [imgFailed, setImgFailed] = useState(false);
  const [fullTextModal, setFullTextModal] = useState<{ title: string; body: string } | null>(null);

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
          setError(e instanceof Error ? e.message : "Не удалось загрузить логи изображений");
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

  const sessions = useMemo(() => buildImageSessions(items), [items]);

  const providers = useMemo(() => {
    const m = new Map<string, string>();
    for (const s of sessions) {
      const t = s.providerFilterToken;
      if (t) {
        const label = s.providerModel?.split(" / ")[0]?.trim() || t;
        if (!m.has(t)) m.set(t, label);
      }
    }
    return Array.from(m.entries())
      .sort((a, b) => a[1].localeCompare(b[1], "ru"))
      .map(([value, label]) => ({ value, label }));
  }, [sessions]);

  const filtered = useMemo(() => {
    const now = Date.now();
    const windowMs = WINDOW_OPTIONS.find((x) => x.label === windowLabel)?.ms ?? WINDOW_OPTIONS[0].ms;
    const q = search.trim().toLowerCase();
    return sessions.filter((s) => {
      if (windowMs > 0 && now - s.lastAt > windowMs) return false;
      if (statusFilter !== "all" && normalizeStatusFilter(s.status) !== statusFilter) return false;
      if (providerFilter !== "all") {
        const tok = s.providerFilterToken || "";
        if (tok !== providerFilter) return false;
      }
      if (!q) return true;
      const assetHay = s.assetRefs.join(" ").toLowerCase();
      return (
        s.executionId.toLowerCase().includes(q) ||
        (s.originalUserPrompt || "").toLowerCase().includes(q) ||
        (s.textEnhancement?.text || "").toLowerCase().includes(q) ||
        (s.finalImagePrompt?.text || "").toLowerCase().includes(q) ||
        (s.providerModel || "").toLowerCase().includes(q) ||
        assetHay.includes(q) ||
        s.rows.some((r) => {
          const st = `${r.stage ?? ""}`.toLowerCase();
          const det = previewSummary(r.details).toLowerCase();
          return st.includes(q) || det.includes(q);
        })
      );
    });
  }, [providerFilter, search, sessions, statusFilter, windowLabel]);

  const totalPagesRaw = Math.ceil(filtered.length / PAGE_SIZE);
  const pageIndex = Math.min(currentPage, Math.max(0, totalPagesRaw - 1));
  const pageSessions = useMemo(
    () => filtered.slice(pageIndex * PAGE_SIZE, (pageIndex + 1) * PAGE_SIZE),
    [filtered, pageIndex]
  );
  const lastPageIndex = Math.max(0, totalPagesRaw - 1);

  useEffect(() => {
    setCurrentPage(0);
  }, [statusFilter, providerFilter, search, windowLabel]);

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

  const selected =
    pageSessions.find((s) => s.executionId === selectedId) ??
    filtered.find((s) => s.executionId === selectedId) ??
    null;

  useEffect(() => {
    setSelectedAssetIdx(0);
  }, [selectedId]);

  useEffect(() => {
    setImgFailed(false);
  }, [selectedId, selectedAssetIdx]);

  const safeAssetIdx =
    selected && selected.assetRefs.length > 0
      ? Math.min(Math.max(0, selectedAssetIdx), selected.assetRefs.length - 1)
      : 0;
  const activeAssetRef =
    selected && selected.assetRefs.length > 0 ? selected.assetRefs[safeAssetIdx] ?? null : null;
  const previewUrl = activeAssetRef ? getAssetPreviewUrl(activeAssetRef) : null;

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
    <div className="page logs-page image-page">
      <h1 className="page__title">Изображения</h1>
      <p className="page__lead rag-page__lead muted">
        Операционная консоль генерации изображений · <code>/api/logs/recent</code> · время: МСК
      </p>

      {loading ? (
        <LoadingState label="Загрузка image-сессий…" />
      ) : error ? (
        <div className="panel panel--error page__mt" role="alert">
          {error}
        </div>
      ) : sessions.length === 0 ? (
        <section className="card">
          <EmptyState message="В выборке нет сессий генерации изображений в логах." />
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
                  value={providerFilter}
                  onChange={(e) => setProviderFilter(e.target.value)}
                  aria-label="Провайдер"
                >
                  <option value="all">провайдер: все</option>
                  {providers.map((p) => (
                    <option key={p.value} value={p.value}>
                      {p.label}
                    </option>
                  ))}
                </select>
                <select
                  className="logs-select"
                  value={statusFilter}
                  onChange={(e) => setStatusFilter(e.target.value as StatusFilter)}
                  aria-label="Статус"
                >
                  <option value="all">статус: все</option>
                  <option value="success">успех</option>
                  <option value="error">ошибка</option>
                  <option value="other">прочие</option>
                </select>
              </div>
              <input
                className="logs-search"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="поиск prompt / execution / stage"
              />
              <div className="logs-filter-meta muted">
                Страница {filtered.length === 0 ? 0 : pageIndex + 1} из {totalPagesRaw || 0} · всего
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
                  disabled={pageIndex === 0}
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
                        IMAGE · {statusLabelRu(s.status).toUpperCase()}
                      </span>
                    </div>
                    <div className="logs-item__preview">{listPreviewLine(s)}</div>
                    <div className="logs-item__row logs-item__meta muted">
                      <span className="mono" title={s.executionId}>
                        {shortId(s.executionId)}
                      </span>
                      <span>assets: {s.assetRefs.length}</span>
                      <span title="Стена времени сессии">{formatDurationMs(s.wallDurationMs)}</span>
                      <span className="mono truncate" title={s.providerModel ?? ""}>
                        {s.providerModel ?? "—"}
                      </span>
                    </div>
                  </button>
                ))
              )}
            </div>
          </section>

          <section className="logs-right card">
            {!selected ? (
              <EmptyState message="Выберите image-сессию в списке слева." />
            ) : (
              <>
                <div className="logs-detail rag-modality-detail">
                  <div className="modality-card__head">
                    <h2 className="modality-card__title">СВОДКА IMAGE-СЕССИИ</h2>
                    <span
                      className={`modality-card__status status-badge status-badge--${imageTitleStatusTone(selected.status)}`}
                      title={selected.status}
                    >
                      {imageTitleStatusText(selected.status)}
                    </span>
                  </div>

                  <div className="modality-ops-panels modality-ops-panels--rag-split image-ops-summary">
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
                              hasNum(selected.processingLatencyMs) ? (
                                `${selected.processingLatencyMs} мс`
                              ) : (
                                <TelemetryGap kind="log" />
                              )
                            }
                          />
                          <OpsRow
                            label="Провайдер / модель"
                            value={
                              selected.providerModel?.trim() ? (
                                <span className="mono">{selected.providerModel}</span>
                              ) : (
                                <TelemetryGap kind="pipeline" />
                              )
                            }
                          />
                          <OpsRow
                            label="Входные токены"
                            value={
                              hasNum(selected.processingInputTokens) ? (
                                String(selected.processingInputTokens)
                              ) : (
                                <TelemetryGap kind="pipeline" />
                              )
                            }
                          />
                          <OpsRow
                            label="Выходные токены"
                            value={
                              hasNum(selected.processingOutputTokens) ? (
                                String(selected.processingOutputTokens)
                              ) : (
                                <TelemetryGap kind="pipeline" />
                              )
                            }
                          />
                          <OpsRow
                            label="Всего токенов"
                            value={
                              hasNum(selected.processingTotalTokens) ? (
                                String(selected.processingTotalTokens)
                              ) : (
                                <TelemetryGap kind="pipeline" />
                              )
                            }
                          />
                          <OpsRow
                            label="Ассетов"
                            value={
                              selected.assetRefs.length > 0 ? (
                                String(selected.assetRefs.length)
                              ) : (
                                <TelemetryGap kind="data" />
                              )
                            }
                          />
                        </dl>
                      </div>
                    </div>
                    <div className="modality-ops-panels__rag-col modality-ops-panels__rag-col--session">
                      <div className="modality-ops-panel">
                        <div className="modality-ops-panel__name">Image pipeline</div>
                        <dl className="kv modality-ops-panel__kv">
                          <OpsRow
                            label="Провайдер изображения"
                            value={
                              selected.imageGenProvider?.trim() ? (
                                <span className="mono">{selected.imageGenProvider}</span>
                              ) : (
                                <TelemetryGap kind="pipeline" />
                              )
                            }
                          />
                          <OpsRow
                            label="Модель изображения"
                            value={
                              selected.imageGenModel?.trim() ? (
                                <span className="mono">{selected.imageGenModel}</span>
                              ) : (
                                <TelemetryGap kind="pipeline" />
                              )
                            }
                          />
                          <OpsRow
                            label="Задержка генерации"
                            value={
                              hasNum(selected.imageGenDurationMs) ? (
                                `${selected.imageGenDurationMs} мс`
                              ) : (
                                <TelemetryGap kind="pipeline" />
                              )
                            }
                          />
                          <OpsRow
                            label="Общая задержка pipeline"
                            value={
                              hasNum(selected.processingLatencyMs) ? (
                                `${selected.processingLatencyMs} мс`
                              ) : (
                                <TelemetryGap kind="pipeline" />
                              )
                            }
                          />
                          <OpsRow
                            label="Сгенерировано файлов"
                            value={
                              generatedFileCount(selected) > 0 ? (
                                String(generatedFileCount(selected))
                              ) : (
                                <TelemetryGap kind="data" />
                              )
                            }
                          />
                          <OpsRow
                            label="Размер файла"
                            value={pipelineFileSizeDisplay(selected)}
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

                      <div className="image-prompt-chain-section">
                        <h4 className="image-prompt-chain__subtitle">Исходный запрос пользователя</h4>
                        <pre className="logs-pre logs-pre--compact mono">
                          {selected.originalUserPrompt?.trim()
                            ? clipText(selected.originalUserPrompt, INLINE_PROMPT_PREVIEW) ??
                              selected.originalUserPrompt
                            : selected.listPreviewFallback?.trim() ||
                              "Исходный запрос не найден в логах."}
                        </pre>
                      </div>

                      {selected.textEnhancement?.text?.trim() ? (
                        <div className="image-prompt-chain-section page__mt-sm">
                          <h4 className="image-prompt-chain__subtitle">Уточнённое описание</h4>
                          <p className="image-prompt-chain__meta muted mono">
                            {formatPromptStageMeta(selected.textEnhancement)}
                          </p>
                          <pre className="logs-pre logs-pre--compact mono">
                            {clipText(selected.textEnhancement.text, INLINE_PROMPT_PREVIEW) ??
                              selected.textEnhancement.text}
                          </pre>
                          <header className="rag-chunk-card__header audio-io-cta-head">
                            <div className="rag-chunk-card__meta-row">
                              <span className="muted mono">этап: image_text_enhancement_done</span>
                              <button
                                type="button"
                                className="rag-chunk-card__fulltext-cta"
                                onClick={() =>
                                  setFullTextModal({
                                    title: "Уточнённое описание (полный текст)",
                                    body: selected.textEnhancement?.text ?? "—",
                                  })
                                }
                              >
                                показать полный текст
                              </button>
                            </div>
                          </header>
                          {(selected.textEnhancement.text.length ?? 0) > INLINE_PROMPT_PREVIEW ? (
                            <details className="rag-diagnostics-fold page__mt-sm">
                              <summary className="rag-diagnostics-fold__summary">
                                Развёрнутый текст в панели
                              </summary>
                              <pre className="logs-pre logs-pre--compact mono page__mt-sm">
                                {selected.textEnhancement.text}
                              </pre>
                            </details>
                          ) : null}
                        </div>
                      ) : (
                        <p className="rag-io-foot muted page__mt-sm">
                          Уточнённое описание (image_text_enhancement_done) в логах отсутствует.
                        </p>
                      )}

                      {selected.finalImagePrompt?.text?.trim() ? (
                        <div className="image-prompt-chain-section page__mt-sm">
                          <h4 className="image-prompt-chain__subtitle">Финальный промпт генерации</h4>
                          <p className="image-prompt-chain__meta muted mono">
                            {formatPromptStageMeta(selected.finalImagePrompt)}
                          </p>
                          <pre className="logs-pre logs-pre--compact mono">
                            {clipText(selected.finalImagePrompt.text, INLINE_PROMPT_PREVIEW) ??
                              selected.finalImagePrompt.text}
                          </pre>
                          <header className="rag-chunk-card__header audio-io-cta-head">
                            <div className="rag-chunk-card__meta-row">
                              <span className="muted mono">этап: image_prompt_refinement_done</span>
                              <button
                                type="button"
                                className="rag-chunk-card__fulltext-cta"
                                onClick={() =>
                                  setFullTextModal({
                                    title: "Финальный промпт генерации (полный текст)",
                                    body: selected.finalImagePrompt?.text ?? "—",
                                  })
                                }
                              >
                                показать полный текст
                              </button>
                            </div>
                          </header>
                          {(selected.finalImagePrompt.text.length ?? 0) > INLINE_PROMPT_PREVIEW ? (
                            <details className="rag-diagnostics-fold page__mt-sm">
                              <summary className="rag-diagnostics-fold__summary">
                                Развёрнутый текст в панели
                              </summary>
                              <pre className="logs-pre logs-pre--compact mono page__mt-sm">
                                {selected.finalImagePrompt.text}
                              </pre>
                            </details>
                          ) : null}
                        </div>
                      ) : (
                        <p className="rag-io-foot muted page__mt-sm">
                          Финальный промпт (image_prompt_refinement_done) в логах отсутствует.
                        </p>
                      )}
                    </div>

                    <div className="logs-detail-block">
                      <h3 className="logs-detail-block__title">ЧТО ОТВЕТИЛА СИСТЕМА</h3>
                      {selected.assetRefs.length > 1 ? (
                        <div className="image-asset-switcher" role="tablist" aria-label="Варианты изображения">
                          {selected.assetRefs.map((ref, idx) => (
                            <button
                              key={`${ref}-${idx}`}
                              type="button"
                              role="tab"
                              className={`logs-chip ${safeAssetIdx === idx ? "logs-chip--active" : ""}`}
                              onClick={() => setSelectedAssetIdx(idx)}
                            >
                              <span className="mono">#{idx + 1}</span>
                              <span className="image-asset-switcher__thumb-wrap">
                                <img
                                  src={getAssetPreviewUrl(ref)}
                                  alt=""
                                  className="image-asset-switcher__thumb"
                                  loading="lazy"
                                />
                              </span>
                            </button>
                          ))}
                        </div>
                      ) : null}

                      <div className="image-ops-preview-card">
                        {!previewUrl ? (
                          <div className="panel panel--muted">
                            Нет сохранённых изображений: в логах нет <span className="mono">asset_ref</span>
                            .
                          </div>
                        ) : imgFailed ? (
                          <div className="panel panel--muted">Не удалось загрузить превью изображения.</div>
                        ) : (
                          <div className="image-preview-wrap image-preview-wrap--ops">
                            <img
                              src={previewUrl}
                              alt="Результат генерации"
                              className="image-preview"
                              onError={() => setImgFailed(true)}
                            />
                          </div>
                        )}
                        <dl className="kv modality-ops-panel__kv image-ops-preview-meta">
                          {renderActiveAssetMetaRows(selected, safeAssetIdx, activeAssetRef)}
                        </dl>
                      </div>
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
                      Технический JSON snapshot · {selected.rows.length} строк
                    </summary>
                    <pre className="log-details__json mono logs-raw-session__body">
                      {JSON.stringify(selected.rows, null, 2)}
                    </pre>
                  </details>
                </div>

                {typeof document !== "undefined" && fullTextModal
                  ? createPortal(
                      <PromptFullTextModal {...fullTextModal} onClose={() => setFullTextModal(null)} />,
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

function formatPromptStageMeta(s: ImagePromptChainStage): string {
  const parts: string[] = [];
  const pm = [s.provider?.trim(), s.model?.trim()].filter(Boolean).join(" / ");
  if (pm) parts.push(pm);
  const tok: string[] = [];
  if (hasNum(s.inputTokens)) tok.push(`вход ${s.inputTokens}`);
  if (hasNum(s.outputTokens)) tok.push(`выход ${s.outputTokens}`);
  if (hasNum(s.totalTokens)) tok.push(`всего ${s.totalTokens}`);
  if (tok.length) parts.push(tok.join(" · "));
  if (hasNum(s.latencyMs)) parts.push(`${s.latencyMs} мс`);
  return parts.join(" · ") || "—";
}

function formatBytesDetailed(n: number): string {
  if (!Number.isFinite(n) || n < 0) return "—";
  const units = ["B", "KB", "MB", "GB"];
  let v = n;
  let i = 0;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i++;
  }
  const human = i === 0 ? `${Math.round(v)} ${units[i]}` : `${v.toFixed(i === 1 ? 1 : 2)} ${units[i]}`;
  return `${human} (${Math.round(n)} B)`;
}

function pmLine(p: string | null | undefined, m: string | null | undefined): string | null {
  const pp = p?.trim();
  const mm = m?.trim();
  if (!pp && !mm) return null;
  return `${pp || "—"} / ${mm || "—"}`;
}

function generatedFileCount(s: ImageSession): number {
  if (s.assetRefs.length > 0) return s.assetRefs.length;
  const nonEmpty = s.outputImageMeta.filter(
    (x) => x.assetRef || x.filename || x.sizeBytes != null
  );
  return nonEmpty.length;
}

function pickPrimaryOutputFileSizeBytes(s: ImageSession): number | null {
  for (const m of s.outputImageMeta) {
    if (m.sizeBytes != null && Number.isFinite(m.sizeBytes)) return m.sizeBytes;
  }
  return null;
}

function pipelineFileSizeDisplay(s: ImageSession): ReactNode {
  const sz = pickPrimaryOutputFileSizeBytes(s);
  if (sz == null) return <TelemetryGap kind="data" />;
  return <span className="mono">{formatBytesDetailed(sz)}</span>;
}

function resolveAssetMeta(
  s: ImageSession,
  assetIdx: number,
  activeRef: string | null
): OutputImageMeta {
  const byIdx = s.outputImageMeta[assetIdx];
  if (activeRef) {
    const byRef = s.outputImageMeta.find((m) => m.assetRef === activeRef);
    if (byRef) return byRef;
  }
  return (
    byIdx ?? {
      assetRef: activeRef,
      filename: null,
      sizeBytes: null,
      provider: null,
      model: null,
    }
  );
}

function renderActiveAssetMetaRows(
  selected: ImageSession,
  assetIdx: number,
  activeAssetRef: string | null
): ReactNode {
  const meta = resolveAssetMeta(selected, assetIdx, activeAssetRef);
  const count = generatedFileCount(selected);
  const pm = pmLine(meta.provider ?? selected.imageGenProvider, meta.model ?? selected.imageGenModel);
  return (
    <>
      <OpsRow
        label="asset_ref"
        value={
          activeAssetRef ? (
            <span className="mono break-all">{activeAssetRef}</span>
          ) : (
            <TelemetryGap kind="data" />
          )
        }
      />
      <OpsRow
        label="filename"
        value={
          meta.filename?.trim() ? (
            <span className="mono break-all">{meta.filename}</span>
          ) : (
            <TelemetryGap kind="data" />
          )
        }
      />
      <OpsRow
        label="размер файла"
        value={
          meta.sizeBytes != null && Number.isFinite(meta.sizeBytes) ? (
            <span className="mono">{formatBytesDetailed(meta.sizeBytes)}</span>
          ) : (
            <TelemetryGap kind="data" />
          )
        }
      />
      <OpsRow
        label="provider / model"
        value={pm ? <span className="mono">{pm}</span> : <TelemetryGap kind="data" />}
      />
      <OpsRow
        label="сгенерировано"
        value={count > 0 ? String(count) : <TelemetryGap kind="data" />}
      />
    </>
  );
}

function PromptFullTextModal({
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
        aria-labelledby="image-prompt-modal-title"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="rag-chunk-modal__head">
          <h2 id="image-prompt-modal-title" className="rag-chunk-modal__title">
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

function imageTitleStatusTone(status: string): "ok" | "warn" | "err" | "muted" {
  const n = status.trim().toLowerCase();
  if (n === "success") return "ok";
  if (n === "error" || n === "failed" || n.includes("fail")) return "err";
  if (n === "warning" || n === "degraded" || n === "skipped") return "warn";
  return "muted";
}

function imageTitleStatusText(status: string): string {
  const n = status.trim().toLowerCase();
  if (n === "success") return "УСПЕХ";
  if (n === "error" || n === "failed") return "ОШИБКА";
  return statusLabelRu(status).toUpperCase();
}

function hasNum(n: number | null | undefined): boolean {
  return n != null && Number.isFinite(n);
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

function listPreviewLine(s: ImageSession): string {
  const p = s.originalUserPrompt?.trim();
  if (p) return clipText(p, 200) ?? p;
  const fb = s.listPreviewFallback?.trim();
  if (fb) return clipText(fb, 200) ?? fb;
  const tail = s.rows[s.rows.length - 1];
  return clipText(tail ? previewSummary(tail.details) : "—", 120) ?? "—";
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

function refsFromOutputImagesBlock(d: Record<string, unknown>): string[] {
  const raw = d.output_images;
  if (!Array.isArray(raw)) return [];
  const out: string[] = [];
  for (const item of raw) {
    if (!item || typeof item !== "object") continue;
    const o = item as Record<string, unknown>;
    const ar = o.asset_ref ?? o.assetRef;
    if (typeof ar === "string" && ar.trim()) out.push(ar.trim());
  }
  return out;
}

function mergeAssetRefLists(primary: string[], secondary: string[]): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const t of [...primary, ...secondary]) {
    if (seen.has(t)) continue;
    seen.add(t);
    out.push(t);
  }
  return out;
}

function collectAssetRefs(detailsPool: Record<string, unknown>[]): string[] {
  const keys = [
    "asset_ref",
    "image_asset_ref",
    "generated_asset_ref",
    "output_image_asset_ref",
    "persisted_asset_ref",
  ];
  const seen = new Set<string>();
  const out: string[] = [];
  for (const d of detailsPool) {
    for (const ref of refsFromOutputImagesBlock(d)) {
      if (!seen.has(ref)) {
        seen.add(ref);
        out.push(ref);
      }
    }
    for (const key of keys) {
      const v = d[key];
      if (typeof v === "string" && v.trim()) {
        const t = v.trim();
        if (!seen.has(t)) {
          seen.add(t);
          out.push(t);
        }
      }
    }
    const nested = ["image", "output", "generated_image"] as const;
    for (const nk of nested) {
      const nest = asRecord(d[nk]);
      if (!nest) continue;
      const ar = nest.asset_ref;
      if (typeof ar === "string" && ar.trim()) {
        const t = ar.trim();
        if (!seen.has(t)) {
          seen.add(t);
          out.push(t);
        }
      }
    }
    const rawArr = d.image_assets ?? d.generated_assets ?? d.assets;
    if (Array.isArray(rawArr)) {
      for (const item of rawArr) {
        if (typeof item === "string" && item.trim()) {
          const t = item.trim();
          if (!seen.has(t)) {
            seen.add(t);
            out.push(t);
          }
        } else if (item && typeof item === "object") {
          const o = item as Record<string, unknown>;
          const ar = o.asset_ref ?? o.ref;
          if (typeof ar === "string" && ar.trim()) {
            const t = ar.trim();
            if (!seen.has(t)) {
              seen.add(t);
              out.push(t);
            }
          }
        }
      }
    }
  }
  return out;
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

function extractOriginalUserPrompt(ordered: LogItem[]): string | null {
  for (const row of ordered) {
    if (String(row.stage || "").toLowerCase() !== "intake_received") continue;
    const d = asRecord(row.details);
    if (!d) continue;
    const u = strField(d, ["user_text"]);
    if (u) return u;
    const q = strField(d, ["query_preview"]);
    if (q) return q;
  }
  for (const row of ordered) {
    const d = asRecord(row.details);
    if (!d) continue;
    const u = strField(d, ["user_text"]);
    if (u) return u;
  }
  for (const row of ordered) {
    const d = asRecord(row.details);
    if (!d) continue;
    const q = strField(d, ["query_preview"]);
    if (q) return q;
  }
  return null;
}

function extractTextEnhancementStage(ordered: LogItem[]): ImagePromptChainStage | null {
  const d = findLatestDetailsByStage(ordered, "image_text_enhancement_done");
  if (!d) return null;
  const text = strField(d, ["enhanced_prompt"]);
  if (!text?.trim()) return null;
  return {
    text,
    provider: strField(d, ["provider"]),
    model: strField(d, ["model"]),
    inputTokens: numField(d, ["input_tokens"]),
    outputTokens: numField(d, ["output_tokens"]),
    totalTokens: numField(d, ["total_tokens"]),
    latencyMs: numField(d, ["enhancement_latency_ms"]),
  };
}

function extractFinalImagePromptStage(ordered: LogItem[]): ImagePromptChainStage | null {
  const stageNames = ["image_prompt_refinement_done", "image_prompt_enhanced"];
  for (const sn of stageNames) {
    const d = findLatestDetailsByStage(ordered, sn);
    if (!d) continue;
    const text = strField(d, ["image_prompt"]) ?? strField(d, ["rewritten_prompt"]);
    if (!text?.trim()) continue;
    return {
      text,
      provider: strField(d, ["provider"]),
      model: strField(d, ["model"]),
      inputTokens: numField(d, ["input_tokens"]),
      outputTokens: numField(d, ["output_tokens"]),
      totalTokens: numField(d, ["total_tokens"]),
      latencyMs: numField(d, ["refinement_latency_ms", "latency_ms"]),
    };
  }
  return null;
}

function extractProcessingDoneMetrics(ordered: LogItem[]): {
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

function extractImageProviderDone(ordered: LogItem[]): {
  provider: string | null;
  model: string | null;
  durationMs: number | null;
} {
  const d = findLatestDetailsByStage(ordered, "image_provider_done");
  if (!d) return { provider: null, model: null, durationMs: null };
  return {
    provider: strField(d, ["provider", "image_provider"]),
    model: strField(d, ["model", "image_model"]),
    durationMs: numField(d, ["duration_ms", "latency_ms", "elapsed_ms"]),
  };
}

function extractOutputImagesMeta(ordered: LogItem[]): OutputImageMeta[] {
  const d = findLatestDetailsByStage(ordered, "image_provider_done");
  if (!d) return [];
  const arr = d.output_images;
  if (!Array.isArray(arr)) return [];
  return arr.map((item) => {
    const o = item && typeof item === "object" ? (item as Record<string, unknown>) : {};
    return {
      assetRef:
        typeof o.asset_ref === "string"
          ? o.asset_ref.trim() || null
          : typeof o.assetRef === "string"
            ? o.assetRef.trim() || null
            : null,
      filename: strField(o, ["filename", "name"]),
      sizeBytes: numField(o, ["size", "size_bytes", "file_size"]),
      provider: strField(o, ["provider"]),
      model: strField(o, ["model"]),
    };
  });
}

function buildListPreviewFallback(
  original: string | null,
  finalP: ImagePromptChainStage | null,
  enh: ImagePromptChainStage | null,
  ordered: LogItem[]
): string | null {
  if (original?.trim()) return null;
  const t = finalP?.text?.trim() || enh?.text?.trim();
  if (t) return t;
  const tail = ordered[ordered.length - 1];
  return tail ? previewSummary(tail.details) : null;
}

function pickPipelineError(ordered: LogItem[]): string | null {
  for (let i = ordered.length - 1; i >= 0; i--) {
    const row = ordered[i];
    const st = String(row.status || "").toLowerCase();
    if (row.error_text?.trim()) return row.error_text.trim();
    if (st === "error") {
      const d = asRecord(row.details);
      const msg =
        d && strField(d, ["error", "error_message", "message", "fallback_reason", "reason"]);
      if (msg) return msg;
    }
  }
  return null;
}

function buildImageSessions(rows: LogItem[]): ImageSession[] {
  const imageExecIds = new Set<string>();
  for (const row of rows) {
    if (!isImageEvent(row)) continue;
    const id = String(row.execution_id || "").trim();
    if (id) imageExecIds.add(id);
  }
  const grouped = new Map<string, LogItem[]>();
  for (const row of rows) {
    const id = String(row.execution_id || "").trim();
    if (!id) continue;
    if (!imageExecIds.has(id)) continue;
    const bucket = grouped.get(id) ?? [];
    bucket.push(row);
    grouped.set(id, bucket);
  }
  const out: ImageSession[] = [];
  for (const [executionId, chunk] of grouped) {
    const ordered = [...chunk].sort((a, b) => (toTs(a.created_at) ?? 0) - (toTs(b.created_at) ?? 0));
    const detailsPool = ordered
      .map((r) => asRecord(r.details))
      .filter((d): d is Record<string, unknown> => d !== null);
    const latest = ordered[ordered.length - 1];
    const first = ordered[0];
    const providerDone = findLatestDetailsByStage(ordered, "image_provider_done");
    const refsFromProvider = providerDone ? refsFromOutputImagesBlock(providerDone) : [];
    const assetRefs = mergeAssetRefLists(refsFromProvider, collectAssetRefs(detailsPool));

    const originalUserPrompt = extractOriginalUserPrompt(ordered);
    const textEnhancement = extractTextEnhancementStage(ordered);
    const finalImagePrompt = extractFinalImagePromptStage(ordered);
    const proc = extractProcessingDoneMetrics(ordered);
    const imgDone = extractImageProviderDone(ordered);
    const outputImageMeta = extractOutputImagesMeta(ordered);

    const providerLine =
      imgDone.provider || imgDone.model
        ? `${imgDone.provider?.trim() || "—"} / ${imgDone.model?.trim() || "—"}`
        : null;
    const providerFilterToken = imgDone.provider?.trim().toLowerCase() || null;

    const tsList = ordered
      .map((r) => toTs(r.created_at))
      .filter((t): t is number => t != null);
    const wallDurationMs = sessionWallDurationMs(tsList);

    const pipelineSummary = ordered
      .map((r) => stageToActionRu(r.stage, r.details))
      .join(" → ");

    out.push({
      executionId,
      rows: ordered,
      startedAt: toTs(first.created_at) ?? 0,
      lastAt: toTs(latest.created_at) ?? 0,
      status: String(latest.status || "—"),
      originalUserPrompt,
      textEnhancement,
      finalImagePrompt,
      listPreviewFallback: buildListPreviewFallback(
        originalUserPrompt,
        finalImagePrompt,
        textEnhancement,
        ordered
      ),
      providerModel: providerLine,
      providerFilterToken,
      processingLatencyMs: proc.latencyMs != null ? Math.round(proc.latencyMs) : null,
      wallDurationMs,
      processingInputTokens:
        proc.inputTokens != null && Number.isFinite(proc.inputTokens)
          ? Math.round(proc.inputTokens)
          : null,
      processingOutputTokens:
        proc.outputTokens != null && Number.isFinite(proc.outputTokens)
          ? Math.round(proc.outputTokens)
          : null,
      processingTotalTokens:
        proc.totalTokens != null && Number.isFinite(proc.totalTokens)
          ? Math.round(proc.totalTokens)
          : null,
      assetRefs,
      outputImageMeta,
      pipelineSummary,
      imageGenProvider: imgDone.provider,
      imageGenModel: imgDone.model,
      imageGenDurationMs:
        imgDone.durationMs != null && Number.isFinite(imgDone.durationMs)
          ? Math.round(imgDone.durationMs)
          : null,
      pipelineError: pickPipelineError(ordered),
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
  if (stage === "processing_done") {
    const r = String(d?.route || row.route || "").toLowerCase();
    if (r === "image" || r === "image_generation") return true;
  }
  return (
    stage === "image_generation_started" ||
    stage === "image_generation_done" ||
    stage === "image_generation_error" ||
    stage === "image_prompt_enhanced" ||
    stage === "image_prompt_refinement_done" ||
    stage === "image_text_enhancement_done" ||
    stage === "image_provider_done" ||
    stage === "image_assets_persisted"
  );
}
