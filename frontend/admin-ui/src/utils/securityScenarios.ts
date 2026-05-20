import type { AuditEventItem } from "../api/client";
import type { AfPipelineStageVariant } from "./operationalConsoleUi";

export type SecuritySeverity = "info" | "warning" | "error" | "critical";
export type ScenarioCategory = "auth" | "rbac" | "retrieval" | "documents" | "other";

export interface RetrievalSecurityStory {
  decision: string;
  reason: string;
  allowedVisibility: string;
  retrievalRole: string;
  scope: string;
}

/** Одна строка в секции pipeline (читаемый kv). */
export interface PipelineLine {
  label: string;
  value: string;
}

/** Канонические секции A–E: одинаковы для всех сценариев. */
export interface SecurityPipelineView {
  user: PipelineLine[];
  systemInterpretation: PipelineLine[];
  decision: PipelineLine[];
  consequences: PipelineLine[];
  timeline: string[];
}

export interface SecurityTimelineStep {
  label: string;
  variant: AfPipelineStageVariant;
  statusLabel: string;
  /** Временная метка этапа (если известна из audit). */
  at?: string | null;
  /** Компактный operational payload для preview / раскрытия (не весь event). */
  payload: Record<string, unknown>;
  deltaMs: number | null;
}

export interface SecurityScenarioView {
  id: string;
  category: ScenarioCategory;
  title: string;
  shortExplanation: string;
  severity: SecuritySeverity;
  resultLabel: string;
  actorLabel: string;
  roleLabel: string;
  permission: string | null;
  auditEventType: string;
  chainSteps: string[];
  retrievalStory: RetrievalSecurityStory | null;
  pipeline: SecurityPipelineView;
}

const ROLE_LABELS: Record<string, string> = {
  admin: "администратор",
  superadmin: "суперадмин",
  operator: "оператор",
  auditor: "аудитор",
  employee: "сотрудник",
  end_user: "гость (end_user)",
  guest: "гость",
};

function roleLabelRu(role: string | null | undefined): string {
  if (!role) return "—";
  return ROLE_LABELS[role] ?? role;
}

function pickPermission(details: Record<string, unknown>): string | null {
  const p = details.permission;
  return typeof p === "string" ? p : null;
}

function retrievalRoleFromPlatform(platformRole: string | null): string {
  const r = (platformRole || "end_user").toLowerCase();
  if (r === "admin" || r === "superadmin") return "admin";
  if (r === "end_user" || r === "guest") return "guest";
  return "employee";
}

export function retrievalPolicyStory(
  platformRole: string | null
): RetrievalSecurityStory {
  const retrievalRole = retrievalRoleFromPlatform(platformRole);
  if (retrievalRole === "admin") {
    return {
      decision: "разрешён полный доступ",
      reason: "роль admin — без ограничений visibility",
      allowedVisibility: "public, internal, unspecified, restricted",
      retrievalRole: "admin",
      scope: "unrestricted",
    };
  }
  if (retrievalRole === "guest") {
    return {
      decision: "ограниченный retrieval",
      reason: "роль guest — только public visibility",
      allowedVisibility: "public",
      retrievalRole: "guest",
      scope: "public_only",
    };
  }
  return {
    decision: "role-aware retrieval",
    reason: "роль employee — public + internal + unspecified",
    allowedVisibility: "public, internal, unspecified",
    retrievalRole: "employee",
    scope: "employee_kb",
  };
}

function severityFor(item: AuditEventItem): SecuritySeverity {
  const et = item.event_type || "";
  const st = item.status || "success";
  if (et === "auth.login.success" || et === "auth.logout") return "info";
  if (et === "auth.login.failure") return "warning";
  if (et === "security.access.denied") return "warning";
  if (et === "security.permission.denied") return "error";
  if (st === "failure") return "warning";
  if (et.startsWith("privileged.") && st === "success") return "info";
  return "info";
}

function categoryFor(et: string): ScenarioCategory {
  if (et.startsWith("auth.")) return "auth";
  if (et.startsWith("security.")) return "rbac";
  if (et.includes("retrieval")) return "retrieval";
  if (et.includes("documents")) return "documents";
  return "other";
}

function titleFor(item: AuditEventItem): string {
  const et = item.event_type || item.action;
  const map: Record<string, string> = {
    "auth.login.success": "Успешный вход",
    "auth.login.failure": "Неудачная попытка входа",
    "auth.logout": "Выход из сессии",
    "security.access.denied": "Доступ без аутентификации",
    "security.permission.denied": "Недостаточно прав (RBAC)",
    "privileged.documents.upload": "Загрузка документа",
    "privileged.documents.reindex": "Переиндексация документа",
    "privileged.documents.edit_text": "Редактирование текста документа",
    "privileged.retrieval.backend.switch": "Смена retrieval backend",
    "privileged.retrieval.settings.update": "Изменение retrieval tuning",
    "privileged.retrieval.settings.delete": "Сброс retrieval tuning",
    "privileged.settings.evaluation.run": "Запуск evaluation",
    "privileged.settings.evaluation.patch": "Изменение evaluation",
    "privileged.settings.evaluation.delete": "Удаление evaluation run",
  };
  if (map[et]) return map[et];
  if (et.startsWith("privileged.")) return `Привилегированное действие: ${item.action}`;
  return et || "Событие безопасности";
}

function shortExplanationFor(item: AuditEventItem, perm: string | null): string {
  const et = item.event_type || "";
  if (et === "auth.login.success") {
    return "Пользователь успешно аутентифицирован, сессия выдана.";
  }
  if (et === "auth.login.failure") {
    return "Неверные учётные данные; доступ не выдан.";
  }
  if (et === "auth.logout") {
    return "Сессия завершена, токен отозван.";
  }
  if (et === "security.access.denied") {
    const path = item.request_path || "";
    if (path.includes("/audit")) {
      return "Запрос к audit API без Bearer-токена или с недействительным токеном.";
    }
    return "Защищённый маршрут без валидной аутентификации (401).";
  }
  if (et === "security.permission.denied" && perm) {
    return `Маршрут требует permission «${perm}», у principal его нет.`;
  }
  if (et.startsWith("privileged.retrieval.")) {
    return item.status === "success"
      ? "Оператор с правами retrieval выполнил изменение."
      : "Попытка изменить retrieval без прав.";
  }
  if (et.startsWith("privileged.documents.")) {
    return "Операция с корпусом документов (upload / reindex / edit).";
  }
  return item.reason || "Событие зафиксировано в admin_audit_log.";
}

function resultLabelFor(item: AuditEventItem): string {
  const et = item.event_type || "";
  if (et === "security.permission.denied" || et === "security.access.denied") {
    return "доступ запрещён";
  }
  if (item.status === "failure") return "ошибка";
  return "доступ разрешён";
}

function defaultChain(item: AuditEventItem): string[] {
  const et = item.event_type || "";
  const steps: string[] = [];
  if (et.startsWith("auth.login")) {
    steps.push("POST /api/auth/login");
    steps.push("IdentityService.authenticate_user");
    steps.push(item.status === "success" ? "issue_session_token" : "401 ответ");
    steps.push(`audit: ${et}`);
    return steps;
  }
  if (et === "security.access.denied") {
    steps.push("HTTP запрос к защищённому API");
    steps.push("IdentityAuthMiddleware: principal anonymous");
    steps.push("401 + audit security.access.denied");
    return steps;
  }
  if (et === "security.permission.denied") {
    steps.push("HTTP запрос с Bearer");
    steps.push("require_permission: проверка RBAC");
    steps.push("403 + audit security.permission.denied");
    return steps;
  }
  if (et.startsWith("privileged.retrieval.")) {
    steps.push("Аутентифицированный запрос");
    steps.push("RBAC: retrieval:admin / retrieval:read");
    steps.push("Retrieval policy (P8 bridge) по platform_role");
    steps.push(`audit: ${et}`);
    return steps;
  }
  if (item.request_method && item.request_path) {
    steps.push(`${item.request_method} ${item.request_path}`);
    steps.push(`audit: ${et}`);
  }
  return steps;
}

function retrievalInterpretationLines(
  platformRole: string | null,
  perm: string | null
): PipelineLine[] {
  const story = retrievalPolicyStory(platformRole);
  const lines: PipelineLine[] = [
    { label: "Retrieval role", value: story.retrievalRole },
    { label: "Visibility policy", value: story.allowedVisibility },
    { label: "Scope", value: story.scope },
    { label: "Retrieval decision", value: story.decision },
  ];
  if (perm?.startsWith("retrieval:")) {
    lines.push({
      label: "Запрошенный permission",
      value: `${perm} — проверка RBAC до retrieval pipeline`,
    });
  }
  return lines;
}

function buildSecurityPipeline(
  item: AuditEventItem,
  perm: string | null,
  chainSteps: string[]
): SecurityPipelineView {
  const et = item.event_type || item.action;
  const http =
    item.request_method && item.request_path
      ? `${item.request_method} ${item.request_path}`
      : "—";
  const actor = item.principal_email ?? "анонимный / неаутентифицированный";
  const role = roleLabelRu(item.platform_role);
  const retrieval = retrievalPolicyStory(item.platform_role);

  const user: PipelineLine[] = [
    { label: "Актор", value: actor },
    { label: "Platform role", value: role },
    { label: "HTTP-запрос", value: http },
    { label: "Намерение", value: userIntentFor(item, perm) },
  ];

  const systemInterpretation: PipelineLine[] = [
    {
      label: "Контекст",
      value: systemContextFor(item, perm),
    },
    ...retrievalInterpretationLines(item.platform_role, perm),
  ];

  const decision: PipelineLine[] = [
    { label: "RBAC / auth", value: rbacDecisionFor(item, perm) },
    {
      label: "Retrieval policy",
      value: `${retrieval.decision} — ${retrieval.reason}`,
    },
    { label: "Итог", value: resultLabelFor(item) },
  ];

  const consequences: PipelineLine[] = [
    { label: "HTTP-ответ", value: httpResponseFor(item) },
    { label: "Enforcement", value: enforcementFor(item) },
    { label: "Audit event", value: et },
    { label: "Статус audit", value: item.status ?? "success" },
  ];
  if (item.reason) {
    consequences.push({ label: "Причина", value: item.reason });
  }

  return {
    user,
    systemInterpretation,
    decision,
    consequences,
    timeline: chainSteps,
  };
}

export function formatPipelineEssence(lines: PipelineLine[]): string {
  return lines.map((l) => `${l.label}: ${l.value}`).join("\n");
}

export interface SecurityIoNarrative {
  prose: string;
  httpLine: string | null;
}

/** Операционная суть запроса (Text-style prose, не KV dump). */
export function buildUserRequestNarrative(
  item: AuditEventItem,
  scenario: SecurityScenarioView
): SecurityIoNarrative {
  const et = item.event_type || "";
  const actor = scenario.actorLabel;
  const role = scenario.roleLabel;
  const http =
    item.request_method && item.request_path
      ? `${item.request_method} ${item.request_path}`
      : null;

  let prose = "";
  if (et === "auth.login.success" || et === "auth.login.failure") {
    prose = `Пользователь ${actor} попытался войти в Admin UI по email/password.`;
  } else if (et === "auth.logout") {
    prose = `Пользователь ${actor} (${role}) завершил активную сессию.`;
  } else if (et === "security.access.denied") {
    prose =
      actor.includes("аноним") || !item.principal_email
        ? "Анонимный пользователь попытался получить доступ к защищённому endpoint."
        : `Пользователь ${actor} обратился к защищённому API без валидной сессии.`;
  } else if (et === "security.permission.denied") {
    const perm = scenario.permission ?? "требуемое permission";
    prose = `Оператор ${actor} (${role}) попытался выполнить операцию, требующую ${perm}.`;
  } else if (et.startsWith("privileged.retrieval.")) {
    prose = `Оператор ${actor} (${role}) попытался изменить настройки retrieval / backend.`;
  } else if (et.includes("audit") || (item.request_path || "").includes("/audit")) {
    prose = `Оператор ${actor} (${role}) попытался открыть audit events.`;
  } else if (et.startsWith("privileged.documents.")) {
    prose = `Оператор ${actor} (${role}) попытался выполнить операцию с корпусом документов.`;
  } else {
    prose = `${actor} (${role}) инициировал действие «${userIntentFor(item, scenario.permission)}».`;
  }

  return { prose, httpLine: http };
}

/** Операционная суть ответа системы (RBAC / retrieval / audit как решение). */
export function buildSystemResponseNarrative(
  item: AuditEventItem,
  scenario: SecurityScenarioView
): string {
  const et = item.event_type || item.action;
  const perm = scenario.permission;
  const retrieval = scenario.retrievalStory;
  const auditNote = `Audit event ${et} записан (status ${item.status ?? "success"}).`;

  if (et === "auth.login.success") {
    return `Доступ разрешён. Principal создан, session token выдан, ${auditNote}`;
  }
  if (et === "auth.login.failure") {
    return `Доступ запрещён. Учётные данные неверны, токен не выдан. ${auditNote}`;
  }
  if (et === "auth.logout") {
    return `Сессия завершена, токен отозван. ${auditNote}`;
  }
  if (et === "security.access.denied") {
    return `Доступ запрещён без аутентификации. Система вернула 401 и записала ${et}.`;
  }
  if (et === "security.permission.denied") {
    const permTxt = perm ? `«${perm}»` : "требуемое permission";
    const retrievalNote =
      retrieval && (scenario.category === "retrieval" || perm?.startsWith("retrieval:"))
        ? ` Retrieval policy: ${retrieval.decision} (${retrieval.allowedVisibility}).`
        : "";
    return `Доступ запрещён. Требуется permission ${permTxt}, у роли ${scenario.roleLabel} его нет.${retrievalNote} ${auditNote}`;
  }
  if (et.startsWith("privileged.retrieval.") && item.status === "success") {
    return `Доступ разрешён. RBAC пройден, изменение retrieval применено. Retrieval policy: ${retrieval?.decision ?? "—"}. ${auditNote}`;
  }
  if (et.startsWith("privileged.") && item.status === "success") {
    return `Доступ разрешён. RBAC и privileged route выполнены. ${auditNote}`;
  }
  if (item.status === "failure") {
    return `Операция заблокирована или завершилась ошибкой. ${httpResponseFor(item)}. ${auditNote}`;
  }
  return `${scenario.resultLabel}. ${enforcementFor(item)} ${auditNote}`;
}

export function securityTitleStatusTone(
  item: AuditEventItem,
  severity: SecuritySeverity
): "ok" | "warn" | "err" | "muted" {
  if (item.status === "failure") return "err";
  if (severity === "error" || severity === "critical") return "err";
  if (severity === "warning") return "warn";
  if (item.event_type?.includes("denied")) return "warn";
  return "ok";
}

function securityTimelineVariant(
  step: string,
  itemStatus: string
): AfPipelineStageVariant {
  const s = step.toLowerCase();
  if (
    s.includes("401") ||
    s.includes("403") ||
    s.includes("deny") ||
    s.includes("failure") ||
    s.includes("invalid")
  ) {
    return "error";
  }
  if (s.includes("issue_session") || s.includes("200") || s.includes("success")) {
    return "success";
  }
  if (s.includes("middleware") || s.includes("require_permission") || s.includes("authenticate")) {
    return "processing";
  }
  if (itemStatus === "failure") return "warning";
  return "muted";
}

function timelineStepStatusLabel(step: string, itemStatus: string): string {
  const s = step.toLowerCase();
  if (s.includes("401") || s.includes("403") || s.includes("deny") || s.includes("failure")) {
    return "error";
  }
  if (s.includes("issue_session") || s.includes("200") || s.includes("success")) {
    return "ok";
  }
  return itemStatus === "success" ? "ok" : "error";
}

function buildTimelineStepPayload(
  item: AuditEventItem,
  step: string,
  perm: string | null
): Record<string, unknown> {
  const s = step.toLowerCase();
  const details = item.details || {};
  if (s.includes("post ") || s.includes("http") || item.request_method) {
    return {
      method: item.request_method,
      path: item.request_path,
      route: "security",
    };
  }
  if (s.includes("middleware") || s.includes("anonymous")) {
    return {
      layer: "IdentityAuthMiddleware",
      principal: item.principal_email ?? "anonymous",
      authenticated: Boolean(item.principal_email),
    };
  }
  if (s.includes("require_permission") || s.includes("rbac")) {
    return {
      permission: perm,
      platform_role: item.platform_role,
      decision: perm ? `missing:${perm}` : "rbac_check",
    };
  }
  if (s.includes("authenticate") || s.includes("identityservice")) {
    return {
      action: item.action,
      auth_source:
        typeof details.auth_source === "string" ? details.auth_source : undefined,
    };
  }
  if (s.includes("401") || s.includes("403")) {
    return {
      http_status: s.includes("403") ? 403 : 401,
      event_type: item.event_type,
    };
  }
  if (s.includes("audit:") || s.includes("audit ")) {
    return {
      event_type: item.event_type,
      action: item.action,
      status: item.status,
    };
  }
  if (s.includes("retrieval")) {
    const story = retrievalPolicyStory(item.platform_role);
    return {
      retrieval_role: story.retrievalRole,
      visibility: story.allowedVisibility,
      scope: story.scope,
    };
  }
  if (s.includes("связано:")) {
    return { related_event: step.replace(/^связано:\s*/i, "") };
  }
  return {
    stage: step,
    event_type: item.event_type,
  };
}

export function buildTimelineSteps(
  item: AuditEventItem,
  chainSteps: string[],
  perm: string | null = null
): SecurityTimelineStep[] {
  const st = item.status ?? "success";
  return chainSteps.map((step) => ({
    label: step,
    variant: securityTimelineVariant(step, st),
    statusLabel: timelineStepStatusLabel(step, st),
    at: item.created_at,
    payload: buildTimelineStepPayload(item, step, perm),
    deltaMs: null,
  }));
}

/** Верхняя строка списка: short-result (Вход OK, 401, RBAC deny, …). */
export function listResultCompact(item: AuditEventItem, scenario: SecurityScenarioView): string {
  const et = item.event_type || "";
  if (et === "auth.login.success") return "Вход OK";
  if (et === "auth.login.failure") return "Login fail";
  if (et === "auth.logout") return "Logout";
  if (et === "security.access.denied") return "Доступ без аутентификации";
  if (et === "security.permission.denied") return "RBAC deny";
  if (item.status === "failure") return "Ошибка";
  if (scenario.resultLabel.includes("запрещ")) return "Access denied";
  return scenario.resultLabel;
}

/** Средняя строка: actor + intent (кто и что хотел сделать). */
export function listIntentTitle(
  item: AuditEventItem,
  scenario: SecurityScenarioView
): string {
  const actor = scenario.actorLabel;
  const perm = scenario.permission;
  const et = item.event_type || "";

  let intent = "";
  if (et === "auth.login.success" || et === "auth.login.failure") {
    intent = "попытка входа в Admin UI";
  } else if (et === "auth.logout") {
    intent = "завершение сессии";
  } else if (et === "security.access.denied") {
    intent = "попытка доступа к защищённому endpoint";
  } else if (et === "security.permission.denied") {
    intent = perm
      ? `попытка операции, требующей ${perm}`
      : "попытка привилегированной операции";
  } else if (et.startsWith("privileged.retrieval.")) {
    intent = "попытка изменения retrieval settings";
  } else if (et.includes("audit") || (item.request_path || "").includes("/audit")) {
    intent = "запрос audit events";
  } else if (et.startsWith("privileged.documents.")) {
    intent = "операция с корпусом документов";
  } else {
    const scope = retrievalPolicyStory(item.platform_role).scope;
    if (scope && scope !== "unrestricted" && scope !== "public_only") {
      intent = `запрос доступа к ${scope}`;
    } else {
      intent = userIntentFor(item, perm);
    }
  }
  return `${actor}: ${intent}`;
}

/** Нижняя строка: role · retrieval/scope · HTTP. */
export function listMetaLine(
  item: AuditEventItem,
  scenario: SecurityScenarioView
): string {
  const retrieval = scenario.retrievalStory;
  const role = scenario.roleLabel !== "—" ? scenario.roleLabel : "—";
  const retrievalPart = retrieval
    ? retrieval.scope === "unrestricted"
      ? "retrieval: unrestricted"
      : `scope: ${retrieval.scope}`
    : null;
  const http =
    item.request_method && item.request_path
      ? `${item.request_method} ${item.request_path}`
      : null;
  return [`role: ${role}`, retrievalPart, http].filter(Boolean).join(" · ");
}

function userIntentFor(item: AuditEventItem, perm: string | null): string {
  const et = item.event_type || "";
  if (et === "auth.login.success" || et === "auth.login.failure") {
    return "Войти в Admin UI (email/password)";
  }
  if (et === "auth.logout") return "Завершить сессию";
  if (et === "security.access.denied") {
    return `Получить доступ к ${item.request_path ?? "защищённому API"} без валидной сессии`;
  }
  if (et === "security.permission.denied" && perm) {
    return `Выполнить операцию, требующую ${perm}`;
  }
  if (et.startsWith("privileged.retrieval.")) {
    return "Изменить настройки retrieval / backend";
  }
  if (et.startsWith("privileged.documents.")) {
    return "Управлять корпусом документов";
  }
  return item.action || "Привилегированное действие";
}

function systemContextFor(item: AuditEventItem, perm: string | null): string {
  const et = item.event_type || "";
  if (et.startsWith("auth.login")) {
    return "IdentityService: проверка email/password, запись auth_login_events";
  }
  if (et === "security.access.denied") {
    return "IdentityAuthMiddleware: principal anonymous, маршрут требует аутентификации";
  }
  if (et === "security.permission.denied") {
    return `require_permission: principal аутентифицирован, permission ${perm ?? "?"} отсутствует`;
  }
  if (et.startsWith("privileged.")) {
    return "Privileged route: RBAC → service → audit hook";
  }
  return "Security layer: policy + audit";
}

function rbacDecisionFor(item: AuditEventItem, perm: string | null): string {
  const et = item.event_type || "";
  if (et === "auth.login.success") return "Учётные данные верны → principal создан";
  if (et === "auth.login.failure") return "Учётные данные неверны → principal не выдан";
  if (et === "auth.logout") return "Сессия активна → logout разрешён";
  if (et === "security.access.denied") return "Аутентификация отсутствует → deny";
  if (et === "security.permission.denied") {
    return perm ? `Permission «${perm}» не выдан → deny` : "Недостаточно прав → deny";
  }
  if (item.status === "success") return "RBAC: permission есть → allow";
  return "RBAC: проверка не пройдена";
}

function httpResponseFor(item: AuditEventItem): string {
  const et = item.event_type || "";
  if (et === "auth.login.failure") return "401 Unauthorized";
  if (et === "security.access.denied") return "401 Unauthorized";
  if (et === "security.permission.denied") return "403 Forbidden";
  if (et.startsWith("auth.login") && item.status === "success") {
    return "200 OK + Bearer token";
  }
  if (item.status === "success") return "2xx (операция выполнена)";
  return "4xx / ошибка";
}

function enforcementFor(item: AuditEventItem): string {
  const et = item.event_type || "";
  if (et === "security.access.denied" || et === "security.permission.denied") {
    return "Запрос отклонён до business logic";
  }
  if (et.startsWith("auth.login") && item.status === "failure") {
    return "Токен не выдан";
  }
  if (et === "auth.login.success") {
    return "Выдан session token; middleware принимает Bearer";
  }
  if (et.startsWith("privileged.retrieval.")) {
    return "Изменение применено к retrieval config";
  }
  if (et.startsWith("privileged.documents.")) {
    return "Операция с документом / индексом";
  }
  return item.status === "success" ? "Действие выполнено" : "Действие заблокировано";
}

export function buildScenarioChain(
  item: AuditEventItem,
  all: AuditEventItem[]
): string[] {
  const base = defaultChain(item);
  if (!item.execution_id) return base;
  const related = all
    .filter((x) => x.execution_id === item.execution_id && x.id !== item.id)
    .slice(0, 4)
    .map((x) => x.event_type);
  if (!related.length) return base;
  return [...base, ...related.map((e) => `связано: ${e}`)];
}

export function auditEventToScenario(
  item: AuditEventItem,
  allItems: AuditEventItem[] = []
): SecurityScenarioView {
  const perm = pickPermission(item.details || {});
  const et = item.event_type || item.action;
  const chainSteps = buildScenarioChain(item, allItems);
  const retrievalStory = retrievalPolicyStory(item.platform_role);

  return {
    id: item.id,
    category: categoryFor(et),
    title: titleFor(item),
    shortExplanation: shortExplanationFor(item, perm),
    severity: severityFor(item),
    resultLabel: resultLabelFor(item),
    actorLabel: item.principal_email ?? "анонимный запрос",
    roleLabel: roleLabelRu(item.platform_role),
    permission: perm,
    auditEventType: et,
    chainSteps,
    retrievalStory,
    pipeline: buildSecurityPipeline(item, perm, chainSteps),
  };
}

export function filterScenarios(
  items: AuditEventItem[],
  opts: {
    search: string;
    category: ScenarioCategory | "all";
    severity: SecuritySeverity | "all";
    status: string;
  }
): AuditEventItem[] {
  const q = opts.search.trim().toLowerCase();
  return items.filter((it) => {
    const sc = auditEventToScenario(it, items);
    if (opts.category !== "all" && sc.category !== opts.category) return false;
    if (opts.severity !== "all" && sc.severity !== opts.severity) return false;
    if (opts.status && it.status !== opts.status) return false;
    if (!q) return true;
    const blob = [
      sc.title,
      sc.shortExplanation,
      it.event_type,
      it.principal_email,
      it.platform_role,
      it.request_path,
      JSON.stringify(it.details),
    ]
      .join(" ")
      .toLowerCase();
    return blob.includes(q);
  });
}

export const CATEGORY_OPTIONS: Array<{ value: ScenarioCategory | "all"; label: string }> =
  [
    { value: "all", label: "все сценарии" },
    { value: "auth", label: "Auth" },
    { value: "rbac", label: "RBAC" },
    { value: "retrieval", label: "Retrieval / LLM" },
    { value: "documents", label: "Documents" },
    { value: "other", label: "прочее" },
  ];

export const SEVERITY_OPTIONS: Array<{ value: SecuritySeverity | "all"; label: string }> =
  [
    { value: "all", label: "все уровни" },
    { value: "info", label: "info" },
    { value: "warning", label: "warning" },
    { value: "error", label: "error" },
    { value: "critical", label: "critical" },
  ];
