import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type ChangeEvent,
  type KeyboardEvent as ReactKeyboardEvent,
  type ReactNode,
} from "react";
import {
  fetchDocumentDetail,
  fetchDocuments,
  postDocumentsReindex,
  uploadDocument,
  type DocumentDetailResponse,
  type DocumentsResponse,
} from "../api/client";
import { EmptyState } from "../components/EmptyState";
import { LoadingState } from "../components/LoadingState";
import { OperationalSessionEmptyHint } from "../components/OperationalSessionEmptyHint";
import { SessionJsonSnapshot } from "../components/SessionJsonSnapshot";
import { StatusBadge } from "../components/StatusBadge";
import {
  formatDurationMs,
  formatShortDateMsk,
  formatTimestampMsk,
  stageToActionRu,
} from "../utils/operationalLabels";

const PAGE_SIZE = 10;
const DOC_FETCH_LIMIT = 400;

function DocFieldRow({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <div className="docs-field-inline" title={label}>
      <span className="docs-field-inline__label">{label}:</span>
      <span className="docs-field-inline__value">{children}</span>
    </div>
  );
}

export function DocumentsPage() {
  const [data, setData] = useState<DocumentsResponse | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selectedVersionNumber, setSelectedVersionNumber] = useState<number | null>(
    null
  );
  const [statusFilter, setStatusFilter] = useState("all");
  const [extFilter, setExtFilter] = useState("all");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [currentPage, setCurrentPage] = useState(0);
  const listRef = useRef<HTMLDivElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const pendingListFocusRef = useRef(false);

  const [detail, setDetail] = useState<DocumentDetailResponse | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  const [uploadBusy, setUploadBusy] = useState(false);
  const [uploadHint, setUploadHint] = useState<string | null>(null);
  const [reindexDocBusy, setReindexDocBusy] = useState(false);
  const [reindexAllBusy, setReindexAllBusy] = useState(false);
  const [actionHint, setActionHint] = useState<string | null>(null);
  const [summaryPopOpen, setSummaryPopOpen] = useState(false);
  const [indexPopOpen, setIndexPopOpen] = useState(false);
  const summaryPopRef = useRef<HTMLDivElement | null>(null);
  const indexPopRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const res = await fetchDocuments(DOC_FETCH_LIMIT);
        if (!cancelled) setData(res);
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : "Не удалось загрузить документы");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [refreshKey]);

  const items = data?.items ?? [];
  const gis = data?.global_index_sync;
  const lastFullReindex = data?.observability?.last_reindex_event;
  const embeddingModel = (data?.embedding_model || "").trim() || null;
  const providerHint = embeddingModel ? `OpenAI · ${embeddingModel}` : null;

  const extensions = useMemo(
    () => Array.from(new Set(items.map((d) => d.extension || "—"))).sort(),
    [items]
  );

  const summary = useMemo(() => {
    let indexed = 0;
    let errors = 0;
    let versions = 0;
    let chunks = 0;
    let lastIndexedMs = 0;
    for (const d of items) {
      if (d.status === "indexed") indexed++;
      if (d.status === "error") errors++;
      versions += d.versions_count ?? 0;
      chunks += d.chunk_count ?? 0;
      if (d.last_indexed_at) {
        const ms = new Date(d.last_indexed_at).getTime();
        if (Number.isFinite(ms) && ms > lastIndexedMs) lastIndexedMs = ms;
      }
    }
    return {
      total: items.length,
      indexed,
      errors,
      versions,
      chunks,
      lastIndexedLabel:
        lastIndexedMs > 0 ? formatTimestampMsk(lastIndexedMs) : "—",
    };
  }, [items]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return items.filter((d) => {
      if (statusFilter !== "all" && d.status !== statusFilter) return false;
      if (extFilter !== "all" && d.extension !== extFilter) return false;
      if (!q) return true;
      const hay = [
        d.filename,
        d.extension,
        d.status,
        d.status_raw,
        String(d.chunk_count ?? ""),
        String(d.active_version ?? ""),
      ]
        .join(" ")
        .toLowerCase();
      return hay.includes(q);
    });
  }, [extFilter, items, search, statusFilter]);

  const totalPagesRaw = Math.ceil(filtered.length / PAGE_SIZE);
  const pageIndex = Math.min(currentPage, Math.max(0, totalPagesRaw - 1));
  const pageDocs = useMemo(
    () => filtered.slice(pageIndex * PAGE_SIZE, (pageIndex + 1) * PAGE_SIZE),
    [filtered, pageIndex]
  );
  const lastPageIndex = Math.max(0, totalPagesRaw - 1);

  const selected =
    pageDocs.find((d) => d.document_id === selectedId) ??
    filtered.find((d) => d.document_id === selectedId) ??
    null;

  const timelineWithDelta = useMemo(() => {
    const raw = detail?.timeline ?? [];
    const sorted = [...raw].sort(
      (a, b) =>
        new Date(a.created_at || 0).getTime() -
        new Date(b.created_at || 0).getTime()
    );
    return sorted.map((ev, i) => {
      let deltaMs: number | null = null;
      if (i > 0) {
        const t0 = new Date(sorted[i - 1].created_at || 0).getTime();
        const t1 = new Date(ev.created_at || 0).getTime();
        if (Number.isFinite(t0) && Number.isFinite(t1)) deltaMs = Math.max(0, t1 - t0);
      }
      return { ev, deltaMs };
    });
  }, [detail?.timeline]);

  useEffect(() => {
    setCurrentPage(0);
  }, [statusFilter, extFilter, search]);

  useEffect(() => {
    if (currentPage !== pageIndex) setCurrentPage(pageIndex);
  }, [currentPage, pageIndex]);

  useEffect(() => {
    setSelectedVersionNumber(null);
  }, [selectedId]);

  useEffect(() => {
    if (!pageDocs.length) {
      setSelectedId(null);
      return;
    }
    if (!selectedId || !filtered.some((d) => d.document_id === selectedId)) {
      setSelectedId(pageDocs[0].document_id);
      return;
    }
    if (!pageDocs.some((d) => d.document_id === selectedId)) {
      const idx = filtered.findIndex((d) => d.document_id === selectedId);
      if (idx >= 0) {
        setCurrentPage(Math.floor(idx / PAGE_SIZE));
        return;
      }
      setSelectedId(pageDocs[0].document_id);
    }
  }, [filtered, pageDocs, selectedId]);

  useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      setDetailError(null);
      return;
    }
    let cancelled = false;
    (async () => {
      setDetailLoading(true);
      setDetailError(null);
      try {
        const d = await fetchDocumentDetail(
          selectedId,
          selectedVersionNumber ?? undefined
        );
        if (!cancelled) setDetail(d);
      } catch (e) {
        if (!cancelled) {
          setDetail(null);
          setDetailError(e instanceof Error ? e.message : "Ошибка загрузки деталей");
        }
      } finally {
        if (!cancelled) setDetailLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [selectedId, selectedVersionNumber]);

  useEffect(() => {
    if (!selectedId) return;
    const list = listRef.current;
    if (!list) return;
    const safeId =
      typeof CSS !== "undefined" && typeof CSS.escape === "function"
        ? CSS.escape(selectedId)
        : selectedId.replace(/"/g, '\\"');
    const row = list.querySelector<HTMLButtonElement>(
      `[data-doc-id="${safeId}"]`
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
        ? filtered.findIndex((d) => d.document_id === selectedId)
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
      setSelectedId(next.document_id);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [filtered, selectedId, pageIndex]);

  useEffect(() => {
    if (!summaryPopOpen && !indexPopOpen) return;
    const onDocMouseDown = (e: MouseEvent) => {
      const t = e.target as Node;
      if (summaryPopOpen && summaryPopRef.current && !summaryPopRef.current.contains(t)) {
        setSummaryPopOpen(false);
      }
      if (indexPopOpen && indexPopRef.current && !indexPopRef.current.contains(t)) {
        setIndexPopOpen(false);
      }
    };
    document.addEventListener("mousedown", onDocMouseDown);
    return () => document.removeEventListener("mousedown", onDocMouseDown);
  }, [summaryPopOpen, indexPopOpen]);

  function resetPagination() {
    pendingListFocusRef.current = true;
    setCurrentPage(0);
    const first = filtered.slice(0, PAGE_SIZE)[0];
    if (first) setSelectedId(first.document_id);
  }

  function goPrevPage() {
    pendingListFocusRef.current = true;
    const np = Math.max(0, pageIndex - 1);
    setCurrentPage(np);
    const slice = filtered.slice(np * PAGE_SIZE, (np + 1) * PAGE_SIZE);
    const pick = slice[slice.length - 1] ?? slice[0];
    if (pick) setSelectedId(pick.document_id);
  }

  function goNextPage() {
    pendingListFocusRef.current = true;
    const np = Math.min(lastPageIndex, pageIndex + 1);
    setCurrentPage(np);
    const slice = filtered.slice(np * PAGE_SIZE, (np + 1) * PAGE_SIZE);
    if (slice[0]) setSelectedId(slice[0].document_id);
  }

  async function onRefresh() {
    setRefreshKey((k) => k + 1);
    setActionHint(null);
  }

  async function onPickUpload() {
    fileInputRef.current?.click();
  }

  async function onFileChange(e: ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    e.target.value = "";
    if (!f) return;
    setUploadBusy(true);
    setUploadHint("Загрузка…");
    try {
      const r = await uploadDocument(f);
      if (r.success) {
        setUploadHint(
          r.chunks != null
            ? `Загружено, индексация завершена · чанков: ${r.chunks}`
            : "Загружено"
        );
        setRefreshKey((k) => k + 1);
        if (r.document_id) {
          setSelectedId(r.document_id);
          setCurrentPage(0);
        }
      } else {
        setUploadHint(r.error || "Ошибка индексации");
      }
    } catch (err) {
      setUploadHint(err instanceof Error ? err.message : "Ошибка загрузки");
    } finally {
      setUploadBusy(false);
    }
  }

  async function onReindexDocument() {
    if (!selectedId) return;
    setReindexDocBusy(true);
    setActionHint(null);
    try {
      const r = await postDocumentsReindex({
        scope: "document",
        document_id: selectedId,
      });
      if (r.success) {
        setActionHint(
          r.chunks != null
            ? `Документ переиндексирован · чанков: ${r.chunks}`
            : "Переиндексация документа завершена"
        );
      } else {
        setActionHint(r.error || "Ошибка переиндексации документа");
      }
      setRefreshKey((k) => k + 1);
    } catch (err) {
      setActionHint(err instanceof Error ? err.message : "Ошибка");
    } finally {
      setReindexDocBusy(false);
    }
  }

  async function onReindexAll() {
    setReindexAllBusy(true);
    setActionHint(null);
    try {
      const r = await postDocumentsReindex({ scope: "all" });
      if (r.success) {
        setActionHint(
          `Полная переиндексация завершена · файлов: ${r.files_indexed_ok ?? "—"} / ${r.files_found ?? "—"}`
        );
      } else {
        setActionHint(r.error || "Ошибка полной переиндексации");
      }
      setRefreshKey((k) => k + 1);
    } catch (err) {
      setActionHint(err instanceof Error ? err.message : "Ошибка");
    } finally {
      setReindexAllBusy(false);
    }
  }

  const docStatusRaw = String(detail?.document?.status ?? selected?.status_raw ?? "");

  return (
    <div className="page logs-page docs-page docs-page-viewport">
      <header className="docs-page-header-row">
        <h1 className="docs-page-header-row__title">Документы</h1>
        <span className="docs-page-header-row__meta muted">
          <code>/api/documents</code> · МСК
        </span>
      </header>

      <div className="docs-toolbar card">
        <div className="docs-toolbar__actions" role="toolbar" aria-label="Операции с базой знаний">
          <input
            ref={fileInputRef}
            type="file"
            accept=".txt,text/plain"
            className="docs-file-input"
            aria-hidden
            onChange={onFileChange}
          />
          <button
            type="button"
            className="docs-action-btn docs-action-btn--primary"
            onClick={onPickUpload}
            disabled={uploadBusy}
          >
            {uploadBusy ? "⏳ Загрузка…" : "⬆ Загрузить файл"}
          </button>
          <button
            type="button"
            className="docs-action-btn docs-action-btn--secondary"
            onClick={onReindexDocument}
            disabled={!selectedId || reindexDocBusy || reindexAllBusy}
          >
            {reindexDocBusy ? "⏳ Переиндексация…" : "↻ Переиндексировать документ"}
          </button>
          <button
            type="button"
            className="docs-action-btn docs-action-btn--caution"
            onClick={onReindexAll}
            disabled={reindexAllBusy || reindexDocBusy}
          >
            {reindexAllBusy ? "⏳ Переиндексация…" : "⚠ Переиндексировать всё"}
          </button>
          <button
            type="button"
            className="docs-action-btn docs-action-btn--ghost"
            onClick={onRefresh}
            disabled={loading}
            aria-busy={loading || undefined}
          >
            {loading ? "Обновление…" : "Обновить"}
          </button>
          {!loading && !error ? (
            <>
              <div className="docs-toolbar__pop-anchor" ref={summaryPopRef}>
                <button
                  type="button"
                  className={`docs-action-btn docs-action-btn--ghost ${summaryPopOpen ? "docs-action-btn--pressed" : ""}`}
                  aria-expanded={summaryPopOpen}
                  onClick={() => {
                    setIndexPopOpen(false);
                    setSummaryPopOpen((v) => !v);
                  }}
                >
                  Сводка
                </button>
                {summaryPopOpen ? (
                  <div className="docs-toolbar__pop" role="dialog" aria-label="Сводка каталога">
                    <DocFieldRow label="Всего документов">
                      <span className="mono">{summary.total}</span>
                    </DocFieldRow>
                    <DocFieldRow label="Проиндексировано">
                      <span className="mono">{summary.indexed}</span>
                    </DocFieldRow>
                    <DocFieldRow label="Ошибки">
                      <span className="mono">{summary.errors}</span>
                    </DocFieldRow>
                    <DocFieldRow label="Версий (сумма)">
                      <span className="mono">{summary.versions}</span>
                    </DocFieldRow>
                    <DocFieldRow label="Чанков (сумма)">
                      <span className="mono">{summary.chunks}</span>
                    </DocFieldRow>
                    <DocFieldRow label="Последняя индексация">
                      <span className="mono">{summary.lastIndexedLabel}</span>
                    </DocFieldRow>
                    <DocFieldRow label="Embeddings">
                      <span className="mono">{providerHint ?? "—"}</span>
                    </DocFieldRow>
                  </div>
                ) : null}
              </div>
              <div className="docs-toolbar__pop-anchor" ref={indexPopRef}>
                <button
                  type="button"
                  className={`docs-action-btn docs-action-btn--ghost ${indexPopOpen ? "docs-action-btn--pressed" : ""}`}
                  aria-expanded={indexPopOpen}
                  onClick={() => {
                    setSummaryPopOpen(false);
                    setIndexPopOpen((v) => !v);
                  }}
                >
                  Статус индекса
                </button>
                {indexPopOpen ? (
                  <div className="docs-toolbar__pop" role="dialog" aria-label="Глобальный статус индекса">
                    <DocFieldRow label="Векторов в Chroma">
                      <span className="mono">{gis?.chroma_collection_chunks ?? "—"}</span>
                    </DocFieldRow>
                    <DocFieldRow label="Σ chunk_count (активные версии)">
                      <span className="mono">
                        {gis?.postgres_chunks_sum_active_versions ?? "—"}
                      </span>
                    </DocFieldRow>
                    <DocFieldRow label="Согласованность">
                      {gis?.global_chunks_mismatch ? (
                        <span className="docs-warn">расхождение</span>
                      ) : (
                        <StatusBadge status="ok" />
                      )}
                    </DocFieldRow>
                    <DocFieldRow label="Полная переиндексация">
                      <span className="mono">
                        {lastFullReindex?.stage
                          ? `${stageToActionRu(lastFullReindex.stage, lastFullReindex.details)} · `
                          : ""}
                        {formatTimestampMsk(lastFullReindex?.created_at ?? null)}
                      </span>
                    </DocFieldRow>
                  </div>
                ) : null}
              </div>
            </>
          ) : null}
        </div>
        {(uploadHint || actionHint) ? (
          <p className="docs-toolbar__hint docs-toolbar__hint--one-line muted" title={`${uploadHint ?? ""} ${actionHint ?? ""}`.trim()}>
            {uploadHint ? <span>{uploadHint}</span> : null}
            {uploadHint && actionHint ? <span> · </span> : null}
            {actionHint ? <span>{actionHint}</span> : null}
          </p>
        ) : null}
      </div>

      <div className="docs-main-split">
      {error ? (
        <div className="docs-split-fill-center">
          <div className="panel panel--error" role="alert">
            {error}
          </div>
        </div>
      ) : (
        <div className="logs-console docs-console docs-console--fill">
          <section className="logs-left card docs-left--fill">
            <div className="logs-filters docs-filters">
              <div className="logs-filter-row docs-filter-row">
                <select
                  className="logs-select"
                  value={statusFilter}
                  onChange={(e) => setStatusFilter(e.target.value)}
                  aria-label="Фильтр статуса"
                >
                  <option value="all">все статусы</option>
                  <option value="indexed">проиндексирован</option>
                  <option value="pending">ожидание</option>
                  <option value="error">ошибка</option>
                  <option value="missing">нет в индексе</option>
                  <option value="unsupported">не поддерживается</option>
                  <option value="stale">устарело</option>
                </select>
                <select
                  className="logs-select"
                  value={extFilter}
                  onChange={(e) => setExtFilter(e.target.value)}
                  aria-label="Тип файла"
                >
                  <option value="all">все типы</option>
                  {extensions.map((ex) => (
                    <option key={ex} value={ex}>
                      {ex}
                    </option>
                  ))}
                </select>
              </div>
              <input
                className="logs-search"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Поиск: имя файла, статус, версия…"
              />
              <div className="logs-filter-meta muted">
                Страница {filtered.length === 0 ? 0 : pageIndex + 1} из{" "}
                {totalPagesRaw || 0} · всего документов: {filtered.length} · показано:{" "}
                {items.length === 0 ? 0 : pageDocs.length}
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
                    extFilter === "all"
                  }
                >
                  Сброс
                </button>
              </div>
            </div>

            <div className="logs-list" ref={listRef}>
              {loading && items.length === 0 ? (
                <LoadingState label="Загрузка документов…" />
              ) : items.length === 0 ? (
                <OperationalSessionEmptyHint
                  title="Документы не найдены."
                  hint="Загрузите документ или обновите список."
                />
              ) : filtered.length === 0 ? (
                <div className="panel panel--muted">Нет документов по фильтрам.</div>
              ) : (
                pageDocs.map((d) => (
                  <button
                    key={d.document_id}
                    type="button"
                    data-doc-id={d.document_id}
                    className={`logs-item ${selectedId === d.document_id ? "logs-item--selected" : ""}`}
                    onClick={() => {
                      pendingListFocusRef.current = true;
                      setSelectedId(d.document_id);
                    }}
                  >
                    <div className="logs-item__row logs-item__row--tight">
                      <span className="mono logs-item__ts">
                        {formatTimestampMsk(d.last_indexed_at)}
                      </span>
                      <span className="logs-item__route-status">
                        {String(d.status || "").toUpperCase()} · v
                        {d.active_version ?? "—"} · чанков {d.chunk_count ?? 0}
                      </span>
                    </div>
                    <div className="logs-item__preview">{d.filename || "—"}</div>
                    <div className="logs-item__row logs-item__meta muted">
                      <span className="mono truncate" title={d.document_id}>
                        {shortId(d.document_id)}
                      </span>
                      {d.status === "error" ? (
                        <span className="docs-card-err">сбой индексации</span>
                      ) : null}
                      {providerHint ? (
                        <span className="mono truncate" title={providerHint}>
                          {providerHint}
                        </span>
                      ) : (
                        <span>embeddings: —</span>
                      )}
                    </div>
                  </button>
                ))
              )}
            </div>
          </section>

          <div className="docs-right-split">
            {!selected ? (
              <div className="docs-detail-placeholder docs-right-split--full card">
                <EmptyState message="Выберите документ в списке слева." />
              </div>
            ) : detailLoading ? (
              <div className="docs-detail-placeholder docs-right-split--full card">
                <LoadingState label="Загрузка карточки документа…" />
              </div>
            ) : detailError ? (
              <div className="docs-detail-placeholder docs-right-split--full card">
                <div className="panel panel--error" role="alert">
                  {detailError}
                </div>
              </div>
            ) : detail ? (
              <>
                <section className="docs-panel-document card">
                  <header className="docs-panel-document__header">
                    <h2 className="docs-panel-document__title">СВОДКА ДОКУМЕНТА</h2>
                    <StatusBadge status={String(selected.status || "—")} />
                  </header>
                  <div className="docs-panel-document__summary">
                    {selected.status === "error" || detail.last_error_message ? (
                      <div className="docs-alert docs-alert--err docs-alert--compact">
                        <strong>Ошибка</strong>
                        {detail.last_error_message ? (
                          <div className="mono docs-alert__msg">{detail.last_error_message}</div>
                        ) : null}
                      </div>
                    ) : null}
                    <div className="docs-ver-table-wrap docs-ver-table-wrap--panel">
                      <table className="docs-ver-table">
                        <thead>
                          <tr>
                            <th scope="col">Версия</th>
                            <th scope="col">Статус</th>
                            <th scope="col" className="docs-ver-table__num">
                              Чанки
                            </th>
                            <th scope="col">Дата</th>
                          </tr>
                        </thead>
                        <tbody>
                          {(detail.versions ?? []).map((v) => {
                            const vn = v.version_number ?? 0;
                            const active = !!v.is_active;
                            const sel = detail.selected_version?.version_number === vn;
                            let stLabel = "архивная";
                            let stClass = "docs-ver-pill docs-ver-pill--arch";
                            if (active) {
                              if (docStatusRaw === "failed") {
                                stLabel = "ACTIVE·сбой";
                                stClass = "docs-ver-pill docs-ver-pill--warn";
                              } else {
                                stLabel = "ACTIVE";
                                stClass = "docs-ver-pill docs-ver-pill--act";
                              }
                            }
                            return (
                              <tr
                                key={`${v.version_id}-${vn}`}
                                className={sel ? "docs-ver-tr docs-ver-tr--selected" : "docs-ver-tr"}
                                tabIndex={0}
                                onClick={() => setSelectedVersionNumber(vn)}
                                onKeyDown={(e: ReactKeyboardEvent) => {
                                  if (e.key === "Enter" || e.key === " ") {
                                    e.preventDefault();
                                    setSelectedVersionNumber(vn);
                                  }
                                }}
                              >
                                <td className="mono">v{vn}</td>
                                <td>
                                  <span className={stClass}>{stLabel}</span>
                                </td>
                                <td className="docs-ver-table__num mono">{v.chunk_count ?? 0}</td>
                                <td className="mono muted">{formatShortDateMsk(v.indexed_at ?? null)}</td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                    <div className="docs-op-grid docs-op-grid--summary docs-op-grid--panel">
                      <DocFieldRow label="Файл">
                        <span className="mono" title={String(selected.filename)}>
                          {String(selected.filename)}
                        </span>
                      </DocFieldRow>
                      <DocFieldRow label="Статус PostgreSQL">
                        <StatusBadge status={docStatusRaw || "—"} />
                      </DocFieldRow>
                      <DocFieldRow label="Активная версия">
                        <span className="mono">v{detail.active_version?.version_number ?? "—"}</span>
                      </DocFieldRow>
                      <DocFieldRow label="Выбранная версия">
                        <span className="mono">v{detail.selected_version?.version_number ?? "—"}</span>
                      </DocFieldRow>
                      <DocFieldRow label="Чанков в версии">
                        <span className="mono">{detail.chunk_count_declared ?? 0}</span>
                      </DocFieldRow>
                      <DocFieldRow label="Найдено в БД">
                        <span className="mono">{detail.chunks_in_db ?? 0}</span>
                      </DocFieldRow>
                      <DocFieldRow label="Provider / model">
                        <span className="mono" title={detail.embedding_model ?? undefined}>
                          {detail.embedding_model
                            ? `OpenAI · ${detail.embedding_model}`
                            : "—"}
                        </span>
                      </DocFieldRow>
                      <DocFieldRow label="Последняя индексация">
                        <span className="mono">
                          {formatTimestampMsk(
                            detail.selected_version?.indexed_at ??
                              detail.active_version?.indexed_at ??
                              null
                          )}
                        </span>
                      </DocFieldRow>
                      <DocFieldRow label="sha256">
                        <span
                          className="mono"
                          title={String(detail.selected_version?.file_hash ?? "")}
                        >
                          {detail.selected_version?.file_hash
                            ? shortHash(String(detail.selected_version.file_hash))
                            : "—"}
                        </span>
                      </DocFieldRow>
                    </div>
                    <p
                      className={`docs-sync-oneline mono docs-sync-oneline--panel ${detail.chunks_sync_ok ? "docs-sync-oneline--ok" : "docs-sync-oneline--warn"}`}
                      title={
                        detail.selected_version_id
                          ? `version_id=${detail.selected_version_id}`
                          : undefined
                      }
                    >
                      Синхрон чанков:{" "}
                      {detail.chunks_sync_ok ? (
                        <strong>OK</strong>
                      ) : (
                        <strong>расхождение</strong>
                      )}{" "}
                      · заявлено {detail.chunk_count_declared ?? 0} / БД {detail.chunks_in_db ?? 0}
                      {!detail.chunks_sync_ok ? " · ↻ переиндексировать в шапке" : ""}
                    </p>
                  </div>
                  <div className="docs-panel-document__body">
                    <div className="docs-panel-document__body-stack">
                      <div className="docs-panel-block docs-panel-block--preview">
                        <div className="docs-zone-title">Предпросмотр</div>
                        <div className="docs-panel-block__scroll docs-panel-block__scroll--tall">
                          {detail.preview_available && detail.text_preview ? (
                            <pre className="docs-preview-body mono">{detail.text_preview}</pre>
                          ) : (
                            <p className="muted docs-preview-panel__empty">
                              Нет предпросмотра (.txt / .md) или файл не на диске.
                            </p>
                          )}
                        </div>
                      </div>
                      <div className="docs-panel-block docs-panel-block--chunks">
                        <div className="docs-zone-title">Чанки выбранной версии</div>
                        <div className="docs-panel-block__scroll docs-panel-block__scroll--tall docs-chunks-scroll">
                          {(detail.chunks ?? []).length === 0 ? (
                            <div className="docs-chunk-empty">
                              <p className="muted">Нет строк document_chunks для выбранной версии.</p>
                              {(detail.chunk_count_declared ?? 0) > 0 ? (
                                <p className="docs-chunk-diag mono">
                                  Заявлено {detail.chunk_count_declared}, в БД{" "}
                                  {detail.chunks_in_db ?? 0}.{" "}
                                  doc_id=
                                  {String(
                                    (detail.document as { document_id?: string } | undefined)
                                      ?.document_id ?? selected.document_id
                                  )}{" "}
                                  ver={detail.selected_version_id ?? "—"}.
                                </p>
                              ) : null}
                              {detail.chunks_sync_diagnostic ? (
                                <pre className="docs-chunk-diag-pre mono">
                                  {detail.chunks_sync_diagnostic}
                                </pre>
                              ) : null}
                            </div>
                          ) : (
                            <div className="docs-chunk-list docs-chunk-list--in-grid">
                              {(detail.chunks ?? []).map((c, idx) => {
                                const text = c.chunk_text_preview || "";
                                const chromaShort =
                                  c.chroma_id && c.chroma_id.length > 12
                                    ? `${c.chroma_id.slice(0, 8)}…`
                                    : c.chroma_id || null;
                                return (
                                  <div key={`${c.chunk_index}-${idx}`} className="docs-chunk-card">
                                    <div className="docs-chunk-card__head">
                                      <span className="mono">#{c.chunk_index ?? idx}</span>
                                      <span className="muted">
                                        {text.length} симв.
                                        {c.token_count != null ? ` · ${c.token_count} ток.` : ""}
                                      </span>
                                      <span className="mono muted" title={c.chroma_id ?? undefined}>
                                        {chromaShort
                                          ? `Chroma: ${chromaShort} (в коллекции)`
                                          : "Chroma: нет id"}
                                      </span>
                                    </div>
                                    <div className="docs-chunk-card__body docs-chunk-card__body--scroll">
                                      {text || "—"}
                                    </div>
                                  </div>
                                );
                              })}
                            </div>
                          )}
                        </div>
                      </div>
                      <SessionJsonSnapshot
                        className="session-json-snapshot--in-body"
                        body={formatJson({
                          document: detail.document,
                          versions: detail.versions,
                          active_version: detail.active_version,
                          selected_version: detail.selected_version,
                          selected_version_id: detail.selected_version_id,
                          chunk_counts_by_version: detail.chunk_counts_by_version,
                          chunks_sync_diagnostic: detail.chunks_sync_diagnostic,
                          chunks_sample: (detail.chunks ?? []).slice(0, 5),
                          timeline: detail.timeline,
                        })}
                      />
                    </div>
                  </div>
                </section>
                <section className="docs-panel-lifecycle card">
                  <h2 className="docs-panel-lifecycle__title">ЖИЗНЕННЫЙ ЦИКЛ</h2>
                  <div className="docs-panel-lifecycle__scroll logs-timeline docs-timeline">
                    {timelineWithDelta.length === 0 ? (
                      <p className="muted">Событий нет.</p>
                    ) : (
                      timelineWithDelta.map(({ ev, deltaMs }, i) => (
                        <div
                          key={`${ev.stage}-${ev.created_at}-${i}`}
                          className="logs-stage logs-stage--compact docs-lifecycle-stage"
                        >
                          <div className="logs-stage__top">
                            <span className="mono logs-stage__time">
                              {formatTimestampMsk(ev.created_at)}
                            </span>
                            <StatusBadge status={String(ev.status || "—")} />
                            <span className="muted mono">Δ {formatDurationMs(deltaMs)}</span>
                          </div>
                          <div className="logs-stage__label">
                            {stageToActionRu(ev.stage, ev.details)}
                          </div>
                          {ev.error_text ? (
                            <div className="logs-stage__details mono">{ev.error_text}</div>
                          ) : null}
                          <SessionJsonSnapshot
                            className="session-json-snapshot--timeline"
                            body={formatJson(ev.details)}
                          />
                        </div>
                      ))
                    )}
                  </div>
                </section>
              </>
            ) : null}
          </div>
        </div>
      )}
      </div>
    </div>
  );
}

function shortId(id: string): string {
  const s = id.replace(/-/g, "");
  return s.length > 10 ? `${s.slice(0, 8)}…` : id;
}

function shortHash(h: string): string {
  return h.length > 14 ? `${h.slice(0, 12)}…` : h;
}

function formatJson(value: unknown): string {
  if (value == null) return "null";
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}
