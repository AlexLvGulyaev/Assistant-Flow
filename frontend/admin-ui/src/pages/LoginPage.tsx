import { FormEvent, useState } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";

export function LoginPage() {
  const { loading, needsLogin, login, authMode, hint } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const from =
    (location.state as { from?: string } | null)?.from ?? "/";

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!loading && !needsLogin) {
    return <Navigate to={from} replace />;
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(email.trim(), password);
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
        <header className="login-card__header">
          <h1 className="login-card__title">Admin console</h1>
          <p className="login-card__subtitle muted">
            Операторский вход · режим {authMode}
          </p>
        </header>

        <form className="login-form" onSubmit={onSubmit}>
          <label className="login-form__field">
            <span className="login-form__label">Email</span>
            <input
              type="email"
              name="email"
              autoComplete="username"
              className="login-form__input"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              disabled={submitting || loading}
            />
          </label>
          <label className="login-form__field">
            <span className="login-form__label">Пароль</span>
            <input
              type="password"
              name="password"
              autoComplete="current-password"
              className="login-form__input"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
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
        </form>

        <footer className="login-card__footer muted">
          {hint ? <p className="login-card__hint">{hint}</p> : null}
          <p>
            Первый запуск: задайте{" "}
            <code>INITIAL_ADMIN_EMAIL</code> и{" "}
            <code>INITIAL_ADMIN_PASSWORD</code> в окружении API.
          </p>
          {authMode === "optional" ? (
            <p>
              <Link to="/">Продолжить без входа</Link> (режим optional)
            </p>
          ) : null}
        </footer>
      </div>
    </div>
  );
}
