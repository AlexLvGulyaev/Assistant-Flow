# Session log: PROJECT_STATE §47.4 — Retrieval Quality Engineering backlog

**Date:** 2026-05-14 (`date +%F`)

---

## Full prompt (verbatim)

Cursor, нужно обновить `PROJECT_STATE.md`, раздел:

`## 47. Предложения по развитию`

Это накопительный engineering backlog / roadmap Assistant Flow.

Важно:

* НЕ менять номер раздела 47;
* НЕ создавать новый верхнеуровневый раздел;
* НЕ переписывать старые `47.*`;
* добавить новую запись в конец раздела как следующий свободный подраздел `### 47.k`;
* сохранить стиль существующих записей;
* НЕ использовать слова:

  * "куратор",
  * "проверка",
  * "домашнее задание",
  * "учебный модуль",
  * любые ссылки на образовательный контекст.

Запись должна выглядеть как внутреннее engineering/planning решение проекта.

Нужно зафиксировать следующие направления развития Retrieval Quality Engineering:

1. Контроль overlap между chunk-фрагментами.
2. Эксперименты с различным размером chunk_size.
3. Сравнение влияния chunk_size:

   * на retrieval distance;
   * на retrieval quality;
   * на качество ответов модели.
4. Retrieval quality metrics в Admin UI:

   * precision@k;
   * irrelevant chunk rate;
   * duplicate chunk rate;
   * retrieval noise indicators.
5. Диагностика semantic duplication и контроль повторяющихся чанков при retrieval.

Структура новой записи:

* **Objective**
* **Planned work**
* **Architectural implications**
* **Operational implications**
* **Current status**

Статус:
`planned`

Допускается указать:
`partially implemented`
только для already existing retrieval diagnostics / chunk inspection / observability features.

Важно:
это roadmap-item,
а не описание уже реализованной функциональности.

Дополнительно:

* создать session log в `docs/cursor_sessions/`;
* включить туда полный текст prompt;
* добавить в конец:
  `## Operator commands / next verification commands`
  согласно operational rules проекта;
* commit НЕ выполнять.

---

## What was done

- **`PROJECT_STATE.md`:** appended **`### 47.4`** after **`### 47.3`** (next free `k` was **4**), before **`## 48`**. Section **47** title and **47.1–47.3** unchanged.
- **Session log:** this file.

---

## Operator commands / next verification commands

```bash
date +%F
rg -n "^## 47\\.|^### 47\\." PROJECT_STATE.md
```

Просмотр вставленного блока **47.4** в редакторе / diff: убедиться, что раздел **48** следует сразу после нового `---` и что нумерация **47.1–47.4** корректна.

---

## Commit

Not performed (per request).
