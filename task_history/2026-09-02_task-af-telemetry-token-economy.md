# 2026-09-02 — AF: telemetry / token economy (долг №3)

## Задание (владелец)

Программа закрытия технического долга AF (PORTFOLIO_CORPUS_AUDIT.md v1.18),
согласованный порядок: №1+№2 → №3. Пункты №1 (heavy RAG safeguards) и №2
(multi-version docs + idempotent reindex) закрыты 02.09 в
[2026-09-02_task-af-tech-debt-closure.md](2026-09-02_task-af-tech-debt-closure.md).
Подтверждение владельца на старт №3: «Делай».

Цель: telemetry/token economy — прозрачная экономика токенов и телеметрии
контура AF (LLM/embeddings) без новой инфраструктуры.

## Порядок и время (~2–3 ч)

1. Файл задачи — 5 мин.
2. Инвентаризация: что уже собирается (token fields в diagnostics,
   processing_logs, evaluation, gigachat/proxy) и что теряется — 30–45 мин.
3. Сведение в экономику: агрегация (per period / per mode / per source),
   минимальный API + поверхность в admin-консоли — 1–1.5 ч.
4. Проверки (live) + файл задачи — 30 мин.

## Выполненные действия

### 1. Инвентаризация (замеры живого контура, 02.09)

- **Что уже собирается:** `processing_logs.details` несёт токены у
  `rag_answer_done` (240/276 строк, 286k токенов all-time), `text_answer_done`
  (21/21), OCR, image-refinement; keys: top-level `total/input/output_tokens`,
  вложенные `token_usage.*` / `usage.*`.
- **Дыра 1:** `stt_completed` (0/9) и `tts_completed` (0/7) — результаты
  `AudioTranscriptionResult`/`TTSResult` несут usage, но лог-строки его теряли.
- **Дыра 2:** телеметрия в Summary считалась по хвостовой выборке
  (`get_recent_logs(limit=500)`) — не полный учёт.
- **Не захватывается:** embeddings (`text-embedding-3-small`) — LangChain
  `OpenAIEmbeddings` не экспонирует API-usage; зафиксировано в OPERATIONS.md
  (оценка chars/4, не замер). Costs: только `cost_usd` от STT-провайдера,
  собственный прайс-линет не вводился (устаревший прайс = ложные цифры).

### 2. Реализация

- **STT/TTS токены в лог** (`interfaces/telegram_bot.py`): `stt_completed` /
  `tts_completed` details дополняются `input/output/total_tokens` + `cost_usd`
  (когда провайдер вернул usage).
- **Точная SQL-агрегация** (`repositories/processing_logs_repository.py`):
  NEW `get_token_economy_since(hours)` — по полному окну, все известные
  локации ключей; возврат `grand_total_tokens`, `by_stage`
  (events / rows_with_tokens / total), `by_model` (top-20).
- **API** (`/api/summary` → `token_economy`): `admin_service.get_summary_payload`,
  `admin_api/schemas/summary.py` (NEW `TokenEconomy`, `TokenEconomyStageRow`,
  `TokenEconomyModelRow`).
- **UI** (`frontend/admin-ui`): типы в `client.ts`; NEW панель
  **Summary → «F. Токен-экономика (точное окно)»** — гранд-тотал, разбивка
  по этапам (токены + rows_with_tokens/events), по моделям.

### 3. Проверки (live)

- Пересборка/деплой admin-api + assistant-flow + admin-ui; все контейнеры Up,
  admin-api `(healthy)`, бот на polling; 0 JS-ошибок сборки (tsc --noEmit OK).
- `/api/summary?hours=720` → `token_economy`: grand 17 007; by_stage (rag
  5 152, ocr 3 025, text 1 575 …), by_model (gpt-4o-mini 11 202,
  GigaChat-Max 2 286, gpt-image-1 494).
- **Кросс-чек точности:** идентичный SQL в psql → ровно 17 007 (PASS).
  All-time сумма (345k) относится к периоду с 10.05 — за 720-часовым окном,
  семантика окна корректна.
- Бандл admin-ui содержит панель (`grep 'Токен-экономика'` в assets).

## Изменённые файлы

| Файл | Что сделано |
|------|-------------|
| `repositories/processing_logs_repository.py` | NEW `get_token_economy_since` (+ SQL-константы локаций токенов) |
| `services/admin_service.py` | `get_summary_payload`: блок `token_economy` (точное окно, try/except → пустой блок) |
| `admin_api/schemas/summary.py` | NEW `TokenEconomy` / `TokenEconomyStageRow` / `TokenEconomyModelRow`; поле в `SummaryResponse` |
| `interfaces/telegram_bot.py` | STT/TTS usage → `stt_completed` / `tts_completed` details |
| `frontend/admin-ui/src/api/client.ts` | Типы `TokenEconomy*`, поле в `SummaryResponse` |
| `frontend/admin-ui/src/pages/SummaryPage.tsx` | NEW панель F «Токен-экономика (точное окно)» |
| `docs/OPERATIONS.md` | Секция токен-экономики: панель, покрытие, embeddings-ограничение |
| `task_history/2026-09-02_task-af-telemetry-token-economy.md` | Этот файл |

## Итоговый статус

**DONE** (2026-09-02). Токен-экономика: точный учёт по полному окну
(SQL-агрегация, кросс-чек psql PASS), API `/api/summary → token_economy`,
панель в Summary-консоли; закрыты дыры STT/TTS-usage в логах. Ограничение
зафиксировано: embeddings-usage не экспонируется LangChain — вне замера.
Визуальная приёмка панели — за владельцем (af-admin → Summary → секция F).

Из контура долга AF (v1.18) остались: RAG UI polish, production build,
async layer, audio P5.4 remainder — по отдельному согласованию. После долга —
второй этап владельца: «причёсывание старичка» = сам Assistant Flow
(методологический предшественник APL; разъяснено владельцем 02.09).