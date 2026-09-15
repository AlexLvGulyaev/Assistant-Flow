# 📖 Assistant Flow — руководство пользователя

Как пользоваться Telegram-ассистентом Assistant Flow. Развёртывание — [🚀 `DEPLOYMENT_GUIDE.md`](DEPLOYMENT_GUIDE.md); операционная консоль — [🎛️ `ADMIN_GUIDE.md`](ADMIN_GUIDE.md).

**Статус:** актуально на 2026-09-15.

---

## 🎯 1. Назначение

Assistant Flow — мультимодальный AI-ассистент в Telegram:

- текстовый диалог;
- RAG — вопросы по корпоративной базе знаний;
- OCR / Vision — текст с фотографий;
- голос (STT/TTS), если включено оператором;
- генерация изображений.

---

## 🔌 2. Подключение к боту

Система должна быть уже запущена ([DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)).

1. Найдите в Telegram бота по **@username**, который задал оператор в BotFather (в репозитории имени нет).
2. **Start** или `/start`.
3. `/help` — режимы и примеры.

Если бот не отвечает — оператору: [⚙️ `OPERATIONS.md`](OPERATIONS.md) § «Типовые проблемы» (токен, restart).

---

## 🧭 3. Сценарии (схемы)

Операционные потоки: стадии соответствуют `processing_logs` и карточкам в консоли (разделы **Текст**, **RAG**, **Логи**). Это не полная архитектурная схема — внутренние вызовы сервисов свёрнуты.

*Этапы pipeline отражаются в `processing_logs` и доступны в операционной консоли.*

### Текст

```mermaid
flowchart TB
    subgraph r1 [" "]
        direction LR
        U[Пользователь] --> TG[Telegram] --> S1[Запрос получен] --> S2[Маршрут: текстовый ответ] --> S3[Подготовка prompt] --> S4[Запрос к AI-провайдеру]
    end
    subgraph r2 [" "]
        direction LR
        S5[Ответ сформирован] --> S6[Завершение обработки] --> A[Ответ пользователю]
    end
    r1 --> r2
    style r1 fill:none,stroke:none
    style r2 fill:none,stroke:none
```

*Стадии в логах:* `intake_received` → `route_selected` → `processing_done` → `text_answer_done`.

### RAG

```mermaid
flowchart TB
    subgraph r1 [" "]
        direction LR
        U[Вопрос по документам] --> TG[Telegram] --> S1[Запрос получен] --> S2[Маршрут: RAG] --> C{Кэш retrieval}
        C -->|MISS| R1[Поиск в векторной базе]
        R1 --> R2[Чанки и ранжирование] --> R3[Запись в кэш] --> C1[Контекст из кэша]
        C -->|HIT| C1
    end
    subgraph r2 [" "]
        direction LR
        L1[Сборка RAG prompt] --> L2[Запрос к AI-провайдеру] --> S3[Ответ RAG зафиксирован] --> S4[Завершение обработки] --> A[Ответ и источники]
    end
    r1 --> r2
    style r1 fill:none,stroke:none
    style r2 fill:none,stroke:none
```

*Стадии в логах:* `intake_received` → `route_selected` → `rag_answer_done` (в `details`: cache HIT/MISS, latency retrieval, чанки) → `processing_done`. При включённой памяти возможны `memory_load_started` / `memory_load_done`.

### OCR (OpenAI Vision)

```mermaid
flowchart TB
    subgraph r1 [" "]
        direction LR
        U[Фото] --> TG[Telegram] --> S1[Запрос получен] --> S2[Изображение принято] --> S3[Старт OCR / Vision] --> S4[Запрос к OpenAI Vision]
    end
    subgraph r2 [" "]
        direction LR
        S5[Текст извлечён] --> S6[Ответ отправлен] --> S7[Завершение обработки] --> A[Распознанный текст]
    end
    r1 --> r2
    style r1 fill:none,stroke:none
    style r2 fill:none,stroke:none
```

*Стадии в логах:* `intake_received` → `image_received` → `ocr_started` → `ocr_done` → `ocr_response_sent` → `processing_done`. Локальный OCR не используется.

### Голос (STT → текст → опционально TTS)

```mermaid
flowchart TB
    subgraph r1 [" "]
        direction LR
        U[Голосовое] --> TG[Telegram] --> S1[Запрос получен] --> S2[Распознавание речи STT] --> S3[Маршрут выбран] --> S4[Текстовый ответ AI]
    end
    subgraph r2 [" "]
        direction LR
        T{TTS включён?} -->|да| S5[Синтез речи TTS] --> S6[Голосовая сессия завершена] --> A[Ответ в чат]
        T -->|нет| S6
    end
    r1 --> r2
    style r1 fill:none,stroke:none
    style r2 fill:none,stroke:none
```

*Стадии в логах:* `intake_received` → `stt_started` → `stt_completed` → `route_selected` → `text_answer_done` → `tts_started` / `tts_skipped` / `tts_completed` → `voice_processing_done`.

---

## 📜 4. Команды Telegram

| Команда | Действие |
|---------|----------|
| `/start` | Приветствие |
| `/help` | Справка по режимам |
| `/mode text` | Диалог и генерация изображений |
| `/mode rag` | Вопросы по базе знаний |
| `/mode ocr` | Распознавание текста на фото |
| `/stats` | Статистика индекса (RAG) |
| `/reset` | Сброс режима и in-memory RAG + ротация диалоговой сессии |
| `/clear` | Очистка контекста RAG (см. `/help`) |

> 💡 `/reset` также завершает текущую диалоговую сессию памяти: следующий диалог начинается с чистой историей (в консоли видно событие `memory_session_cleared` — раздел [🎛️ `ADMIN_GUIDE.md`](ADMIN_GUIDE.md) § Memory).

---

## 💬 5. Текстовый режим (`/mode text`)

- Вопросы на естественном языке.
- «Нарисуй…» — генерация изображения.
- Память диалога — если включена оператором (PostgreSQL).

**Пример:** «объясни простыми словами, что такое фотосинтез».

![Пример текстового ответа в Telegram](screenshots/text-tg.png)

<p align="center"><em>
Пример текстового ответа Telegram-ассистента в режиме обычного диалога.
</em></p>

---

## 🔍 6. RAG (`/mode rag`)

Оператор заранее загружает документы ([🎛️ `ADMIN_GUIDE.md`](ADMIN_GUIDE.md) § Документы).

1. `/mode rag`.
2. Вопрос по содержимому проиндексированных файлов.
3. Ответ + блок **Источники**.

**Пример:** «дай полную сводку по компании НоваТех» (если такие документы есть в базе).

Без индексации — fallback без релевантных источников.

![RAG-ответ в Telegram](screenshots/rag-tg.png)

<p align="center"><em>
RAG-ответ Telegram-ассистента на основе корпоративной базы знаний Assistant Flow.
</em></p>

---

## 📄 7. Распознавание текста (OCR)

OpenAI Vision; локальный Tesseract не используется.

**Режим OCR:** `/mode ocr` → фото (подпись необязательна).

**В text/rag:** фото + подпись «распознай текст», «OCR», «извлеки текст» и т.п.

**Ответ:** блок «Распознанный текст:». В `/mode ocr` подпись может уточнить задание для vision (один вызов API).

**Примеры:** фото договора; фото + «объясни простыми словами, что написано».

**Ограничения:** размытие, рукопись, мелкий шрифт, сложные таблицы. RAG по картинке без OCR не выполняется.

![OCR в Telegram](screenshots/ocr_tg.png)

<p align="center"><em>
Пример OCR-обработки изображения в Telegram: распознавание текста средствами OpenAI Vision.
</em></p>

---

## 🔊 8. Голос

При включённом аудио в окружении: голосовое → текст (и опционально озвучка). По умолчанию в демо — отключено.

![Голосовое взаимодействие в Telegram](screenshots/audio-tg.png)

<p align="center"><em>
Пример голосового взаимодействия с Telegram-ассистентом: распознавание речи и генерация аудио-ответа.
</em></p>

---

## 🖼️ 9. Генерация изображений

`/mode text` → «нарисуй слона в посудной лавке» → изображение в чате.

![Генерация изображения в Telegram](screenshots/image-tg.png)

<p align="center"><em>
Пример генерации изображения Telegram-ассистентом по текстовому запросу пользователя.
</em></p>

---

## 🧠 10. Память диалога

- История в PostgreSQL (если настроено).
- Контекст для модели ограничен по размеру — ответы остаются устойчивыми и предсказуемыми.
- `/reset` — начать диалог заново (см. § 4).

Как память видна оператору — [🎛️ `ADMIN_GUIDE.md`](ADMIN_GUIDE.md) § Memory.

---

## 📚 11. См. также

- [🏠 `README.md`](../README.md) — точка входа в проект.
- [🎛️ `ADMIN_GUIDE.md`](ADMIN_GUIDE.md) — руководство администратора консоли.
- [🎬 `SYSTEM_DEMO.md`](SYSTEM_DEMO.md) — скриншоты и типовой сценарий.
- [🧭 `DEMO_ROUTE.md`](DEMO_ROUTE.md) — маршрут проверки демо.
- [🏗️ `ARCHITECTURE.md`](ARCHITECTURE.md) — устройство системы.