// Относительные /api — тот же origin, nginx проксирует на admin-api
const DEFAULT_BASE = "";

function getApiBaseUrl(): string {
  const raw = import.meta.env.VITE_ADMIN_API_BASE_URL;
  if (typeof raw === "string" && raw.trim()) {
    return raw.replace(/\/+$/, "");
  }
  return DEFAULT_BASE;
}
import type { AuthMeResponse, WhoamiResponse } from "./types";
import { getAccessToken, notifyUnauthorized, setAccessToken } from "./token";

/** Build-time демо-токен для витринного входа (VITE_OPS_DEMO_TOKEN). */
const OPS_DEMO_TOKEN = import.meta.env.VITE_OPS_DEMO_TOKEN || "";

export function isDemoConfigured(): boolean {
  return Boolean(OPS_DEMO_TOKEN);
}

async function parseJson<T>(res: Response): Promise<T> {
  const text = await res.text();
  if (!text) {
    throw new Error(`Пустой ответ (${res.status})`);
  }
  try {
    return JSON.parse(text) as T;
  } catch {
    throw new Error(`Некорректный JSON (${res.status})`);
  }
}

export async function fetchAuthMe(): Promise<AuthMeResponse> {
  const headers = new Headers();
  const token = getAccessToken();
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  const res = await fetch(`${getApiBaseUrl()}/api/auth/me`, { headers });
  if (!res.ok) {
    throw new Error(`/api/auth/me: ${res.status}`);
  }
  return parseJson<AuthMeResponse>(res);
}

export async function signInWithToken(
  token: string
): Promise<WhoamiResponse> {
  // Демо-стандарт APL: вход по Bearer-токену через /api/auth/whoami.
  const trimmed = token.trim();
  if (!trimmed) {
    throw new Error("Введите токен.");
  }
  const res = await fetch(`${getApiBaseUrl()}/api/auth/whoami`, {
    headers: { Authorization: `Bearer ${trimmed}` },
  });
  if (res.status === 401) {
    throw new Error("Токен не принят. Проверьте, что токен указан верно.");
  }
  if (res.status === 403) {
    throw new Error("Недействительный токен.");
  }
  if (!res.ok) {
    throw new Error(`Ошибка авторизации (${res.status}).`);
  }
  const data = await parseJson<WhoamiResponse>(res);
  setAccessToken(trimmed);
  return data;
}

/** Вход в демо-режиме: запечённый при сборке read-only токен. */
export async function signInDemo(): Promise<WhoamiResponse> {
  if (!OPS_DEMO_TOKEN) {
    throw new Error("Демо-вход не настроен на этом экземпляре.");
  }
  return signInWithToken(OPS_DEMO_TOKEN);
}

export async function postLogout(): Promise<void> {
  const headers = new Headers();
  const token = getAccessToken();
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  try {
    await fetch(`${getApiBaseUrl()}/api/auth/logout`, {
      method: "POST",
      headers,
    });
  } finally {
    setAccessToken(null);
  }
}

export async function authAwareFetch(
  path: string,
  init?: RequestInit
): Promise<Response> {
  const headers = new Headers(init?.headers);
  const token = getAccessToken();
  if (token && !headers.has("Authorization")) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  const res = await fetch(`${getApiBaseUrl()}${path}`, { ...init, headers });
  if (res.status === 401 && token) {
    setAccessToken(null);
    notifyUnauthorized();
  }
  return res;
}
