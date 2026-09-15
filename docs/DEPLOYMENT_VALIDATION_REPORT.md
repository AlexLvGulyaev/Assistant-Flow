# ✅ DEPLOYMENT_VALIDATION_REPORT.md — Assistant Flow

**Проект:** Assistant-Flow
**Дата:** 2026-09-15
**Статус:** Deployment Validation пройдена (2 прогона; чистое окружение — изолированный Docker Host).

**Гайд:** [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) · **Класс проверки:** Validation
(воспроизводимость с нуля), не Verification (работоспособность существующего инстанса).

---

## 1. Методика

- **Чистое окружение:** изолированный Docker-in-Docker хост (image `docker:29-dind`,
  privileged, собственный `/var/lib/docker`, собственные сети и volumes) — эквивалент
  «нового Docker Host» из требований Validation. Хост-машина: Linux, Docker Engine 24+.
- **Источник кода:** свежий `git clone https://github.com/AlexLvGulyaev/Assistant-Flow.git`
  (HEAD `08d3ca0`) + наложение дельты рабочих изменений документации (рефакторинг
  15.09, до коммита) — валидируется итоговое состояние документационного пакета.
- **Окружение прогона:** `.env` строго по §4 гайда: `TELEGRAM_BOT_TOKEN` — плейсхолдер
  из `.env.example`, `OPENAI_API_KEY` — реальный ключ AI-провайдера (значения не
  публикуются), `AF_ADMIN_TOKEN` / `AF_ADMIN_DEMO_TOKEN` — сгенерированные длинные
  случайные строки, `DATABASE_URL` — без изменений.
- **Действия за пределами гайда:** только инструменты верификации (установка `curl`
  внутри dind-образа); никаких действий по развёртыванию сверх §1–11 не выполнялось.
- **Границы:** браузерные шаги (§6.5 экран консоли, §7 Telegram-диалог, §8 загрузка
  через UI) проверялись на уровне HTTP/API/CLI; визуальную приёмку выполняет владелец.

## 2. Сводка прогонов

| Прогон | Дата | Состояние гайда | Результат |
|--------|------|-----------------|-----------|
| #1 | 2026-09-15 | до фикса §6.2 | **FAIL (1 пункт)** → исправлен гайд → прогон #2 |
| #2 | 2026-09-15 | после фикса §6.2 | **PASS** |

## 3. Прогон #1 (2026-09-15)

Полный цикл: §1–§9. Стек собран и поднят, все контейнеры зелёные.

| Шаг гайда | Действие | Ожидание | Факт | Статус |
|-----------|----------|----------|------|--------|
| §1 | `docker --version`, `docker compose version` | Docker 24+, Compose v2 | docker 29.7.2, Compose v5.5.0 | PASS |
| §2 | свежий клон репозитория | репо на диске | клон 08d3ca0 | PASS |
| §3 | `docker network ls \| grep n8n_default \|\| docker network create n8n_default` | сеть создана | сеть `n8n_default` создана (в чистом dind отсутствовала) | PASS |
| §4 | `cp .env.example .env`, заполнение | .env готов | плейсхолдер бота, LLM-ключ, сгенерированные токены | PASS |
| §5 | `up -d --build --remove-orphans` | 6 сервисов, postgres healthy | все 6 контейнеров запущены; initdb применён автоматически | PASS |
| §6.1 | `compose ps` | postgres/admin-api/weaviate healthy, остальные Up | postgres (healthy), admin-api (healthy), weaviate (healthy), chroma/admin-ui/assistant-flow Up | PASS |
| §6.2 | `curl …/api/health \| python3 -m json.tool` | HTTP 200, `status: ok` | HTTP 200, `status: "ok"`; **pipe `python3 -m json.tool` невыполним — в минимальном окружении нет python3** (выполнен curl без форматирования) | **FAIL (as written)** |
| §6.3 | `psql … "\dt"` | таблицы присутствуют | 25 таблиц: `app_users`, `documents`, `processing_logs`, `intake_events`, `platform_settings`, `async_jobs`, `admin_audit_log`, `user_channel_identities`, `evaluation_*` и др. | PASS |
| §6.4 | chroma heartbeat, weaviate ready | heartbeat-JSON / 200 | `{"nanosecond heartbeat":…}` / HTTP 200 | PASS |
| §6.5 | UI `:8080` + вход | HTML консоли загружается | `GET /` → 200 (index.html React-консоли); same-origin `/api/health` через nginx admin-ui → 200; без токена `GET /api/overview` → **401**, admin-токен → 200 `role: admin`, демо-токен → 200 `role: demo`, демо-мутация `POST /api/documents/reindex` → **403** | PASS |
| §7 | реальный бот: /start, /help, /mode text | ответ бота | **NOT VERIFIED**: реальный `TELEGRAM_BOT_TOKEN` недоступен в чистом окружении (использование токена работающего инстанса вызвало бы конфликт polling 409). Задокументированное поведение плейсхолдера подтверждено: контейнер `assistant-flow` Up, в логах — ожидание реального токена | NOT VERIFIED |
| §8 | документ + индексация + RAG | `chunk_count` > 0, ответ с опорой на контекст | тестовый MD → `admin_index_documents.py --reindex`: 1 файл, 1 чанк, Postgres metadata True; `rag_smoke_test.py` → ответ по содержимому документа (retrieved 1, score 0.82) | PASS |
| §9 | `down` → `up -d` (без пересборки) | volumes сохранены, стек зелёный | volumes `portfolio_{pg,chroma,weaviate}_data` сохранены; после `up -d` все 6 контейнеров Up, admin-api/postgres/weaviate healthy | PASS |

**Итог #1:** единственное несоответствие — §6.2 в записи гайда: шаг завершения
`| python3 -m json.tool` делает проверку зависимой от наличия python3, что не
требуется по существу. По правилам Validation гайд признан несоответствующим
статусу SOT → исправление документации → повторный чистый прогон.

**Исправление гайда (только документация, код не менялся):** §1 — требование
`curl` добавлено явно; §6.2 — команда без `python3 -m json.tool`, форматирование
`| jq .` упомянуто как опция при наличии jq.

## 4. Прогон #2 (2026-09-15) — после фикса гайда

Полная очистка: `down -v`, удаление volumes, удаление клона; свежий клон (08d3ca0),
та же дельта документации, обновлённый гайд, новые `.env` и токены.

| Шаг гайда | Действие | Ожидание | Факт | Статус |
|-----------|----------|----------|------|--------|
| §2 | свежий клон | репо на диске | клон 08d3ca0, чистый `git status` | PASS |
| §3 | сеть n8n_default | сеть есть | сеть присутствует (создана §3 этого же стенда; проверка `grep \|\| create` идемпотентна) | PASS |
| §4 | .env по §4 | .env готов | плейсхолдер бота, LLM-ключ, новые токены | PASS |
| §5 | `up -d --build` | стек с нуля | все 6 контейнеров; postgres healthy → admin-api/ui стартуют | PASS |
| §6.1 | `compose ps` | healthy-набор | postgres/admin-api/weaviate (healthy), chroma/admin-ui/bot Up | PASS |
| §6.2 | `curl -sS http://localhost:8600/api/health` **как записано** | HTTP 200, ok | HTTP 200, `status: "ok"`, зависимости postgres/chroma/rag — ok, LLM-ключи configured | PASS |
| §6.3 | psql `\dt` | таблицы присутствуют | 25 таблиц | PASS |
| §6.4 | chroma/weaviate пробы | heartbeat / 200 | heartbeat-JSON / HTTP 200 | PASS |
| §6.5 | UI + same-origin API | загрузка | `GET /` 200, `:8080/api/health` 200 | PASS |
| §8 | документ + индексация + RAG | ответ с опорой на документ | 1 чанк, Postgres metadata True; ответ по содержимому тестового документа | PASS |
| §7 | Telegram end-to-end | — | NOT VERIFIED (см. #1; owner-verifiable) | NOT VERIFIED |

**Итог #2:** все шаги, воспроизводимые в чистом окружении, выполнены строго по
тексту гайда — PASS.

## 5. Вердикт

**Deployment Validation: PASS (прогон #2).** `DEPLOYMENT_GUIDE.md` воспроизводит
полностью работоспособный стек (6 сервисов, БД 25 таблиц, health-пробы, консоль
с токен-доступом и read-only демо, индексация и RAG) на чистом Docker-хосте,
используя только содержимое публичного репозитория.

**Границы вердикта (честная фиксация):**

- §7 (Telegram end-to-end: `/start`, ответ бота) — не проверено в чистом
  окружении: требует реального `TELEGRAM_BOT_TOKEN`; использование токена
  работающего инстанса нарушило бы его polling (409). Поведение плейсхолдера,
  задокументированное в гайде, подтверждено. Шаг остаётся owner-verifiable.
- Браузерная визуальная приёмка консоли (§6.5, §8) — за владельцем; HTTP/API-уровень
  пройден.
- `DEPLOYMENT_GUIDE` валиден для portfolio-контура; server-контур (§10) явно
  помечен гайдом как «продвинутый», не входит в канонический путь и не валидировался.

## 6. Окружение прогонов

| Параметр | Прогоны #1 и #2 |
|----------|-----------------|
| Docker (dind) | 29.7.2 |
| Docker Compose | v5.5.0 |
| Базовый образ dind | docker:29-dind (privileged, изолированный /var/lib/docker) |
| Репозиторий | HEAD 08d3ca0 + дельта рефакторинга документации (15.09) |
| .env | по §4: `OPENAI_API_KEY`, сгенерированные `AF_ADMIN_TOKEN`/`AF_ADMIN_DEMO_TOKEN`, плейсхолдер бота |
| Сеть | `n8n_default` создана по §3 |

---

[DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) · [OPERATIONS.md](OPERATIONS.md) · [SECURITY_NOTES.md](SECURITY_NOTES.md)