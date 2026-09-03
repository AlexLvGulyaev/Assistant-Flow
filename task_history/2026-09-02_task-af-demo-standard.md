# 2026-09-02 — AF: демо-стандарт APL (токен + демо-вход) + ссылки на админку в витрине

## Задание (владелец)

> «Предлагаю сразу применить демо-стандарт к AF, и включить ссылки на админку на страницы лендинга»
> «Демо-стандарт APL должен быть применен к AF. Референсов полно, точнее, все кейсы с админкой.»

## План

1. Бэкенд: `AF_ADMIN_TOKEN` / `AF_ADMIN_DEMO_TOKEN` (env + compose), роль `demo`
   (read-only) в `rbac.py`, распознавание static ops-токенов в `auth_middleware.py`.
2. `GET /api/auth/whoami` (канон 401/403), аудит `console_login` с ролью,
   enforcement required при заданных токенах.
3. UI: `LoginPage.tsx` → канон RF/AIC/LQ (токен + демо-вход + «К проекту»),
   демо-токен запекается `VITE_OPS_DEMO_TOKEN`, чип 🎭 для роли demo.
4. Витрина `assistant-flow.html`: кнопка «Admin Console» (rel="opener", без JS).
5. Деплой + проверки + регистры.

## Результаты

**Решение владельца:** вариант 1 — UI только токен-вход (канон), P9
email/password остаётся в API без UI.

### Изменённые файлы (бэкенд)

| Файл | Изменение |
|------|-----------|
| `services/security/ops_token.py` | NEW: `AF_ADMIN_TOKEN`/`AF_ADMIN_DEMO_TOKEN`, `resolve_ops_role` (compare_digest) |
| `services/security/rbac.py` | роль `PLATFORM_DEMO="demo"`: read-only perms (documents/logs/retrieval/settings read + audit:read); retrieval_role demo → guest |
| `services/security/principal.py` | `AUTH_SOURCE_OPS_TOKEN`, фабрика `PrincipalContext.from_ops_token(role)` |
| `services/security/auth_middleware.py` | Bearer → сперва ops-токен, затем session token |
| `services/security/auth_policy.py` | `/api/auth/whoami` в PUBLIC_PATHS; `get_auth_mode`: режим не задан + токены настроены → `required` (канон LQ), иначе `disabled` |
| `admin_api/routes/auth.py` | `GET /api/auth/whoami` (канон 401 «Ops token required» / 403 «Invalid ops token»), аудит `console_login` (event `auth.console.login`); hint /me переписан на Bearer |

### Изменённые файлы (фронтенд)

| Файл | Изменение |
|------|-----------|
| `auth/api.ts` | `signInWithToken` (whoami, канон ошибок: пусто → «Введите токен.», 401 → «Токен не принят…», 403 → «Недействительный токен.»), `signInDemo` (VITE_OPS_DEMO_TOKEN), `isDemoConfigured` |
| `auth/types.ts` | `WhoamiResponse`, убран `LoginResponse` |
| `auth/AuthContext.tsx` | `login(token)` / `loginDemo()`, поля `isDemo`/`displayName`/`demoAvailable` |
| `pages/LoginPage.tsx` | канон-форма: иконка 🤖, h1 «Assistant Flow Admin Console», «Введите Bearer token…», label «Bearer token», password «Вставьте токен...», ошибки канона, «Войти» + «Войти в демо-режим (только просмотр)» + «К проекту» (витрина AIP, rel="opener") |
| `layout/Sidebar.tsx` | сессия ops-токена: display_name; demo → «🎭 …» |
| `utils/securityScenarios.ts` | маппинг `auth.console.login` |
| `styles/globals.css` | `.login-card__icon`, `.login-form__btn(--outline/--home)` — канон LQ/RF |
| `vite-env.d.ts` | `VITE_OPS_DEMO_TOKEN` |

### Инфраструктура и витрина

| Файл | Изменение |
|------|-----------|
| `.env.example` | блок ops-токенов (плейсхолдеры) |
| `.env` (живой) | сгенерированы `AF_ADMIN_TOKEN` + `AF_ADMIN_DEMO_TOKEN` (значения не печатаются) |
| `docker-compose.portfolio.yml` | admin-ui build-arg `VITE_OPS_DEMO_TOKEN: ${AF_ADMIN_DEMO_TOKEN:-}`; сети admin-ui в map-форме с **уникальным alias `assistant-flow-admin-ui`** на `n8n_default` |
| `frontend/admin-ui/Dockerfile` | `ARG VITE_OPS_DEMO_TOKEN` + `ENV` (без объявления ARG build-arg молча игнорировался — токен не запекался) |
| `/opt/n8n/dynamic.yml` | сервис `assistant-flow-admin-ui` → `http://assistant-flow-admin-ui:80` (было `admin-ui:80`) |
| `cases/ai-portfolio/src/cases/assistant-flow.html` | hero + final CTA: кнопка «Admin Console» → `https://af-admin.alex-n8n.site/` (target=_blank, data-console="1", rel="opener", без JS); в живой контейнер ai-portfolio страница скопирована `docker cp` (источник в репо — попадёт в образ при следующем rebuild) |

**Инфра-инцидент (найден и устранён):** после пересоздания admin-ui субдомен
af-admin стал попеременно отдавать то AF-, то LQ-консоль. Причина: LQ-проект
тоже называет свой сервис `admin-ui` и его контейнер сидит в той же
`n8n_default`; Docker DNS отдавал оба IP round-robin. Решение: уникальный
network-alias `assistant-flow-admin-ui` у AF admin-ui + правка сервиса в
`/opt/n8n/dynamic.yml` + `docker restart n8n-traefik-1` (файл-провайдер без
watch). LQ/витрина/n8n после рестарта — 200. Паттерн записан в
`shared/patterns/shared-network-service-name-collision.md`.

### Документация

- `RUNBOOK.md` §B.2 — токены консоли (что задать, пересборка при смене демо-токена).
- `docs/OPERATIONS.md` — раздел «Авторизация (демо-стандарт APL)».

### Проверки (целевой e2e /tmp/af-demo-check.js — **19/19 PASS**)

- Форма входа: канон (заголовок, подзаголовок, иконка, label «Bearer token»
  с title-хэлпом, placeholder «Вставьте токен...», «Войти», демо-кнопка,
  «К проекту» → витрина, rel="opener").
- Ошибки канона: пусто → «Введите токен.»; неверный токен → 403
  «Недействительный токен.»; без токена whoami → 401.
- Демо-вход: сессия открывается, сайдбар «🎭 … / demo»; мутация
  `PUT /api/retrieval/active-backend` → **403** (read-only подтверждён).
- Админ-вход: роль admin без 🎭; `/api/auth/me` → authenticated, required.
- Аудит: события `auth.console.login` пишутся, читаются через
  `/api/security/audit/recent` (роль admin).
- 0 JS-ошибок на всех шагах.

**Статус: DONE** (2026-09-02). Визуальная приёмка — за владельцем
(https://af-admin.alex-n8n.site, демо-вход — кнопка на форме).