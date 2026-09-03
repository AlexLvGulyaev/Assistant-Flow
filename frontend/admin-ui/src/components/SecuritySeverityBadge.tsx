import type { SecuritySeverity } from "../utils/securityScenarios";
import { SEVERITY } from "../lib/chipContract";

/**
 * Серьёзность события — тихий чип по эмодзи-SOT (SEVERITY в
 * lib/chipContract.ts): ℹ️ INFO / ⚠️ WARN / ❌ ERROR / 🚨 CRIT.
 */
export function SecuritySeverityBadge({ severity }: { severity: SecuritySeverity }) {
  const chip = SEVERITY[severity];
  return (
    <span
      className={`ai-status ai-status--emoji ${chip?.variant ?? "ai-status--muted"}`}
      title={severity}
    >
      <span aria-hidden>{chip?.emoji ?? "➖"}</span>
      {chip?.label ?? severity}
    </span>
  );
}