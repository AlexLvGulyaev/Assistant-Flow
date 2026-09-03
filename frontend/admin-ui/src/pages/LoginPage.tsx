import { FormEvent, useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";

/** Канон логина админок APL (RF/AIC/LQ): токен + демо-вход + «К проекту». */
const PROJECT_URL = "https://ai.alex-n8n.site/cases/assistant-flow.html";

export function LoginPage() {
  const { loading, needsLogin, login, loginDemo, demoAvailable, authMode, hint } =
    useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const from =
    (location.state as { from?: string } | null)?.from ?? "/";

  const [token, setToken] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!loading && !needsLogin) {
    return <Navigate to={from} replace />;
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (!token.trim()) {
      setError("Введите токен.");
      return;
    }
    setSubmitting(true);
    try {
      await login(token);
      navigate(from, { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ошибка входа");
    } finally {
      setSubmitting(false);
    }
  }

  async function onDemo() {
    setError(null);
    setSubmitting(true);
    try {
      await loginDemo();
      navigate(from, { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ошибка входа");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="login-page">
      <div className="login-card">
        <div className="login-card__icon" aria-hidden>
          🤖
        </div>
        <h1 className="login-card__title">Assistant Flow Admin Console</h1>
        <p className="login-card__subtitle">
          Введите Bearer token для доступа к панели управления.
        </p>

        <form className="login-form" onSubmit={onSubmit} noValidate>
          <label className="login-form__field">
            <span
              className="login-form__label"
              title="Полный доступ к панели управления — по токену."
            >
              Bearer token
            </span>
            <input
              type="password"
              name="token"
              autoComplete="current-password"
              className="login-form__input"
              placeholder="Вставьте токен..."
              value={token}
              onChange={(e) => setToken(e.target.value)}
              disabled={submitting || loading}
            />
          </label>

          {error ? (
            <p className="login-form__error" role="alert">
              {error}
            </p>
          ) : null}

          <button
            type="submit"
            className="login-form__submit"
            disabled={submitting || loading}
          >
            {submitting ? "Вход…" : "Войти"}
          </button>
          {demoAvailable ? (
            <button
              type="button"
              className="login-form__btn login-form__btn--outline"
              title="Демо-режим: посмотрите консоль без прав изменения (read-only)."
              onClick={() => void onDemo()}
              disabled={submitting || loading}
            >
              Войти в демо-режим (только просмотр)
            </button>
          ) : null}
          <a
            className="login-form__btn login-form__btn--outline login-form__btn--home"
            href={PROJECT_URL}
            target="_blank"
            rel="opener"
            title="Вернуться на страницу проекта в витрине AIP."
          >
            К проекту
          </a>
        </form>

        <footer className="login-card__footer muted">
          {hint ? <p className="login-card__hint">{hint}</p> : null}
          {authMode === "disabled" ? (
            <p>Авторизация выключена (локальный режим без токенов).</p>
          ) : null}
        </footer>
      </div>
    </div>
  );
}