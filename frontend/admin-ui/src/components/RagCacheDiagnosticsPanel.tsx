import type { ReactNode } from "react";
import { CacheObservabilityBadge } from "./CacheObservabilityBadge";
import {
  cacheStateBadgeText,
  isCacheLookupActive,
  isCacheSessionComparisonAllowed,
  type CacheTelemetry,
  type ComparableSession,
} from "../utils/cacheObservability";

function OpsRow({ label, value }: { label: string; value: ReactNode }) {
  return (
    <>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </>
  );
}

function gap(): ReactNode {
  return <span className="telemetry-gap muted">—</span>;
}

function fmtText(v: string | null | undefined): ReactNode {
  return v?.trim() ? <span className="mono">{v}</span> : gap();
}

function fmtMs(v: number | null | undefined): ReactNode {
  return v != null && Number.isFinite(v) ? (
    <span className="mono">{v} мс</span>
  ) : (
    gap()
  );
}

function fmtBool(v: boolean | null | undefined): ReactNode {
  if (v === true) return "да";
  if (v === false) return "нет";
  return gap();
}

type Props = {
  telemetry: CacheTelemetry;
  previousMatch: ComparableSession | null;
  current: ComparableSession;
};

/** Column 3: Cache panel (stacked above Comparison in RAG header grid). */
export function RagCacheDiagnosticsPanel({ telemetry }: Props) {
  return (
    <div className="modality-ops-panel modality-ops-panel--rag-header-compact">
      <div className="modality-ops-panel__name">Кэш</div>
      <dl className="kv modality-ops-panel__kv">
        <OpsRow label="state" value={<CacheObservabilityBadge state={telemetry.state} />} />
        <OpsRow label="cache_layer" value={fmtText(telemetry.cacheLayer)} />
        <OpsRow label="cache_latency_ms" value={fmtMs(telemetry.cacheLatencyMs)} />
        <OpsRow
          label="generation"
          value={fmtText(telemetry.retrievalCacheGeneration)}
        />
        <OpsRow
          label="fingerprint_backend"
          value={fmtText(telemetry.fingerprintBackend ?? telemetry.retrievalCacheBackend)}
        />
        <OpsRow label="key_hash_prefix" value={fmtText(telemetry.keyHashPrefix)} />
        <OpsRow
          label="invalidation_reason"
          value={fmtText(telemetry.invalidationReason)}
        />
        <OpsRow label="skipped_retrieval" value={fmtBool(telemetry.skippedRetrieval)} />
      </dl>
    </div>
  );
}

/** Column 3: Comparison panel. */
export function RagCacheComparePanel({ telemetry, previousMatch, current }: Props) {
  const prevState = previousMatch?.cacheState ?? null;
  const curState = telemetry.state;
  const comparisonAllowed = isCacheSessionComparisonAllowed(curState, prevState);
  const prevLat = previousMatch?.retrievalLatencyMs ?? null;
  const curLat = current.retrievalLatencyMs;
  const latDelta =
    comparisonAllowed &&
    prevLat != null &&
    curLat != null &&
    Number.isFinite(prevLat) &&
    Number.isFinite(curLat)
      ? curLat - prevLat
      : null;

  return (
    <div className="modality-ops-panel modality-ops-panel--rag-header-compact cache-obs-compare">
      <div className="modality-ops-panel__name">Сравнение</div>
      {!previousMatch ? (
        <p className="muted cache-obs-compare__empty">нет пары в окне</p>
      ) : (
        <>
          <dl className="kv modality-ops-panel__kv cache-obs-compare__kv">
            <OpsRow
              label="пред."
              value={
                <span className="mono" title={previousMatch.executionId}>
                  {cacheStateBadgeText(prevState ?? "na")}
                </span>
              }
            />
            <OpsRow label="тек." value={<span className="mono">{cacheStateBadgeText(curState)}</span>} />
            <OpsRow
              label="Δ retrieval ms"
              value={
                latDelta != null ? (
                  <span className="mono">
                    {latDelta > 0 ? "+" : ""}
                    {latDelta} мс
                  </span>
                ) : (
                  <span className="telemetry-gap muted" title="cache OFF/BYPASS или нет HIT/MISS">
                    н/д
                  </span>
                )
              }
            />
          </dl>
          {!comparisonAllowed && !isCacheLookupActive(curState) ? (
            <p className="muted cache-obs-compare__empty">сравнение кэша недоступно (OFF)</p>
          ) : !comparisonAllowed ? (
            <p className="muted cache-obs-compare__empty">сравнение кэша: нет HIT/MISS</p>
          ) : null}
        </>
      )}
    </div>
  );
}
