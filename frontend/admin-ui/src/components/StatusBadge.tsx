import { statusChip } from "../lib/chipContract";

interface StatusBadgeProps {
  status: string;
}

/**
 * Статус-чип по эмодзи-SOT (канон RF OpChip / LQ ai-status): тихий чип
 * «эмодзи + лейбл», эмодзи заменяет точку, цвет — только текст.
 * Контракт значений — STATUS в lib/chipContract.ts (SOT).
 */
export function StatusBadge({ status }: StatusBadgeProps) {
  const chip = statusChip(status);
  return (
    <span className={`ai-status ai-status--emoji ${chip.variant}`} title={status}>
      <span aria-hidden>{chip.emoji}</span>
      {chip.label}
    </span>
  );
}