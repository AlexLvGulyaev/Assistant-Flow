import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { fetchAuthMe, postLogin, postLogout } from "./api";
import { setUnauthorizedHandler } from "./token";
import type { AuthMeResponse, AuthMode } from "./types";

export interface AuthState {
  loading: boolean;
  authenticated: boolean;
  authMode: AuthMode;
  email: string | null;
  userId: string | null;
  platformRole: string | null;
  permissions: string[];
  hint: string | null;
  /** В режиме required без сессии — нужен login. */
  needsLogin: boolean;
  /** Login доступен (optional/required). */
  loginAvailable: boolean;
  refresh: () => Promise<void>;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

function deriveFromMe(me: AuthMeResponse): Omit<
  AuthState,
  "loading" | "refresh" | "login" | "logout"
> {
  const authMode = me.auth_mode;
  const authenticated =
    authMode === "disabled" ? true : Boolean(me.authenticated);
  const needsLogin = authMode === "required" && !me.authenticated;
  const loginAvailable = authMode !== "disabled";

  return {
    authenticated,
    authMode,
    email: me.email ?? null,
    userId: me.user_id ?? null,
    platformRole: me.platform_role ?? null,
    permissions: me.permissions ?? [],
    hint: me.hint ?? null,
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
    async (email: string, password: string) => {
      await postLogin(email, password);
      await refresh();
    },
    [refresh]
  );

  const logout = useCallback(async () => {
    await postLogout();
    await refresh();
  }, [refresh]);

  const value = useMemo<AuthState>(
    () => ({
      loading,
      ...core,
      refresh,
      login,
      logout,
    }),
    [loading, core, refresh, login, logout]
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
