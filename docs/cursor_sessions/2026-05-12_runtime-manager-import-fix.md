# Session: RetrievalBackendManager import fix (Telegram startup)

**Date:** 2026-05-12  
**Symptom:** `startup degraded: rag unavailable (NameError: name 'RetrievalBackendManager' is not defined)` in assistant-flow logs.

**Cause:** `build_rag_query_service()` in `interfaces/telegram_bot.py` instantiates `RetrievalBackendManager` after P6.9/P6.10, but the module import was missing (likely dropped during an earlier refactor that removed unused imports).

**Fix:** Restore explicit import:

```python
from services.retrieval.runtime_manager import RetrievalBackendManager
```

**Other P6.10 symbols:** Grep of `interfaces/telegram_bot.py` shows no other references to `PlatformSettingsRepository` / factory helpers — only `RetrievalBackendManager` was undefined.

**Verification (local):**

```bash
python -m py_compile interfaces/telegram_bot.py services/retrieval/runtime_manager.py services/rag_query_service.py
python -c "from interfaces.telegram_bot import build_rag_query_service; …"
```

**Docker:** After `docker compose build` / recreate `portfolio-test-assistant-flow-1`, expect no startup `NameError` for RAG; `docker logs --tail=100 …` should show retrieval health lines without degraded from this bug.

**No commit** until operator confirms logs.
