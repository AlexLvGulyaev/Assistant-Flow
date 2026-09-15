# 📊 PROJECT STATE — Assistant Flow

Паспорт состояния проекта (канон APL). Точка входа для любого агента, начинающего работу с кейсом.

---

## Project Summary

**Assistant Flow** — мультимодальная AI-платформа для работы с корпоративными знаниями: Telegram-ассистент (текст, RAG, OCR/Vision, голос STT/TTS, генерация изображений), корпоративная база знаний с управляемой индексацией и переключаемыми vector-бэкендами (Chroma / FAISS / Weaviate), операционная консоль (FastAPI Admin API + React Admin UI) с наблюдаемостью, оценкой качества RAG (RAGAS), памятью диалога и журналом аудита.

Позиционирование: исследовательская платформа (прототип) для проверки мультимодальных AI-сценариев. Принцип: operational-first / observability-first.

Стек: Python / FastAPI / PostgreSQL / ChromaDB / Weaviate / FAISS / React / Vite / Docker Compose; провайдеры OpenAI / GigaChat / ProxyAPI (embeddings отделены от chat).

---

## Current Status

**Стадия:** Портфельный актив в сопровождении (публичный репозиторий, живой инстанс).

- **Живой контур:** portfolio-стек `docker-compose.portfolio.yml`, compose-проект = имя каталога `assistant-flow`; сервисы `postgres`, `chroma`, `weaviate`, `assistant-flow` (бот), `admin-api`, `admin-ui`. Порт на витрину: `https://af-admin.alex-n8n.site` (traefik → `admin-ui`, same-origin `/api`).
- **Подсистемы в строю:** текстовый контур, RAG (включая полный текст чанка в UI), индексация с heavy-RAG safeguards (`ADMIN_UPLOAD_MAX_MB`), retrieval cache, память диалога, token economy в Summary, авторизация консоли (Bearer-токен + демо-вход read-only), журнал аудита (`admin_audit_log`), healthchecks, graceful degradation, multi-stage production-образы.
- **Security:** identity foundation, auth middleware (включая legacy-режимы), RBAC, audit trail, security console — реализованы и проверены (e2e 19/19 PASS).
- **Асинхронный слой:** очередь `async_jobs` (миграция 004) + воркер-поток внутри admin-api потребляет `rag_reindex`-задачи; enqueue/retry/список — через Admin API и панель «Фоновые задачи» в Документах; reclaim stale-`running` задач на старте.
- **Известные закрытые инциденты:** fd-leak chromadb HttpClient (утечка сокетов → unhealthy; закрыто 2026-09-03 — HttpClient переведён на short-lived соединения с явным закрытием); Chroma persistence bug (volume); Streamlit sticky/autoscroll (решено отказом от Streamlit).
- **Не решено:** heavy RAG на пике нагрузки (reindex + concurrent RAG) может деградировать на VPS 7.8 GiB RAM + 5 GiB swap; semantic/glossary-aware chunking (см. SPEC § «Вне скоупа»).

---

## Market Validation

Внешних клиентских заказов нет. Проект развивается как исследовательский актив AI Automation Portfolio Lab. Рыночный сигнал — косвенный: платформа демонстрирует компетенции (RAG, мультимодальность, эксплуатация AI-систем), востребованные в других кейсах лаборатории.

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

Проект сохраняется как **портфельный актив** лаборатории: живой инстанс используется как витрина (демо-вход read-only), публичный репозиторий — Source of Truth развёртывания ([DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)). Накопленные долги (token economy, async layer, аудио hardening и др.) закрыты в 2026-09.

---

## Next Steps

1. Решения владельца: удаление устаревших volumes/образов `portfolio-test_*`.
2. Опционально: rag_smoke_test без tuning-резолвера тестирует env-конфиг, а не effective (Retrieval Settings) — кандидат на однострочный фикс.

---

## Status History

| Дата | Статус | Событие |
|------|--------|---------|
| 2025–2026 | Разработка | Учебный проект → операционная платформа |
| 2026-08 | Кейс | Выделение проекта в самостоятельный git-репозиторий |
| 2026-09-02 | Активная разработка | Демо-стандарт (токен + демо-вход), публичный эндпойнт, token economy, heavy-RAG safeguards, multi-version docs, production build (multi-stage, −25…−33%) |
| 2026-09-03 | Сопровождение | Инцидент fd-leak chroma HttpClient закрыт; KB-паттерн; актуализация документации по стандартам APL |
| 2026-09-03 | Разработка | Долг №6 закрыт: async-воркер (вариант A) — очередь `async_jobs`, панель «Фоновые задачи», enqueue/retry API |
| 2026-09-03 | Разработка | Долг №7 закрыт: аудио-контур — таймауты/ретраи OpenAI STT/TTS, оценочная стоимость (cost_usd, cost_basis=estimated), token economy с per-stage/model/grand cost, стоимость в UI Сводки и Аудио |
| 2026-09-15 | Упаковка | Рефакторинг публичной документации: канонический DEPLOYMENT_GUIDE, OPERATIONS (консолидация RUNBOOK), SECURITY_NOTES, DEMO_ROUTE, PROJECT_STRUCTURE, MEDIA_INDEX; устранение исторического sprawl (docs/security/, docs/architecture/, P-коды) |
| 2026-09-15 | Разработка | RAG-поведение доведено до документации: блок «Источники» в Telegram, retrieval top_k 3→5 (батарея PASS); канон возврата на лэндинг (goProject), подпись логинформы без dev-жаргона, позиционирование /start; USER_GUIDE и PROJECT_STATE перенесены в docs/ |
| 2026-09-15 | Сопровождение | Консоль: демо-доступ к KB (demo → employee-scope, read-only), честный бейдж «Экспозиция админки» (по auth-состоянию, не health), предупреждение рассинхронизации только для реальных статусов; страница «Текст» без чужих сессий (voice → «Аудио», memory-сбросы → Memory) |
| 2026-09-15 | Упаковка | Рефакторинг документации по трёхслойному стандарту (референс RF): README 616→239 строк (продающий вход, карта документации тремя слоями с иконками); новые BUSINESS_VALUE, SYSTEM_DEMO (галерея скриншотов), ADMIN_GUIDE; USER_GUIDE — только клиент (было: смешаны клиент и админ); скриншоты распределены по назначению (дубль README↔USER_GUIDE устранён); фиксы фактов (SECURITY_NOTES demo→employee-scope, RAG_SMOKE_TEST top_k/резолвер, /reset, НоваТех, раскладка консоли по канону сайдбара, /exit), шапки Дата/Статус во всех doc-файлах, эмодзи-контракт (H1 ADMIN_INDEXING 🖥️, H2 правленных документов) |

---

## Границы документа

- **PROJECT_STATE.md** — только паспорт: состояние, решения, шаги. Не содержит session logs, task prompts, пошаговых walkthrough.
- Специализированная документация: `docs/` (DEPLOYMENT_GUIDE, DEPLOYMENT_VALIDATION_REPORT, OPERATIONS, SECURITY_NOTES, ARCHITECTURE и др.), `database/POSTGRES_SETUP.md`; полная карта — [docs/PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md).