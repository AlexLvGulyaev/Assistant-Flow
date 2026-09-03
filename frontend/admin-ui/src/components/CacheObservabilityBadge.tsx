import { RETRIEVAL } from "../lib/chipContract";
import { cacheStateLabelRu, type CacheState } from "../utils/cacheObservability";

type Props = {
  state: CacheState;
  className?: string;
};

/**
 * Результат retrieval-кэша — тихий чип по эмодзи-SOT (RETRIEVAL,
 * канон AIC: hit 🎯 / miss 💨; bypass ⏭️ согласован с владельцем).
 */
export function CacheObservabilityBadge({ state, className = "" }: Props) {
  const chip = RETRIEVAL[state] ?? RETRIEVAL.na;
  return (
    <span
      className={`ai-status ai-status--emoji ${chip.variant}${className ? ` ${className}` : ""}`}
      title={cacheStateLabelRu(state)}
    >
      <span aria-hidden>{chip.emoji}</span>
      {chip.label}
    </span>
  );
}