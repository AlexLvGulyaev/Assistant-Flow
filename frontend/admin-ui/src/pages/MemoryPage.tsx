import { useCallback, useEffect, useState } from "react";
import {
  fetchMemoryObservabilitySummary,
  fetchMemorySessionDetail,
  fetchMemorySessionsList,
  type MemoryObservabilitySummary,
  type MemorySessionDetailResponse,
  type MemorySessionListItem,
  type MemorySessionsListResponse,
} from "../api/client";
import { EmptyState } from "../components/EmptyState";
import { LoadingState } from "../components/LoadingState";
import { OperationalRefreshButton } from "../components/OperationalRefreshButton";
import { SectionCard } from "../components/SectionCard";
import { StatusBadge } from "../components/StatusBadge";

function shortId(id: string | undefined, n = 8): string {
  if (!id) return "—";
  return id.length <= n ? id : `${id.slice(0, n)}…`;
}

function sourceLabel(src: string | undefined): string {
  if (src === "pg") return "PostgreSQL";
  if (src === "fallback_in_memory") return "in-memory fallback";
  return src || "—";
}

function formatMemoryLifecycleDetails(details: unknown): string {
  if (!details || typeof details !== "object" || Array.isArray(details)) return "";
  const d = details as Record<string, unknown>;
  const keys = [
    "session_id",
    "user_id",
    "telegram_user_id",
    "messages_loaded",
    "messages_saved",
    "limit",
    "latency_ms",
    "command",
    "status",
  ];
  const parts: string[] = [];
  for (const k of keys) {
    if (d[k] == null || d[k] === "") continue;
    let v = String(d[k]);
    if ((k === "session_id" || k === "user_id") && v.length > 13) {
      v = `${v.slice(0, 8)}…`;
    }
    parts.push(`${k}=${v}`);
  }
  const joined = parts.join(" · ");
  return joined.length <= 200 ? joined : `${joined.slice(0, 197)}…`;
}

export function MemoryPage() {
  const [hours] = useState(24);
  const [summary, setSummary] = useState<MemoryObservabilitySummary | null>(null);
  const [list, setList] = useState<MemorySessionsListResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshNonce, setRefreshNonce] = useState(0);
  const [activeOnly, setActiveOnly] = useState(false);
  const [detailId, setDetailId] = useState<string | null>(null);
  const [detail, setDetail] = useState<MemorySessionDetailResponse | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [s, l] = await Promise.all([
        fetchMemoryObservabilitySummary(hours),
        fetchMemorySessionsList({ activeOnly, limit: 80, offset: 0 }),
      ]);
      setSummary(s);
      setList(l);
    } catch (e) {
      setSummary(null);
      setList(null);
      setError(e instanceof Error ? e.message : "Ошибка загрузки");
    } finally {
      setLoading(false);
    }
  }, [hours, activeOnly, refreshNonce]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!detailId) {
      setDetail(null);
      return;
    }
    let cancelled = false;
    setDetailLoading(true);
    setDetailError(null);
    void fetchMemorySessionDetail(detailId)
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
  }, [detailId]);

  const head = (
    <div className="page__head memory-console-page">
      <h1 className="page__title">Memory / Sessions</h1>
      <p className="page__subtitle muted">
        Operational conversational state — не чат, не дашборд плитками; только
        метаданные и усечённые превью реплик.
      </p>
    </div>
  );

  if (loading && !summary && !list) {
    return (
      <div className="page memory-console-page">
        {head}
        <LoadingState label="Загрузка memory observability…" />
      </div>
    );
  }

  const src = summary?.memory_runtime_source ?? list?.memory_runtime_source;
  const bl = summary?.budget_limits;

  return (
    <div className="page memory-console-page">
      {head}

      {error ? (
        <div className="logs-page-error" role="alert">
          {error}
        </div>
      ) : null}

      <div className="page__toolbar">
        <OperationalRefreshButton
          onClick={() => setRefreshNonce((n) => n + 1)}
          loading={loading}
        />
        <label className="memory-console-filter">
          <input
            type="checkbox"
            checked={activeOnly}
            onChange={(e) => setActiveOnly(e.target.checked)}
          />{" "}
          только активные сессии
        </label>
      </div>

      <SectionCard
        title="Summary / health"
        description="Источник runtime-контекста Telegram RAG и лимиты budget (конфиг)."
      >
        <div className="memory-top-strip">
          <div className="memory-metric">
            <div className="muted" style={{ fontSize: "0.72rem" }}>
              PG memory (конфиг)
            </div>
            <div>
              <StatusBadge
                status={
                  summary?.telegram_pg_conversation_memory ? "on" : "off"
                }
              />
            </div>
          </div>
          <div className="memory-metric">
            <div className="muted" style={{ fontSize: "0.72rem" }}>
              Runtime source
            </div>
            <strong>{sourceLabel(src)}</strong>
          </div>
          <div className="memory-metric">
            <div className="muted" style={{ fontSize: "0.72rem" }}>
              БД доступна
            </div>
            <StatusBadge
              status={summary?.database_available ? "yes" : "no"}
            />
          </div>
          <div className="memory-metric">
            <div className="muted" style={{ fontSize: "0.72rem" }}>
              Активных сессий
            </div>
            <strong>{summary?.active_sessions_count ?? "—"}</strong>
          </div>
          <div className="memory-metric">
            <div className="muted" style={{ fontSize: "0.72rem" }}>
              Avg turns (сессии с активностью)
            </div>
            <strong>{summary?.avg_turns_sessions_touched ?? "—"}</strong>
          </div>
          <div className="memory-metric">
            <div className="muted" style={{ fontSize: "0.72rem" }}>
              Clear/reset (логи, {summary?.hours ?? hours}h)
            </div>
            <strong>{summary?.clear_reset_events_count ?? 0}</strong>
          </div>
        </div>
        <p className="muted" style={{ marginTop: "0.5rem", fontSize: "0.78rem" }}>
          Memory: лимит пар <code>{bl?.max_turn_pairs ?? "—"}</code>, max LLM
          сообщений <code>{bl?.max_llm_messages ?? "—"}</code>
          {summary?.llm_conversation_tail_cap != null ? (
            <>
              {" "}
              · RAG LLM history tail: последние{" "}
              <code>{summary.llm_conversation_tail_cap}</code> сообщений (совпадает с
              Telegram PG load cap)
            </>
          ) : null}
          {summary?.chat_session_idle_timeout_seconds ? (
            <>
              {" "}
              · idle timeout (config):{" "}
              <code>{summary.chat_session_idle_timeout_seconds}s</code>
            </>
          ) : null}
        </p>
      </SectionCard>

      <SectionCard
        title="Sessions"
        description="Компактный список chat_sessions + счётчик сообщений. Источник =
        конфигурация runtime (см. summary), не построчный трейс per-request без
        логов."
      >
        {!list?.items?.length ? (
          <EmptyState
            title="Нет сессий"
            message="При пустой БД или отсутствии пользователей список пуст."
          />
        ) : (
          <div className="memory-table-wrap">
            <table className="memory-table">
              <thead>
                <tr>
                  <th>session</th>
                  <th>user</th>
                  <th>mode</th>
                  <th>active</th>
                  <th>updated</th>
                  <th>msgs</th>
                  <th>turns~</th>
                  <th>source</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {list.items.map((row: MemorySessionListItem) => (
                  <tr key={row.session_id}>
                    <td>
                      <code title={row.session_id}>
                        {shortId(row.session_id, 10)}
                      </code>
                    </td>
                    <td className="memory-cell-user" title={row.user_label}>
                      {row.user_label}
                    </td>
                    <td>{row.mode}</td>
                    <td>{row.is_active ? "yes" : "no"}</td>
                    <td className="muted" style={{ fontSize: "0.75rem" }}>
                      {row.updated_at
                        ? row.updated_at.slice(0, 19).replace("T", " ")
                        : "—"}
                    </td>
                    <td>{row.messages_count ?? 0}</td>
                    <td>{row.turns_approx ?? 0}</td>
                    <td>{sourceLabel(row.memory_source)}</td>
                    <td>
                      {row.recent_clear_badge ? (
                        <span className="memory-badge-clear">clear</span>
                      ) : null}
                      <button
                        type="button"
                        className="logs-page-btn logs-page-btn--muted"
                        style={{ marginLeft: "0.35rem" }}
                        onClick={() => setDetailId(row.session_id ?? null)}
                      >
                        Inspect
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </SectionCard>

      {detailId ? (
        <div
          className="memory-modal-backdrop"
          role="presentation"
          onClick={() => setDetailId(null)}
        >
          <div
            className="memory-modal"
            role="dialog"
            aria-modal
            aria-labelledby="memory-modal-title"
            onClick={(e) => e.stopPropagation()}
          >
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                marginBottom: "0.75rem",
              }}
            >
              <h2 id="memory-modal-title" className="card__title" style={{ margin: 0 }}>
                Session {shortId(detailId, 12)}
              </h2>
              <button
                type="button"
                className="logs-page-btn"
                onClick={() => setDetailId(null)}
              >
                Закрыть
              </button>
            </div>
            {detailLoading ? <LoadingState label="Деталь…" /> : null}
            {detailError ? (
              <div className="logs-page-error">{detailError}</div>
            ) : null}
            {detail && !detailLoading ? (
              <div className="memory-detail-body">
                <p className="muted" style={{ fontSize: "0.8rem" }}>
                  tg: <code>{detail.telegram_user_id}</code> · user_id:{" "}
                  <code>{shortId(detail.user_id, 12)}</code> · mode{" "}
                  <strong>{detail.mode}</strong>
                </p>
                {detail.budget ? (
                  <div className="memory-metric" style={{ marginBottom: "0.75rem" }}>
                    <div className="muted" style={{ fontSize: "0.72rem" }}>
                      Budget / last load
                    </div>
                    <div style={{ fontSize: "0.85rem" }}>
                      <strong>
                        {detail.budget.last_load_messages_loaded ?? "—"}
                      </strong>{" "}
                      / {detail.budget.dialog_messages_in_session ?? 0} dialog msgs
                      in session · limit pairs{" "}
                      <code>{String(detail.budget.last_load_limit_pairs ?? "—")}</code>{" "}
                      · trimmed:{" "}
                      <strong>{detail.budget.trimmed ? "yes" : "no"}</strong> ·
                      caps:{" "}
                      <code>{detail.budget.max_turn_pairs}</code> pairs /{" "}
                      <code>{detail.budget.max_llm_messages}</code> msgs
                      {detail.budget.llm_conversation_tail_cap != null ? (
                        <>
                          {" "}
                          · RAG LLM tail cap:{" "}
                          <code>{detail.budget.llm_conversation_tail_cap}</code>
                        </>
                      ) : null}
                    </div>
                  </div>
                ) : null}
                <h3 className="card__title" style={{ fontSize: "0.95rem" }}>
                  Recent clean turns (preview)
                </h3>
                <ul className="memory-turn-list">
                  {(detail.recent_turns ?? []).map((t, i) => (
                    <li key={`${t.role}-${i}`}>
                      <span className="muted">{t.role}</span>: {t.preview}
                    </li>
                  ))}
                </ul>
                <h3 className="card__title" style={{ fontSize: "0.95rem", marginTop: "1rem" }}>
                  Lifecycle (memory_*)
                </h3>
                <ul className="memory-lifecycle-list">
                  {(detail.memory_lifecycle_recent ?? []).map((ev, i) => (
                    <li key={`${ev.stage}-${i}`}>
                      <code>{String(ev.stage)}</code>{" "}
                      <span className="muted">
                        {String(ev.created_at ?? "").slice(0, 19)}
                      </span>{" "}
                      — {String(ev.status)}{" "}
                      {ev.details && Object.keys(ev.details as object).length ? (
                        <span className="memory-lifecycle-inline muted">
                          {formatMemoryLifecycleDetails(ev.details)}
                        </span>
                      ) : null}
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
          </div>
        </div>
      ) : null}
    </div>
  );
}
