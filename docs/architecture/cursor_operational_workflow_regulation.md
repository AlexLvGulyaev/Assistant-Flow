# 🏗️ Cursor Operational Workflow Regulation
## Assistant Flow Engineering Process

Status: active  
Scope: Assistant Flow / operational AI engineering  
Audience: single-operator engineering workflow with AI-assisted development

---

# 1. Purpose

Настоящий регламент определяет правила работы с Cursor в проекте Assistant Flow с целью:

- снижения token burn;
- стабилизации AI-assisted workflow;
- предотвращения giant-context degradation;
- сохранения архитектурной памяти проекта;
- повышения воспроизводимости engineering-процессов;
- разделения architectural reasoning и execution work.

---

# 2. Core Principles

## 2.1 Architecture-first workflow

Cursor не рассматривается как долговременный conversational partner.

Cursor используется как:

```text
bounded execution agent
```

Архитектурное reasoning, subsystem planning и cross-cutting engineering decisions фиксируются вне conversational context.

---

## 2.2 Conversational memory is disposable

Conversational context считается:

- дорогим;
- нестабильным;
- невоспроизводимым;
- подверженным degradation при длинных чатах.

Потеря conversational memory допустима.

Критично сохранять:

- architectural memory;
- operational decisions;
- findings;
- engineering rationale.

---

## 2.3 Project memory must exist outside chats

Долговременная память проекта должна храниться в репозитории:

- `PROJECT_STATE.md`
- `docs/cursor_sessions/*`
- architecture/design docs
- ADR-like engineering logs
- operational contracts

Чат не является source of truth.

---

# 3. Memory Model

## 3.1 PROJECT_STATE.md

Главный operational memory artifact проекта.

Содержит:

- текущую архитектуру;
- infrastructure;
- active services;
- operational rules;
- roadmap;
- known issues;
- decisions log;
- UI contracts;
- retrieval/evaluation backlog.

Назначение:

```text
canonical project state
```

---

## 3.2 docs/cursor_sessions/*

Назначение:

```text
engineering knowledge ledger
```

Session logs являются append-only инженерной памятью проекта.

Содержат:

- полный engineering prompt;
- findings;
- architectural decisions;
- implementation rationale;
- incidents;
- root-cause analysis;
- operational implications;
- operator commands;
- verification steps.

Примеры:

- retrieval observability audit;
- RAGAS integration decisions;
- UI standardization contracts;
- Chroma persistence incidents.

Session logs считаются долговременной памятью.

---

## 3.3 docs/cursor_tasks/*

Назначение:

```text
execution envelopes
```

Task-файлы содержат только:

- текущую задачу;
- scope;
- constraints;
- acceptance criteria;
- execution boundaries.

Task-файлы не являются knowledge-base.

После завершения задачи task:

- удаляется;
- архивируется;
- либо преобразуется в session log.

---

# 4. Chat Lifecycle Rules

## 4.1 One chat = one subsystem/sprint

Запрещается использовать:

- бесконечные mega-chats;
- giant cross-subsystem conversations;
- mixed architecture/UI/debugging/retrieval chats.

Правильная модель:

```text
1 chat = 1 subsystem
или
1 chat = 1 sprint
```

Примеры:

- Evaluation UI stabilization
- Retrieval threshold debugging
- Memory console alignment
- RAGAS ground-truth workflow

---

## 4.2 New chat bootstrap

Новый Cursor-chat должен начинаться с короткого bootstrap prompt.

Bootstrap prompt должен:

- задавать subsystem context;
- ссылаться на PROJECT_STATE;
- ссылаться на relevant session logs;
- задавать execution boundaries;
- запрещать unrelated audits/refactors.

Bootstrap prompt не должен:

- пересказывать историю проекта;
- содержать giant reasoning;
- содержать conversational replay.

---

## 4.3 Task execution flow

Правильный workflow:

```text
1. Создать task-файл
2. Открыть новый Cursor-chat
3. Дать bootstrap prompt
4. Передать task-file
5. Выполнить bounded execution
6. Создать/обновить session log
7. Завершить chat
```

---

# 5. Token Economy Rules

## 5.1 Main token burn sources

Основные источники token burn:

- giant chat history;
- whole-project Composer usage;
- mixed-context reasoning;
- giant logs pasted into chat;
- repeated architectural replay;
- broad repository audits;
- uncontrolled Auto orchestration;
- execution inside degraded mega-context.

---

## 5.2 Preferred execution model

Рекомендуемая модель:

- короткие task-scoped chats;
- narrow prompts;
- externalized context via files;
- explicit subsystem boundaries;
- session logs вместо conversational replay.

---

## 5.3 File-based prompting

Предпочтительный workflow:

```text
Read:
docs/cursor_tasks/YYYY-MM-DD_task-name.md

Execute only this task.
Do not expand scope.
```

Вместо:

- giant inline prompts;
- multi-thousand-token conversational instructions.

---

# 6. Model Usage Policy

## 6.1 Preferred models

| Task Type | Preferred Model |
|---|---|
| Architecture / diagnostics / backend reasoning | GPT-5.5 |
| React / TS / UI refinement | Sonnet 4.6 (if routing stable) |
| Small safe edits | Codex 5.3 |
| Runtime/provider recovery | Auto |

---

## 6.2 Auto mode policy

Auto не используется как основной постоянный режим.

Auto допускается:

- для runtime recovery;
- provider failover;
- temporary degraded routing situations.

Причина:

- непредсказуемый provider/model selection;
- повышенный token burn risk;
- orchestration overhead.

---

## 6.3 Whole-project audit restrictions

Запрещается без необходимости:

- giant Composer runs;
- whole-repository audits;
- broad refactors;
- architecture rewrites inside execution chats.

---

# 7. Engineering Logging Rules

## 7.1 Every substantial task requires session log

Каждый значимый engineering pass должен сопровождаться:

```text
docs/cursor_sessions/YYYY-MM-DD_task-name.md
```

---

## 7.2 Session log structure

Минимально:

- prompt;
- scope;
- changed files;
- findings;
- architectural implications;
- operational implications;
- operator commands;
- verification steps.

---

## 7.3 Operator commands mandatory

Каждый session log должен содержать:

```text
## Operator commands / next verification commands
```

С командами:

- rebuild;
- smoke tests;
- curl/API checks;
- frontend build;
- docker exec verification;
- git status.

---

# 8. Separation of Responsibilities

## 8.1 ChatGPT responsibilities

ChatGPT используется для:

- architectural reasoning;
- system analysis;
- engineering planning;
- prompt engineering;
- operational workflow design;
- retrieval/evaluation analysis;
- root-cause reasoning.

---

## 8.2 Cursor responsibilities

Cursor используется для:

- bounded implementation;
- targeted code changes;
- local subsystem execution;
- constrained refactoring;
- operational patching;
- UI refinement;
- engineering log generation.

---

# 9. Expected Outcome

Ожидаемый результат workflow:

- снижение token burn;
- стабильные short-lived chats;
- воспроизводимый engineering process;
- сохранение architectural memory;
- снижение giant-context degradation;
- controllable operational AI development workflow.
