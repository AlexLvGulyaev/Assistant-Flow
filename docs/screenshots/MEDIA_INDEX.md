# 🖼️ MEDIA_INDEX.md — Assistant Flow

**Проект:** Assistant-Flow
**Дата:** 2026-09-15
**Статус:** Каталог всех скриншотов публичного репозитория: назначение, использование, статус.

Каждый файл из `docs/screenshots/` зарегистрирован ниже. Визуальная приёмка
соответствия подписи и содержимого — за владельцем репозитория.

---

## 📋 Реестр скриншотов

| Файл | Категория | Что показывает | Где используется | Статус |
|------|-----------|----------------|------------------|--------|
| `AF_portfolio_light.png` | Hero | Интерфейс системы (светлая тема) — обзорная композиция консоли | [README.md](../../README.md) (главный визуал) | ✅ Актуален |
| `AF_portfolio_dark.png` | Hero | Интерфейс системы (тёмная тема) — обзорная композиция консоли | [ARCHITECTURE.md](../ARCHITECTURE.md) (главный визуал) | ✅ Актуален |
| `text-tg.png` | Telegram | Текстовый ответ бота в чате | USER_GUIDE, SYSTEM_DEMO | ✅ Актуален |
| `text-adm.png` | Консоль | Трассировка текстового pipeline сессии | SYSTEM_DEMO | ✅ Актуален |
| `rag-tg.png` | Telegram | RAG-ответ с блоком «Источники» | USER_GUIDE, SYSTEM_DEMO | ✅ Актуален |
| `rag-adm.png` | Консоль | RAG-сессии: чанки, latency, cache-статус | SYSTEM_DEMO | ✅ Актуален |
| `retrieval-details-adm.png` | Консоль | Расширенная диагностика retrieval (полный текст чанка) | SYSTEM_DEMO | ✅ Актуален |
| `ocr_tg.png` | Telegram | Распознавание текста с фото (OCR) | USER_GUIDE, SYSTEM_DEMO | ✅ Актуален |
| `ocr_adm.png` | Консоль | OCR / Vision pipeline в консоли | SYSTEM_DEMO | ✅ Актуален |
| `audio-tg.png` | Telegram | Голосовое взаимодействие (STT/TTS) | USER_GUIDE, SYSTEM_DEMO | ✅ Актуален |
| `audio-adm.png` | Консоль | Voice pipeline: транскрипция, TTS, стоимость | SYSTEM_DEMO | ✅ Актуален |
| `image-tg.png` | Telegram | Генерация изображения по запросу | USER_GUIDE, SYSTEM_DEMO | ✅ Актуален |
| `image-adm.png` | Консоль | Телеметрия генерации изображений | SYSTEM_DEMO | ✅ Актуален |
| `mem-adm.png` | Консоль | Диагностика runtime memory (сессии, контекст) | SYSTEM_DEMO, ADMIN_GUIDE | ✅ Актуален |
| `documents-adm.png` | Консоль | Управление документами knowledge base (upload, reindex) | SYSTEM_DEMO, ADMIN_GUIDE | ✅ Актуален |
| `rs-adm.png` | Консоль | Панель Retrieval Settings (бэкенды, параметры) | SYSTEM_DEMO, ADMIN_GUIDE | ✅ Актуален |
| `cache-hit-adm.png` | Консоль | Сравнение retrieval cache MISS и HIT | SYSTEM_DEMO, ADMIN_GUIDE | ✅ Актуален |
| `logs-adm.png` | Консоль | Журнал execution-сессий (processing_logs) | SYSTEM_DEMO, ADMIN_GUIDE | ✅ Актуален |
| `overview-adm.png` | Консоль | Обзор: health зависимостей, провайдеры, retrieval backend | SYSTEM_DEMO, ADMIN_GUIDE | ✅ Актуален |
| `summary-adm.png` | Консоль | Сводная операционная статистика | SYSTEM_DEMO | ✅ Актуален |
| `ragas-adm.png` | Консоль | Консоль оценки качества RAG (RAGAS) | SYSTEM_DEMO | ✅ Актуален |
| `evaluation-run-adm.png` | Консоль | Сравнение сессий в evaluation run | SYSTEM_DEMO | ✅ Актуален |

---

## 📐 Visual contract

- **README** — светлый hero (`AF_portfolio_light.png`); тема GitHub по умолчанию светлая.
- **ARCHITECTURE.md** — тёмный hero (`AF_portfolio_dark.png`).
- **SYSTEM_DEMO.md** — галерея: продукт как работающая система (все скриншоты реестра).
- Скриншоты консоли (`*-adm.png`) — операционная консоль (Admin UI); `*-tg.png` — пользовательский контур (Telegram-бот).