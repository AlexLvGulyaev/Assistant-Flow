import {
  DOC_STATUS,
  HEALTH,
  MODALITY,
  RETRIEVAL,
  SEVERITY,
  SESSION_ACTIVE,
  statusChip,
} from "../lib/chipContract";

/**
 * Данные «Справка → Обозначения». Секции выводят реальные семьи чипов
 * из lib/chipContract.ts (эмодзи-SOT); `where` проверен поиском по экранам:
 * где семья реально рендерится.
 */

export interface LegendRow {
  emoji: string;
  label: string;
  note: string;
}

export interface LegendSection {
  title: string;
  where: string;
  rows: LegendRow[];
}

/* Статусы — универсальный резолвер StatusBadge (исход события + состояние).
   Порядок строк — по смыслу: успех → работа → ожидание → внимание →
   ошибка → нейтрально. */
const STATUS_ROWS: LegendRow[] = (
  [
    ["ok", "проверка/состояние в норме"],
    ["succeeded", "выполнено без ошибок"],
    ["running", "операция выполняется"],
    ["queued", "стоит в очереди"],
    ["degraded", "работает с ограничением"],
    ["error", "операция упала — детали в «Логах» / «Журнале аудита»"],
    ["off", "выключено или отсутствует"],
  ] as Array<[string, string]>
).map(([code, note]) => ({
  emoji: statusChip(code).emoji,
  label: statusChip(code).label,
  note,
}));

const HEALTH_ROWS: LegendRow[] = (
  [
    ["ok", "компонент здоров"],
    ["warning", "компонент сообщает о проблеме"],
    ["degraded", "компонент работает с ограничением"],
    ["disabled", "компонент отключен конфигурацией"],
    ["unknown", "состояние недоступно"],
    ["error", "компонент в ошибке"],
  ] as Array<[string, string]>
).map(([code, note]) => ({
  emoji: HEALTH[code].emoji,
  label: HEALTH[code].label,
  note,
}));

const MODALITY_ROWS: LegendRow[] = (
  [
    ["rag", "ответ по базе знаний"],
    ["text", "текстовый запрос"],
    ["vision", "анализ изображения"],
    ["ocr", "распознавание текста на изображении"],
    ["image", "генерация изображения"],
    ["audio", "аудио: STT/TTS"],
    ["doc", "индексация документов"],
    ["mem", "память диалога"],
    ["test", "smoke-прогон (synthetic)"],
    ["log", "прочее служебное"],
  ] as Array<[string, string]>
).map(([code, note]) => ({
  emoji: MODALITY[code].emoji,
  label: MODALITY[code].label,
  note,
}));

const CACHE_ROWS: LegendRow[] = (
  [
    ["hit", "ответ отдан из кэша"],
    ["miss", "промах — запрос ушёл в поиск"],
    ["bypass", "запрос намеренно прошёл мимо кэша"],
    ["off", "кэш выключен конфигурацией"],
    ["na", "кэш-телеметрия недоступна"],
  ] as Array<[string, string]>
).map(([code, note]) => ({
  emoji: RETRIEVAL[code].emoji,
  label: RETRIEVAL[code].label,
  note,
}));

const DOC_ROWS: LegendRow[] = [
  ...(
    [
      ["draft", "документ ещё не загружен в индекс"],
      ["pending", "документ ждёт обработки"],
      ["processing", "индексация идёт"],
      ["indexed", "документ проиндексирован и участвует в поиске"],
      ["error", "ошибка индексации"],
      ["archived", "документ убран из индекса"],
    ] as Array<[string, string]>
  ).map(([code, note]) => ({
    emoji: DOC_STATUS[code].emoji,
    label: DOC_STATUS[code].label,
    note,
  })),
  { emoji: SESSION_ACTIVE.active.emoji, label: "ACTIVE", note: "активная версия документа" },
  { emoji: SESSION_ACTIVE.inactive.emoji, label: "в архиве", note: "неактивная версия документа" },
];

const SEVERITY_ROWS: LegendRow[] = (
  [
    ["info", "событие для сведения"],
    ["warning", "подозрительная активность или сбои"],
    ["error", "ошибка безопасности"],
    ["critical", "критическое событие (требует разбора)"],
  ] as Array<[string, string]>
).map(([code, note]) => ({
  emoji: SEVERITY[code].emoji,
  label: SEVERITY[code].label,
  note,
}));

export const LEGEND_SECTIONS: LegendSection[] = [
  {
    title: "Модальности",
    where: "Логи и Memory: маркер модальности в строке события/сессии; те же значки — в меню и на страницах модальностей.",
    rows: MODALITY_ROWS,
  },
  {
    title: "Состояние компонентов",
    where: "Панель состояния, Retrieval Settings, блоки readiness и LLM-провайдеров: состояние компонента.",
    rows: HEALTH_ROWS,
  },
  {
    title: "Кэш retrieval",
    where: "RAG, Анализ RAG, Retrieval Settings: результат retrieval-кэша в списках и карточках.",
    rows: CACHE_ROWS,
  },
  {
    title: "Документы и версии",
    where: "Документы: статус жизненного цикла в списке/карточке; ⚡/⏸️ — активная и неактивная версии.",
    rows: DOC_ROWS,
  },
  {
    title: "Статусы операций",
    where:
      "Панель состояния, Документы, RAG, Изображения, Аудио, Memory, Сводка, " +
      "Анализ RAG, Retrieval Settings: значок состояния в списках, карточках и kv-строках.",
    rows: STATUS_ROWS,
  },
  {
    title: "Серьёзность события",
    where: "Журнал аудита: значок серьёзности security-события в строке списка и в карточке сценария.",
    rows: SEVERITY_ROWS,
  },
];