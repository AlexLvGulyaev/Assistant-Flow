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
  { path: "/", label: "Overview", end: true },
  { path: "/summary", label: "Summary" },
  { path: "/text", label: "Text", placeholder: true },
  { path: "/rag", label: "RAG", placeholder: true },
  { path: "/images", label: "Images", placeholder: true },
  { path: "/audio", label: "Audio", placeholder: true },
  { path: "/documents", label: "Documents", placeholder: true },
  { path: "/logs", label: "Logs" },
];
