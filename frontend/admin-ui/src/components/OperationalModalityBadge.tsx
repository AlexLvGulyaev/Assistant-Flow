import {
  OPERATIONAL_MODALITY_LABEL,
  normalizeOperationalModality,
  operationalModalityBadgeClassList,
  type OperationalModality,
} from "../utils/operationalConsoleUi";

type Props = {
  modality: OperationalModality | string;
  className?: string;
  title?: string;
};

export function OperationalModalityBadge({ modality, className = "", title }: Props) {
  const safe =
    typeof modality === "string" ? normalizeOperationalModality(modality) : modality;
  const label = OPERATIONAL_MODALITY_LABEL[safe];
  return (
    <span
      className={`${operationalModalityBadgeClassList(safe)}${className ? ` ${className}` : ""}`}
      title={title ?? label}
    >
      {label}
    </span>
  );
}
