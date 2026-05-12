# Session log: `.env.example` vs `.env` audit (portfolio contour)

## Root cause / why the audit was needed

- **`.env.example`** обновлялся по мере фич (FAISS / retrieval abstraction, кэш, hybrid, eval, Admin CORS и т.д.), а рабочий **`.env`** в portfolio-контуре мог отставать или, наоборот, содержать **явные operational** переменные, которых ещё нет в example.
- Риски: неочевидные дефолты в коде, «тихие» отличия portfolio от документации, расхождение при включении retrieval cache / смене backend без bump fingerprint.
- Задача аудита — **сравнить только имена ключей**, не раскрывая секреты, и зафиксировать безопасные дополнения / пробелы в документации.

## Compared files

| File | Role |
|------|------|
| `/opt/assistant-flow/.env.example` | Шаблон с плейсхолдерами (в репозитории). |
| `/opt/assistant-flow/.env` | Рабочий portfolio/local env (секреты; в отчёт значения не включались). |

Метод: извлечение строк вида `NAME=value` (без вывода значений из `.env`).

## Missing keys (in `.env.example` but not in `.env`)

**На момент записи лога: нет** — все ключи, объявленные в `.env.example`, присутствуют в текущем `.env`.

*(Если позже example снова обгонит `.env`, повторите diff по именам ключей.)*

## Extra keys (in `.env` but not in `.env.example`)

Следующие переменные есть в **`.env`**, но **не перечислены** в **`.env.example`** (они поддерживаются `utils/config.py` / кэшем):

| VARIABLE | Note |
|----------|------|
| `RAG_BACKEND` | Default в коде: `chroma`. Для FAISS: `faiss`. |
| `FAISS_INDEX_DIR` | Default в коде: `storage/faiss`. |
| `RAG_EMBEDDING_REQUEST_TIMEOUT` | Default: `30` (float). |
| `RAG_RETRIEVAL_TIMEOUT` | Default: `60` (int). |
| `RAG_MAX_DISTANCE` | Default: `1.38` (float). |
| `RAG_RETRIEVAL_GENERATION` | Fingerprint retrieval cache; в example только закомментированный hint. |

Рекомендация для репозитория (отдельная задача, не делалось в этом логе): **дополнить `.env.example`** этими ключами с комментариями, чтобы example снова покрывал portfolio `.env`.

## Documentation oddity (example only)

- В **`.env.example`** есть **`GIGACHAT_CLIENT_ID`** и **`GIGACHAT_CLIENT_SECRET`**, но в Python-конфиге AF они **не читаются** (`load_config` использует **`GIGACHAT_AUTH_KEY`** и связанные поля). Это не «extra key» в `.env`, а потенциальная **путаница в шаблоне** — при следующей правке example стоит либо пояснить назначение, либо убрать, если не используется.

## Suggested additions (for humans / future `.env` edits — not applied)

**Правило:** для секретов — только плейсхолдер `<KEEP_EXISTING_SECRET_OR_SET_REAL_VALUE>`; реальные значения из рабочего `.env` не вставлять.

Если когда-либо понадобится **выровнять новый `.env` с example** с нуля, безопасный каркас (секреты — плейсхолдеры):

```env
# --- Secrets (never copy real values into docs or commits) ---
TELEGRAM_BOT_TOKEN=<KEEP_EXISTING_SECRET_OR_SET_REAL_VALUE>
OPENAI_API_KEY=<KEEP_EXISTING_SECRET_OR_SET_REAL_VALUE>
PROXY_API_KEY=<KEEP_EXISTING_SECRET_OR_SET_REAL_VALUE>
GIGACHAT_AUTH_KEY=<KEEP_EXISTING_SECRET_OR_SET_REAL_VALUE>

# --- Operational defaults (portfolio-style; adjust per host) ---
DATABASE_URL=postgresql://assistant:assistant@postgres:5432/assistant_flow
CHROMA_USE_HTTP=true
CHROMA_HOST=chroma
CHROMA_PORT=8000
ADMIN_API_CORS_ORIGINS=http://localhost:8080,http://127.0.0.1:8080
ENABLE_HYBRID_RETRIEVAL=false
ENABLE_RAGAS_EVALUATION=false
ENABLE_RETRIEVAL_CACHE=false
ENABLE_ANSWER_CACHE=false
CACHE_DB_PATH=storage/cache/assistant_cache.sqlite3
RETRIEVAL_CACHE_TTL_SECONDS=86400
ANSWER_CACHE_TTL_SECONDS=86400

# --- Explicit retrieval backend (optional; defaults exist in code) ---
RAG_BACKEND=chroma
FAISS_INDEX_DIR=storage/faiss
# RAG_RETRIEVAL_GENERATION=1   # bump when ENABLE_RETRIEVAL_CACHE=true after reindex
```

Текущий рабочий **`.env` не изменялся** по этой задаче.

## Risks

| Risk | Mitigation |
|------|------------|
| Секрет попал бы в лог/коммит | В этом логе значения `.env` не процитированы; для секретов в шаблонах — только `<KEEP_EXISTING_SECRET_OR_SET_REAL_VALUE>`. |
| Расхождение example ↔ code | Extra keys в `.env` показывают, что example отстаёт от `load_config`; синхронизировать example при следующем PR. |
| Устаревший retrieval cache | При `ENABLE_RETRIEVAL_CACHE=true` — менять **`RAG_RETRIEVAL_GENERATION`** после reindex / смены корпуса (см. `services/cache/retrieval_cache_key.py`). |
| FAISS vs embedding model | Индекс и `OPENAI_EMBEDDING_MODEL` должны совпадать с operational policy (manifest / переиндексация). |

## FAISS operational check: env changes required?

| Scenario | Env |
|----------|-----|
| **Оставаться на Chroma (default production)** | Достаточно **`RAG_BACKEND=chroma`** или **не задавать** `RAG_BACKEND` — в коде default `chroma`. |
| **Включить operational FAISS indexing + RAG на FAISS** | Нужно явно **`RAG_BACKEND=faiss`** и каталог **`FAISS_INDEX_DIR`** (часто `storage/faiss` в контейнере с volume), плюс рабочий **`OPENAI_API_KEY`** для эмбеддингов. Без смены `RAG_BACKEND` FAISS operational path не активируется — это **не silent switch**. |
| **Только дефолты** | Operational FAISS может работать с дефолтным путём индекса из кода, но для portfolio **явная** `FAISS_INDEX_DIR` снижает риск путаницы между хостом и контейнером. |

**Вывод:** для «проверки FAISS operational» в смысле задания (index + query через FAISS) **нужны** env-изменения относительно чистого chroma-only контура: как минимум **`RAG_BACKEND=faiss`** и согласованный **`FAISS_INDEX_DIR`**; остальное — таймауты/эмбеддинг по необходимости.

## Actions taken in this session

- Сравнение ключей `.env.example` ↔ `.env` (имена только).
- Создание этого append-only session log.
- **Не** правили `.env`, **не** коммитили.
