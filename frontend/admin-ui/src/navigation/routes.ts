import { PERM } from "../auth/permissions";

export interface NavItem {
  /** Router path (relative to site root), e.g. "/" or "/logs" */
  path: string;
  label: string;
  /** NavLink `end` — only Overview uses true */
  end?: boolean;
  /** Not wired to API yet */
  placeholder?: boolean;
  /** Minimum permission to show in sidebar (P9.6e). Omit = visible to all authenticated. */
  requiredPermission?: string;
}

/** Primary sidebar navigation (order matches legacy Streamlit tabs intent). */
export const NAV_ITEMS: NavItem[] = [
  { path: "/", label: "Обзор", end: true, requiredPermission: PERM.documentsRead },
  { path: "/summary", label: "Сводка", requiredPermission: PERM.documentsRead },
  { path: "/text", label: "Текст", requiredPermission: PERM.logsRead },
  { path: "/rag", label: "RAG", requiredPermission: PERM.logsRead },
  { path: "/images", label: "Изображения", requiredPermission: PERM.documentsRead },
  { path: "/audio", label: "Аудио", requiredPermission: PERM.documentsRead },
  { path: "/documents", label: "Документы", requiredPermission: PERM.documentsRead },
  { path: "/retrieval", label: "Retrieval Settings", requiredPermission: PERM.retrievalRead },
  { path: "/logs", label: "Логи", requiredPermission: PERM.logsRead },
  { path: "/memory", label: "Memory", requiredPermission: PERM.logsRead },
  { path: "/evaluation", label: "Анализ RAG", requiredPermission: PERM.logsRead },
  { path: "/audit", label: "Безопасность", requiredPermission: PERM.auditRead },
];

/** Permission-filtered nav for sidebar (nav hint only; routes stay registered). */
export function navItemsForPermissions(
  hasPermission: (permission: string) => boolean
): NavItem[] {
  return NAV_ITEMS.filter(
    (item) => !item.requiredPermission || hasPermission(item.requiredPermission)
  );
}
