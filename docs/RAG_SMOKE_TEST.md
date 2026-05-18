# Smoke-тест RAG

Проверка поиска по базе знаний после подъёма стека или изменений retrieval/кэша. Для полной индексации с Postgres см. [ADMIN_INDEXING.md](ADMIN_INDEXING.md).

---

## 1. Запуск portfolio-стека

```bash
cp .env.example .env
COMPOSE_BAKE=false docker compose -p portfolio-test -f docker-compose.portfolio.yml up -d --build --remove-orphans
```

Заполните в `.env` минимум: ключи LLM/embeddings (`OPENAI_*` или Proxy), при живом боте — `TELEGRAM_BOT_TOKEN`.

---

## 2. Health Admin API

```bash
curl -sS http://localhost:8600/api/health | jq .
```

**Успех:** HTTP 200, JSON с полями зависимостей; общий статус `ok` или осознанный `degraded` (например, без ключей LLM) с понятными причинами в теле.

---

## 3. Admin UI — RAG

1. Открыть `http://localhost:8080/rag`.
2. **Успех:** страница загружается, нет ошибки CORS к `localhost:8600`.

---

## 4. Документы и индекс

1. Загрузить тестовый `.txt` / `.md` в **Документы** или положить файл в `data/documents/`.
2. Выполнить индексацию (UI pipeline или `python scripts/admin_index_documents.py --reindex`).
3. **Успех:** документ в списке, `chunk_count` > 0 (при Postgres).

---

## 5. Тестовый RAG-запрос

**Через Admin UI (RAG):** вопрос по содержимому загруженного файла.

**Через CLI (без Telegram):**

```bash
python scripts/rag_smoke_test.py --reindex --question "Ваш вопрос по документам"
```

**Успех:**

- ответ с опорой на контекст;
- блок найденных **чанков** (файл, score/расстояние);
- при пустом индексе — явный fallback, а не «тишина».

---

## 6. Кэш запросов (если включён)

В `.env` или **Retrieval Settings**: `ENABLE_RETRIEVAL_CACHE=true`.

1. Два одинаковых запроса подряд в RAG UI.
2. **Успех:** первый — MISS (или OFF при выключенном кэше), второй — **HIT**; в заголовке карточки видны задержки поиска и кэша.
3. Сравнение Δ между сессиями — только когда кэш участвовал в обеих (см. `docs/architecture/cache_observability_console_design.md`).

---

## 7. Параметры в UI

В RAG-консоли и **Retrieval Settings** проверить видимость:

- активного **backend** (chroma / faiss / weaviate);
- **top_k** и связанных параметров поиска (если отображаются в текущей сборке).

---

## 8. Telegram (опционально)

```bash
# в контейнере или локально с тем же .env
python run_telegram_bot.py
```

`/mode rag` → вопрос по индексу → ответ + **Источники:** в сообщении.

---

## Локальный smoke без compose

Если Postgres/Chroma уже подняты вручную:

```bash
python scripts/rag_smoke_test.py --reindex
python scripts/rag_smoke_test.py --question "Что такое RAG в этом проекте?"
```

Режимы Chroma (HTTP vs persist), переменные — в `.env.example`. Модули: `services/rag_chroma_store.py`, `rag_query_service.py`, `providers/rag_embeddings.py`.

---

## Ожидаемые коды выхода CLI индексации

`scripts/admin_index_documents.py`: `0` — успех; ненулевой — ошибки по файлам (см. вывод консоли).

См. также: [DEMO_SCENARIOS.md](DEMO_SCENARIOS.md), [OPERATIONS.md](OPERATIONS.md).
