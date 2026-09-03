import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  fetchAuditRecent,
  fetchAuditSummary,
  type AuditEventItem,
  type AuditSummaryResponse,
} from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { PERM } from "../auth/permissions";
import { LoadingState } from "../components/LoadingState";
import { OperationalRefreshButton } from "../components/OperationalRefreshButton";
import { OperationalSessionEmptyHint } from "../components/OperationalSessionEmptyHint";
import { SecurityScenarioDetail } from "../components/SecurityScenarioDetail";
import {
  auditEventToScenario,
  CATEGORY_OPTIONS,
  filterScenarios,
  listIntentTitle,
  listMetaLine,
  listResultCompact,
  SEVERITY_OPTIONS,
  type ScenarioCategory,
  type SecuritySeverity,
} from "../utils/securityScenarios";
import { formatTimestampMsk } from "../utils/operationalLabels";

const WINDOW_OPTIONS = [
  { label: "24ч", hours: 24 },
  { label: "48ч", hours: 48 },
  { label: "7д", hours: 24 * 7 },
];

const PAGE_SIZE = 12;

export function AuditPage() {
  const { hasPermission } = useAuth();
  const canRead = hasPermission(PERM.auditRead);
  const [items, setItems] = useState<AuditEventItem[]>([]);
  const [summary, setSummary] = useState<AuditSummaryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [currentPage, setCurrentPage] = useState(0);
  const [windowLabel, setWindowLabel] = useState("48ч");
  const [search, setSearch] = useState("");
  const [categoryFilter, setCategoryFilter] = useState<ScenarioCategory | "all">("all");
  const [severityFilter, setSeverityFilter] = useState<SecuritySeverity | "all">("all");
  const [statusFilter, setStatusFilter] = useState<"all" | "success" | "failure">("all");
  const [refreshNonce, setRefreshNonce] = useState(0);
  const listRef = useRef<HTMLDivElement | null>(null);

  const sinceHours =
    WINDOW_OPTIONS.find((w) => w.label === windowLabel)?.hours ?? 48;

  const load = useCallback(async () => {
    if (!canRead) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const [recent, sum] = await Promise.all([
        fetchAuditRecent({
          limit: 120,
          status: statusFilter === "all" ? undefined : statusFilter,
          since_hours: sinceHours,
        }),
        fetchAuditSummary(24),
      ]);
      setItems(recent.items);
      setSummary(sum);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Ошибка загрузки аудита");
    } finally {
      setLoading(false);
    }
  }, [canRead, sinceHours, statusFilter, refreshNonce]);

  useEffect(() => {
    void load();
  }, [load]);

  const filtered = useMemo(
    () =>
      filterScenarios(items, {
        search,
        category: categoryFilter,
        severity: severityFilter,
        status: statusFilter === "all" ? "" : statusFilter,
      }),
    [items, search, categoryFilter, severityFilter, statusFilter]
  );

  const totalPagesRaw = Math.ceil(filtered.length / PAGE_SIZE);
  const pageIndex = Math.min(currentPage, Math.max(0, totalPagesRaw - 1));
  const pageItems = useMemo(
    () => filtered.slice(pageIndex * PAGE_SIZE, (pageIndex + 1) * PAGE_SIZE),
    [filtered, pageIndex]
  );
  const lastPageIndex = Math.max(0, totalPagesRaw - 1);

  useEffect(() => {
    setCurrentPage(0);
  }, [search, categoryFilter, severityFilter, statusFilter, windowLabel]);

  useEffect(() => {
    if (currentPage !== pageIndex) {
      setCurrentPage(pageIndex);
    }
  }, [currentPage, pageIndex]);

  useEffect(() => {
    if (!filtered.length) {
      setSelectedId(null);
      return;
    }
    if (!selectedId || !filtered.some((it) => it.id === selectedId)) {
      setSelectedId(filtered[0].id);
      return;
    }
    if (!pageItems.some((it) => it.id === selectedId)) {
      const idx = filtered.findIndex((it) => it.id === selectedId);
      if (idx >= 0) {
        setCurrentPage(Math.floor(idx / PAGE_SIZE));
      } else {
        setSelectedId(pageItems[0]?.id ?? filtered[0].id);
      }
    }
  }, [filtered, pageItems, selectedId]);

  const selected =
    pageItems.find((it) => it.id === selectedId) ??
    filtered.find((it) => it.id === selectedId) ??
    null;

  function goPrevPage() {
    const np = Math.max(0, pageIndex - 1);
    setCurrentPage(np);
    const slice = filtered.slice(np * PAGE_SIZE, (np + 1) * PAGE_SIZE);
    const pick = slice[slice.length - 1] ?? slice[0];
    if (pick) setSelectedId(pick.id);
  }

  function goNextPage() {
    const np = Math.min(lastPageIndex, pageIndex + 1);
    setCurrentPage(np);
    const slice = filtered.slice(np * PAGE_SIZE, (np + 1) * PAGE_SIZE);
    if (slice[0]) setSelectedId(slice[0].id);
  }

  function resetPagination() {
    setCurrentPage(0);
    const first = filtered[0];
    if (first) setSelectedId(first.id);
  }

  if (!canRead) {
    return (
      <div className="page logs-page security-console-page">
        <h1 className="page__title">Журнал аудита</h1>
        <p className="muted">
          Нет права <code>audit:read</code>. Доступно ролям auditor и admin.
        </p>
      </div>
    );
  }

  const summaryLine = summary
    ? `24ч: ${summary.total} событий · auth ${summary.auth_events} · security ${summary.security_events}`
    : null;

  return (
    <div className="page logs-page security-console-page">
      <h1 className="page__title">Журнал аудита</h1>
      <p className="page__lead rag-page__lead muted">
        Операционная консоль security-сценариев · <code>/api/security/audit/*</code> · время: МСК
      </p>

      {error ? (
        <div className="panel panel--error page__mt" role="alert">
          {error}
        </div>
      ) : (
        <div className="logs-console">
          <section className="logs-left card">
            <div className="logs-filters">
              <div className="logs-filter-row logs-filter-row--security">
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
                  value={categoryFilter}
                  onChange={(e) =>
                    setCategoryFilter(e.target.value as ScenarioCategory | "all")
                  }
                  aria-label="Категория"
                >
                  {CATEGORY_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                </select>
                <select
                  className="logs-select"
                  value={severityFilter}
                  onChange={(e) =>
                    setSeverityFilter(e.target.value as SecuritySeverity | "all")
                  }
                  aria-label="Severity"
                >
                  {SEVERITY_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                </select>
                <select
                  className="logs-select"
                  value={statusFilter}
                  onChange={(e) =>
                    setStatusFilter(e.target.value as "all" | "success" | "failure")
                  }
                  aria-label="Статус"
                >
                  <option value="all">все статусы</option>
                  <option value="success">success</option>
                  <option value="failure">failure</option>
                </select>
              </div>
              <input
                className="logs-search"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Поиск: актор, сценарий, permission, event_type, путь…"
              />
              <div className="logs-filter-meta logs-filter-meta--with-refresh muted">
                <span>
                  {summaryLine ? `${summaryLine} · ` : ""}
                  Страница {filtered.length === 0 ? 0 : pageIndex + 1} из {totalPagesRaw || 0}{" "}
                  · сценариев: {filtered.length} · показано: {pageItems.length}
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
                <LoadingState label="Загрузка security scenarios…" />
              ) : items.length === 0 ? (
                <OperationalSessionEmptyHint
                  title="Нет audit events за период."
                  hint="Выполните login или privileged action; проверьте миграцию 008."
                />
              ) : filtered.length === 0 ? (
                <div className="panel panel--muted">Нет сценариев по фильтрам.</div>
              ) : (
                pageItems.map((it) => {
                  const sc = auditEventToScenario(it, items);
                  return (
                    <button
                      key={it.id}
                      type="button"
                      className={`logs-item ${selectedId === it.id ? "logs-item--selected" : ""}`}
                      onClick={() => setSelectedId(it.id)}
                    >
                      <div className="logs-item__row logs-item__row--tight security-list-head">
                        <span className="mono logs-item__ts">
                          {formatTimestampMsk(it.created_at)}
                        </span>
                        <span className="mini-badge mini-badge--af mini-badge--af-sec">sec</span>
                        <span className="security-list-short-result">
                          {listResultCompact(it, sc)}
                        </span>
                      </div>
                      <div className="logs-item__preview security-list-intent">
                        {listIntentTitle(it, sc)}
                      </div>
                      <div className="logs-item__row logs-item__meta muted security-list-meta">
                        <span className="truncate">{listMetaLine(it, sc)}</span>
                      </div>
                    </button>
                  );
                })
              )}
            </div>
          </section>

          <section className="logs-right card">
            {selected ? (
              <SecurityScenarioDetail item={selected} allItems={items} />
            ) : (
              <div className="panel panel--muted security-detail-empty">
                Нет сценариев для отображения.
              </div>
            )}
          </section>
        </div>
      )}
    </div>
  );
}
