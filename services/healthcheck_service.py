"""
Lightweight dependency health checks (PostgreSQL, Chroma, RAG readiness, LLM config).
No heavy LLM completion calls; short timeouts suitable for UI and startup probes.
"""

from __future__ import annotations

import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from utils.config import AppConfig

# Short defaults: avoid blocking Streamlit Overview or startup for long.
DEFAULT_PG_TIMEOUT_S = 2.0
DEFAULT_CHROMA_HTTP_TIMEOUT_S = 2.0
DEFAULT_CHROMA_LOCAL_TIMEOUT_S = 3.0


@dataclass
class HealthSnapshot:
    """One dependency check result."""

    status: str  # ok | error | degraded | configured | not_configured
    latency_ms: int | None = None
    error_message: str | None = None
    detail: str | None = None
    extras: dict[str, Any] = field(default_factory=dict)


def _now_ms(t0: float) -> int:
    return int((time.perf_counter() - t0) * 1000)


def check_postgresql(*, timeout_s: float = DEFAULT_PG_TIMEOUT_S) -> HealthSnapshot:
    """SELECT 1 via DATABASE_URL."""
    t0 = time.perf_counter()
    try:
        from repositories.connection import get_database_url

        url = get_database_url()
    except Exception as exc:
        return HealthSnapshot(
            status="error",
            latency_ms=_now_ms(t0),
            error_message=str(exc)[:500],
            detail="DATABASE_URL missing or empty",
        )

    try:
        import psycopg

        conn_timeout = max(1, int(timeout_s))
        with psycopg.connect(url, connect_timeout=conn_timeout) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                row = cur.fetchone()
        if row is None:
            return HealthSnapshot(
                status="error",
                latency_ms=_now_ms(t0),
                error_message="SELECT 1 returned no row",
            )
        return HealthSnapshot(status="ok", latency_ms=_now_ms(t0))
    except Exception as exc:
        return HealthSnapshot(
            status="error",
            latency_ms=_now_ms(t0),
            error_message=str(exc)[:500],
        )


def _chroma_http_probe(
    host: str, port: int, timeout_s: float
) -> tuple[bool, str | None, str | None]:
    """Quick HTTP heartbeat probe. Returns (ok, method_label, error)."""
    base = f"http://{host}:{port}".rstrip("/")
    for path in ("/api/v1/heartbeat", "/api/v2/heartbeat"):
        url = f"{base}{path}"
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=timeout_s) as resp:
                _ = resp.read(64)
            return True, f"http:{path}", None
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                continue
            return False, None, f"{type(exc).__name__}: {exc}"[:500]
        except Exception as exc:
            # Could be connection-refused / timeout; we still continue to client methods.
            return False, None, f"{type(exc).__name__}: {exc}"[:500]
    return False, None, "heartbeat endpoint not found"


def _chroma_collection_count_worker(config: AppConfig, persist_path: str) -> int:
    from pathlib import Path

    from services.rag_chroma_store import RAG_CHROMA_COLLECTION_NAME, chromadb_client_for_config

    p = Path(persist_path)
    client = chromadb_client_for_config(config, persist_directory=p)
    coll = client.get_collection(RAG_CHROMA_COLLECTION_NAME)
    return int(coll.count())


def _chroma_client_heartbeat_worker(config: AppConfig, persist_path: str) -> bool:
    from pathlib import Path

    from services.rag_chroma_store import chromadb_client_for_config

    p = Path(persist_path)
    client = chromadb_client_for_config(config, persist_directory=p)
    hb = getattr(client, "heartbeat", None)
    if callable(hb):
        _ = hb()
        return True
    raise AttributeError("client has no heartbeat()")


def _chroma_probe_with_timeout(
    config: AppConfig,
    *,
    persist_path: str,
    timeout_s: float,
    http_timeout_s: float,
) -> HealthSnapshot:
    """
    Chroma: optional fast heartbeat for HTTP, then get_collection().count() in a worker
    bounded by timeout (avoids hanging HttpClient).
    """
    t0 = time.perf_counter()
    target = f"{config.chroma_host}:{config.chroma_port}"
    method_used: str | None = None
    method_error: str | None = None
    extras: dict[str, Any] = {"target": target}

    if config.chroma_use_http:
        ok_http, method_label, err = _chroma_http_probe(
            config.chroma_host, config.chroma_port, http_timeout_s
        )
        if ok_http:
            method_used = method_label or "http:heartbeat"
        elif err:
            method_error = err

    import concurrent.futures

    # B. Try client.heartbeat() if available
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        fut_hb = ex.submit(_chroma_client_heartbeat_worker, config, persist_path)
        try:
            _ = fut_hb.result(timeout=timeout_s)
            if method_used is None:
                method_used = "client:heartbeat"
        except concurrent.futures.TimeoutError:
            if method_error is None:
                method_error = f"heartbeat timeout after {timeout_s}s"
        except Exception as exc:
            if method_error is None:
                method_error = str(exc)[:500]

    # C. Always try collection count; this is also the proof for RAG usage.
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        fut_count = ex.submit(_chroma_collection_count_worker, config, persist_path)
        try:
            n = fut_count.result(timeout=timeout_s)
            extras["collection_count"] = n
            if method_used is None:
                method_used = "collection:count"
            else:
                # Prefer strongest method in UI when count succeeded.
                method_used = "collection:count"
            return HealthSnapshot(
                status="ok",
                latency_ms=_now_ms(t0),
                detail=f"{target} · {method_used}",
                extras=extras,
            )
        except concurrent.futures.TimeoutError:
            if method_used is not None:
                # One method already succeeded => still OK.
                return HealthSnapshot(
                    status="ok",
                    latency_ms=_now_ms(t0),
                    detail=f"{target} · {method_used}",
                    extras=extras,
                )
            return HealthSnapshot(
                status="error",
                latency_ms=_now_ms(t0),
                detail=target,
                error_message=f"count timeout after {timeout_s}s",
                extras=extras,
            )
        except Exception as exc:
            if method_used is not None:
                return HealthSnapshot(
                    status="ok",
                    latency_ms=_now_ms(t0),
                    detail=f"{target} · {method_used}",
                    extras=extras,
                )
            return HealthSnapshot(
                status="error",
                latency_ms=_now_ms(t0),
                detail=target,
                error_message=method_error or str(exc)[:500],
                extras=extras,
            )


def _chroma_local_probe(
    config: AppConfig,
    *,
    persist_path: str,
    timeout_s: float,
) -> HealthSnapshot:
    t0 = time.perf_counter()

    def _work() -> HealthSnapshot:
        from pathlib import Path

        from services.rag_chroma_store import RAG_CHROMA_COLLECTION_NAME, chromadb_client_for_config

        p = Path(persist_path)
        client = chromadb_client_for_config(config, persist_directory=p)
        coll = client.get_collection(RAG_CHROMA_COLLECTION_NAME)
        n = int(coll.count())
        return HealthSnapshot(
            status="ok",
            latency_ms=_now_ms(t0),
            detail="PersistentClient",
            extras={"collection_count": n},
        )

    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        fut = ex.submit(_work)
        try:
            return fut.result(timeout=timeout_s)
        except concurrent.futures.TimeoutError:
            return HealthSnapshot(
                status="error",
                latency_ms=_now_ms(t0),
                error_message=f"timeout after {timeout_s}s",
                detail="PersistentClient",
            )
        except Exception as exc:
            return HealthSnapshot(
                status="error",
                latency_ms=_now_ms(t0),
                error_message=str(exc)[:500],
                detail="PersistentClient",
            )


def check_chroma(
    config: AppConfig,
    *,
    persist_path: str,
    http_timeout_s: float = DEFAULT_CHROMA_HTTP_TIMEOUT_S,
    local_timeout_s: float = DEFAULT_CHROMA_LOCAL_TIMEOUT_S,
) -> HealthSnapshot:
    """Chroma reachability + collection count; HTTP uses heartbeat + bounded client call."""
    if config.chroma_use_http:
        return _chroma_probe_with_timeout(
            config,
            persist_path=persist_path,
            timeout_s=local_timeout_s,
            http_timeout_s=http_timeout_s,
        )
    return _chroma_local_probe(
        config, persist_path=persist_path, timeout_s=local_timeout_s
    )


def check_llm_providers_config(config: AppConfig) -> dict[str, HealthSnapshot]:
    """Cheap config-only checks (no API calls)."""
    out: dict[str, HealthSnapshot] = {}

    gk = (config.gigachat_auth_key or "").strip()
    out["gigachat"] = HealthSnapshot(
        status="configured" if gk else "not_configured",
        detail="GIGACHAT_AUTH_KEY",
    )

    ok = (config.openai_api_key or "").strip()
    out["openai"] = HealthSnapshot(
        status="configured" if ok else "not_configured",
        detail="OPENAI_API_KEY",
    )

    pk = (config.proxy_api_key or "").strip()
    out["proxy"] = HealthSnapshot(
        status="configured" if pk else "not_configured",
        detail="PROXY_API_KEY",
    )
    return out


def check_rag_readiness(
    config: AppConfig,
    chroma: HealthSnapshot,
    llm: dict[str, HealthSnapshot],
) -> HealthSnapshot:
    """
    RAG = Chroma reachable + embeddings (OpenAI key) + collection usable.
    """
    if chroma.status != "ok":
        return HealthSnapshot(
            status="error",
            detail="Chroma недоступен",
            error_message=chroma.error_message,
        )
    if llm.get("openai", HealthSnapshot("not_configured")).status != "configured":
        return HealthSnapshot(
            status="degraded",
            detail="Нет OPENAI_API_KEY — embeddings недоступны",
        )
    return HealthSnapshot(
        status="ok",
        detail="RAG готов",
        extras={"collection_count": chroma.extras.get("collection_count")},
    )


@dataclass
class SystemHealthReport:
    postgres: HealthSnapshot
    chroma: HealthSnapshot
    rag: HealthSnapshot
    llm: dict[str, HealthSnapshot]


def run_system_healthchecks(
    config: AppConfig,
    *,
    chroma_persist_path: str,
    pg_timeout_s: float = DEFAULT_PG_TIMEOUT_S,
    chroma_http_timeout_s: float = DEFAULT_CHROMA_HTTP_TIMEOUT_S,
    chroma_local_timeout_s: float = DEFAULT_CHROMA_LOCAL_TIMEOUT_S,
) -> SystemHealthReport:
    """Run all checks (suitable for Overview); keep timeouts tight."""
    pg = check_postgresql(timeout_s=pg_timeout_s)
    chroma = check_chroma(
        config,
        persist_path=chroma_persist_path,
        http_timeout_s=chroma_http_timeout_s,
        local_timeout_s=chroma_local_timeout_s,
    )
    llm = check_llm_providers_config(config)
    rag = check_rag_readiness(config, chroma, llm)
    return SystemHealthReport(
        postgres=pg,
        chroma=chroma,
        rag=rag,
        llm=llm,
    )


def format_health_badge_status(raw: str) -> str:
    """RU label for ops Overview (plain text, escaped by caller if needed)."""
    m = {
        "ok": "OK",
        "error": "ERR",
        "degraded": "DEG",
        "configured": "CFG",
        "not_configured": "—",
    }
    return m.get(raw.lower(), raw.upper() if raw else "—")
