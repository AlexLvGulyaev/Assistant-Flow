import { PERM } from "../auth/permissions";

export interface NavItem {
  /** Router path (relative to site root), e.g. "/" or "/logs" */
  path: string;
  label: string;
  /** Эмодзи-иконка пункта (меню-канон APL: эмодзи + текст, без `◇`). */
  icon: string;
  /** NavLink `end` — only «Панель состояния» uses true */
  end?: boolean;
  /** Not wired to API yet */
  placeholder?: boolean;
  /** Minimum permission to show in sidebar (P9.6e). Omit = visible to all authenticated. */
  requiredPermission?: string;
}

export interface NavGroup {
  title: string;
  items: NavItem[];
}

/**
 * Меню-канон APL (shared/patterns/admin-menu-canon.md):
 * Система → Ядро (проектное имя) → Аналитика → Наблюдаемость → Справка.
 *
 * AF-раскладка (утверждена владельцем 2026-09-03):
 *  - Ядро = «База знаний» (Документы — индекс Chroma);
 *  - RAG — модальность (в ТГ выбирается наряду с текстом);
 *  - «Обзор» = health/readiness рантаймов → «Панель состояния» в «Системе»;
 *  - Memory (журнал сессий памяти) — в «Наблюдаемости»;
 *  - аудит — канонное имя «Журнал аудита».
 */
export const NAV_GROUPS: NavGroup[] = [
  {
    title: "Система",
    items: [
      {
        path: "/",
        label: "Панель состояния",
        icon: "🩺",
        end: true,
        requiredPermission: PERM.documentsRead,
      },
      {
        path: "/retrieval",
        label: "Retrieval Settings",
        icon: "⚙️",
        requiredPermission: PERM.retrievalRead,
      },
    ],
  },
  {
    title: "База знаний",
    items: [
      {
        path: "/documents",
        label: "Документы",
        icon: "📄",
        requiredPermission: PERM.documentsRead,
      },
    ],
  },
  {
    title: "Модальности",
    items: [
      { path: "/text", label: "Текст", icon: "💬", requiredPermission: PERM.logsRead },
      { path: "/rag", label: "RAG", icon: "🔎", requiredPermission: PERM.logsRead },
      {
        path: "/images",
        label: "Изображения",
        icon: "🖼️",
        requiredPermission: PERM.documentsRead,
      },
      { path: "/audio", label: "Аудио", icon: "🔊", requiredPermission: PERM.documentsRead },
    ],
  },
  {
    title: "Аналитика",
    items: [
      {
        path: "/summary",
        label: "Сводка",
        icon: "📊",
        requiredPermission: PERM.documentsRead,
      },
      {
        path: "/evaluation",
        label: "Анализ RAG",
        icon: "🧪",
        requiredPermission: PERM.logsRead,
      },
    ],
  },
  {
    title: "Наблюдаемость",
    items: [
      { path: "/logs", label: "Логи", icon: "📜", requiredPermission: PERM.logsRead },
      { path: "/memory", label: "Memory", icon: "🧠", requiredPermission: PERM.logsRead },
      {
        path: "/audit",
        label: "Журнал аудита",
        icon: "📋",
        requiredPermission: PERM.auditRead,
      },
    ],
  },
  {
    title: "Справка",
    items: [{ path: "/legend", label: "Обозначения", icon: "🗺️" }],
  },
];

/** Permission-filtered nav groups for sidebar (nav hint only; routes stay registered). */
export function navGroupsForPermissions(
  hasPermission: (permission: string) => boolean
): NavGroup[] {
  return NAV_GROUPS.map((group) => ({
    title: group.title,
    items: group.items.filter(
      (item) => !item.requiredPermission || hasPermission(item.requiredPermission)
    ),
  })).filter((group) => group.items.length > 0);
}