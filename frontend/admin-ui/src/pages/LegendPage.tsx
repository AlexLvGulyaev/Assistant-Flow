import { LEGEND_SECTIONS, LegendSection } from "./legendData";

function Help({ text }: { text: string }) {
  if (!text) return null;
  return (
    <span className="legend-help">
      <button type="button" className="legend-help__btn" aria-label="Где используется">
        ?
      </button>
      <span className="legend-help__pop">{text}</span>
    </span>
  );
}

function Section({ section }: { section: LegendSection }) {
  return (
    <div className="legend-panel">
      <h3 className="legend-panel__head">
        <span className="legend-panel__title">{section.title}</span>
        <Help text={section.where} />
      </h3>
      {section.rows.map((row) => (
        <div key={row.emoji + row.label} className="legend-row">
          {/* Канон RF: чип в легенде — эмодзи-only, лейбл в своей колонке. */}
          <span className="ai-status ai-status--emoji ai-status--icon-lg ai-status--muted" aria-hidden>
            {row.emoji}
          </span>
          <span className="legend-row__label">{row.label}</span>
          <span className="legend-row__note">{row.note}</span>
        </div>
      ))}
    </div>
  );
}

/**
 * «Справка → Обозначения» — канон RF LegendWorkspace / LQ legend:
 * интро-строка, сетка 3 колонки, панель = uppercase-заголовок +
 * «?»-хэлп «где используется», строка = эмодзи-чип (icon-lg) +
 * лейбл + пояснение. Новая семья чипов ⇒ секция здесь (правило паттерна).
 */
export function LegendPage() {
  return (
    <div className="page logs-page legend-page">
      <h1 className="page__title">Обозначения</h1>
      <p className="page__lead muted legend-intro">
        Единый значковый контракт консоли: значок задаёт смысл статуса и не меняется
        от экрана к экрану. В фильтрах значок стоит рядом с тем же значением.
      </p>
      <div className="legend-grid">
        {LEGEND_SECTIONS.map((section) => (
          <Section key={section.title} section={section} />
        ))}
      </div>
    </div>
  );
}