import type { AuthMode } from "./types";

/** RBAC в UI совпадает с backend: disabled / anonymous optional — без ограничений. */
export function rbacUiEnforced(
  authMode: AuthMode,
  authenticated: boolean
): boolean {
  if (authMode === "disabled") return false;
  if (authMode === "optional" && !authenticated) return false;
  return true;
}

export function hasPermission(
  permissions: string[],
  permission: string,
  authMode: AuthMode,
  authenticated: boolean
): boolean {
  if (!rbacUiEnforced(authMode, authenticated)) return true;
  return permissions.includes(permission);
}

export const PERM = {
  documentsRead: "documents:read",
  documentsWrite: "documents:write",
  documentsReindex: "documents:reindex",
  logsRead: "logs:read",
  logsForensic: "logs:forensic",
  retrievalRead: "retrieval:read",
  retrievalAdmin: "retrieval:admin",
  settingsRead: "settings:read",
  settingsWrite: "settings:write",
  auditRead: "audit:read",
} as const;
