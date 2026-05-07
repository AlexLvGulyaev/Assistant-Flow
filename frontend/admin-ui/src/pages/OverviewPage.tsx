import { useEffect, useState } from "react";
import { fetchOverview, type OverviewResponse } from "../api/client";
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
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const o = await fetchOverview();
        if (!cancelled) setData(o);
      } catch (e) {
        if (!cancelled)
          setError(e instanceof Error ? e.message : "Failed to load overview");
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

  return (
    <div className="page">
      <h1 className="page__title">Overview</h1>
      <p className="page__lead muted">
        Operational snapshot · <code>/api/overview</code>
      </p>

      <SectionCard
        title="System readiness"
        description="Config flags only — no secrets exposed."
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

        <SectionCard title="RAG / Chroma">
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
