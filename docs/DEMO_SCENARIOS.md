# 🎬 Демо-сценарии (GitHub v2.0)

Проверки перед демонстрацией или review репозитория. Команды — из **корня** проекта; стек — portfolio ([OPERATIONS.md](OPERATIONS.md)).

**Предусловия:** `.env` из `.env.example`, ключи LLM/embeddings; для Postgres-метаданных — `DATABASE_URL` и init-схема.

```bash
COMPOSE_BAKE=false docker compose -f docker-compose.portfolio.yml up -d --build --remove-orphans
```

---

## 1. Текстовый режим (GigaChat)

1. Запустить бота (контейнер `assistant-flow` или `python run_telegram_bot.py`).
2. Telegram: `/reset`, `/mode text`.
3. Вопрос: *«Объясни простыми словами, что такое инфляция»*.
4. **Ожидание:** ответ на русском, без блока источников RAG.

Admin UI: раздел **Текст** — трассировка запроса после прогона.

---

## 2. RAG по документам

1. Индексировать базу ([ADMIN_INDEXING.md](ADMIN_INDEXING.md) или smoke `--reindex`).
2. `/mode rag` в Telegram **или** запрос в Admin UI → **RAG**.
3. Вопрос по содержимому загруженного файла.
4. **Ожидание:** ответ + источники (файл, score); в UI — найденные чанки и диагностика.

---

## 3. Кэш запросов к базе знаний

1. Включить кэш (Retrieval Settings / `ENABLE_RETRIEVAL_CACHE`).
2. Два одинаковых RAG-запроса подряд в **RAG**.
3. **Ожидание:** MISS → HIT, отображение задержек; при OFF — без ложного сравнения Δ.

---

## 4. Документы: загрузка и reindex

1. Admin UI → **Документы**: загрузить PDF/TXT/MD.
2. Дождаться индексации; при сбое — **Reindex**.
3. **Ожидание:** документ в списке, `chunk_count` > 0; в **Логи** — события upload/reindex.

CLI (альтернатива): `python scripts/admin_index_documents.py --reindex`.

---

## 5. Генерация изображений

1. `/mode text`.
2. *«Нарисуй закат над морем в минималистичном стиле»*.
3. **Ожидание:** статус, затем фото; при ошибке — сообщение бота.

Admin UI: **Изображения** — телеметрия.

---

## 6. OCR (распознавание текста с фото)

1. Настроить `OPENAI_API_KEY` и vision-модель.
2. Telegram: `/mode ocr` → фото с печатным текстом (или фото с подписью «распознай текст» в `/mode text`).
3. **Ожидание:** ответ «Распознанный текст:…»; в **Текст** / **Логи** — маршрут `vision_ocr`.

С подписью в `/mode ocr`: *«объясни простыми словами, что написано»* — один ответ Vision (см. [USER_GUIDE.md](../USER_GUIDE.md)).

---

## 7. Аудио (STT/TTS)

Если в `.env`: `AUDIO_ENABLED=true`, настроены `STT_PROVIDER` / `TTS_PROVIDER`.

1. Голосовое сообщение в Telegram или раздел **Аудио** в консоли.
2. **Ожидание:** распознавание → текстовый/RAG-ответ; TTS при включении.

По умолчанию (`disabled`) — сценарий пропустить, зафиксировать в демо как «опционально».

---

## 8. Обзор консоли, логи, оценка

| Раздел | Что показать |
|--------|----------------|
| **Обзор** | Health зависимостей, счётчики |
| **Сводка** | Агрегаты по времени |
| **Логи** | `processing_logs`, фильтры |
| **Memory** | Сессии и контекст (при Postgres) |
| **Анализ RAG** | RAGAS / ручная оценка (если включено) |

Скриншоты для README: `docs/screenshots/`.

---

## 9. `/stats` и `/reset` (Telegram)

- `/stats` — число чанков, backend, каталог документов.
- `/reset` — режим `text`, очистка in-memory RAG-истории.

---

## Быстрый RAG без Telegram

```bash
curl -sS http://localhost:8600/api/health
python scripts/rag_smoke_test.py --reindex --question "Ваш вопрос"
```

См. [RAG_SMOKE_TEST.md](RAG_SMOKE_TEST.md), [ARCHITECTURE.md](ARCHITECTURE.md).
