# 📂 PROJECT_STRUCTURE.md — Assistant Flow

**Проект:** Assistant-Flow
**Дата:** 2026-09-15
**Статус:** Карта репозитория — структура и назначение каждого элемента кодовой базы.

---

## 📁 Дерево репозитория

```text
Assistant-Flow/
├── README.md                            # Точка входа: что это, возможности, стек, быстрый старт, карта документации
├── .env.example                         # Шаблон переменных окружения (заполнить → .env)
├── .env.server.example                  # Шаблон окружения для server-контура (docker-compose.assistant.yml)
├── .gitignore / .dockerignore           # Исключения git / Docker build context
├── Dockerfile                           # Многоступенчатый образ: бот + admin-api (INSTALL_RAGAS/INSTALL_DASHBOARD)
├── docker-compose.portfolio.yml         # Portfolio-стек: postgres + chroma + weaviate + assistant-flow + admin-api + admin-ui
├── docker-compose.assistant.yml         # Server-контур: один образ без векторных БД (Chroma как сервис отдельно)
├── requirements.txt                     # Python-зависимости основного контура (бот + admin-api)
├── requirements-ragas.txt               # Зависимости RAGAS-оценки (опционально, build-arg INSTALL_RAGAS)
├── requirements-dashboard.txt           # Зависимости legacy Streamlit-консоли (опционально)
├── main.py                              # Точка входа Telegram-бота (модуль)
├── run_telegram_bot.py                  # Запуск бота: long polling, инициализация контура
├── run_admin_api.py                     # Запуск Admin API (FastAPI/uvicorn)
├── dashboard.py                         # Legacy Streamlit-консоль (заменена React Admin UI; не входит в portfolio-стек)
│
├── core/                                # Ядро
│   └── orchestrator.py                  # Оркестратор: маршрутизация запросов по модальностям (text/rag/ocr/voice/image)
│
├── interfaces/
│   └── telegram_bot.py                  # Telegram-хэндлеры: /start, /mode, /stats, /reset, фото, голос
│
├── services/                            # Бизнес-сервисы (основной объём логики)
│   ├── rag_query_service.py             # Retrieval → сборка контекста → ответ с источниками
│   ├── rag_chroma_store.py              # Store Chroma: чанки, метаданные
│   ├── rag_document_loader.py           # Загрузка и чанкинг документов
│   ├── rag_local_indexer.py             # Индексация (в т.ч. FAISS)
│   ├── rag_types.py                     # Типы retrieval-контура
│   ├── retrieval/                       # Multi-backend retrieval: base, chroma/faiss/weaviate backend, factory, runtime_manager, tuning
│   ├── hybrid_retrieval/                # Гибридный поиск (dense + полнотекст)
│   ├── chunking/                        # Чанкинг: base, smart_chunker
│   ├── preprocessing/                   # Извлечение (pdf/html/txt), очистка, нормализация текста
│   ├── cache/                           # Retrieval cache: ключ, сериализация, SQLite-хранилище, инвалидация, обёртка backend
│   ├── memory/                          # Память диалога: conversation_memory_service (Postgres)
│   ├── memory_meta_intent.py            # Мета-интенты поверх памяти («что ты помнишь обо мне»)
│   ├── retrieval_security/              # Data-path security: visibility, фильтрация результатов, PII-masking, policy resolver
│   ├── security/                        # Control-plane security: RBAC, токены (admin/demo), auth middleware, сессии, sanitizer логов, аудит
│   ├── evaluation/                      # Оценка качества RAG: ragas_adapter, rag_evaluation_service
│   ├── audio_pipeline_service.py        # STT/TTS-конвейер (таймауты, ретраи, telemetry)
│   ├── vision_ocr_service.py            # OCR-маршрут (OpenAI Vision)
│   ├── image_generation_service.py      # Генерация изображений (провайдеры image)
│   ├── gigachat_service.py              # GigaChat chat-провайдер
│   ├── async_job_service.py             # Очередь фоновых задач (async_jobs)
│   ├── async_job_worker.py              # Воркер фоновых задач (поток в admin-api)
│   ├── admin_knowledge_indexer.py       # Индексация базы знаний из консоли
│   ├── healthcheck_service.py           # Health-пробы зависимостей (postgres/chroma/weaviate)
│   ├── audit_log_service.py             # Журнал аудита обращений к Admin API
│   ├── asset_repository.py              # Файловое хранилище (абстракция, готовность к S3)
│   ├── document_catalog_service.py      # Каталог документов
│   ├── chat_session_service.py          # Сессии чатов
│   ├── evaluation_* / admin_service.py  # Evaluation-сервисы, агрегация для консоли
│   └── runtime_lifecycle_service.py     # Lifecycle runtime-статусов
│
├── admin_api/                           # Операционная консоль (бэкенд)
│   ├── app.py                           # FastAPI-приложение: маршруты, middleware, запуск воркера
│   ├── deps.py                          # DI-зависимости маршрутов
│   ├── routes/                          # /api: overview, summary, text, rag, documents, retrieval, logs, sessions, assets, evaluation, auth, security_audit, health
│   ├── schemas/                         # Pydantic-схемы (common, summary, evaluation)
│   └── security/                        # Внедрение principal/permission в запросы
│
├── frontend/admin-ui/                   # Операционная консоль (фронтенд)
│   ├── Dockerfile                       # Сборка UI (nginx), VITE_OPS_DEMO_TOKEN ← AF_ADMIN_DEMO_TOKEN
│   ├── nginx.conf                       # Раздача статики, same-origin проксирование /api
│   ├── e2e/                             # Playwright-сценарии (auth, demo-badge, меню, pairwise)
│   └── src/                             # React/TypeScript: разделы консоли, auth (токен, permissions), компоненты
│
├── admin_ui/
│   └── app.py                           # Legacy Streamlit-консоль (заменена frontend/admin-ui)
│
├── providers/                           # AI-провайдеры (единый интерфейс)
│   ├── openai_chat_provider.py          # OpenAI Chat Completions
│   ├── gigachat_provider.py             # GigaChat
│   ├── openai_stt_provider.py / tts_provider.py  # Голос: STT/TTS
│   ├── image_provider.py / openai_image_provider.py / proxy_image_provider.py  # Генерация изображений
│   └── rag_embeddings.py                # Embeddings (text-embedding-3-small)
│
├── repositories/                        # Доступ к PostgreSQL
│   ├── connection.py                    # Пул соединений (DATABASE_URL)
│   ├── document_repository.py           # Документы, версии, чанки
│   ├── logs_repository.py / processing_logs_repository.py  # Продуктовые логи
│   ├── audit_repository.py              # admin_audit_log + auth_login_events
│   ├── user_repository.py / channel_identity_repository.py  # Identity (007)
│   ├── platform_settings_repository.py  # Retrieval Settings, runtime-статусы
│   ├── evaluation_repository.py         # Evaluation runs
│   └── runtime_lifecycle_repository.py  # Статусы жизненного цикла
│
├── utils/                               # Утилиты
│   ├── config.py                        # Загрузка .env / Settings
│   ├── request_logger.py                # Структурированные логи этапов
│   ├── telegram_formatter.py            # Markdown-форматирование ответов
│   └── telegram_user_state.py           # Режимы пользователя (/mode)
│
├── database/                            # Схема и миграции
│   ├── schema.sql                       # Snapshot полной схемы (initdb в portfolio-стеке)
│   ├── schema_v2_applied.sql            # Маркер применённой версии схемы
│   ├── migrations/                      # Идемпотентная цепочка 002–008 (runtime_lifecycle → admin_audit_extend)
│   ├── db_contract.md                   # Контракт таблиц и полей
│   └── POSTGRES_SETUP.md                # Создание БД, пользователь, volume, init-скрипты
│
├── evaluation/                          # Датасеты оценки
│   └── datasets/                        # rag_smoke_dataset.json, ragas_facts_baseline.txt, retrieval_diagnostics_smoke.json
│
├── scripts/                             # CLI: операции и smoke-тесты
│   ├── admin_index_documents.py         # Индексация/reindex базы знаний из CLI
│   ├── rag_smoke_test.py                # Smoke-тест RAG без Telegram (--reindex)
│   ├── build_faiss_demo_index.py / clean_demo_index.py  # FAISS demo-индекс
│   ├── analyze_logs.py                  # Анализ processing_logs
│   ├── index_consistency_check.py       # Сверка индексов
│   ├── evaluation_*.py                  # Управление evaluation: прогон, импорт, сравнение, датасеты
│   ├── test_*.py                        # Smoke- и regression-тесты по контурам (retrieval, security, memory, cache, preprocessing)
│   └── p9_6*.py                         # Форензик-скрипты security-эпохи (visibility backfill, parity)
│
├── docs/                                # Публичная документация
│   ├── DEPLOYMENT_GUIDE.md              # Развёртывание с нуля (Source of Truth)
│   ├── DEPLOYMENT_VALIDATION_REPORT.md  # Отчёт Deployment Validation (чистое окружение)
│   ├── USER_GUIDE.md                    # Руководство пользователя: Telegram-команды, режимы, консоль
│   ├── PROJECT_STATE.md                 # Паспорт состояния проекта (статус, следующие шаги, история)
│   ├── OPERATIONS.md                    # Эксплуатация: compose, БД, векторные бэкенды, кэш, логи
│   ├── SECURITY_NOTES.md                # Секреты, модель доступа, RBAC, retrieval security, аудит
│   ├── ARCHITECTURE.md                  # Архитектура и принципы системы
│   ├── SPEC.md                          # Продуктовая спецификация
│   ├── IMPLEMENTATION_PLAN.md           # Технический план и критерии готовности
│   ├── DEMO_ROUTE.md                    # Маршрут проверки демо (2–5 действий)
│   ├── DEMO_SCENARIOS.md                # Расширенная матрица демо-проверок
│   ├── ADMIN_INDEXING.md                # Гигиена и аудит индекса базы знаний
│   ├── RAG_SMOKE_TEST.md                # Smoke-проверка RAG
│   ├── PROJECT_STRUCTURE.md             # Этот документ
│   └── screenshots/                     # Скриншоты системы (каталог — [MEDIA_INDEX.md](screenshots/MEDIA_INDEX.md))
│
└── (на диске, вне git: storage/, data/, legacy/, outputs/ — рабочие данные и артефакты рантайма)
```

---

## 🔗 Связанные документы

- [README.md](../README.md) — точка входа и карта документации
- [ARCHITECTURE.md](ARCHITECTURE.md) — архитектура системы
- [OPERATIONS.md](OPERATIONS.md) — эксплуатация стеков
- [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) — развёртывание с нуля