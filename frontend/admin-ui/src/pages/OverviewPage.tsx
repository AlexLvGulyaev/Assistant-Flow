import { Fragment, useEffect, useState } from "react";
import {
  fetchDocuments,
  fetchHealth,
  fetchOverview,
  fetchSummary,
  type DocumentsResponse,
  type HealthResponse,
  type OverviewResponse,
  type SummaryResponse,
} from "../api/client";
import { EmptyState } from "../components/EmptyState";
import { LoadingState } from "../components/LoadingState";
import { SectionCard } from "../components/SectionCard";
import { StatusBadge } from "../components/StatusBadge";

const READINESS_KEYS: { key: string; label: string }[] = [
  { key: "database_url_configured", label: "DATABASE_URL" },
  { key: "openai_configured", label: "OpenAI" },
  { key: "proxy_configured", label: "Proxy" },
  { key: "gigachat_configured", label: "GigaChat" },
  { key: "audio_enabled", label: "Аудио" },
  { key: "chroma_use_http", label: "Chroma HTTP" },
];

export function OverviewPage() {
  const [data, setData] = useState<OverviewResponse | null>(null);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [summary, setSummary] = useState<SummaryResponse | null>(null);
  const [docs, setDocs] = useState<DocumentsResponse | null>(null);
  const [healthWarn, setHealthWarn] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

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
          fetchSummary(24),
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
  }, []);

  if (loading) {
    return (
      <div className="page">
        <h1 className="page__title">Обзор</h1>
        <LoadingState label="Загрузка обзора…" />
        <div className="skeleton-grid page__mt">
          <div className="skeleton skeleton--card" />
          <div className="skeleton skeleton--card" />
          <div className="skeleton skeleton--card" />
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="page">
        <h1 className="page__title">Обзор</h1>
        <div className="panel panel--error page__mt" role="alert">
          {error}
        </div>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="page">
        <h1 className="page__title">Обзор</h1>
        <EmptyState message="Нет данных обзора от API." />
      </div>
    );
  }

  const mods = data.supported_modalities ?? [];
  const db = data.database ?? {};
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
    Number(chromaLive.latency_ms),
    Number(ragLive.latency_ms),
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
  });
  return (
    <div className="page overview-page">
      <h1 className="page__title">Обзор</h1>
      <p className="page__lead muted overview-lead">
        Конфигурационный снимок <code>/api/overview</code> + live-проверки{" "}
        <code>/api/health</code>
      </p>

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
              <dt>Chroma</dt>
              <dd className="overview-kv__split">
                <StatusBadge status={String(chromaLive.status ?? "—")} />
                <span className="muted mono">{fmtMs(chromaLive.latency_ms)}</span>
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
        description="Операционные метрики маршрутов и телеметрии за 24 часа."
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
        title="База знаний (операционный статус)"
        description="Синхронизация документов, индекса и админ-операций."
      >
          <dl className="kv overview-kv">
            <dt>Документов в БД</dt>
            <dd>{formatVal(db.postgres_documents)}</dd>
            <dt>Файлов в каталоге</dt>
            <dd>н/д</dd>
            <dt>Активных чанков</dt>
            <dd>{formatVal(db.postgres_chunks_sum)}</dd>
            <dt>Чанков Chroma</dt>
            <dd>{formatVal(db.collection_chunk_count)}</dd>
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
}): string[] {
  const out: string[] = [];
  if (args.healthStatus && args.healthStatus !== "ok") {
    out.push("API работает в degraded-режиме.");
  }
  if (args.ragStatus && args.ragStatus !== "ok") {
    out.push("RAG-пайплайн сообщает не-OK статус.");
  }
  if (args.chromaStatus && args.chromaStatus !== "ok") {
    out.push("Chroma недоступна или нестабильна.");
  }
  if (args.docsSyncState !== "ok") {
    out.push("Индекс и документы потенциально рассинхронизированы.");
  }
  if (!args.readiness.openai_configured && !args.readiness.proxy_configured) {
    out.push("LLM-ключи не настроены.");
  }
  if ((args.summary?.events?.error ?? 0) > 0) {
    out.push("За 24ч есть ошибки в processing logs.");
  }
  return out.slice(0, 6);
}
