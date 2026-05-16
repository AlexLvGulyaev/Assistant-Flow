export interface NavItem {
  /** Router path (relative to site root), e.g. "/" or "/logs" */
  path: string;
  label: string;
  /** NavLink `end` — only Overview uses true */
  end?: boolean;
  /** Not wired to API yet */
  placeholder?: boolean;
}

/** Primary sidebar navigation (order matches legacy Streamlit tabs intent). */
export const NAV_ITEMS: NavItem[] = [
  { path: "/", label: "Обзор", end: true },
  { path: "/summary", label: "Сводка" },
  { path: "/text", label: "Текст" },
  { path: "/rag", label: "RAG" },
  { path: "/images", label: "Изображения" },
  { path: "/audio", label: "Аудио" },
  { path: "/documents", label: "Документы" },
  { path: "/retrieval", label: "Retrieval Settings" },
  { path: "/logs", label: "Логи" },
  { path: "/memory", label: "Memory" },
  { path: "/evaluation", label: "Evaluation" },
];
