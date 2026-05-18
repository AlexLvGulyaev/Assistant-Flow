# Session: README v2 architecture + readability hard-fix

**Дата:** 2026-05-18  
**Задача:** `cursor_tasks_local/2026-05-18_readme_v2_architecture_fix.md`  
**Изменённые файлы:** `README.md`, `readme_v_2_draft_for_cursor.md` (синхронизирован с README)

---

## Исходный промпт (задача)

После final polish README review выявил критичные проблемы перед GitHub v2.0:

1. **Нет архитектурной ASCII-диаграммы** — раздел «Архитектура» перегружен текстом.
2. **`legacy/` в публичной структуре проекта** — убрать без сносок и объяснений.
3. **Мультимодальность недооценена** — README читается RAG-first; нужен абзац: текст/аудио/изображения раньше RAG, RAG встроен в платформу.
4. **Англо-русские конструкции** — «контур retrieval», retrieval backend, runtime, metadata, retrieval cache и т.п.
5. **Лишние low-level operational детали** — invalidation, `RAG_RETRIEVAL_GENERATION`, глубокие env-таблицы; сохранить compose, порты, env overview.

**Обязательно:** ASCII/text diagram сразу после `## Архитектура платформы`, до подразделов; элементы: Telegram, Admin UI, orchestrator, multimodal routing, retrieval, memory, AI providers, vector storage, PostgreSQL, observability.

**Жёсткое требование:** без диаграммы задача не выполнена.

---

## Журнал выполнения

1. В начало README добавлен абзац о мультимодальной истории платформы (до «Бизнес-сценарий»).
2. Переупорядочен список возможностей в бизнес-сценарии: текст/голос/изображения перед RAG.
3. После `## Архитектура платформы` вставлена ASCII-схема верхнего уровня (Telegram + Admin UI → бот/API → оркестратор → Текст/Аудио/Изображения/RAG/Память → провайдеры → Chroma/FAISS/Weaviate + PostgreSQL + логи/телеметрия).
4. Подразделы архитектуры сжаты до коротких абзацев.
5. Из дерева проекта удалена строка `legacy/`; у `admin_ui/` убрана отсылка к legacy.
6. Секция кэша сокращена (убраны bump generation, runtime invalidation, детальный HIT/MISS narrative).
7. Таблицы env для vector/cache сведены в одну строку со ссылкой на `.env.example`.
8. Language cleanup по всему README (retrieval → поиск по KB / RAG где уместно).
9. Исправлен комментарий в bash-блоке health-check (`##` → `#`).
10. Roadmap: исправлена иерархия заголовков (`### Ближайшие направления`).
11. `readme_v_2_draft_for_cursor.md` синхронизирован копией `README.md`.

---

## README architecture fix report

1. **Диаграмма добавлена:** да, ASCII/text block в fenced code block.
2. **Размещение:** сразу после заголовка `## Архитектура платформы` и вводного предложения, **до** `### Пользовательский контур`.
3. **Элементы на схеме:** Telegram, Admin UI (React), Telegram-бот, Admin API, оркестратор запросов, маршрутизация Текст/Аудио (STT/TTS)/Изображения/RAG/Память диалога, AI-провайдеры (OpenAI, GigaChat, Proxy API), векторные хранилища (Chroma/FAISS/Weaviate), PostgreSQL (метаданные, сессии, документы), логи и телеметрия в консоли.
4. **Legacy удалён:** да, `legacy/` убран из блока «Структура проекта»; упоминаний migration/historical compatibility нет.
5. **Мультимодальность:** абзац под H1; переупорядочен список в бизнес-сценарии; на диаграмме явно три модальности + RAG как равноправные ветки оркестратора.
6. **Замены языка (примеры):** «контур retrieval» / «retrieval backend» → «поиск по базе знаний», «backend векторного поиска»; «retrieval precision» → «точность поиска»; «metadata» → «метаданные»; «runtime» → «во время работы»; «retrieval cache» / длинный cache-runbook → короткий абзац + ссылка на design doc; «подключает retrieval» → «подключает поиск по базе знаний».
7. **Сокращённые operational-секции:** «Кэширование…» (с ~15 строк до ~3); env — убраны отдельные таблицы Retrieval cache и детальный vector block (оставлена сводная строка); архитектурные подразделы — списки заменены краткими абзацами.
8. **Кандидаты на future cleanup:** имена UI-маршрутов на английском (`Retrieval Settings`, OFF/MISS/HIT); `services/` в дереве с «retrieval»; отдельные RUNBOOK/USER_GUIDE; возможное вынесение Admin UI table в сжатую таблицу; Streamlit `admin_ui/` в дереве (исторический, но не legacy-нарратив).
9. **Ещё один review-pass:** желателен лёгкий проход на повторяемость «RAG» vs «база знаний» и длину Roadmap; для GitHub v2.0 текущий уровень достаточен.

---

## Operator commands

```text
Rebuild не требуется: изменена только документация.
```

Проверка локально: открыть `README.md` на GitHub preview или `grip`/IDE markdown preview; убедиться, что ASCII-блок не ломает ширину (monospace, ~80 cols).
