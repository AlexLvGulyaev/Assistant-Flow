# Локальный smoke-test RAG (ChromaDB)

Инкремент 2 добавляет **read-only** сервис запросов к векторному индексу и **локальный индексатор** файлов. Для **админской индексации** с отчётом и опциональным PostgreSQL используйте `scripts/admin_index_documents.py` (**`docs/ADMIN_INDEXING.md`**); этот документ описывает smoke-test «индекс + вопрос» в одном скрипте.

## Режимы Chroma (HTTP vs локальный persist)

Индексация и поиск используют **один и тот же** нативный клиент `chromadb`:

| Режим | Переменные | Когда использовать |
|--------|------------|-------------------|
| **HTTP** | `CHROMA_USE_HTTP=true`, `CHROMA_HOST`, `CHROMA_PORT` | Chroma в **Docker** на сервере; с локальной машины — **SSH-туннель** (например `127.0.0.1:8000` → контейнер). Рекомендуется на **Windows**: встроенный `PersistentClient` на локальной папке может завершать процесс с кодом **-1073741819** при `collection.add()`. |
| **Локальный persist** | `CHROMA_USE_HTTP=false`, `CHROMA_PERSIST_DIR` | Встроенная БД в каталоге на диске (удобно на Linux/macOS при стабильном окружении). |

`CHROMA_PERSIST_DIR` при **HTTP** не хранит векторы: путь остаётся **подсказкой** для `/stats` и скриптов (см. `.env.example`).

Типичный сценарий **Docker + туннель**:

1. На сервере поднят Chroma с HTTP API (порт 8000 в контейнере).
2. Локально: `ssh -L 8000:127.0.0.1:8000 user@server` (или аналог).
3. В `.env`: `CHROMA_USE_HTTP=true`, `CHROMA_HOST=127.0.0.1`, `CHROMA_PORT=8000`.

## Зависимости

Установите зависимости проекта (`requirements.txt`), в том числе `chromadb`, LangChain (core) и `pypdf`.

## Переменные окружения

Минимально для embeddings и ответа LLM:

| Переменная | Назначение |
|------------|------------|
| `OPENAI_API_KEY` | Ключ API (или используйте `PROXY_API_KEY`) |
| `OPENAI_BASE_URL` | Необязательно; для OpenAI-совместимого прокси (например ProxyAPI) |
| `OPENAI_MODEL` | Модель чата для ответа (по умолчанию из `.env.example`) |
| `OPENAI_EMBEDDING_MODEL` | Модель эмбеддингов (по умолчанию `text-embedding-3-small`) |

Каталоги и параметры RAG / Chroma:

| Переменная | По умолчанию |
|------------|----------------|
| `CHROMA_USE_HTTP` | `false` (в `.env.example` задано `true` как ориентир для удалённой Chroma) |
| `CHROMA_HOST` | `127.0.0.1` |
| `CHROMA_PORT` | `8000` |
| `CHROMA_PERSIST_DIR` | `data/chroma_db` |
| `RAG_DOCUMENTS_DIR` | `data/documents` |
| `RAG_TOP_K` | `3` |
| `RAG_CHUNK_SIZE` | `1000` |
| `RAG_CHUNK_OVERLAP` | `200` |
| `RAG_ANSWER_MAX_TOKENS` | `1500` |

См. также корневой `.env.example`.

## Документы для индексации

Положите файлы **`.txt`**, **`.md`** или **`.pdf`** в каталог `data/documents/` (или в путь из `RAG_DOCUMENTS_DIR`). Подкаталоги обходятся рекурсивно.

В репозитории есть пример: `data/documents/sample_career_rag.txt`.

## Запуск smoke-test

Из **корня репозитория** `assistant-flow`:

```bash
python scripts/rag_smoke_test.py
```

Полная переиндексация (удаляет **коллекцию на сервере Chroma** при HTTP или каталог `CHROMA_PERSIST_DIR` при локальном режиме, затем строит индекс заново):

```bash
python scripts/rag_smoke_test.py --reindex
```

Свой вопрос:

```bash
python scripts/rag_smoke_test.py --question "Что такое RAG в этом проекте?"
```

Другой каталог с документами:

```bash
python scripts/rag_smoke_test.py --documents-dir path/to/docs --reindex
```

Скрипт печатает найденные источники (с метрикой расстояния/скора Chroma) и итоговый ответ модели.

## Архитектура модулей (кратко)

- `services/rag_chroma_store.py` — нативный `chromadb` (Http или Persistent), `collection.add` / `collection.query` (без LangChain Chroma для retrieval).
- `services/rag_document_loader.py` — загрузка и chunking файлов.
- `services/rag_local_indexer.py` — запись чанков в индекс (CLI / админские сценарии).
- `services/rag_query_service.py` — **read-only** поиск + формирование ответа через LLM.
- `providers/rag_embeddings.py` — фабрика эмбеддингов OpenAI-совместого API.
- `providers/openai_chat_provider.py` — синхронный вызов chat completions для ответа.

Индексация через Telegram пользователям **не предлагается**; для продукта предусмотрены отдельные админ-процессы (следующие инкременты).

## Telegram: режим RAG

После индексации запустите бота (`python run_telegram_bot.py`). Команды:

- `/mode rag` — вопросы по базе; ответ дополняется списком источников (файл + score), если чанки найдены.
- `/mode text` — прежний сценарий (GigaChat, генерация изображений по ключевым словам).
- `/stats` — число чанков в Chroma и путь/режим backend (HTTP или persist).
- `/reset` — режим снова `text`, история RAG в памяти очищена.

Нужны те же ключи OpenAI/Proxy, что и для smoke-test (эмбеддинги + ответ). Режим пользователя пока in-memory (см. TODO в `utils/telegram_user_state.py`).
