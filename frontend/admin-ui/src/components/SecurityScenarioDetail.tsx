import { useMemo, type ReactNode } from "react";
import type { AuditEventItem } from "../api/client";
import { OperationalPipelineStageIcon } from "./OperationalPipelineStageIcon";
import { SecuritySeverityBadge } from "./SecuritySeverityBadge";
import { SessionJsonSnapshot } from "./SessionJsonSnapshot";
import { StatusBadge } from "./StatusBadge";
import { formatTimestampMsk } from "../utils/operationalLabels";
import {
  detailsJsonPreview,
  formatDetailsJson,
} from "../utils/operationalConsoleUi";
import {
  auditEventToScenario,
  buildSystemResponseNarrative,
  buildTimelineSteps,
  buildUserRequestNarrative,
  retrievalPolicyStory,
  securityTitleStatusTone,
} from "../utils/securityScenarios";

function OpsRow({ label, value }: { label: string; value: ReactNode }) {
  return (
    <>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </>
  );
}

export function SecurityScenarioDetail({
  item,
  allItems,
}: {
  item: AuditEventItem;
  allItems: AuditEventItem[];
}) {
  const scenario = useMemo(
    () => auditEventToScenario(item, allItems),
    [item, allItems]
  );
  const userNarrative = useMemo(
    () => buildUserRequestNarrative(item, scenario),
    [item, scenario]
  );
  const systemNarrative = useMemo(
    () => buildSystemResponseNarrative(item, scenario),
    [item, scenario]
  );
  const timeline = useMemo(
    () => buildTimelineSteps(item, scenario.chainSteps, scenario.permission),
    [item, scenario.chainSteps, scenario.permission]
  );
  const retrieval = useMemo(
    () => retrievalPolicyStory(item.platform_role),
    [item.platform_role]
  );

  const http =
    item.request_method && item.request_path
      ? `${item.request_method} ${item.request_path}`
      : "—";

  const target =
    item.target_type && item.target_id
      ? `${item.target_type}:${item.target_id}`
      : item.target_id || item.target_type || "—";

  const auditJson = useMemo(
    () =>
      JSON.stringify(
        {
          id: item.id,
          event_type: item.event_type,
          action: item.action,
          status: item.status,
          details: item.details,
          execution_id: item.execution_id,
          request_method: item.request_method,
          request_path: item.request_path,
          principal_email: item.principal_email,
          platform_role: item.platform_role,
          target_type: item.target_type,
          target_id: item.target_id,
          created_at: item.created_at,
        },
        null,
        2
      ),
    [item]
  );

  const titleTone = securityTitleStatusTone(item, scenario.severity);

  return (
    <div className="logs-detail rag-modality-detail security-detail">
      <div className="modality-card__head">
        <h2 className="modality-card__title">СВОДКА SECURITY-СЕССИИ</h2>
        <span
          className={`modality-card__status status-badge status-badge--${titleTone}`}
          title={scenario.auditEventType}
        >
          {scenario.title.toUpperCase()}
        </span>
      </div>

      <div className="modality-ops-panels modality-ops-panels--rag-split security-ops-summary">
        <div className="modality-ops-panels__rag-col modality-ops-panels__rag-col--session">
          <div className="modality-ops-panel">
            <div className="modality-ops-panel__name">Actor / session context</div>
            <dl className="kv modality-ops-panel__kv">
              <OpsRow label="event_id" value={<span className="mono break-all">{item.id}</span>} />
              <OpsRow
                label="время"
                value={
                  <span className="mono rag-ops-timestamp-value">
                    {formatTimestampMsk(item.created_at) ?? "—"}
                  </span>
                }
              />
              <OpsRow label="actor" value={scenario.actorLabel} />
              <OpsRow label="role" value={scenario.roleLabel} />
              <OpsRow
                label="retrieval_role"
                value={<span className="mono">{retrieval.retrievalRole}</span>}
              />
              <OpsRow label="scope" value={<span className="mono">{retrieval.scope}</span>} />
              <OpsRow
                label="principal"
                value={
                  <span className="mono">{item.principal_email ?? "—"}</span>
                }
              />
            </dl>
          </div>
        </div>
        <div className="modality-ops-panels__rag-col modality-ops-panels__rag-col--session">
          <div className="modality-ops-panel">
            <div className="modality-ops-panel__name">Security / policy / event</div>
            <dl className="kv modality-ops-panel__kv">
              <OpsRow label="severity" value={<SecuritySeverityBadge severity={scenario.severity} />} />
              <OpsRow
                label="status"
                value={<StatusBadge status={item.status === "success" ? "ok" : "error"} />}
              />
              <OpsRow label="event result" value={scenario.title} />
              <OpsRow label="policy result" value={retrieval.decision} />
              <OpsRow
                label="audit result"
                value={
                  <span>
                    <code>{scenario.auditEventType}</code> · {item.status ?? "success"}
                  </span>
                }
              />
              <OpsRow label="HTTP" value={<span className="mono">{http}</span>} />
              <OpsRow label="action" value={<code>{item.action}</code>} />
              <OpsRow label="target" value={<span className="mono">{target}</span>} />
            </dl>
          </div>
        </div>
      </div>

      <div className="logs-detail-grid logs-detail-grid--dense rag-io-grid page__mt-sm">
        <div className="logs-detail-block">
          <h3 className="logs-detail-block__title">ЧТО ЗАПРОСИЛ ПОЛЬЗОВАТЕЛЬ</h3>
          <pre className="logs-pre logs-pre--compact mono">{userNarrative.prose}</pre>
          {userNarrative.httpLine ? (
            <p className="rag-io-foot muted mono">{userNarrative.httpLine}</p>
          ) : null}
        </div>
        <div className="logs-detail-block">
          <h3 className="logs-detail-block__title">ЧТО ОТВЕТИЛА СИСТЕМА</h3>
          <pre className="logs-pre logs-pre--compact mono">{systemNarrative}</pre>
        </div>
      </div>

      <details className="rag-diagnostics-fold page__mt">
        <summary className="rag-diagnostics-fold__summary">
          Таймлайн pipeline ({timeline.length})
        </summary>
        <div className="logs-timeline page__mt-sm">
          {timeline.map((step, i) => (
            <div
              key={`${step.label}-${i}`}
              className="logs-stage logs-stage--compact"
              title={step.label}
            >
              <div className="logs-stage__top">
                <span className="mono logs-stage__time">
                  {formatTimestampMsk(step.at) ?? "—"}
                </span>
                <span className="logs-stage__label af-logs-stage-label-with-icon">
                  <OperationalPipelineStageIcon variant={step.variant} />
                  <span>{step.label}</span>
                </span>
                <StatusBadge status={step.statusLabel} />
                {step.deltaMs != null ? (
                  <span className="muted mono logs-stage__delta">+{step.deltaMs} мс</span>
                ) : null}
              </div>
              <details className="logs-stage__details">
                <summary className="log-details__summary">
                  {detailsJsonPreview(step.payload)}
                </summary>
                <pre className="log-details__json mono">
                  {formatDetailsJson(step.payload)}
                </pre>
              </details>
            </div>
          ))}
        </div>
      </details>

      <SessionJsonSnapshot
        className="page__mt"
        summaryLabel="Технический снимок security-сессии (JSON)"
        body={auditJson}
      />
    </div>
  );
}
