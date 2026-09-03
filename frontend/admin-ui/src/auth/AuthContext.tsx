import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { fetchAuthMe, isDemoConfigured, postLogout, signInDemo, signInWithToken } from "./api";
import { hasPermission as checkPerm } from "./permissions";
import { setUnauthorizedHandler } from "./token";
import type { AuthMeResponse, AuthMode } from "./types";

export interface AuthState {
  loading: boolean;
  authenticated: boolean;
  authMode: AuthMode;
  email: string | null;
  userId: string | null;
  platformRole: string | null;
  displayName: string | null;
  permissions: string[];
  hint: string | null;
  /** Сессия открыта демо-токеном (витринный read-only вход). */
  isDemo: boolean;
  /** Демо-токен запечён при сборке — кнопка «Войти в демо-режиме» доступна. */
  demoAvailable: boolean;
  /** В режиме required без сессии — нужен login. */
  needsLogin: boolean;
  /** Login доступен (optional/required). */
  loginAvailable: boolean;
  refresh: () => Promise<void>;
  login: (token: string) => Promise<void>;
  loginDemo: () => Promise<void>;
  logout: () => Promise<void>;
  hasPermission: (permission: string) => boolean;
}

const AuthContext = createContext<AuthState | null>(null);

function deriveFromMe(me: AuthMeResponse): Omit<
  AuthState,
  "loading" | "refresh" | "login" | "loginDemo" | "logout" | "hasPermission"
> {
  const authMode = me.auth_mode;
  const authenticated =
    authMode === "disabled" ? true : Boolean(me.authenticated);
  const needsLogin = authMode === "required" && !me.authenticated;
  const loginAvailable = authMode !== "disabled";
  const principal = (me.principal ?? null) as { display_name?: string } | null;

  return {
    authenticated,
    authMode,
    email: me.email ?? null,
    userId: me.user_id ?? null,
    platformRole: me.platform_role ?? null,
    displayName: principal?.display_name ?? null,
    permissions: me.permissions ?? [],
    hint: me.hint ?? null,
    isDemo: (me.platform_role ?? "") === "demo",
    demoAvailable: isDemoConfigured(),
    needsLogin,
    loginAvailable,
  };
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [loading, setLoading] = useState(true);
  const [core, setCore] = useState(() =>
    deriveFromMe({
      authenticated: false,
      auth_mode: "disabled",
      user_id: null,
      email: null,
      platform_role: null,
      permissions: [],
    })
  );

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const me = await fetchAuthMe();
      setCore(deriveFromMe(me));
    } catch {
      setCore(
        deriveFromMe({
          authenticated: false,
          auth_mode: "required",
          user_id: null,
          email: null,
          platform_role: null,
          permissions: [],
          hint: "Не удалось проверить сессию",
        })
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    setUnauthorizedHandler(() => {
      void refresh();
    });
    return () => setUnauthorizedHandler(null);
  }, [refresh]);

  const login = useCallback(
    async (token: string) => {
      await signInWithToken(token);
      await refresh();
    },
    [refresh]
  );

  const loginDemo = useCallback(async () => {
    await signInDemo();
    await refresh();
  }, [refresh]);

  const logout = useCallback(async () => {
    await postLogout();
    await refresh();
  }, [refresh]);

  const hasPermission = useCallback(
    (permission: string) => {
      if (loading) return false;
      return checkPerm(
        core.permissions,
        permission,
        core.authMode,
        core.authenticated
      );
    },
    [loading, core.permissions, core.authMode, core.authenticated]
  );

  const value = useMemo<AuthState>(
    () => ({
      loading,
      ...core,
      refresh,
      login,
      loginDemo,
      logout,
      hasPermission,
    }),
    [loading, core, refresh, login, loginDemo, logout, hasPermission]
  );

  return (
    <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth вне AuthProvider");
  }
  return ctx;
}
