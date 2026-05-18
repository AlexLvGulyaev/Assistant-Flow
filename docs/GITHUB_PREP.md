# Подготовка к публикации GitHub v2.0

Чеклист перед открытым репозиторием. Документ **не выполняет** очистку автоматически и не заменяет решение владельца репозитория.

Связанные документы: [README.md](../README.md), [RUNBOOK.md](../RUNBOOK.md), [USER_GUIDE.md](../USER_GUIDE.md), [SECURITY_NOTES.md](SECURITY_NOTES.md).

---

## 1. Публичная документация

| Пункт | Проверка |
|-------|----------|
| [README.md](../README.md) | Актуален под v2: мультимодальность, ASCII-архитектура, portfolio-compose, ссылки на RUNBOOK/USER_GUIDE |
| [RUNBOOK.md](../RUNBOOK.md) | Эксплуатация portfolio; server-контур вынесен в advanced |
| [USER_GUIDE.md](../USER_GUIDE.md) | Пользовательские сценарии (draft допустим) |
| [docs/ARCHITECTURE.md](ARCHITECTURE.md) | FastAPI + React Admin UI, без Streamlit как текущего UI |
| [docs/OPERATIONS.md](OPERATIONS.md) | Каноническая команда `-p portfolio-test`, порты, Chroma/кэш |
| [docs/screenshots/](screenshots/) | Скриншоты для README (15 файлов, пути `docs/screenshots/*.png`) |
| Внутренние логи | `docs/cursor_sessions/` **не** в публичной навигации README |

---

## 2. Конфигурация и compose

| Пункт | Проверка |
|-------|----------|
| [.env.example](../.env.example) | Только плейсхолдеры, без реальных ключей |
| [docker-compose.portfolio.yml](../docker-compose.portfolio.yml) | Канонический demo-стек: postgres, chroma, weaviate, bot, admin-api, admin-ui |
| Секреты | `.env`, `.env.server` в `.gitignore`, не в индексе |
| Server-compose | Упоминается только в RUNBOOK/OPERATIONS как advanced, не в README как основной путь |

---

## 3. Код и артефакты

| Пункт | Проверка |
|-------|----------|
| `git status` | Нет неожиданных секретов, дампов, личных токенов |
| `frontend/admin-ui/node_modules/` | Не в git (`.gitignore`) |
| `frontend/admin-ui/dist/` | Не в git |
| `_test_chroma/`, локальные SQLite | Не коммитить runtime cache/shm/wal без необходимости |
| `storage/assets/` | Нет чувствительных данных среды разработки |
| `cursor_tasks_local/` | Не в публичной навигации (может оставаться в репо для команды) |

---

## 4. Сканирование секретов

- [gitleaks](https://github.com/gitleaks/gitleaks), `git secrets` или аналог по всему репо.
- Ручная выборка: `sk-`, длинные токены, `postgresql://` с паролями в истории коммитов.

---

## 5. Smoke после клона

```bash
cp .env.example .env
COMPOSE_BAKE=false docker compose -p portfolio-test -f docker-compose.portfolio.yml up -d --build --remove-orphans
curl -sS http://localhost:8600/api/health
```

Далее по [RAG_SMOKE_TEST.md](RAG_SMOKE_TEST.md) и [DEMO_SCENARIOS.md](DEMO_SCENARIOS.md).

---

## 6. Очистка индекса git (по решению владельца)

Если тяжёлые пути уже в истории:

```bash
git rm -r --cached frontend/admin-ui/node_modules
git rm -r --cached frontend/admin-ui/dist
git rm -r --cached _test_chroma
```

Полная очистка истории (`git filter-repo`, BFG) — только после backup и согласования; **force-push** деструктивен.

---

## 7. [PROJECT_STATE.md](../PROJECT_STATE.md)

Инженерный backlog для команды; не обязателен внешнему reviewer, но должен не противоречить README по статусу подсистем.
