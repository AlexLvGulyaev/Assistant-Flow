# Операционная дисциплина
## Регламент взаимодействия Промпт-инженера, Оператора и Cursor в Assistant Flow

Статус: active  
Область применения: Assistant Flow / AI-assisted engineering workflow  
Участники процесса:
- Промпт-инженер (Оптимус / ChatGPT)
- Оператор (Александр)
- Исполнительный агент (Cursor)

---

# 1. Назначение документа

Настоящий регламент определяет порядок взаимодействия между:
- Промпт-инженером;
- Оператором;
- Cursor;

в рамках одного рабочего цикла (спринта) разработки Assistant Flow.

Цель регламента:
- снизить token burn;
- уменьшить giant-context degradation;
- сохранить архитектурную память проекта;
- отделить архитектурное мышление от исполнительной реализации;
- сделать AI-assisted workflow воспроизводимым и управляемым;
- предотвратить хаотичные рефакторинги и scope creep.

Документ является верхнеуровневым operational-регламентом и описывает:
- роли участников;
- жизненный цикл задачи;
- порядок передачи контекста;
- правила фиксации результатов;
- границы ответственности.

---

# 2. Роли участников

## 2.1 Промпт-инженер (Оптимус / ChatGPT)

Промпт-инженер отвечает за:
- архитектурное reasoning;
- анализ системы;
- проектирование решений;
- decomposition задач;
- prompt engineering;
- выявление рисков;
- root-cause analysis;
- operational planning;
- формирование execution boundaries;
- контроль инженерной дисциплины.

Принцип:

```text
Оптимус думает.
Cursor исполняет.
```

Принципиально:
- ChatGPT не используется как source of truth проекта;
- архитектурная память должна фиксироваться вне чатов.

---

## 2.2 Оператор (Александр)

Оператор отвечает за:
- принятие инженерных решений;
- определение приоритетов;
- управление scope задач;
- запуск Cursor;
- выполнение rebuild/redeploy;
- smoke tests;
- ручную проверку результатов;
- принятие или отклонение изменений;
- фиксацию milestone-состояний.

Оператор является:

```text
human-in-the-loop controller
```

Именно оператор:
- подтверждает изменения;
- принимает архитектурные решения;
- контролирует production safety.

---

## 2.3 Cursor

Cursor рассматривается как:

```text
bounded execution agent
```

Cursor отвечает за:
- локальные изменения кода;
- ограниченные рефакторинги;
- UI/UX-полировку;
- targeted implementation;
- генерацию session logs;
- выполнение task-scoped engineering work.

Cursor не должен:
- самостоятельно расширять scope задачи;
- перепроектировать архитектуру без явного запроса;
- выполнять giant audits;
- делать broad refactors;
- принимать архитектурные решения.

---

# 3. Основной принцип workflow

## 3.1 Один спринт = одна subsystem-задача

Правильная модель:

```text
1 sprint = 1 subsystem
или
1 sprint = 1 bounded engineering task
```

Примеры:
- стабилизация Evaluation UI;
- диагностика retrieval;
- доработка RAG-консоли;
- интеграция RAGAS;
- улучшение observability;
- исследование retrieval noise.

Запрещается:
- смешивать несколько subsystem в одном execution-cycle;
- вести giant mega-chats;
- совмещать архитектуру, UI, retrieval, backend и deployment в одном task-pass.

---

# 4. Жизненный цикл рабочего цикла (спринта)

## Этап 1. Архитектурный анализ

Исполняет:
- Промпт-инженер;
- Оператор.

На этапе:
- анализируется проблема;
- формируется hypothesis;
- определяется subsystem scope;
- выделяются constraints;
- оцениваются риски;
- определяется acceptance criteria.

Результат:
- инженерное решение;
- task scope;
- понимание boundaries.

Cursor на этом этапе не используется.

---

## Этап 2. Подготовка task-файла

Исполняет:
- Промпт-инженер.

Создаётся:

```text
cursor_tasks_local/<task-name>.md
```

Task-файл содержит:
- цель задачи;
- контекст;
- scope;
- constraints;
- acceptance criteria;
- operational rules;
- session logging requirements;
- expected output.

Task-файл НЕ является knowledge-base.

Это:

```text
execution envelope
```

---

## Этап 3. Запуск Cursor

Исполняет:
- Оператор.

Workflow:

```text
1. Открыть новый Cursor-chat
2. Дать bootstrap-команду
3. Передать task-file
4. Ограничить scope
```

Bootstrap prompt должен:
- ссылаться на PROJECT_STATE;
- ссылаться на relevant session logs;
- задавать subsystem boundaries;
- запрещать unrelated refactors.

Bootstrap prompt НЕ должен:
- пересказывать историю проекта;
- содержать giant reasoning;
- воспроизводить длинные conversational logs.

---

## Этап 4. Bounded execution

Исполняет:
- Cursor.

Cursor выполняет:
- локальные изменения;
- ограниченные исправления;
- targeted implementation;
- UI refinement;
- diagnostics.

Во время execution-pass Cursor обязан:
- соблюдать scope;
- не расширять задачу самостоятельно;
- фиксировать findings;
- создавать session log;
- указывать verification commands.

---

## Этап 5. Проверка результата

Исполняет:
- Оператор.

Оператор выполняет:
- rebuild;
- redeploy;
- smoke tests;
- визуальную проверку UI;
- проверку retrieval behavior;
- operational verification.

Только после этого:
- изменения считаются принятыми;
- возможен git commit.

---

## Этап 6. Фиксация архитектурной памяти

Исполняет:
- Промпт-инженер;
- Оператор.

После завершения significant engineering pass:
- обновляется PROJECT_STATE.md;
- сохраняется session log;
- фиксируются findings;
- фиксируются operational implications.

Принцип:

```text
Чат не является долговременной памятью проекта.
```

---

# 5. Модель памяти проекта

## 5.1 PROJECT_STATE.md

Главный operational memory artifact проекта.

Содержит:
- текущую архитектуру;
- infrastructure;
- active services;
- operational rules;
- roadmap;
- known issues;
- UI contracts;
- retrieval/evaluation findings;
- decisions log.

PROJECT_STATE.md является:

```text
canonical project state
```

---

## 5.2 docs/cursor_sessions/*

Назначение:

```text
engineering knowledge ledger
```

Session logs содержат:
- полный engineering prompt;
- findings;
- root-cause analysis;
- architectural implications;
- operational implications;
- operator commands;
- verification steps;
- git status.

Session logs считаются долговременной инженерной памятью проекта.

---

## 5.3 cursor_tasks_local/*

Task-файлы используются как:

```text
execution envelopes
```

Они содержат:
- только текущую задачу;
- scope;
- constraints;
- acceptance criteria.

После завершения задачи:
- task архивируется;
- либо удаляется;
- либо превращается в session log.

---

# 6. Правила token economy

## 6.1 Основные источники token burn

Главные причины деградации workflow:
- giant chat history;
- repeated architectural replay;
- broad repository audits;
- whole-project Composer runs;
- mixed-context conversations;
- uncontrolled Auto orchestration;
- execution inside degraded mega-context.

---

## 6.2 Предпочтительная модель

Рекомендуемый workflow:
- короткие task-scoped chats;
- узкие prompts;
- file-based context;
- explicit subsystem boundaries;
- session logs вместо conversational replay.

---

## 6.3 Разделение reasoning и execution

Архитектурное мышление:
- ChatGPT.

Исполнение:
- Cursor.

Контроль и verification:
- Оператор.

Это предотвращает:
- хаотичное перепроектирование;
- scope explosion;
- giant-context degradation;
- потерю architectural memory.

---

# 7. Правила инженерной дисциплины

## 7.1 Каждый значимый pass требует session log

Формат:

```text
docs/cursor_sessions/YYYY-MM-DD_task-name.md
```

Минимально должны присутствовать:
- prompt;
- scope;
- findings;
- changed files;
- architectural implications;
- operational implications;
- verification commands;
- git status.

---

## 7.2 Operator commands обязательны

Каждый session log обязан содержать:

```text
## Operator commands
```

С командами:
- rebuild;
- redeploy;
- smoke tests;
- curl/API checks;
- frontend build;
- docker verification;
- git status.

---

## 7.3 Scope discipline

Cursor запрещается:
- выполнять unrelated refactors;
- менять архитектуру вне scope;
- делать broad audits без запроса;
- переписывать subsystem целиком.

Любое расширение scope:
- сначала обсуждается;
- затем фиксируется новым task-pass.

---

# 8. Ожидаемый результат workflow

Ожидаемый operational-результат:
- снижение token burn;
- стабильные short-lived chats;
- воспроизводимый engineering process;
- сохранение architectural memory;
- контролируемый AI-assisted workflow;
- уменьшение giant-context degradation;
- стабильное развитие Assistant Flow как operational AI-platform prototype.

---

# 9. Краткая схема взаимодействия

```text
Оптимус:
анализ → архитектура → prompt engineering → scope

↓

Александр:
контроль → запуск → проверка → принятие решения

↓

Cursor:
bounded execution → session log → implementation

↓

PROJECT_STATE + session logs:
долговременная память проекта
```

---

# 10. Главный operational-принцип

```text
Архитектура и инженерная память живут в документах.
Чаты являются временным execution-интерфейсом.
```

