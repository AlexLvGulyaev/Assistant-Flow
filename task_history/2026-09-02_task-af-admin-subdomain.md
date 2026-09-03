# 2026-09-02 — AF: стандартный эндпойнт af-admin.alex-n8n.site

## Задание (владелец)

> «стартуем с создания для AF стандартного эндпойнта на базе субдомена. Мне ведь нужно смотреть и принимать результаты. Минуту назад появился субдомен af-admin.alex-n8n.site. Сделай все необходимые настройки, пожалуйста»

## Состояние на момент задачи

- Боевой экземпляр AF: compose-проект `assistant-flow`
  (`docker-compose.portfolio.yml` в кейсе APL), 6 сервисов.
- `assistant-flow-admin-ui-1` — статика nginx, хост-порт 8080;
  `assistant-flow-admin-api-1` — FastAPI, хост-порт 8600; сеть проекта своя
  (`assistant-flow_default`), traefik (в `n8n_default`) туда не смотрит.
- UI собирается с `VITE_ADMIN_API_BASE_URL=http://localhost:8600`,
  зашитым в бандл, — из браузера за субдоменом API недоступен.

## Результаты

**Статус: DONE** (2026-09-02). Консоль доступна на
**https://af-admin.alex-n8n.site** (UI 200, сертификат Let's Encrypt для
субдомена выпущен, `/api/health` через субдомен — все зависимости ok).

### Изменённые файлы

| Файл | Изменение |
|------|-----------|
| `/opt/n8n/dynamic.yml` | роутер `assistant-flow-admin` (`Host(af-admin…)` → сервис `assistant-flow-admin-ui` = `http://admin-ui:80`); бэкап `dynamic.yml.bak-2026-09-02-af`; после правки — `docker restart n8n-traefik-1` (файл-провайдер без watch) |
| `docker-compose.portfolio.yml` | `admin-ui`: подключён к `n8n_default` (external) + `default`; build-arg `VITE_ADMIN_API_BASE_URL: ""` |
| `frontend/admin-ui/nginx.conf` | `location /api/` → `proxy_pass http://admin-api:8600` (same-origin, `client_max_body_size 25m`, timeout 120s) |
| `frontend/admin-ui/src/api/client.ts` | `DEFAULT_BASE: "http://localhost:8600"` → `""` (относительные `/api`) |
| `frontend/admin-ui/src/auth/api.ts` | то же (auth-эндпойнты и обёртка `authAwareFetch`) |
| `docs/OPERATIONS.md` | таблица доступов: публичный субдомен + примечание о схеме проксирования и рестарте traefik |

### Схема

```
Браузер → https://af-admin.alex-n8n.site (traefik, TLS myresolver)
        → контейнер assistant-flow-admin-ui-1 (nginx :80, сети
          assistant-flow_default + n8n_default)
        → /            статика React (vite build)
        → /api/* proxy → admin-api:8600 (FastAPI, same project network)
```

### Проверка

- `UI html: 200`, сертификат `CN = af-admin.alex-n8n.site` (ACME выпущен).
- `/api/health` через субдомен: `{"status":"ok"}`, postgres ok (184 мс),
  chroma ok (collection_count 427), rag ok.
- Бандл `assets/index-CAN2d3TP.js` не содержит захардкоженного
  `localhost:8600` (grep: 0).
- Локальный доступ `localhost:8080` сохранён (200).
- Соседи после рестарта traefik: n8n (n8n-de) — 200.

### Примечания

- **Авторизация P9 в этом экземпляре выключена**: `AF_AUTH_MIDDLEWARE_MODE`
  не задан, `/api/auth/me` → `{"authenticated":false,"auth_mode":"disabled"}`.
  Консоль открывается без логина. Включение (required + INITIAL_ADMIN_*) —
  решение владельца.
- Хост-порты 8080/8600 остаются открытыми на 0.0.0.0 (до сих пор так);
  с появлением публичного субдомена стоит рассмотреть loopback-биндинг —
  отдельно, по решению владельца.
- Пересборка: `docker compose -f docker-compose.portfolio.yml build admin-ui
  && docker compose -f docker-compose.portfolio.yml up -d --no-deps admin-ui`
  (`--no-deps` — admin-api и БД не трогаются).