# Полный исходный промпт

```text
# Промпт для Cursor: русификация списка RAG-сессий в «Анализе качества RAG»

Используй Codex 5.3.

Сделай русификацию и UI-унификацию экрана списка RAG-сессий в разделе «Анализ качества RAG».

ВАЖНО:
1. Язык общения, комментариев и всех новых текстов — русский.
2. Не писать новые диагностические/исследовательские markdown-файлы на английском языке.
3. Если в рамках работы будут создаваться новые md/txt-отчеты — только на русском.
4. Текст данного промпта обязательно полностью сохрани в session log file.

Работаем ТОЛЬКО с экраном списка RAG-сессий (Recent RAG turns).
Главную панель «Анализ» пока НЕ трогаем.

Цель:
привести UI к стилю operational-консоли RAG:
- меньше англицизмов;
- единый язык интерфейса;
- production-style UI;
- без ощущения “внутреннего dev/debug tool”.

ВАЖНО:
Не переводить технические термины системы:
- RAG
- RAGAS
- top_k
- fallback
- Weaviate
- Chroma
- FAISS
- execution_id

execution_id — не трогать вообще.
Это operational identifier.

Также:
если элемент уже русифицирован — не переписывать его повторно.

========================
НУЖНЫЕ ИЗМЕНЕНИЯ
========================

1. Заголовок страницы

Было:
Evaluation / RAGAS

Сделать:
Анализ качества RAG

Подзаголовок:

Было:
Operational console: import RAG turns from logs · offline RAGAS · без CLI UI workflow

Сделать:
Операционная диагностика retrieval и качества ответов

========================

2. Вкладки сверху

Было:
Recent RAG turns
Evaluation runs

Сделать:
Недавние RAG-сессии
Анализ

========================

3. Фильтры

Перевести только еще НЕ переведенные элементы.

Например:
all fallback
→ все fallback-режимы

all RAGAS
→ все оценки

Не трогать уже русские элементы.

========================

4. Кнопки

Было:
Import selected
Import last 5
Refresh

Сделать:
Импорт выбранных
Импорт последних 5
Обновить

========================

5. Пагинация

Привести к стилю основной RAG-консоли.

Было:
Previous
Next

Сделать:
← Предыдущая
Следующая →

========================

6. Правая карточка

Было:
RAG turn

Сделать:
RAG-сессия

========================

7. Блок Session

Было:
Session

Сделать:
Сессия

Поля:
backend → Backend
latency_ms → Задержка, мс
tokens → Токены

execution_id НЕ переводить.
top_k НЕ переводить.

========================

8. Retrieval-блок

Перевести:

retrieved_count
→ Найдено чанков

fallback_reason
→ Причина fallback

unique_sources
→ Уникальных источников

========================

9. RAGAS-блок

Было:
scored yes

Сделать:
Оценка выполнена
Да

или аналогичный аккуратный production-style вариант на русском.

========================

10. Найденные чанки

Если где-то осталось:
retrieved chunks

Сделать:
Найденные чанки

========================

11. Визуальная цель

После изменений экран должен восприниматься:
- как часть единой operational-консоли Assistant Flow;
- а не как отдельный ML/debug screen.

Сохраняем:
- компактность;
- инженерный стиль;
- observability-first подход.

========================

Session logging:
создай session log:
`docs/cursor_sessions/2026-05-16_evaluation_recent_rag_turns_ui_russification.md`

В начало session log полностью помести этот prompt.

В конец добавь:
1. измененные файлы;
2. краткое описание изменений;
3. команды проверки;
4. результат build/typecheck;
5. git status.

Commit НЕ выполнять.

После завершения в ответе предоставить только:
1. список измененных файлов;
2. краткое описание изменений;
3. команды проверки;
4. git status.
```

## Измененные файлы

- `frontend/admin-ui/src/pages/EvaluationPage.tsx`
- `docs/cursor_sessions/2026-05-16_evaluation_recent_rag_turns_ui_russification.md`

## Краткое описание изменений

Точечно русифицирован и унифицирован экран списка `Recent RAG turns` в разделе Evaluation:

1. Заголовок и подзаголовок страницы:
   - `Evaluation / RAGAS` → `Анализ качества RAG`
   - подзаголовок заменен на `Операционная диагностика retrieval и качества ответов`
2. Вкладки:
   - `Recent RAG turns` → `Недавние RAG-сессии`
   - `Evaluation runs` → `Анализ`
3. Фильтры:
   - `все fallback` → `все fallback-режимы`
   - `все RAGAS` → `все оценки`
4. Кнопки:
   - `Import selected` → `Импорт выбранных`
   - `Import last 5` → `Импорт последних 5`
   - `Refresh` уже был русифицирован (`Обновить`) через shared компонент, оставлен без изменений.
5. Пагинация:
   - уже соответствовала требуемому стилю (`← Предыдущая` / `Следующая →`), без изменений.
6. Правая карточка:
   - `RAG turn` → `RAG-сессия`
7. Блок сессии:
   - `backend` → `Backend`
   - `latency_ms` → `Задержка, мс`
   - `tokens` → `Токены`
   - `execution_id` и `top_k` не переводились.
8. Retrieval-блок:
   - `retrieved_count` → `Найдено чанков`
   - `fallback_reason` → `Причина fallback`
   - `unique_sources` → `Уникальных источников`
9. RAGAS-блок:
   - `scored` + `да/not scored` → `Оценка выполнена` + `Да/Нет`
10. Дополнительно унифицированы соседние элементы этого экрана:
   - `RAGAS: yes` → `RAGAS: да`
   - `Выбрать turn` → `Выбрать сессию`
   - `selected for import` → `выбрано для импорта`
   - `Нет RAG turns` / `Нет RAG turns за выбранное окно` / `Детали turn…` → русские аналоги для единого стиля.

Логика данных, API-контракты и поведение импорта/фильтров не менялись.

## Команды проверки

```bash
cd /opt/assistant-flow/frontend/admin-ui && npm run build
cd /opt/assistant-flow && git status --short
```

## Результат build/typecheck

```bash
tsc -b && vite build
```

Результат: успешно, ошибок typecheck/build нет.

## Git status

```bash
 M frontend/admin-ui/src/pages/EvaluationPage.tsx
 M frontend/admin-ui/tsconfig.tsbuildinfo
?? docs/cursor_sessions/2026-05-15_rag_memory_leakage_diagnostic.md
?? docs/cursor_sessions/2026-05-15_ragas_negative_absence_inconsistency_diagnostic.md
?? docs/cursor_sessions/2026-05-16_evaluation_recent_rag_turns_ui_russification.md
```
