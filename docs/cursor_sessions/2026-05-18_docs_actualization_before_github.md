# Session: Actualize docs/ before GitHub v2.0

**Дата:** 2026-05-18  
**Задача:** `cursor_tasks_local/2026-05-18_docs_actualization_before_github.md`  
**Изменённые файлы:** `docs/ARCHITECTURE.md`, `docs/OPERATIONS.md`, `docs/GITHUB_PREP.md`, `docs/SECURITY_NOTES.md`, `docs/ADMIN_INDEXING.md`, `docs/RAG_SMOKE_TEST.md`, `docs/DEMO_SCENARIOS.md`

---

## Исходный промпт (кратко)

Актуализировать `docs/` под README v2, RUNBOOK, portfolio-compose, FastAPI+React Admin UI; убрать Streamlit как текущий UI; server/Traefik — только advanced; без секретов и публичной навигации на `cursor_sessions`; без изменения кода и rebuild.

---

## docs actualization report

1. **Изменённые документы:** все семь целевых файлов в `docs/` (см. список выше).

2. **Удалённые устаревшие утверждения:**
   - Streamlit как текущая админка (ARCHITECTURE, OPERATIONS);
   - обобщённый `docker compose up` без `-p portfolio-test`;
   - ADMIN_INDEXING только как CLI без Admin UI;
   - DEMO_SCENARIOS на английском без portfolio/UI/cache сценариев;
   - GITHUB_PREP v1 без RUNBOOK/USER_GUIDE/screenshots v2;
   - ссылка на session logs в публичной навигации (не добавлялась).

3. **Streamlit → FastAPI/React:** ARCHITECTURE и OPERATIONS — React `frontend/admin-ui/` + Admin API; Streamlit только как historical note в server advanced; ADMIN_INDEXING — путь через UI **Документы**.

4. **Canonical portfolio command:** зафиксирован в OPERATIONS, RAG_SMOKE_TEST, DEMO_SCENARIOS:
   `COMPOSE_BAKE=false docker compose -p portfolio-test -f docker-compose.portfolio.yml up -d --build --remove-orphans`

5. **Draft:** RUNBOOK.md и USER_GUIDE.md в корне остаются draft (не менялись в этой сессии); ссылки из README уже рабочие.

6. **Проверки выполнены:**
   - `git status --short`
   - `find docs -maxdepth 2 -type f | sort`
   - `ls` README, RUNBOOK, USER_GUIDE, PROJECT_STATE, compose, .env.example
   - `find docs/screenshots` — 15 PNG

7. **Review-pass:** лёгкий проход по `docs/architecture/*.md` и `PROJECT_STATE.md` при желании (вне scope задачи); основной набор для GitHub reviewer согласован.

---

## Operator commands

```text
Rebuild не требуется: изменена только документация.
```
