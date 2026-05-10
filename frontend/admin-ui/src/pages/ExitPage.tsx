import { Link } from "react-router-dom";

/**
 * Frontend-only «выход»: не вызывает API и не останавливает бэкенд.
 */
export function ExitPage() {
  return (
    <div className="exit-screen">
      <div className="exit-screen__card">
        <h1 className="exit-screen__title">Вы вышли из административной консоли</h1>
        <p className="exit-screen__lead muted">
          Это действие только закрывает режим консоли в браузере. Сервер и сервисы продолжают
          работать.
        </p>
        <Link to="/" className="exit-screen__return">
          Вернуться в консоль
        </Link>
      </div>
    </div>
  );
}
