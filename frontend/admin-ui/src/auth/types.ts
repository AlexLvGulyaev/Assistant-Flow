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

export interface LoginResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  user_id: string;
  email: string | null;
  platform_role: string;
}
