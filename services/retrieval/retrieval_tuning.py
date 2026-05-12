"""
DB-backed retrieval tuning (P6.12): ``platform_settings.retrieval_tuning`` JSON overrides env defaults.

Env / ``AppConfig`` remains bootstrap; PostgreSQL stores partial overrides only (keys omitted = use env).
"""

from __future__ import annotations

import math
from typing import Any

from dataclasses import replace

from repositories.platform_settings_repository import (
    KEY_RETRIEVAL_TUNING,
    PlatformSettingsRepository,
)
from utils.config import AppConfig

TUNING_RUNTIME_KEYS: frozenset[str] = frozenset(
    {
        "rag_top_k",
        "rag_max_distance",
        "rag_answer_max_tokens",
        "rag_retrieval_timeout",
        "rag_embedding_request_timeout",
    }
)
TUNING_INDEXING_KEYS: frozenset[str] = frozenset(
    {
        "rag_chunk_size",
        "rag_chunk_overlap",
    }
)
TUNING_ALL_KEYS: frozenset[str] = TUNING_RUNTIME_KEYS | TUNING_INDEXING_KEYS
TUNING_REQUIRES_REINDEX_KEYS: frozenset[str] = frozenset(TUNING_INDEXING_KEYS)


def tuning_effective_values(cfg: AppConfig) -> dict[str, Any]:
    """Flat public dict of all tuning fields (numbers JSON-serializable)."""
    return {k: getattr(cfg, k) for k in sorted(TUNING_ALL_KEYS)}


def load_retrieval_tuning_db(conn: Any) -> dict[str, Any]:
    raw = PlatformSettingsRepository().get_setting(conn, KEY_RETRIEVAL_TUNING)
    if not raw:
        return {}
    return sanitize_db_dict(raw)


def sanitize_db_dict(raw: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in raw.items():
        if k in TUNING_ALL_KEYS and v is not None:
            out[k] = v
    return out


def _float_eq(a: float, b: float) -> bool:
    return math.isclose(a, b, rel_tol=0.0, abs_tol=1e-9)


def value_matches_env(key: str, value: Any, base: AppConfig) -> bool:
    """True if ``value`` equals the env/bootstrap field on ``base`` (for dropping redundant DB keys)."""
    env_v = getattr(base, key)
    if isinstance(env_v, bool):
        return bool(value) is env_v
    if isinstance(env_v, int) and not isinstance(env_v, bool):
        try:
            return int(value) == int(env_v)
        except (TypeError, ValueError):
            return False
    if isinstance(env_v, float):
        try:
            return _float_eq(float(value), float(env_v))
        except (TypeError, ValueError):
            return False
    try:
        return float(value) == float(env_v)
    except (TypeError, ValueError):
        return str(value) == str(env_v)


def apply_db_overrides_to_config(base: AppConfig, db: dict[str, Any]) -> AppConfig:
    if not db:
        return base
    kwargs: dict[str, Any] = {}
    if "rag_top_k" in db:
        kwargs["rag_top_k"] = int(db["rag_top_k"])
    if "rag_max_distance" in db:
        kwargs["rag_max_distance"] = float(db["rag_max_distance"])
    if "rag_answer_max_tokens" in db:
        kwargs["rag_answer_max_tokens"] = int(db["rag_answer_max_tokens"])
    if "rag_retrieval_timeout" in db:
        kwargs["rag_retrieval_timeout"] = int(db["rag_retrieval_timeout"])
    if "rag_embedding_request_timeout" in db:
        kwargs["rag_embedding_request_timeout"] = float(db["rag_embedding_request_timeout"])
    if "rag_chunk_size" in db:
        kwargs["rag_chunk_size"] = int(db["rag_chunk_size"])
    if "rag_chunk_overlap" in db:
        kwargs["rag_chunk_overlap"] = int(db["rag_chunk_overlap"])
    return replace(base, **kwargs)


def field_sources_from_db(db: dict[str, Any]) -> dict[str, str]:
    """Per-field ``env`` | ``db`` based on whether the key exists in stored overrides."""
    return {k: ("db" if k in db else "env") for k in sorted(TUNING_ALL_KEYS)}


def _validate_one(key: str, raw: Any) -> Any:
    if raw is None:
        raise ValueError(f"{key}: value must not be null")
    if key == "rag_top_k":
        v = int(raw)
        if not (1 <= v <= 20):
            raise ValueError(f"rag_top_k: expected integer 1..20, got {v}")
        return v
    if key == "rag_max_distance":
        v = float(raw)
        if not (0.1 <= v <= 10.0):
            raise ValueError(f"rag_max_distance: expected float 0.1..10.0, got {v}")
        return v
    if key == "rag_answer_max_tokens":
        v = int(raw)
        if not (100 <= v <= 8000):
            raise ValueError(f"rag_answer_max_tokens: expected integer 100..8000, got {v}")
        return v
    if key == "rag_retrieval_timeout":
        v = float(raw)
        if not (5.0 <= v <= 300.0):
            raise ValueError(f"rag_retrieval_timeout: expected number 5..300, got {v}")
        return int(round(v))
    if key == "rag_embedding_request_timeout":
        v = float(raw)
        if not (5.0 <= v <= 300.0):
            raise ValueError(f"rag_embedding_request_timeout: expected number 5..300, got {v}")
        return float(v)
    if key == "rag_chunk_size":
        v = int(raw)
        if not (200 <= v <= 5000):
            raise ValueError(f"rag_chunk_size: expected integer 200..5000, got {v}")
        return v
    if key == "rag_chunk_overlap":
        v = int(raw)
        if not (0 <= v <= 1000):
            raise ValueError(f"rag_chunk_overlap: expected integer 0..1000, got {v}")
        return v
    raise ValueError(f"unsupported tuning key {key!r}")


def validate_and_normalize_patch(
    base: AppConfig,
    db_existing: dict[str, Any],
    patch: dict[str, Any],
) -> dict[str, Any]:
    """
    Validate keys present in ``patch``; return normalized patch entries only.
    Cross-validates chunk overlap vs effective chunk size after merge.
    """
    unknown = set(patch) - TUNING_ALL_KEYS
    if unknown:
        raise ValueError(f"unknown tuning keys: {', '.join(sorted(unknown))}")
    if not patch:
        raise ValueError("empty tuning patch")
    normalized: dict[str, Any] = {}
    for k, raw in patch.items():
        normalized[k] = _validate_one(k, raw)
    merged = {**db_existing, **normalized}
    eff = apply_db_overrides_to_config(base, merged)
    if eff.rag_chunk_overlap >= eff.rag_chunk_size:
        raise ValueError(
            f"rag_chunk_overlap ({eff.rag_chunk_overlap}) must be strictly less than "
            f"rag_chunk_size ({eff.rag_chunk_size})"
        )
    return normalized


def strip_db_keys_matching_env(db: dict[str, Any], base: AppConfig) -> dict[str, Any]:
    """Remove override keys that match env defaults (keeps DB minimal)."""
    out = dict(db)
    for k in list(out.keys()):
        if value_matches_env(k, out[k], base):
            del out[k]
    return out
