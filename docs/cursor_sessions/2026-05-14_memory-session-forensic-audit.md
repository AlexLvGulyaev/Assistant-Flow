# Forensic audit: Memory UI sessions `tg:-100…` / smoke payloads (2026-05-14)

**Observed in UI (reported ~2026-05-11):** many sessions labeled `tg:-1000000…` (large negative integers), message bodies such as `hello smoke` / `world smoke` and `LIM-U0`…`LIM-A4`, bursts of distinct TG ids within the same second.

## Root cause

These rows are **not** traffic from real Telegram end-users via webhook. They are **automated smoke-test fixtures** written to the **same PostgreSQL** that backs Memory / Admin UI when operators (or CI) run repository scripts with `DATABASE_URL` pointing at that database.

Specifically:

1. **`scripts/test_conversation_memory_smoke.py`**  
   - Generates **six** synthetic `telegram_user_id` values per run:  
     `tid = -(10**15 + rng.randrange(10**9))` → order of magnitude **≈ −10¹⁵** (UI shows `tg:` + id, hence `tg:-1000000…`-style strings).  
   - Writes **`hello smoke` / `world smoke`** (main scenario), **`LIM-U{i}` / `LIM-A{i}`** (limit test), **`ORD-U*` / `ORD-A*`** (ordering), **`abcdefgh`**, **`X*`** / `second` (budget/trim), plus empty-session checks.  
   - Uses `AppUserService.ensure_user_for_telegram(...)`, `ChatSessionService`, `ConversationMemoryService.append_*` — same tables as production memory.

2. **`scripts/test_memory_v1_pg_short_term_smoke.py`**  
   - Uses a **random positive** `telegram_user_id` in range `9_000_000_000_000` … `9_999_999_999_999` and messages **`hello smoke user` / `hello smoke assistant`** (not identical to the pair above but same naming family).

3. **`scripts/test_hybrid_retrieval_smoke.py`**  
   - Also uses **`-(10**15 + rng.randrange(10**9))`** for synthetic Telegram users when the hybrid smoke runs against Postgres.

**Container startup:** `docker-compose.portfolio.yml` runs `python run_telegram_bot.py` / `run_admin_api.py` — **no** automatic execution of these smoke scripts on `up`. Data appears when someone runs e.g.  
`docker exec portfolio-test-assistant-flow-1 python scripts/test_conversation_memory_smoke.py`  
(or host `python3 …` with the same `DATABASE_URL`).

## Could this be production / external Telegram?

| Question | Answer |
|----------|--------|
| Real human Telegram `from_user.id`? | **Unlikely** for these rows: the **large negative** ids are **explicitly chosen** in smoke code to reduce collision with real accounts (real user ids are typically **positive** 32-bit-ish integers; negative ids are used elsewhere in Telegram API for **chats**, but this code path stores them as **synthetic test user ids**). |
| From Telegram webhook? | **No** for the quoted strings: they are **hard-coded** in `test_conversation_memory_smoke.py` / `test_memory_v1_pg_short_term_smoke.py`. Webhook traffic would mirror real dialog text, not `LIM-U3` patterns. |
| Same DB as “production contour”? | **If** `DATABASE_URL` in that environment points at the **same** Postgres as the operator UI, smoke rows **will** show in Memory Sessions — that is expected coupling, not a separate “test namespace” DB today. |

## Recommended cleanup (manual only — not executed here)

**Prerequisite:** take a backup or run in a transaction you can roll back; verify row counts with `SELECT` first.

Synthetic users from `test_conversation_memory_smoke.py` / `test_hybrid_retrieval_smoke.py` (negative ids in the **−(10¹⁵ + …)** family):

```sql
-- PREVIEW
SELECT id, telegram_user_id, created_at
FROM app_users
WHERE telegram_user_id < -900000000000000;

-- DELETE (CASCADE removes chat_sessions / chat_messages tied to these users per schema)
-- Adjust threshold if you also store legitimate negative ids (unlikely for app_users.telegram_user_id).
BEGIN;
DELETE FROM app_users
WHERE telegram_user_id < -900000000000000;
COMMIT;
```

Smoke from **`test_memory_v1_pg_short_term_smoke.py`** (positive ids **9e12–9.99e12** — may overlap other tooling; preview first):

```sql
SELECT id, telegram_user_id FROM app_users
WHERE telegram_user_id BETWEEN 9000000000000 AND 9999999999999;

-- DELETE only if you confirm these rows are test-only:
-- DELETE FROM app_users WHERE telegram_user_id BETWEEN 9000000000000 AND 9999999999999;
```

Optional narrow delete by **known smoke literals** (still verify counts):

```sql
SELECT m.id, m.content, u.telegram_user_id
FROM chat_messages m
JOIN app_users u ON u.id = m.user_id
WHERE m.content IN ('hello smoke', 'world smoke')
   OR m.content LIKE 'LIM-%'
   OR m.content LIKE 'ORD-%';
-- Then delete parents (sessions/users) or messages only per your policy.
```

## Future protection (recommendations)

1. **Separate DB or schema** for automated smoke (`DATABASE_URL_SMOKE` vs prod).  
2. **Reserved ID ranges / prefix:** e.g. only use `telegram_user_id` in `[-2e15, -2e15+1e6)` for tests and document it; or add `app_users.is_synthetic BOOLEAN` / `source='smoke'` (requires migration + writer changes).  
3. **Memory UI filter:** hide `telegram_user_id < 0` (or `< -threshold`) behind an “include synthetic” toggle — quick UX mitigation without deleting data.  
4. **Seed markers:** write `metadata` on first message e.g. `{"smoke_suite": "conversation_memory_smoke"}` and filter in list API (already partially used: `p6_smoke` on one path — not on all test users).  
5. **CI guard:** fail pipeline if smoke targets prod URL pattern.  
6. **Auto-cleanup:** optional scheduled job deleting users older than N days with `telegram_user_id` in reserved range — policy decision only.

## Operator commands / next verification commands

Canonical contour:

```bash
COMPOSE_BAKE=false docker compose -p portfolio-test -f docker-compose.portfolio.yml up -d --build
```

**Confirm origin (read-only in DB):**

```bash
docker exec portfolio-test-assistant-flow-1 python -c "
import os
from repositories.connection import get_connection
assert os.getenv('DATABASE_URL')
with get_connection() as conn:
    with conn.cursor() as cur:
        cur.execute('''
          SELECT telegram_user_id, COUNT(*)::int
          FROM app_users
          WHERE telegram_user_id < -900000000000000
          GROUP BY telegram_user_id
          ORDER BY COUNT(*) DESC
          LIMIT 20
        ''')
        print('negative_synthetic_users:', cur.fetchall())
        cur.execute('''
          SELECT content, COUNT(*)::int FROM chat_messages
          WHERE content IN ('hello smoke','world smoke') OR content LIKE 'LIM-%%' OR content LIKE 'ORD-%%'
          GROUP BY content ORDER BY COUNT(*) DESC LIMIT 30
        ''')
        print('smoke_like_messages:', cur.fetchall())
"
```

**Re-run smoke only when intended (pollutes UI DB):**

```bash
docker exec portfolio-test-assistant-flow-1 python scripts/test_conversation_memory_smoke.py
docker exec portfolio-test-assistant-flow-1 python scripts/test_memory_v1_pg_short_term_smoke.py
```

Do **not** run these against a shared prod Postgres unless that pollution is acceptable.
