import { useEffect, useState } from "react";
import {
  fetchHealth,
  fetchOverview,
  type HealthResponse,
  type OverviewResponse,
} from "../api/client";
import { EmptyState } from "../components/EmptyState";
import { LoadingState } from "../components/LoadingState";
import { MetricCard } from "../components/MetricCard";
import { SectionCard } from "../components/SectionCard";
import { StatusBadge } from "../components/StatusBadge";

const READINESS_KEYS: { key: string; label: string }[] = [
  { key: "database_url_configured", label: "DATABASE_URL" },
  { key: "openai_configured", label: "OpenAI key" },
  { key: "proxy_configured", label: "Proxy key" },
  { key: "gigachat_configured", label: "GigaChat key" },
  { key: "audio_enabled", label: "Audio" },
  { key: "chroma_use_http", label: "Chroma HTTP" },
];

export function OverviewPage() {
  const [data, setData] = useState<OverviewResponse | null>(null);
  const [health, setHealth] = useState<HealthResponse | null>(null);
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
        const [oRes, hRes] = await Promise.allSettled([
          fetchOverview(),
          fetchHealth(),
        ]);
        if (cancelled) return;
        if (oRes.status === "rejected") {
          setData(null);
          setError(
            oRes.reason instanceof Error
              ? oRes.reason.message
              : "Failed to load overview"
          );
        } else {
          setData(oRes.value);
        }
        if (hRes.status === "rejected") {
          setHealth(null);
          setHealthWarn(
            hRes.reason instanceof Error
              ? hRes.reason.message
              : "Failed to load live checks"
          );
        } else {
          setHealth(hRes.value);
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
        <h1 className="page__title">Overview</h1>
        <LoadingState label="Loading overview…" />
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
        <h1 className="page__title">Overview</h1>
        <div className="panel panel--error page__mt" role="alert">
          {error}
        </div>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="page">
        <h1 className="page__title">Overview</h1>
        <EmptyState message="No overview payload returned." />
      </div>
    );
  }

  const mods = data.supported_modalities ?? [];
  const providers = data.providers ?? {};
  const db = data.database ?? {};
  const audio = data.audio ?? {};
  const assets = data.asset_storage ?? {};
  const rag = data.rag ?? {};
  const chroma = data.chroma ?? {};
  const readiness = data.config_readiness ?? {};
  const deps = health?.dependencies ?? {};
  const pg = asRecord(deps.postgres);
  const chromaLive = asRecord(deps.chroma);
  const ragLive = asRecord(deps.rag);
  const llmMap = asRecordMap(deps.llm);

  return (
    <div className="page">
      <h1 className="page__title">Overview</h1>
      <p className="page__lead muted">
        Configuration snapshot (<code>/api/overview</code>) + live probes (
        <code>/api/health</code>)
      </p>

      {healthWarn ? (
        <div className="panel panel--muted page__mt" role="status">
          {healthWarn}
        </div>
      ) : null}

      {health ? (
        <SectionCard
          title="Live dependency checks"
          description="Runtime probes — distinct from static config readiness below."
          className="page__mt"
        >
          <div className="health-banner">
            <div>
              <StatusBadge status={String(health.status ?? "—")} />
              <div className="health-banner__meta muted page__mt-sm">
                {health.timestamp ? (
                  <>
                    UTC{" "}
                    <span className="mono">
                      {formatTs(health.timestamp)}
                    </span>
                  </>
                ) : null}
                {health.version ? (
                  <>
                    {" · "}
                    <span className="mono">v{health.version}</span>
                  </>
                ) : null}
              </div>
            </div>
          </div>
          <div className="health-deps page__mt-sm">
            <div className="health-dep">
              <div className="health-dep__title">PostgreSQL</div>
              <div className="health-dep__row">
                <StatusBadge status={String(pg.status ?? "—")} />
                {pg.latency_ms != null ? (
                  <span className="muted mono">{`${pg.latency_ms} ms`}</span>
                ) : (
                  <span className="muted">—</span>
                )}
              </div>
            </div>
            <div className="health-dep">
              <div className="health-dep__title">Chroma</div>
              <div className="health-dep__row">
                <StatusBadge status={String(chromaLive.status ?? "—")} />
                {chromaLive.latency_ms != null ? (
                  <span className="muted mono">{`${chromaLive.latency_ms} ms`}</span>
                ) : (
                  <span className="muted">—</span>
                )}
              </div>
            </div>
            <div className="health-dep">
              <div className="health-dep__title">RAG pipeline</div>
              <div className="health-dep__row">
                <StatusBadge status={String(ragLive.status ?? "—")} />
                {ragLive.latency_ms != null ? (
                  <span className="muted mono">{`${ragLive.latency_ms} ms`}</span>
                ) : (
                  <span className="muted">—</span>
                )}
              </div>
            </div>
          </div>
          {Object.keys(llmMap).length > 0 ? (
            <div className="page__mt-sm">
              <div className="health-dep__title">LLM providers</div>
              <div className="health-llm page__mt-sm">
                {Object.entries(llmMap).map(([name, snap]) => (
                  <div key={name} className="health-llm__chip">
                    <span className="mono">{name}</span>
                    <StatusBadge status={String(snap.status ?? "—")} />
                  </div>
                ))}
              </div>
            </div>
          ) : null}
        </SectionCard>
      ) : null}

      <SectionCard
        title="System readiness"
        description="Config flags only — no secrets exposed."
        className="page__mt"
      >
        <div className="readiness-strip">
          {READINESS_KEYS.map(({ key, label }) => {
            const v = readiness[key];
            const flag =
              typeof v === "boolean" ? (v ? "yes" : "no") : String(v ?? "—");
            return (
              <div key={key} className="readiness-chip">
                <span className="readiness-chip__lbl muted">{label}</span>
                <StatusBadge status={flag} />
              </div>
            );
          })}
        </div>
      </SectionCard>

      <SectionCard
        title="Modalities"
        description="Capabilities exposed by the platform."
        className="page__mt"
      >
        {mods.length === 0 ? (
          <EmptyState title="No modalities" message="API returned an empty list." />
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

      <div className="page__grid page__mt">
        <SectionCard title="Providers (configuration)">
          {Object.keys(providers).length === 0 ? (
            <p className="muted">No provider entries.</p>
          ) : (
            <div className="provider-grid">
              {Object.entries(providers).map(([name, snap]) => (
                <div key={name} className="provider-cell">
                  <span className="provider-cell__name mono">{name}</span>
                  <StatusBadge status={String(snap.status ?? "—")} />
                </div>
              ))}
            </div>
          )}
        </SectionCard>

        <SectionCard title="Data &amp; index">
          <dl className="kv">
            <dt>PostgreSQL</dt>
            <dd>
              {db.postgres_available === true ? (
                <StatusBadge status="available" />
              ) : (
                <StatusBadge status="unavailable" />
              )}
            </dd>
            <dt>Documents (DB)</dt>
            <dd>{formatVal(db.postgres_documents)}</dd>
            <dt>Chunks (DB sum)</dt>
            <dd>{formatVal(db.postgres_chunks_sum)}</dd>
            <dt>Chroma chunks</dt>
            <dd>{formatVal(db.collection_chunk_count)}</dd>
          </dl>
        </SectionCard>

        <SectionCard title="RAG / Chroma (config view)">
          <dl className="kv">
            <dt>RAG</dt>
            <dd>
              <StatusBadge status={String(rag.status ?? "—")} />
            </dd>
            <dt>Chroma</dt>
            <dd>
              <StatusBadge status={String(chroma.status ?? "—")} />
            </dd>
          </dl>
        </SectionCard>

        <MetricCard title="Asset storage">
          <dl className="kv">
            <dt>Backend</dt>
            <dd className="mono">{formatVal(assets.backend)}</dd>
            <dt>Directory</dt>
            <dd className="mono break-all">{formatVal(assets.dir)}</dd>
          </dl>
        </MetricCard>

        <MetricCard title="Audio">
          <dl className="kv">
            <dt>Enabled</dt>
            <dd>
              {audio.enabled === true ? (
                <StatusBadge status="on" />
              ) : (
                <StatusBadge status="off" />
              )}
            </dd>
            <dt>STT</dt>
            <dd className="mono">{formatVal(audio.stt_provider)}</dd>
            <dt>TTS</dt>
            <dd className="mono">{formatVal(audio.tts_provider)}</dd>
            <dt>Namespace</dt>
            <dd className="mono">{formatVal(audio.storage_namespace)}</dd>
          </dl>
        </MetricCard>
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
