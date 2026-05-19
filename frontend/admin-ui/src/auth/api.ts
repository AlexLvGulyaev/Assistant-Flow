const DEFAULT_BASE = "http://localhost:8600";

function getApiBaseUrl(): string {
  const raw = import.meta.env.VITE_ADMIN_API_BASE_URL;
  if (typeof raw === "string" && raw.trim()) {
    return raw.replace(/\/+$/, "");
  }
  return DEFAULT_BASE;
}
import type { AuthMeResponse, LoginResponse } from "./types";
import { getAccessToken, notifyUnauthorized, setAccessToken } from "./token";

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

export async function postLogin(
  email: string,
  password: string
): Promise<LoginResponse> {
  const res = await fetch(`${getApiBaseUrl()}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (res.status === 401) {
    const body = await res.json().catch(() => ({}));
    const detail =
      typeof body?.detail === "string"
        ? body.detail
        : "Неверный email или пароль";
    throw new Error(detail);
  }
  if (!res.ok) {
    throw new Error(`Вход: ${res.status}`);
  }
  const data = await parseJson<LoginResponse>(res);
  setAccessToken(data.access_token);
  return data;
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
