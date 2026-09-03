# 2026-09-03 — AF: аудио-контур P5.4 remainder (долг №7)

## Задание (владелец)

> «Давай номер 7» — после закрытия долга №6 (async layer). Пункт №7 из
> PORTFOLIO_CORPUS_AUDIT v1.18: **Audio P5.4 remainder** — runtime hardening,
> нормализация STT/TTS telemetry, учёт стоимости.

## Скоуп (оценка ~6–8 ч)

Контур аудио уже построен (P5.4c/d/e): asset-first pipeline, OpenAI STT/TTS
провайдеры, voice-хэндлер с telemetry и safeguards (`audio_max_bytes`,
SHA256-сверка, lock против гонок). Реальные остатки, найденные ревизией кода:

1. **Runtime hardening:** OpenAI-клиенты STT/TTS создаются без явного
   timeout/max_retries (lib-дефолт: 600 c + 2 retry) — зависший вызов под
   `_VOICE_AUDIO_PIPELINE_LOCK` блокирует обработку голоса у всех
   пользователей. Явные таймауты через env.
2. **Учёт стоимости:** whisper и TTS не возвращают usage → tokens/cost всегда
   None. Оценочная стоимость: STT — по длительности аудио
   (`STT_COST_PER_MINUTE_USD`, default 0.006 = цена whisper-1), TTS — по
   символам (`TTS_COST_PER_1M_CHARS_USD`, default 15.0). В details пишутся
   `cost_usd` + `cost_basis: "estimated"`.
3. **Нормализация telemetry / token economy:** token economy в Summary
   агрегирует только токены; добавить per-stage и grand-total `cost_usd`
   (guarded SQL cast, безопасно к мусорным значениям), отображение в UI
   Summary; в AudioPage — стоимость STT/TTS в карточке сессии.
4. **Доки**: README (env-таблица), .env.example, IMPLEMENTATION_PLAN
   (P5.4 ◐→✅), PROJECT_STATE (№7 закрыт).

КТ-1 — после провайдеров/конфига/стоимости; КТ-2 — после token economy + UI;
финал — деплой и живая верификация (в контейнере полный TTS→STT цикл:
синтез → транскрипция → проверка cost/telemetry).

## Результаты

### КТ-1 — провайдеры/конфиг/стоимость (код)

- `utils/config.py`: +`audio_timeout_seconds` (AUDIO_TIMEOUT_SECONDS, 60),
  `audio_max_retries` (AUDIO_MAX_RETRIES, 1), `stt_cost_per_minute_usd`
  (STT_COST_PER_MINUTE_USD, 0.006), `tts_cost_per_1m_chars_usd`
  (TTS_COST_PER_1M_CHARS_USD, 15.0).
- `providers/openai_stt_provider.py`: OpenAI-клиент с явными
  timeout/max_retries; `usage={"cost_usd", "cost_basis":"estimated",
  "duration_sec"}` — длительность из metadata (fallback — latency), мин.
  1 биллинговая секунда; при тарифе 0 — `cost_basis: "unpriced"`.
- `providers/openai_tts_provider.py`: явные timeout/max_retries;
  `usage={"cost_usd", "cost_basis":"estimated", "chars"}` по числу
  символов входного текста.
- `interfaces/telegram_bot.py`: `duration_sec` передаётся в STT metadata
  (реальная длительность голосового); `cost_basis` пишется в
  stt/tts details рядом с существующей с долга №3 пропагацией `cost_usd`.

### КТ-2 — token economy + UI

- `repositories/processing_logs_repository.py` (`get_token_economy_since`):
  +`_COST_SQL` — guarded cast `details->>'cost_usd'` (regex-проверка
  числового вида, мусор → 0, не ломает агрегат); per-stage и per-model
  `cost_usd`, grand-total `grand_total_cost_usd` (round 4). Строки с
  стоимостью включаются в by_stage/by_model даже без токенов
  (stt_completed/tts_completed теперь видны в панели).
- `admin_api/schemas/summary.py`: +`cost_usd` в Stage/Model rows,
  +`grand_total_cost_usd` в TokenEconomy (все optional).
- `SummaryPage.tsx`: grand-total `· ~$X` рядом с «Всего токенов за окно»;
  per-stage и per-model строки с `· ~$X` в muted; фильтры включают
  cost-only строки.
- `AudioPage.tsx` (`client.ts`): парсинг `cost_usd` из stt/tts sub-records
  и stage-строк; 2 новые OpsRow в панели «Аудио pipeline» — «Стоимость STT
  (оценка)» / «Стоимость TTS (оценка)» с TelemetryGap при отсутствии.
- tsc 0 ошибок; vite build ok (index-DL2-rR8U.js).

### Доки

- `.env.example`: блок hardening/стоимости в секции «Аудио».
- `README.md`: строка env-таблицы «Аудио» дополнена 4 новыми переменными.
- `docs/IMPLEMENTATION_PLAN.md`: P5.4 ◐→✅ (remainder закрыт).
- `docs/SPEC.md`: голос-строка 3.1 (таймауты/ретраи, cost_basis=estimated),
  3.3 token economy с стоимостью per stage/model/grand.
- `PROJECT_STATE.md`: Decision — №3–№7 закрыты; Next Steps без №7;
  Status History строка.

### Финал — деплой + живая верификация (2026-09-03)

- Деплой: `assistant-flow`, `admin-api`, `admin-ui` пересобраны и подняты;
  бот стартовал (infinity_polling), admin-api healthy, postgres/chroma/weaviate
  healthy, fd admin-api = 11 (утечек нет).
- Конфиг в контейнере: audio on, STT/TTS = openai, timeout 60, retries 1,
  тарифы 0.006/15.0 (значения ключей не печатались).
- **Полный TTS→STT цикл в контейнере**: синтез 65 симв. (71 КБ mp3, 3758 мс)
  → `usage {cost_usd: 0.000975, estimated, chars: 65}`; транскрипция
  (2121 мс) → `usage {cost_usd: 0.0004, estimated, duration_sec: 4.0}`;
  транскрипт совпал с исходным текстом.
- **Token economy API** (синтетические строки): grand_total_cost_usd = 0.0014
  (= 0.0004 + 0.001); per-stage stt_completed/tts_completed и per-model
  whisper-1/tts-1 с стоимостью; строка с мусорным `cost_usd` («garbage-value»)
  дала 0 через guarded cast — агрегат не сломался. Синтетика удалена.
- **Headless DOM (1280×900)**: Сводка — 6/6 PASS (карточка, «Всего токенов
  за окно», grand `~$0.0014`, строки whisper-1/tts-1 с стоимостью, без
  переполнения); Аудио — 7/7 PASS (синтетическая сессия в списке, детали:
  «Стоимость STT/TTS (оценка)» со значениями, 0 JS-ошибок, без переполнения).
  Синтетика удалена после проб.
- Health: `/api/health` ok (postgres 11 мс, chroma 88 мс), все контейнеры
  healthy.

## Изменённые файлы

- `utils/config.py`, `providers/openai_stt_provider.py`,
  `providers/openai_tts_provider.py`, `interfaces/telegram_bot.py`,
  `repositories/processing_logs_repository.py`,
  `admin_api/schemas/summary.py`.
- `frontend/admin-ui/src/api/client.ts`, `src/pages/SummaryPage.tsx`,
  `src/pages/AudioPage.tsx`.
- Доки: `.env.example`, `README.md`, `docs/IMPLEMENTATION_PLAN.md`,
  `docs/SPEC.md`, `PROJECT_STATE.md`.
- NEW: `task_history/2026-09-03_task-af-audio-p54-remainder.md`.

## Итоговый статус

**DONE** (2026-09-03). Долг №7 закрыт: P5.4 полностью (foundation + UI +
observability + hardening + учёт стоимости). Живая верификация: полный
TTS→STT цикл, token economy API с guarded cast, headless DOM 13/13 PASS.
Не пушится — по явной команде владельца.