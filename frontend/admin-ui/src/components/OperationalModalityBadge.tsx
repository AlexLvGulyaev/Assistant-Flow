import { MODALITY } from "../lib/chipContract";
import {
  normalizeOperationalModality,
  type OperationalModality,
} from "../utils/operationalConsoleUi";

type Props = {
  modality: OperationalModality | string;
  className?: string;
  title?: string;
};

/**
 * Маркер модальности — тихий эмодзи-чип по эмодзи-SOT (MODALITY):
 * эмодзи меню, утверждены владельцем; ocr 🔤 / vision 👁️ / test 🧪 —
 * согласованы с владельцем (аналогии в референсах нет).
 */
export function OperationalModalityBadge({ modality, className = "", title }: Props) {
  const safe =
    typeof modality === "string" ? normalizeOperationalModality(modality) : modality;
  const chip = MODALITY[safe] ?? MODALITY.log;
  return (
    <span
      className={`ai-status ai-status--emoji ${chip.variant}${className ? ` ${className}` : ""}`}
      title={title ?? chip.label}
    >
      <span aria-hidden>{chip.emoji}</span>
      {chip.label}
    </span>
  );
}