# Session log: RAG-console retrieval-ready query observability (2026-05-11)

## Verbatim development prompt

Cursor, продолжаем развитие operational observability для RAG-console.

Нужно реализовать диагностику retrieval-ready query — то есть показывать, какой именно запрос реально ушёл в retrieval после:

* route selection,
* memory injection,
* query rewrite / expansion.

Сейчас в RAG-console пользователь видит:

* raw user query,
* retrieved chunks,
* final answer.

Но отсутствует критически важный слой observability:

* transformed retrieval query.

Это мешает анализировать:

* почему retrieval был вызван,
* почему retrieval не был вызван,
* почему retrieval вернул именно такие чанки,
* где ошибка: routing / rewrite / retrieval / LLM.

---

## ЦЕЛЬ

В панели:
"Что спросил пользователь"

нужно сделать интерактивное раскрытие retrieval-query.

---

## UI / UX

Сейчас под user query есть серая подпись:
"RAG-запрос"

Нужно:

1. Сделать её НЕ серой подписью,
   а синей action-ссылкой / кнопкой
   в стиле operational console.

Например:
[RAG-запрос ▼]

или
[RAG-запрос]

2. По нажатию:
   expand / collapse panel.

3. В раскрытии показывать:
   retrieval-ready query,
   который реально ушёл в retrieval backend.

---

## ВАЖНО

Нужно показывать НЕ raw user query,
а именно transformed query:

* после memory/context injection;
* после route processing;
* после query rewrite/expansion;
* после любых retrieval transformations.

То есть именно тот query,
который реально был отправлен в:

* Weaviate,
* Chroma,
* FAISS,
  и т.д.

---

## ПОВЕДЕНИЕ

1. Если retrieval НЕ вызывался:

* кнопку не показывать вообще.

2. Если transformed query полностью совпадает
   с raw user query:

* кнопку можно скрывать,
  ИЛИ
* показывать, но в collapsed виде без смысла раскрытия.
  (реши аккуратно по UX)

3. Если retrieval query отличается:

* раскрытие обязательно должно быть доступно.

---

## ПРИМЕР

User:
"Там — это где?"

Expanded retrieval query:
"Assistant Flow индексация документов"

Именно это должно стать видимым.

---

## АРХИТЕКТУРНО

Нужно:

1. Найти место,
   где формируется retrieval query.

2. Сохранить его в diagnostics / telemetry.

3. Передать в API.

4. Отобразить в UI.

---

## СТАНДАРТЫ CONSOLE

Соблюдать существующий standard:

* dark operational UI;
* same spacing;
* same expand/collapse style;
* same typography;
* same JSON/diagnostic conventions.

Не делать отдельный визуальный стиль.

---

## ОСОБО ВАЖНО

Это НЕ cosmetic feature.

Это retrieval observability layer.

Нужно реализовать аккуратно и архитектурно правильно,
без хардкода под конкретный backend.

---

## PS

Текст данного prompt ОБЯЗАТЕЛЬНО включить в session log / progress log текущей сессии разработки.

---

## Implementation notes (this session)

- Backend: `RagRequestDiagnostics.retrieval_ready_query` is populated from the string passed into `_retrieve_raw` (`retrieval_query` in `answer()`, argument to `retrieve()`), with `_retrieval_ready_query_for_logs` (cap + simple secret-pattern redaction) before persistence in `to_log_details()`.
- Stdout: `emit_stdout()` logs `retrieval_ready_query_len` and a short preview when the field is set.
- Admin UI: under «ЧТО СПРОСИЛ ПОЛЬЗОВАТЕЛЬ», a `<details>` with `log-details__summary` / `log-details__json` is shown only when `retrieval_ready_query` exists in merged session details **and** normalized whitespace differs from the displayed user query (so identical strings hide the control; absence of the field implies no telemetry or no retrieval-ready capture — no control).
