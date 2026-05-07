import { useEffect, useState } from "react";
import { fetchOverview, type OverviewResponse } from "../api/client";
import { MetricCard } from "../components/MetricCard";
import { StatusBadge } from "../components/StatusBadge";

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
        <div className="skeleton-grid">
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
        <div className="panel panel--error" role="alert">
          {error}
        </div>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="page">
        <h1 className="page__title">Overview</h1>
        <div className="panel panel--muted">No data.</div>
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

  return (
    <div className="page">
      <h1 className="page__title">Overview</h1>
      <p className="page__lead muted">
        Operational snapshot from <code>/api/overview</code>
      </p>

      <div className="page__grid">
        <MetricCard title="Data &amp; index">
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
        </MetricCard>

        <MetricCard title="RAG / Chroma">
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
        </MetricCard>

        <MetricCard title="Supported modalities">
          {mods.length === 0 ? (
            <p className="muted">None reported.</p>
          ) : (
            <ul className="tag-list">
              {mods.map((m) => (
                <li key={m}>
                  <span className="tag">{m}</span>
                </li>
              ))}
            </ul>
          )}
        </MetricCard>

        <MetricCard title="Providers (config)">
          {Object.keys(providers).length === 0 ? (
            <p className="muted">No provider entries.</p>
          ) : (
            <ul className="inline-list">
              {Object.entries(providers).map(([name, snap]) => (
                <li key={name}>
                  <span className="mono">{name}</span>{" "}
                  <StatusBadge status={String(snap.status ?? "—")} />
                </li>
              ))}
            </ul>
          )}
        </MetricCard>

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
              {String(audio.enabled) === "true" ? (
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
