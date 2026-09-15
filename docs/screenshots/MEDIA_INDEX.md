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
| `text-tg.png` | Telegram | Текстовый ответ бота в чате | README, USER_GUIDE | ✅ Актуален |
| `text-adm.png` | Консоль | Трассировка текстового pipeline сессии | README, USER_GUIDE | ✅ Актуален |
| `rag-tg.png` | Telegram | RAG-ответ с блоком «Источники» | README, USER_GUIDE | ✅ Актуален |
| `rag-adm.png` | Консоль | RAG-сессии: чанки, latency, cache-статус | README, USER_GUIDE | ✅ Актуален |
| `retrieval-details-adm.png` | Консоль | Расширенная диагностика retrieval (полный текст чанка) | README, USER_GUIDE, ARCHITECTURE | ✅ Актуален |
| `ocr_tg.png` | Telegram | Распознавание текста с фото (OCR) | README, USER_GUIDE | ✅ Актуален |
| `ocr_adm.png` | Консоль | OCR / Vision pipeline в консоли | README, USER_GUIDE | ✅ Актуален |
| `audio-tg.png` | Telegram | Голосовое взаимодействие (STT/TTS) | README, USER_GUIDE | ✅ Актуален |
| `audio-adm.png` | Консоль | Voice pipeline: транскрипция, TTS, стоимость | README, USER_GUIDE | ✅ Актуален |
| `image-tg.png` | Telegram | Генерация изображения по запросу | README, USER_GUIDE | ✅ Актуален |
| `image-adm.png` | Консоль | Телеметрия генерации изображений | README, USER_GUIDE | ✅ Актуален |
| `mem-adm.png` | Консоль | Диагностика runtime memory (сессии, контекст) | README, USER_GUIDE | ✅ Актуален |
| `documents-adm.png` | Консоль | Управление документами knowledge base (upload, reindex) | README, USER_GUIDE | ✅ Актуален |
| `rs-adm.png` | Консоль | Панель Retrieval Settings (бэкенды, параметры) | README, USER_GUIDE | ✅ Актуален |
| `cache-hit-adm.png` | Консоль | Сравнение retrieval cache MISS и HIT | README, USER_GUIDE | ✅ Актуален |
| `logs-adm.png` | Консоль | Журнал execution-сессий (processing_logs) | README, USER_GUIDE, ARCHITECTURE | ✅ Актуален |
| `overview-adm.png` | Консоль | Обзор: health зависимостей, провайдеры, retrieval backend | README, USER_GUIDE | ✅ Актуален |
| `summary-adm.png` | Консоль | Сводная операционная статистика | README, USER_GUIDE | ✅ Актуален |
| `ragas-adm.png` | Консоль | Консоль оценки качества RAG (RAGAS) | README, USER_GUIDE | ✅ Актуален |
| `evaluation-run-adm.png` | Консоль | Сравнение сессий в evaluation run | README, USER_GUIDE | ✅ Актуален |

---

## 📐 Visual contract

- **README** — светлый hero (`AF_portfolio_light.png`); тема GitHub по умолчанию светлая.
- **ARCHITECTURE.md** — тёмный hero (`AF_portfolio_dark.png`).
- Скриншоты консоли (`*-adm.png`) — операционная консоль (Admin UI); `*-tg.png` — пользовательский контур (Telegram-бот).