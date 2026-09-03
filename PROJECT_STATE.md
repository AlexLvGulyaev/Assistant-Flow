# 📊 PROJECT STATE — Assistant Flow

Паспорт состояния проекта (канон APL). Точка входа для любого агента, начинающего работу с кейсом.
Append-only инженерный журнал (хронология, инциденты, этапы P5–P9) — внутренний аналог task-history: [task_history/engineering_log.md](task_history/engineering_log.md).

---

## Project Summary

**Assistant Flow** — мультимодальная AI-платформа для работы с корпоративными знаниями: Telegram-ассистент (текст, RAG, OCR/Vision, голос STT/TTS, генерация изображений), корпоративная база знаний с управляемой индексацией и переключаемыми vector-бэкендами (Chroma / FAISS / Weaviate), операционная консоль (FastAPI Admin API + React Admin UI) с наблюдаемостью, оценкой качества RAG (RAGAS), памятью диалога и журналом аудита.

Позиционирование: `production-grade multimodal AI operations platform prototype` (single-tenant maturity stage). Принцип: operational-first / observability-first, без образовательных MVP-упрощений.

Стек: Python / FastAPI / PostgreSQL / ChromaDB / Weaviate / FAISS / React / Vite / Docker Compose; провайдеры OpenAI / GigaChat / ProxyAPI (embeddings отделены от chat).

---

## Current Status

**Стадия:** Портфельный актив в сопровождении (публичный репозиторий, живой инстанс).

- **Живой контур:** portfolio-стек `docker-compose.portfolio.yml`, compose-проект = имя каталога `assistant-flow`; сервисы `postgres`, `chroma`, `weaviate`, `assistant-flow` (бот), `admin-api`, `admin-ui`. Порт на витрину: `https://af-admin.alex-n8n.site` (traefik → `admin-ui`, same-origin `/api`).
- **Подсистемы в строю:** текстовый контур, RAG (включая полный текст чанка в UI), индексация с heavy-RAG safeguards (`ADMIN_UPLOAD_MAX_MB`), retrieval cache, память диалога, token economy в Summary, авторизация консоли (Bearer-токен + демо-вход read-only), журнал аудита (`admin_audit_log`), healthchecks, graceful degradation, multi-stage production-образы.
- **Security (P8/P9):** identity foundation, auth middleware hardening (P9.2 legacy-режимы), RBAC, audit trail, security console — реализованы и проверены (e2e 19/19 PASS).
- **Асинхронный слой (P5.3, вариант A):** очередь `async_jobs` (миграция 004) + воркер-поток внутри admin-api потребляет `rag_reindex`-задачи; enqueue/retry/список — через Admin API и панель «Фоновые задачи» в Документах; reclaim stale-`running` задач на старте.
- **Известные закрытые инциденты:** fd-leak chromadb HttpClient (утечка сокетов → unhealthy; закрыто 2026-09-03, паттерн в KB `shared/patterns/short-lived-chroma-http-client-fd-leak.md`); Chroma persistence bug (volume); Streamlit sticky/autoscroll (решено отказом от Streamlit).
- **Не решено:** heavy RAG на пике нагрузки (reindex + concurrent RAG) может деградировать на VPS 7.8 GiB RAM + 5 GiB swap; retrieval quality (простой chunking) — P5.5.

---

## Market Validation

Внешних клиентских заказов нет. Проект вырос из учебного контура (Module 5) и развивается как инженерный актив AI Automation Portfolio Lab. Рыночный сигнал — косвенный: платформа демонстрирует компетенции (RAG, мультимодальность, эксплуатация AI-систем), востребованные в других кейсах лаборатории.

---

## Commercial Assessment

- **Ценность:** витринный кейс «полноценная эксплуатация AI-системы» — не просто бот, а консоль оператора, аудит, качество RAG, безопасность. Основа для КП по корпоративным базам знаний и AI-ассистентам.
- **Коммерческие риски:** single-tenant (нет multi-tenant изоляции), heavy RAG на малых VPS, нет CI/CD и автоматических бэкапов.
- **Стоимость сопровождения:** один VPS (7.8 GiB RAM), стек ~820 MB памяти; поддержка — точечные доработки.

---

## Key Technology Areas

Компетенции (подтверждены): FastAPI Admin API, React/Vite консоль, PostgreSQL как source of truth, векторные хранилища (Chroma HTTP, Weaviate, FAISS), Telegram Bot API, мультимодальные провайдеры (OpenAI/GigaChat/ProxyAPI), Docker Compose (multi-stage), наблюдаемость (processing_logs / intake_events / telemetry), security-контур (token auth, RBAC, audit trail).

Дефициты: semantic/glossary-aware chunking, CI/CD, мониторинг и бэкапы инфраструктуры, multi-tenant.

---

## Decision

Проект сохраняется как **портфельный актив** лаборатории: живой инстанс используется как витрина (демо-вход read-only), публичный репозиторий — Source of Truth развёртывания (RUNBOOK). Долговой контур (PORTFOLIO_CORPUS_AUDIT v1.18): долги №3–№7 закрыты (№6 async layer — вариант A, воркер-поток в admin-api; №7 audio P5.4 remainder — hardening, telemetry, учёт стоимости).

---

## Next Steps

1. Deployment Validation в чистом окружении перед публикацией новой версии.
2. Решения владельца: удаление устаревших volumes/образов `portfolio-test_*`.

---

## Status History

| Дата | Статус | Событие |
|------|--------|---------|
| 2025–2026 | Разработка | Проект из Module 5 (уроки → операционная платформа) |
| 2026-08 | Кейс APL | Перенос из `/opt/assistant-flow/` в `cases/assistant-flow/` как самостоятельный git-репозиторий |
| 2026-09-02 | Активная разработка | Демо-стандарт APL (токен + демо-вход), публичный эндпойнт, token economy (долг №3), heavy-RAG safeguards, multi-version docs, production build (multi-stage, −25…−33%) |
| 2026-09-03 | Сопровождение | Инцидент fd-leak chroma HttpClient закрыт; KB-паттерн; актуализация документации по стандартам APL |
| 2026-09-03 | Разработка | Долг №6 закрыт: async-воркер (вариант A) — очередь `async_jobs`, панель «Фоновые задачи», enqueue/retry API |
| 2026-09-03 | Разработка | Долг №7 закрыт: аудио-контур — таймауты/ретраи OpenAI STT/TTS, оценочная стоимость (cost_usd, cost_basis=estimated), token economy с per-stage/model/grand cost, стоимость в UI Сводки и Аудио |

---

## Границы документа

- **PROJECT_STATE.md** — только паспорт: состояние, решения, шаги. Не содержит session logs, task prompts, пошаговых walkthrough.
- Инженерная история: [task_history/engineering_log.md](task_history/engineering_log.md) (append-only), `task_history/*.md` по задачам.
- Специализированная документация: `docs/` (RUNBOOK, OPERATIONS, ARCHITECTURE, SECURITY_NOTES, security/, architecture/), `database/POSTGRES_SETUP.md`.