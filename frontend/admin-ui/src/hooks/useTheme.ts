import { useEffect, useState } from "react";

/*
 * Тема день/ночь по канону APL
 * (shared/patterns/admin-console-dual-theme-mirror-inversion.md):
 * localStorage 'ai-theme', дефолт dark, dataset.theme на <html> синхронно.
 * Модульный стор + слушатели: несколько потребителей хука (App и Sidebar)
 * видят одно значение и не откатывают тему при ре-рендере.
 */
const STORAGE_KEY = "ai-theme";
const DEFAULT_THEME = "dark";

type Theme = "dark" | "light";

function readInitial(): Theme {
  try {
    return localStorage.getItem(STORAGE_KEY) === "light" ? "light" : DEFAULT_THEME;
  } catch {
    return DEFAULT_THEME;
  }
}

let currentTheme: Theme = readInitial();
const listeners = new Set<() => void>();

function applyTheme(theme: Theme) {
  document.documentElement.dataset.theme = theme;
}

function setTheme(theme: Theme) {
  currentTheme = theme;
  try {
    localStorage.setItem(STORAGE_KEY, theme);
  } catch {
    /* приватный режим — тема живёт до перезагрузки */
  }
  applyTheme(theme);
  listeners.forEach((listener) => listener());
}

applyTheme(currentTheme);

export function useTheme() {
  const [theme, setLocalTheme] = useState<Theme>(currentTheme);

  useEffect(() => {
    const listener = () => setLocalTheme(currentTheme);
    listeners.add(listener);
    return () => {
      listeners.delete(listener);
    };
  }, []);

  return {
    theme,
    toggle: () => setTheme(currentTheme === "dark" ? "light" : "dark"),
  };
}