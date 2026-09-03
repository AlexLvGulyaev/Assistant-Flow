export type AuthMode = "disabled" | "optional" | "required";

export interface AuthMeResponse {
  authenticated: boolean;
  auth_mode: AuthMode;
  auth_enforced?: boolean;
  path_public?: boolean;
  user_id: string | null;
  email: string | null;
  platform_role: string | null;
  retrieval_role?: string | null;
  permissions: string[];
  auth_source?: string | null;
  principal?: Record<string, unknown> | null;
  hint?: string;
}

/** GET /api/auth/whoami — проверка Bearer-токена (демо-стандарт APL). */
export interface WhoamiResponse {
  role: string;
  is_demo: boolean;
  auth_source: string | null;
  email: string | null;
  display_name: string | null;
}
