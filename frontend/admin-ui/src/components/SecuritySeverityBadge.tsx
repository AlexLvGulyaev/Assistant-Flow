import type { SecuritySeverity } from "../utils/securityScenarios";

const LABELS: Record<SecuritySeverity, string> = {
  info: "INFO",
  warning: "WARN",
  error: "ERROR",
  critical: "CRIT",
};

export function SecuritySeverityBadge({ severity }: { severity: SecuritySeverity }) {
  return (
    <span className={`security-severity security-severity--${severity}`}>
      {LABELS[severity]}
    </span>
  );
}
