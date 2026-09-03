# 📖 Assistant Flow User Guide

Как **пользоваться** уже запущенной системой. Развёртывание и smoke — [🚀 RUNBOOK.md](RUNBOOK.md).

---

## 1. Назначение платформы

Assistant Flow — мультимодальная AI-платформа:

- корпоративная база знаний и RAG;
- текстовый диалог в Telegram;
- голос (STT/TTS), если включено оператором;
- генерация изображений;
- OCR / Vision — текст с фотографий;
- административная консоль для оператора.

---

## 2. Основные интерфейсы

| Интерфейс | Кто | Назначение |
|-----------|-----|------------|
| **Telegram** | Пользователь | Вопросы, RAG, фото, голос, картинки |
| **Admin UI** | Оператор | Диагностика, документы, память, оценка RAG |

Адрес UI после portfolio-запуска: `http://localhost:8080` (см. RUNBOOK).

---

## 3. Подключение к Telegram-боту

Система должна быть уже запущена ([RUNBOOK.md](RUNBOOK.md)).

1. Найдите в Telegram бота по **@username**, который задал оператор в BotFather (в репозитории имени нет).
2. **Start** или `/start`.
3. `/help` — режимы и примеры.

Если бот не отвечает — оператору: RUNBOOK §G (токен, restart).

---

## 4. Сценарии (схемы)

Операционные потоки: стадии соответствуют `processing_logs` и карточкам в Admin UI (разделы **Текст**, **RAG**, **Логи**). Это не полная архитектурная схема — внутренние вызовы сервисов свёрнуты.

*Этапы pipeline отражаются в `processing_logs` и доступны в Admin UI.*

### Текст

```mermaid
flowchart LR
    U[Пользователь] --> TG[Telegram]
    TG --> S1[Запрос получен]
    S1 --> S2[Маршрут: текстовый ответ]
    S2 --> S3[Подготовка prompt]
    S3 --> S4[Запрос к AI-провайдеру]
    S4 --> S5[Ответ сформирован]
    S5 --> S6[Завершение обработки]
    S6 --> A[Ответ пользователю]
```

*Стадии в логах:* `intake_received` → `route_selected` → `processing_done` → `text_answer_done`.

### RAG

```mermaid
flowchart LR
    U[Вопрос по документам] --> TG[Telegram]
    TG --> S1[Запрос получен]
    S1 --> S2[Маршрут: RAG]
    S2 --> C{Кэш retrieval}

    C -->|HIT| C1[Контекст из кэша]
    C -->|MISS| R1[Поиск в векторной базе]
    R1 --> R2[Чанки и ранжирование]
    R2 --> R3[Запись в кэш]
    R3 --> C1

    C1 --> L1[Сборка RAG prompt]
    L1 --> L2[Запрос к AI-провайдеру]
    L2 --> S3[Ответ RAG зафиксирован]
    S3 --> S4[Завершение обработки]
    S4 --> A[Ответ и источники]
```

*Стадии в логах:* `intake_received` → `route_selected` → `rag_answer_done` (в `details`: cache HIT/MISS, latency retrieval, чанки) → `processing_done`. При включённой памяти возможны `memory_load_started` / `memory_load_done`.

### OCR (OpenAI Vision)

```mermaid
flowchart LR
    U[Фото] --> TG[Telegram]
    TG --> S1[Запрос получен]
    S1 --> S2[Изображение принято]
    S2 --> S3[Старт OCR / Vision]
    S3 --> S4[Запрос к OpenAI Vision]
    S4 --> S5[Текст извлечён]
    S5 --> S6[Ответ отправлен]
    S6 --> S7[Завершение обработки]
    S7 --> A[Распознанный текст]
```

*Стадии в логах:* `intake_received` → `image_received` → `ocr_started` → `ocr_done` → `ocr_response_sent` → `processing_done`. Локальный OCR не используется.

### Голос (STT → текст → опционально TTS)

```mermaid
flowchart LR
    U[Голосовое] --> TG[Telegram]
    TG --> S1[Запрос получен]
    S1 --> S2[Распознавание речи STT]
    S2 --> S3[Маршрут выбран]
    S3 --> S4[Текстовый ответ AI]
    S4 --> T{TTS включён?}
    T -->|да| S5[Синтез речи TTS]
    T -->|нет| S6[Голосовая сессия завершена]
    S5 --> S6
    S6 --> A[Ответ в чат]
```

*Стадии в логах:* `intake_received` → `stt_started` → `stt_completed` → `route_selected` → `text_answer_done` → `tts_started` / `tts_skipped` / `tts_completed` → `voice_processing_done`.

### Индексация документов (оператор)

```mermaid
flowchart LR
    OP[Оператор] --> UI[Admin UI: Документы]
    UI --> S1[Загрузка файла]
    S1 --> S2[Предобработка текста]
    S2 --> S3[Артефакт сохранён]
    S3 --> S4[Копия для RAG-каталога]
    S4 --> S5[Индексация: чанки]
    S5 --> S6[Эмбеддинги в vector backend]
    S5 --> PG[(Метаданные PostgreSQL)]
    S6 --> S7[Пайплайн загрузки завершён]
```

*Стадии в логах:* `admin_document_uploaded_raw` → `document_preprocessing_started` → `document_preprocessing_done` → `document_processed_artifact_saved` → `document_compatibility_file_written` → `document_indexing_started` → `document_indexing_done` → `document_upload_pipeline_done`.

### Кэш retrieval (внутри RAG)

```mermaid
flowchart LR
    Q[RAG-запрос] --> C{Кэш retrieval}
    C -->|HIT| H[Повторное использование чанков]
    C -->|MISS| R[Поиск в vector backend]
    R --> W[Сохранение в кэш]
    W --> H
    H --> L[Дальше: RAG prompt и LLM]
```

*В UI:* OFF / MISS / HIT и `retrieval_latency_ms` в карточке RAG; в логах — поля `retrieval_cache_hit` / `retrieval_cache_miss` внутри `rag_answer_done`.

---

## 5. Команды Telegram

| Команда | Действие |
|---------|----------|
| `/start` | Приветствие |
| `/help` | Справка по режимам |
| `/mode text` | Диалог и генерация изображений |
| `/mode rag` | Вопросы по базе знаний |
| `/mode ocr` | Распознавание текста на фото |
| `/stats` | Статистика индекса (RAG) |
| `/reset` | Сброс режима и in-memory RAG |
| `/clear` | Очистка контекста RAG (см. `/help`) |

---

## 6. Текстовый режим (`/mode text`)

- Вопросы на естественном языке.
- «Нарисуй…» — генерация изображения.
- Память диалога — если включена оператором (PostgreSQL).

**Пример:** «объясни простыми словами, что такое фотосинтез».

![Пример текстового ответа в Telegram](docs/screenshots/text-tg.png)

<p align="center"><em>
Пример текстового ответа Telegram-ассистента в режиме обычного диалога.
</em></p>

![Консоль текстового pipeline](docs/screenshots/text-adm.png)

<p align="center"><em>
Консоль текстового pipeline: параметры LLM-запроса, telemetry и таймлайн обработки text-response.
</em></p>

---

## 7. RAG (`/mode rag`)

Оператор заранее загружает документы (**Документы** в Admin UI).

1. `/mode rag`.
2. Вопрос по содержимому проиндексированных файлов.
3. Ответ + блок **Источники**.

**Пример:** «дай сводку по компании NovaTex» (если такие документы есть в базе).

Без индексации — fallback без релевантных источников.

![RAG-ответ в Telegram](docs/screenshots/rag-tg.png)

<p align="center"><em>
RAG-ответ Telegram-ассистента на основе корпоративной базы знаний Assistant Flow.
</em></p>

![Операционная консоль RAG-сессий](docs/screenshots/rag-adm.png)

<p align="center"><em>
Операционная консоль RAG-сессий с диагностикой retrieval, latency, cache-state и найденных чанков.
</em></p>

![Расширенная диагностика retrieval](docs/screenshots/retrieval-details-adm.png)

<p align="center"><em>
Расширенная диагностика retrieval: найденные чанки, relevance-score, latency retrieval и состояние retrieval cache.
</em></p>

---

## 8. Распознавание текста (OCR)

OpenAI Vision; локальный Tesseract не используется.

**Режим OCR:** `/mode ocr` → фото (подпись необязательна).

**В text/rag:** фото + подпись «распознай текст», «OCR», «извлеки текст» и т.п.

**Ответ:** блок «Распознанный текст:». В `/mode ocr` подпись может уточнить задание для vision (один вызов API).

**Примеры:** фото договора; фото + «объясни простыми словами, что написано».

**Ограничения:** размытие, рукопись, мелкий шрифт, сложные таблицы. RAG по картинке без OCR не выполняется.

Оператор смотрит маршрут `vision_ocr` в **Текст** / **Логи**.

![OCR в Telegram](docs/screenshots/ocr_tg.png)

<p align="center"><em>
Пример OCR-обработки изображения в Telegram: распознавание текста средствами OpenAI Vision.
</em></p>

![OCR / Vision pipeline в консоли](docs/screenshots/ocr_adm.png)

<p align="center"><em>
OCR/Vision pipeline: распознавание изображения, telemetry обработки и извлечённый текст документа.
</em></p>

---

## 9. Голос

При включённом аудио в окружении: голосовое → текст (и опционально озвучка). По умолчанию в demo — отключено.

![Голосовое взаимодействие в Telegram](docs/screenshots/audio-tg.png)

<p align="center"><em>
Пример голосового взаимодействия с Telegram-ассистентом: распознавание речи и генерация аудио-ответа.
</em></p>

![Консоль voice pipeline](docs/screenshots/audio-adm.png)

<p align="center"><em>
Операционная консоль voice pipeline: STT/TTS telemetry, аудио-сессия и таймлайн обработки голосового запроса.
</em></p>

---

## 10. Генерация изображений

`/mode text` → «нарисуй слона в посудной лавке» → изображение в чате.

![Генерация изображения в Telegram](docs/screenshots/image-tg.png)

<p align="center"><em>
Пример генерации изображения Telegram-ассистентом по текстовому запросу пользователя.
</em></p>

![Консоль генерации изображений](docs/screenshots/image-adm.png)

<p align="center"><em>
Консоль генерации изображений: refined prompt, telemetry image pipeline и сохранённый generated asset.
</em></p>

---

## 11. Память диалога

- История в PostgreSQL (если настроено).
- Контекст для модели ограничен по размеру.
- Оператор: **Memory** (`/memory`) в Admin UI.

`/reset` — сброс режима и in-memory RAG.

![Диагностика runtime memory](docs/screenshots/mem-adm.png)

<p align="center"><em>
Диагностика runtime memory: контекст диалога, trimming history и политика ограничения conversational memory.
</em></p>

---

## 12. Документы (оператор)

Admin UI → **Документы**: загрузка, индексация, reindex, `chunk_count`.

[docs/ADMIN_INDEXING.md](docs/ADMIN_INDEXING.md)

![Управление документами knowledge base](docs/screenshots/documents-adm.png)

<p align="center"><em>
Управление документами knowledge base: индексация, preprocessing, версии документов и жизненный цикл ingestion pipeline.
</em></p>

---

## 13. Административная консоль

### Вход

- Токены заданы в `.env` (`AF_ADMIN_TOKEN`, `AF_ADMIN_DEMO_TOKEN`) → при открытии консоли открывается экран входа: введите токен или нажмите **«Войти в демо-режиме»** (read-only, токен запечён в UI при сборке).
- Токены не заданы → консоль открывается без авторизации (локальный режим).
- Выход — кнопка **Выход** (экран `/exit`) сбрасывает сессию.
- Подробности и legacy-режим Basic-аутентификации — [docs/SECURITY_NOTES.md](docs/SECURITY_NOTES.md) и [docs/security/auth_modes.md](docs/security/auth_modes.md).

### Разделы

| Раздел | Путь |
|--------|------|
| Обзор | `/` |
| Сводка | `/summary` |
| Текст | `/text` |
| RAG | `/rag` |
| Изображения | `/images` |
| Аудио | `/audio` |
| Документы | `/documents` |
| Retrieval Settings | `/retrieval` |
| Логи | `/logs` |
| Memory | `/memory` |
| Анализ RAG | `/evaluation` |
| Аудит | `/audit` |
| Вход | `/login` |
| Выход | `/exit` |

Раздел **Аудит** показывает журнал обращений к Admin API (действие, ресурс, роль, IP). В демо-режиме запись недоступна для изменения — только просмотр.

Кэш OFF/MISS/HIT — в карточках RAG.

![Обзор состояния платформы](docs/screenshots/overview-adm.png)

<p align="center"><em>
Обзор состояния платформы Assistant Flow: health-check сервисов, активные AI-провайдеры, retrieval backend и операционные метрики.
</em></p>

![Сводная операционная статистика](docs/screenshots/summary-adm.png)

<p align="center"><em>
Сводная операционная статистика платформы: маршруты обработки, этапы pipeline, телеметрия провайдеров и агрегированные метрики.
</em></p>

![Панель Retrieval Settings](docs/screenshots/rs-adm.png)

<p align="center"><em>
Панель управления retrieval backend: переключение vector storage, runtime tuning, chunking и cache-настройки RAG.
</em></p>

![Сравнение retrieval cache MISS и HIT](docs/screenshots/cache-hit-adm.png)

<p align="center"><em>
Сравнение retrieval cache MISS и HIT: снижение latency retrieval при повторном запросе.
</em></p>

![Журнал execution-сессий](docs/screenshots/logs-adm.png)

<p align="center"><em>
Журнал execution-сессий и трассировка pipeline обработки запросов Assistant Flow.
</em></p>

![Консоль оценки качества RAG](docs/screenshots/ragas-adm.png)

<p align="center"><em>
Консоль оценки качества RAG: RAGAS-метрики, ручная валидация ответов и анализ retrieved chunks.
</em></p>

![Сравнение сессий в evaluation run](docs/screenshots/evaluation-run-adm.png)

<p align="center"><em>
Сравнение отдельных RAG-сессий внутри evaluation run с отображением метрик quality evaluation.
</em></p>

---

## 14. См. также

- [🏠 README.md](README.md)
- [🎬 docs/DEMO_SCENARIOS.md](docs/DEMO_SCENARIOS.md)
- [🏗️ docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — устройство системы
