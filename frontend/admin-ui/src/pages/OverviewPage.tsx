import { Fragment, useEffect, useState } from "react";
import {
  fetchDocuments,
  fetchHealth,
  fetchOverview,
  fetchSummary,
  type DocumentsResponse,
  type HealthResponse,
  type OverviewResponse,
  type RetrievalPlatformCompact,
  type SummaryResponse,
} from "../api/client";
import { EmptyState } from "../components/EmptyState";
import { LoadingState } from "../components/LoadingState";
import { OperationalRefreshButton } from "../components/OperationalRefreshButton";
import { OperationalSessionEmptyHint } from "../components/OperationalSessionEmptyHint";
import { SectionCard } from "../components/SectionCard";
import { StatusBadge } from "../components/StatusBadge";
import { formatRetrievalBackendTitle, retrievalReadinessForStatusBadge } from "../utils/operationalLabels";

const READINESS_KEYS: { key: string; label: string }[] = [
  { key: "database_url_configured", label: "DATABASE_URL" },
  { key: "openai_configured", label: "OpenAI" },
  { key: "proxy_configured", label: "Proxy" },
  { key: "gigachat_configured", label: "GigaChat" },
  { key: "audio_enabled", label: "Аудио" },
  { key: "chroma_use_http", label: "Chroma HTTP" },
];

/** Окно для блока «AI-активность» (данные /api/summary?hours=…). */
const OVERVIEW_SUMMARY_WINDOWS: Array<{ label: string; hours: number }> = [
  { label: "24h", hours: 24 },
  { label: "48h", hours: 48 },
  { label: "7d", hours: 168 },
];

export function OverviewPage() {
  const [data, setData] = useState<OverviewResponse | null>(null);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [summary, setSummary] = useState<SummaryResponse | null>(null);
  const [docs, setDocs] = useState<DocumentsResponse | null>(null);
  const [healthWarn, setHealthWarn] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshNonce, setRefreshNonce] = useState(0);
  const [summaryWindowLabel, setSummaryWindowLabel] = useState("24h");
  const summaryHours =
    OVERVIEW_SUMMARY_WINDOWS.find((w) => w.label === summaryWindowLabel)?.hours ?? 24;

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      setHealthWarn(null);
      try {
        const [oRes, hRes, sRes, dRes] = await Promise.allSettled([
          fetchOverview(),
          fetchHealth(),
          fetchSummary(summaryHours),
          fetchDocuments(200),
        ]);
        if (cancelled) return;
        if (oRes.status === "rejected") {
          setData(null);
          setError(
            oRes.reason instanceof Error
              ? oRes.reason.message
              : "Не удалось загрузить обзор"
          );
        } else {
          setData(oRes.value);
        }
        if (hRes.status === "rejected") {
          setHealth(null);
          setHealthWarn(
            hRes.reason instanceof Error
              ? hRes.reason.message
              : "Не удалось загрузить live-проверки"
          );
        } else {
          setHealth(hRes.value);
        }
        if (sRes.status === "fulfilled") {
          setSummary(sRes.value);
        }
        if (dRes.status === "fulfilled") {
          setDocs(dRes.value);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [refreshNonce, summaryHours]);

  const overviewHead = (
    <div className="overview-page__head">
      <div>
        <h1 className="page__title">Панель состояния</h1>
        <p className="page__lead muted overview-lead">
          Конфигурационный снимок <code>/api/overview</code> + live-проверки{" "}
          <code>/api/health</code>
        </p>
      </div>
      <div className="summary-head__actions">
        <label className="summary-hours">
          <span className="muted">Период</span>
          <select
            className="summary-hours__select"
            value={summaryWindowLabel}
            onChange={(e) => setSummaryWindowLabel(e.target.value)}
            aria-label="Период операционной сводки на обзоре"
            disabled={loading}
          >
            {OVERVIEW_SUMMARY_WINDOWS.map((w) => (
              <option key={w.label} value={w.label}>
                {w.label}
              </option>
            ))}
          </select>
        </label>
        <OperationalRefreshButton
          loading={loading}
          onClick={() => setRefreshNonce((n) => n + 1)}
        />
      </div>
    </div>
  );

  if (loading) {
    return (
      <div className="page overview-page">
        {overviewHead}
        <LoadingState label="Загрузка обзора…" />
        <div className="skeleton-grid overview-tight">
          <div className="skeleton skeleton--card" />
          <div className="skeleton skeleton--card" />
          <div className="skeleton skeleton--card" />
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="page overview-page">
        {overviewHead}
        <div className="panel panel--error overview-tight" role="alert">
          {error}
        </div>
        <p className="muted overview-tight metric-sub">
          Проверьте доступность бэкенда и сети, затем нажмите «Обновить».
        </p>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="page overview-page">
        {overviewHead}
        <OperationalSessionEmptyHint
          title="Данные обзора от API не получены."
          hint="Проверьте /api/overview и нажмите «Обновить»."
        />
      </div>
    );
  }

  const mods = data.supported_modalities ?? [];
  const db = data.database ?? {};
  const retrieval = (data.retrieval ?? null) as RetrievalPlatformCompact | null;
  const audio = data.audio ?? {};
  const readiness = data.config_readiness ?? {};
  const deps = health?.dependencies ?? {};
  const pg = asRecord(deps.postgres);
  const chromaLive = asRecord(deps.chroma);
  const ragLive = asRecord(deps.rag);
  const llmMap = asRecordMap(deps.llm);
  const providerCount = Object.keys(llmMap).length;
  const checkedAt = health?.timestamp ? formatTs(health.timestamp) : "—";
  const latencySummary = averageMs([
    Number(pg.latency_ms),
    Number(ragLive.latency_ms),
    ...(retrieval ? [] : [Number(chromaLive.latency_ms)]),
  ]);
  const routes = summary?.routes;
  const telem = summary?.telemetry_sample;
  const docsItems = docs?.items ?? [];
  const docsObs = docs?.observability ?? {};
  const lastAdmin = (docsObs.admin_operations ?? [])[0] ?? null;
  const largestDoc = pickLargestDocument(docsItems);
  const kbState = kbSyncState(docsItems);
  const warnings = buildOverviewWarnings({
    healthStatus: String(health?.status ?? ""),
    ragStatus: String(ragLive.status ?? ""),
    chromaStatus: String(chromaLive.status ?? ""),
    docsSyncState: kbState,
    readiness,
    summary,
    retrieval: (data.retrieval ?? null) as RetrievalPlatformCompact | null,
  });
  return (
    <div className="page overview-page">
      {overviewHead}

      {warnings.length > 0 ? (
        <div className="overview-warnings-strip">
          {warnings.map((w) => (
            <div key={w} className="overview-warning-item">
              {w}
            </div>
          ))}
        </div>
      ) : null}

      {healthWarn ? (
        <div className="panel panel--muted overview-tight" role="status">
          {healthWarn}
        </div>
      ) : null}

      <SectionCard
        title="Состояние системы"
        description="Runtime health, зависимости и оперативный статус."
        className="overview-tight"
      >
        <div className="overview-system-grid">
          <div className="overview-system-col">
            <div className="overview-system-col__title">RUNTIME / СОСТОЯНИЕ</div>
            <dl className="kv overview-kv">
              <dt>API</dt>
              <dd>
                <StatusBadge status={String(health?.status ?? "—")} />
              </dd>
              <dt>PostgreSQL</dt>
              <dd className="overview-kv__split">
                <StatusBadge status={String(pg.status ?? "—")} />
                <span className="muted mono">{fmtMs(pg.latency_ms)}</span>
              </dd>
              <dt>Retrieval{retrieval?.effective_backend ? ` (${formatRetrievalBackendTitle(retrieval.effective_backend)})` : ""}</dt>
              <dd className="overview-kv__split">
                <StatusBadge
                  status={retrievalReadinessForStatusBadge(
                    retrieval?.active_readiness,
                    retrieval?.active_ok
                  )}
                />
                <span className="muted mono">—</span>
              </dd>
              <dt>RAG</dt>
              <dd className="overview-kv__split">
                <StatusBadge status={String(ragLive.status ?? "—")} />
                <span className="muted mono">{fmtMs(ragLive.latency_ms)}</span>
              </dd>
            </dl>
          </div>

          <div className="overview-system-col">
            <div className="overview-system-col__title">LLM-ПРОВАЙДЕРЫ</div>
            {Object.keys(llmMap).length > 0 ? (
              <div className="health-llm">
                {Object.entries(llmMap).map(([name, snap]) => (
                  <div key={name} className="health-llm__chip">
                    <span className="mono">{name}</span>
                    <StatusBadge status={String(snap.status ?? "—")} />
                  </div>
                ))}
              </div>
            ) : (
              <div className="muted">Нет данных по LLM-провайдерам.</div>
            )}
          </div>

          <div className="overview-system-col">
            <div className="overview-system-col__title">ОПЕРАТИВНЫЙ СТАТУС</div>
            <dl className="kv overview-kv">
              <dt>Проверено</dt>
              <dd className="mono">{checkedAt}</dd>
              <dt>Latency summary</dt>
              <dd className="mono">{latencySummary}</dd>
              <dt>LLM-провайдеров</dt>
              <dd>{Object.keys(llmMap).length}</dd>
              <dt>Провайдеров всего</dt>
              <dd>{providerCount}</dd>
            </dl>
          </div>
        </div>
      </SectionCard>

      <div className="page__grid overview-tight">
        <SectionCard
        title="AI-активность"
        description="Операционные метрики маршрутов и телеметрии"
      >
          <dl className="kv overview-kv">
            <dt>Text</dt>
            <dd>{formatVal(routes?.text)}</dd>
            <dt>RAG</dt>
            <dd>{formatVal(routes?.rag)}</dd>
            <dt>Изображения</dt>
            <dd>{formatVal(routes?.images)}</dd>
            <dt>Аудио / voice</dt>
            <dd>{formatVal(routes?.audio_voice)}</dd>
            <dt>Всего событий</dt>
            <dd>{formatVal(summary?.events?.total)}</dd>
            <dt>Запросов (сессий)</dt>
            <dd>{formatVal(summary?.sessions?.unique_execution_ids)}</dd>
            <dt>Токены (sample)</dt>
            <dd>{formatVal(telem?.tokens_total)}</dd>
            <dt>Top provider/model</dt>
            <dd className="mono break-all">{formatVal(telem?.top_provider_model)}</dd>
            <dt>STT / TTS</dt>
            <dd className="mono">
              {formatVal(audio.stt_provider)} / {formatVal(audio.tts_provider)}
            </dd>
          </dl>
        </SectionCard>

        <SectionCard
          title="Retrieval platform"
          description="Активный backend, краткая сводка по индексам и операционные метрики документов."
          className="overview-tight"
        >
          <div className="overview-retrieval-matrix">
            <div className="overview-retrieval-matrix__active">
              <div className="overview-retrieval-matrix__active-label">Active backend</div>
              <div className="overview-retrieval-matrix__active-row">
                <span className="overview-retrieval-matrix__active-name mono">
                  {retrieval?.effective_backend
                    ? formatRetrievalBackendTitle(retrieval.effective_backend).toUpperCase()
                    : "—"}
                </span>
                <StatusBadge
                  status={retrievalReadinessForStatusBadge(
                    retrieval?.active_readiness,
                    retrieval?.active_ok
                  )}
                />
              </div>
            </div>
            <div className="overview-retrieval-matrix__grid" role="list" aria-label="Сводка по backends">
              {retrieval?.backends_compact &&
              Object.keys(retrieval.backends_compact).length > 0 ? (
                [...Object.entries(retrieval.backends_compact)].sort(([a], [b]) => a.localeCompare(b)).map(
                  ([name, row]) => {
                    const isActive =
                      retrieval?.effective_backend &&
                      name.toLowerCase() === String(retrieval.effective_backend).toLowerCase();
                    return (
                    <div
                      key={name}
                      className={`overview-retrieval-matrix__row${isActive ? " overview-retrieval-matrix__row--active" : ""}`}
                      role="listitem"
                    >
                      <span className="overview-retrieval-matrix__backend mono">{name}</span>
                      <StatusBadge
                        status={retrievalReadinessForStatusBadge(row?.readiness, row?.ok)}
                      />
                      <span className="overview-retrieval-matrix__count mono">
                        {row?.count == null ? "—" : String(row.count)}
                      </span>
                    </div>
                    );
                  }
                )
              ) : (
                <div className="muted overview-retrieval-matrix__empty">Нет данных по backends.</div>
              )}
            </div>
          </div>
          <dl className="kv overview-kv">
            <dt>Документов в БД</dt>
            <dd>{formatVal(db.postgres_documents)}</dd>
            <dt>Чанков (активный индекс)</dt>
            <dd>{formatVal(db.collection_chunk_count ?? db.vector_index_chunk_count)}</dd>
            <dt>Синхронизация</dt>
            <dd>
              <StatusBadge status={kbState} />
            </dd>
            <dt>Последняя индексация</dt>
            <dd className="mono">
              {largestDoc?.last_indexed_at ? formatTs(largestDoc.last_indexed_at) : "—"}
            </dd>
            <dt>Крупнейший документ</dt>
            <dd className="mono break-all">{largestDoc ? clip(largestDoc.filename, 44) : "—"}</dd>
          </dl>
        </SectionCard>

        <SectionCard
        title="Админ и безопасность"
        description="Best-effort контекст hardening и последних действий."
      >
          <dl className="kv overview-kv">
            <dt>Auth статус</dt>
            <dd>
              <StatusBadge
                status={
                  readiness.openai_configured || readiness.proxy_configured
                    ? "configured"
                    : "not_configured"
                }
              />
            </dd>
            <dt>Экспозиция админки</dt>
            <dd>
              <StatusBadge status={health?.status === "ok" ? "degraded" : "warning"} />
            </dd>
            <dt>Последнее admin-действие</dt>
            <dd className="mono">{formatVal(lastAdmin?.stage)}</dd>
            <dt>Время действия</dt>
            <dd className="mono">
              {lastAdmin?.created_at ? formatTs(String(lastAdmin.created_at)) : "—"}
            </dd>
            <dt>Logout capability</dt>
            <dd>
              <StatusBadge status="unknown" />
            </dd>
            <dt>Hardening state</dt>
            <dd>
              <StatusBadge status={warnings.length ? "warning" : "ok"} />
            </dd>
          </dl>
        </SectionCard>

        <SectionCard
        title="Готовность системы"
        description="Флаги конфигурации (без секретов)."
      >
          <dl className="kv overview-kv">
            {READINESS_KEYS.map(({ key, label }) => {
              const v = readiness[key];
              const flag =
                typeof v === "boolean" ? (v ? "yes" : "no") : String(v ?? "—");
              return (
                <Fragment key={key}>
                  <dt>{label}</dt>
                  <dd>
                    <StatusBadge status={flag} />
                  </dd>
                </Fragment>
              );
            })}
          </dl>
        </SectionCard>

        <SectionCard
        title="Модальности"
        description="Возможности платформы."
      >
        {mods.length === 0 ? (
          <EmptyState title="Нет модальностей" message="API вернул пустой список." />
        ) : (
          <div className="modality-grid">
            {mods.map((m) => (
              <div key={m} className="modality-card">
                <span className="modality-card__icon" aria-hidden>
                  ◇
                </span>
                <span className="modality-card__name">{m}</span>
              </div>
            ))}
          </div>
        )}
        </SectionCard>
      </div>
    </div>
  );
}

function formatVal(v: unknown): string {
  if (v === null || v === undefined) return "—";
  return String(v);
}

function asRecord(v: unknown): Record<string, unknown> {
  return v !== null && typeof v === "object" && !Array.isArray(v)
    ? (v as Record<string, unknown>)
    : {};
}

function asRecordMap(v: unknown): Record<string, Record<string, unknown>> {
  const raw = asRecord(v);
  const out: Record<string, Record<string, unknown>> = {};
  for (const [k, val] of Object.entries(raw)) {
    out[k] = asRecord(val);
  }
  return out;
}

function formatTs(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toISOString().replace("T", " ").slice(0, 19);
}

function fmtMs(v: unknown): string {
  const n = Number(v);
  return Number.isFinite(n) ? `${n} ms` : "—";
}

function averageMs(values: number[]): string {
  const v = values.filter((x) => Number.isFinite(x) && x >= 0);
  if (!v.length) return "—";
  const avg = v.reduce((a, b) => a + b, 0) / v.length;
  return `${Math.round(avg)} ms`;
}

function clip(v: string, n: number): string {
  return v.length > n ? `${v.slice(0, n)}…` : v;
}

function pickLargestDocument(
  docs: Array<{
    filename: string;
    size_bytes?: number | null;
    chunk_count?: number;
    last_indexed_at?: string | null;
  }>
): {
  filename: string;
  size_bytes?: number | null;
  chunk_count?: number;
  last_indexed_at?: string | null;
} | null {
  if (!docs.length) return null;
  return [...docs].sort((a, b) => {
    const as = Number(a.size_bytes ?? 0) || Number(a.chunk_count ?? 0);
    const bs = Number(b.size_bytes ?? 0) || Number(b.chunk_count ?? 0);
    return bs - as;
  })[0];
}

function kbSyncState(docs: Array<{ status?: string }>): string {
  if (!docs.length) return "unknown";
  const err = docs.filter((d) => String(d.status || "") === "error").length;
  const pend = docs.filter((d) => String(d.status || "") === "pending").length;
  if (err > 0) return "warning";
  if (pend > 0) return "degraded";
  return "ok";
}

function buildOverviewWarnings(args: {
  healthStatus: string;
  ragStatus: string;
  chromaStatus: string;
  docsSyncState: string;
  readiness: Record<string, unknown>;
  summary: SummaryResponse | null;
  retrieval: RetrievalPlatformCompact | null;
}): string[] {
  const out: string[] = [];
  if (args.healthStatus && args.healthStatus !== "ok") {
    out.push("API работает в degraded-режиме.");
  }
  if (args.ragStatus && args.ragStatus !== "ok") {
    out.push("RAG-пайплайн сообщает не-OK статус.");
  }
  if (args.retrieval) {
    if (args.retrieval.active_ok === false) {
      out.push("Активный retrieval backend не готов (health).");
    } else if (args.retrieval.reindex_recommended) {
      out.push("Рекомендуется переиндексация для активного retrieval backend.");
    }
  } else if (args.chromaStatus && args.chromaStatus !== "ok") {
    out.push("Chroma недоступна или нестабильна.");
  }
  if (args.docsSyncState !== "ok") {
    out.push("Индекс и документы потенциально рассинхронизированы.");
  }
  if (!args.readiness.openai_configured && !args.readiness.proxy_configured) {
    out.push("LLM-ключи не настроены.");
  }
  if ((args.summary?.events?.error ?? 0) > 0) {
    out.push("В сводке за выбранный период есть ошибки (processing logs).");
  }
  return out.slice(0, 6);
}
