# 🎬 Assistant Flow — демонстрация системы

Assistant Flow — как работающая система: live demo, скриншоты интерфейса и типовой сценарий обработки запроса.

**Статус:** актуально на 2026-09-15 (живой инстанс, демо-вход read-only).

---

## ▶️ Live Demo

🌐 **Операционная консоль:** [af-admin.alex-n8n.site](https://af-admin.alex-n8n.site) — кнопка **«Войти в демо-режиме»** (read-only). Полный доступ — Bearer-админ-токен ([SECURITY_NOTES](SECURITY_NOTES.md) §2).

Telegram-бот разворачивается на своём токене (`TELEGRAM_BOT_TOKEN`) — общего демо-бота в репозитории нет ([DEMO_ROUTE](DEMO_ROUTE.md)).

---

## 🖥️ Операционная консоль

Обзор состояния платформы: health-check сервисов, активные AI-провайдеры, retrieval backend, операционные метрики.

![Обзор состояния платформы](screenshots/overview-adm.png)

<p align="center"><em>
Обзор состояния платформы Assistant Flow: health-check сервисов, активные AI-провайдеры, retrieval backend и операционные метрики.
</em></p>

---

## 📱 Пользовательский контур (Telegram)

### Текстовый режим

Пример текстового ответа Telegram-ассистента в режиме обычного диалога.

![Пример текстового ответа в Telegram](screenshots/text-tg.png)

<p align="center"><em>
Пример текстового ответа Telegram-ассистента в режиме обычного диалога.
</em></p>

### RAG по базе знаний

RAG-ответ ассистента на основе корпоративной базы знаний Assistant Flow.

![RAG-ответ в Telegram](screenshots/rag-tg.png)

<p align="center"><em>
RAG-ответ Telegram-ассистента на основе корпоративной базы знаний Assistant Flow.
</em></p>

### Голос (STT/TTS)

Пример голосового взаимодействия: распознавание речи и генерация аудио-ответа.

![Голосовое взаимодействие в Telegram](screenshots/audio-tg.png)

<p align="center"><em>
Пример голосового взаимодействия с Telegram-ассистентом: распознавание речи и генерация аудио-ответа.
</em></p>

### Генерация изображений

Пример генерации изображения по текстовому запросу пользователя.

![Генерация изображения в Telegram](screenshots/image-tg.png)

<p align="center"><em>
Пример генерации изображения Telegram-ассистентом по текстовому запросу пользователя.
</em></p>

### OCR / Vision (распознавание текста с фото)

Распознавание текста средствами OpenAI Vision.

![OCR в Telegram](screenshots/ocr_tg.png)

<p align="center"><em>
Пример OCR-обработки изображения в Telegram: распознавание текста средствами OpenAI Vision.
</em></p>

---

## 🔍 Контур базы знаний (консоль)

### RAG-сессии и диагностика retrieval

Операционная консоль RAG-сессий: диагностика retrieval, latency, cache-state, найденные чанки.

![Операционная консоль RAG-сессий](screenshots/rag-adm.png)

<p align="center"><em>
Операционная консоль RAG-сессий с диагностикой retrieval, latency, cache-state и найденных чанков.
</em></p>

Расширенная диагностика: чанки, relevance-score, latency retrieval, состояние retrieval cache.

![Расширенная диагностика retrieval](screenshots/retrieval-details-adm.png)

<p align="center"><em>
Расширенная диагностика retrieval: найденные чанки, relevance-score, latency retrieval и состояние retrieval cache.
</em></p>

### Управление документами

Индексация, preprocessing, версии документов, жизненный цикл ingestion pipeline, фоновые задачи reindex.

![Управление документами knowledge base](screenshots/documents-adm.png)

<p align="center"><em>
Управление документами knowledge base: индексация, preprocessing, версии документов, жизненный цикл ingestion pipeline и фоновые задачи reindex (воркер потребляет очередь <code>async_jobs</code> внутри admin-api).
</em></p>

Workflow и safeguard-и индексации — [🖥️ `ADMIN_INDEXING.md`](ADMIN_INDEXING.md).

### Retrieval Settings

Переключение vector storage, runtime tuning, chunking и cache-настройки RAG.

![Панель Retrieval Settings](screenshots/rs-adm.png)

<p align="center"><em>
Панель управления retrieval backend: переключение vector storage, runtime tuning, chunking и cache-настройки RAG.
</em></p>

### Retrieval cache

Снижение latency retrieval при повторном запросе (OFF / MISS / HIT).

![Сравнение retrieval cache MISS и HIT](screenshots/cache-hit-adm.png)

<p align="center"><em>
Сравнение retrieval cache MISS и HIT: снижение latency retrieval при повторном запросе.
</em></p>

---

## 🎛️ Сессии по модальностям (консоль)

### Текстовый pipeline

Параметры LLM-запроса, telemetry и таймлайн обработки text-response.

![Консоль текстового pipeline](screenshots/text-adm.png)

<p align="center"><em>
Консоль текстового pipeline: параметры LLM-запроса, telemetry и таймлайн обработки text-response.
</em></p>

### Voice pipeline

STT/TTS telemetry, аудио-сессия и таймлайн обработки голосового запроса.

![Консоль voice pipeline](screenshots/audio-adm.png)

<p align="center"><em>
Операционная консоль voice pipeline: STT/TTS telemetry, аудио-сессия и таймлайн обработки голосового запроса.
</em></p>

### Генерация изображений

Refined prompt, telemetry image pipeline и сохранённый generated asset.

![Консоль генерации изображений](screenshots/image-adm.png)

<p align="center"><em>
Консоль генерации изображений: refined prompt, telemetry image pipeline и сохранённый generated asset.
</em></p>

### OCR / Vision pipeline

Распознавание изображения, telemetry обработки и извлечённый текст документа.

![OCR / Vision pipeline в консоли](screenshots/ocr_adm.png)

<p align="center"><em>
OCR/Vision pipeline: распознавание изображения, telemetry обработки и извлечённый текст документа.
</em></p>

### Память диалога

Контекст диалога, trimming history и политика ограничения conversational memory.

![Диагностика runtime memory](screenshots/mem-adm.png)

<p align="center"><em>
Диагностика runtime memory: контекст диалога, trimming history и политика ограничения conversational memory.
</em></p>

---

## 📊 Наблюдаемость и качество RAG

### Сводная статистика и журнал сессий

Сводная операционная статистика платформы: маршруты обработки, этапы pipeline, телеметрия провайдеров.

![Сводная операционная статистика](screenshots/summary-adm.png)

<p align="center"><em>
Сводная операционная статистика платформы: маршруты обработки, этапы pipeline, телеметрия провайдеров и агрегированные метрики.
</em></p>

Журнал execution-сессий и трассировка pipeline обработки запросов.

![Журнал execution-сессий](screenshots/logs-adm.png)

<p align="center"><em>
Журнал execution-сессий и трассировка pipeline обработки запросов Assistant Flow.
</em></p>

### Оценка качества RAG

Консоль оценки качества: RAGAS-метрики, ручная валидация ответов, анализ retrieved chunks.

![Консоль оценки качества RAG](screenshots/ragas-adm.png)

<p align="center"><em>
Консоль оценки качества RAG: RAGAS-метрики, ручная валидация ответов и анализ retrieved chunks.
</em></p>

Сравнение отдельных RAG-сессий внутри evaluation run.

![Сравнение сессий в evaluation run](screenshots/evaluation-run-adm.png)

<p align="center"><em>
Сравнение отдельных RAG-сессий внутри evaluation run с отображением метрик quality evaluation.
</em></p>

Smoke-тест RAG из репозитория — [🧪 `RAG_SMOKE_TEST.md`](RAG_SMOKE_TEST.md).

---

## 🧭 Типовой сценарий

1. Оператор загружает документы в консоль («Документы») — платформа индексирует базу знаний.
2. Пользователь задаёт вопрос в Telegram (например, `/mode rag` и вопрос по базе знаний).
3. Система выполняет поиск по базе знаний и формирует ответ с блоком «Источники».
4. Оператор просматривает трассировку в консоли (RAG: чанки, score, latency; Логи: этапы pipeline).

Маршрут проверки живого демо за 5 шагов — [🧭 `DEMO_ROUTE.md`](DEMO_ROUTE.md); расширенная матрица — [🎬 `DEMO_SCENARIOS.md`](DEMO_SCENARIOS.md).

---

## 📚 Связанные документы

- [🏠 `README.md`](../README.md) — точка входа в проект.
- [💼 `BUSINESS_VALUE.md`](BUSINESS_VALUE.md) — бизнес-проблема, решение, эффект, выгода.
- [🧭 `DEMO_ROUTE.md`](DEMO_ROUTE.md) — маршрут проверки демо.
- [🎬 `DEMO_SCENARIOS.md`](DEMO_SCENARIOS.md) — расширенная матрица демо-проверок.
- [🖼️ `screenshots/MEDIA_INDEX.md`](screenshots/MEDIA_INDEX.md) — каталог медиаматериалов.