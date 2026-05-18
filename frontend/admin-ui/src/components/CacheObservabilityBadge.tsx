import {
  cacheStateBadgeText,
  cacheStateLabelRu,
  type CacheState,
} from "../utils/cacheObservability";

type Props = {
  state: CacheState;
  className?: string;
};

export function CacheObservabilityBadge({ state, className = "" }: Props) {
  const tone =
    state === "hit"
      ? "hit"
      : state === "miss"
        ? "miss"
        : state === "bypass"
          ? "bypass"
          : state === "off"
            ? "off"
            : "na";
  return (
    <span
      className={`cache-obs-badge cache-obs-badge--${tone}${className ? ` ${className}` : ""}`}
      title={cacheStateLabelRu(state)}
    >
      {cacheStateBadgeText(state)}
    </span>
  );
}
