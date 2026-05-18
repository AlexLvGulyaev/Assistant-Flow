# Session: README v2 final operational polish + documentation wiring

**Дата:** 2026-05-18  
**Задача:** `cursor_tasks_local/2026-05-18_readme_v2_final_polish_for_cursor.md`  
**Изменённые файлы:** `README.md`, `readme_v_2_draft_for_cursor.md`, `RUNBOOK.md`

---

## Исходный промпт (задача)

Последний documentation wiring pass перед GitHub v2.0:

1. Добавить кликабельные ссылки на `RUNBOOK.md` и `USER_GUIDE.md` (draft, «в разработке»).
2. Убрать server-contour noise из README (Traefik, `.env.server`, `docker-compose.assistant.yml`, предупреждения о смешивании контуров).
3. Оставить только canonical portfolio compose-команду.
4. Добавить короткий user-flow (оператор → индексация → Telegram → RAG → диагностика в консоли).
5. Не упоминать `cursor_tasks_local`, `docs/cursor_sessions`, внутренние артефакты.
6. Финальная языковая чистка.
7. Упростить Roadmap до 3–5 направлений.

Не менять архитектурную диаграмму, не удалять раздел про кэш, не трогать код, без rebuild.

---

## Журнал выполнения

- Обновлена таблица «Документация проекта»: добавлены `RUNBOOK.md`, `USER_GUIDE.md` с относительными ссылками; убрана строка про `docs/cursor_sessions/`.
- Удалены из README: подраздел Server-контур, упоминания Traefik/HTTPS, server-compose в инфраструктуре и дереве проекта, дублирующий «Пример сценария работы».
- Server-контур перенесён в `RUNBOOK.md` §8.
- Добавлен блок «Типовой сценарий работы» (5 шагов) перед «Архитектура платформы».
- Roadmap сжат до 5 пунктов со ссылкой на Runbook.
- Развёртывание: только canonical compose + ссылка на RUNBOOK.
- В дереве проекта добавлены `RUNBOOK.md`, `USER_GUIDE.md`; убран `docker-compose.assistant.yml`.
- Синхронизирован `readme_v_2_draft_for_cursor.md`.

---

## README final polish report

1. **Удалено из README:** подраздел «Server-контур (production / Traefik)»; строки про Traefik, server-compose, `.env.server`, внешние сети; `docker-compose.assistant.yml` из дерева; упоминание `docs/cursor_sessions/` и «RUNBOOK/USER_GUIDE пока не вынесены»; развёрнутый Roadmap с подзаголовками; секция «Пример сценария работы» (дублировала новый flow).
2. **Перенесено в RUNBOOK:** §8 «Server-контур (production)» — `docker-compose.assistant.yml`, Traefik/HTTPS, `.env.server`, предупреждение о смешивании с portfolio.
3. **Documentation section:** таблица с кликабельными `RUNBOOK.md`, `USER_GUIDE.md`, `ARCHITECTURE`, `OPERATIONS`, `PROJECT_STATE`, `docs/architecture/`; статус «в разработке» в формулировках задачи сохранён.
4. **User-flow:** раздел `## Типовой сценарий работы` — после «Анализ качества RAG», перед «Архитектура платформы».
5. **Язык:** «инженерию AI-платформ» → «проектирование мультимодальных AI-систем»; «retrieval» в комментарии дерева → «поиск»; инфраструктура без server-контура.
6. **Future cleanup:** английские UI-лейблы (`Retrieval Settings`, faithfulness/relevance в RAG-секции); `retrieval_security` в статусе; возможное слияние `docs/OPERATIONS.md` и RUNBOOK при зрелости v1.

---

## Operator commands

```text
Rebuild не требуется: изменена только документация.
```
