"""
Централизованная sanitization operational logs (P8.3).

Отдельно от retrieval filtering и pre-LLM masking.
"""

from __future__ import annotations

import re
from typing import Any

from services.retrieval_security.masking import mask_common_pii

POLICY_OPERATIONAL = "operational"
POLICY_FORENSIC_ADMIN = "forensic_admin"

_SECRET_MARKERS = ("sk-", "api_key", "openai_api_key")

# Поля, которые в operational mode не пишутся raw (redact или замена на preview).
_REDACT_KEYS_OPERATIONAL: frozenset[str] = frozenset(
    {
        "user_input",
        "retrieval_ready_query",
        "chunk_text_full",
        "text_full",
        "transcript",
        "context",
        "raw_payload",
        "prompt",
        "query",
    }
)

# Лимиты длины для строковых полей (operational).
_DEFAULT_MAX_LEN: dict[str, int] = {
    "query_preview": 200,
    "answer_text": 1500,
    "answer_preview": 1500,
    "user_text": 400,
    "recognized_text_preview": 600,
    "transcript_preview": 400,
    "output_text": 1500,
    "text_preview": 220,
}

_CHUNK_PREVIEW_CAP = 96

_FORENSIC_MAX_LEN: dict[str, int] = {
    "user_input": 800,
    "retrieval_ready_query": 4000,
    "chunk_text_full": 2000,
    "answer_text": 3000,
    "transcript": 2000,
}


def is_forensic_log_policy(
    details: dict[str, Any] | None,
    *,
    forensic: bool = False,
) -> bool:
    if forensic:
        return True
    if not details:
        return False
    role = str(details.get("retrieval_security_role") or "").strip().lower()
    if role == "admin":
        return True
    pol = str(details.get("sanitization_policy") or "").strip().lower()
    return pol == POLICY_FORENSIC_ADMIN


def _has_secret_pattern(text: str) -> bool:
    lower = (text or "").lower()
    return any(m in lower for m in _SECRET_MARKERS)


def sanitize_text_for_log(
    text: object,
    *,
    max_len: int = 400,
    mask_pii: bool = True,
) -> str:
    """Маскирование PII + усечение + redaction secret patterns."""
    t = " ".join(str(text or "").split())
    if not t:
        return ""
    if _has_secret_pattern(t):
        return "[redacted: possible secret pattern]"
    if mask_pii:
        t = mask_common_pii(t)
    if len(t) <= max_len:
        return t
    return t[: max_len - 1].rstrip() + "…"


def _sanitize_chunk_row(row: dict[str, Any], *, forensic: bool) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in row.items():
        if k in ("chunk_text_full", "text_full"):
            if not forensic:
                out["chunk_text_full_redacted"] = True
                continue
            if isinstance(v, str):
                out[k] = sanitize_text_for_log(
                    v, max_len=_FORENSIC_MAX_LEN.get("chunk_text_full", 2000)
                )
                continue
        if k == "text_preview" and isinstance(v, str):
            out[k] = sanitize_text_for_log(v, max_len=_CHUNK_PREVIEW_CAP)
        elif isinstance(v, str) and k in _DEFAULT_MAX_LEN:
            out[k] = sanitize_text_for_log(v, max_len=_DEFAULT_MAX_LEN[k])
        else:
            out[k] = v
    if not forensic and ("chunk_text_full" in row or "text_full" in row):
        out.setdefault("chunk_text_full_redacted", True)
    return out


def sanitize_log_details(
    details: dict[str, Any] | None,
    *,
    forensic: bool = False,
) -> dict[str, Any]:
    """
    Санитизирует ``processing_logs.details`` перед записью или отдачей в API.

    Добавляет markers: ``sanitized``, ``sanitization_policy``, ``redacted_fields``,
    ``truncated_fields``.
    """
    if not details:
        return {}

    forensic_mode = is_forensic_log_policy(details, forensic=forensic)
    policy = POLICY_FORENSIC_ADMIN if forensic_mode else POLICY_OPERATIONAL

    redacted: list[str] = []
    truncated: list[str] = []
    out: dict[str, Any] = {}

    for key, value in details.items():
        if key.startswith("_") or key in (
            "sanitized",
            "sanitization_policy",
            "redacted_fields",
            "truncated_fields",
        ):
            continue

        if not forensic_mode and key in _REDACT_KEYS_OPERATIONAL:
            redacted.append(key)
            if key == "transcript" and isinstance(value, str) and value.strip():
                prev = sanitize_text_for_log(
                    value, max_len=_DEFAULT_MAX_LEN["transcript_preview"]
                )
                if prev:
                    out["transcript_preview"] = prev
                    out["transcript_chars"] = len(value.strip())
            continue

        if forensic_mode and key in _FORENSIC_MAX_LEN and isinstance(value, str):
            cap = _FORENSIC_MAX_LEN[key]
            cleaned = sanitize_text_for_log(value, max_len=cap)
            if len(value.strip()) > cap:
                truncated.append(key)
            out[key] = cleaned
            continue

        if key == "retrieved_chunks" and isinstance(value, list):
            out[key] = [
                _sanitize_chunk_row(c, forensic=forensic_mode)
                for c in value
                if isinstance(c, dict)
            ]
            continue

        if isinstance(value, str):
            cap = _DEFAULT_MAX_LEN.get(key)
            if cap is not None:
                cleaned = sanitize_text_for_log(value, max_len=cap)
                if len(value.strip()) > cap:
                    truncated.append(key)
                out[key] = cleaned
            elif not forensic_mode and len(value) > 2000:
                out[key] = sanitize_text_for_log(value, max_len=2000)
                truncated.append(key)
            else:
                out[key] = (
                    sanitize_text_for_log(value, max_len=8000 if forensic_mode else 2000)
                    if mask_pii_needed(value)
                    else value
                )
            continue

        if isinstance(value, dict):
            out[key] = sanitize_log_details(value, forensic=forensic_mode)
            continue

        if isinstance(value, list):
            out[key] = value
            continue

        out[key] = value

    out["sanitized"] = True
    out["sanitization_policy"] = policy
    if redacted:
        out["redacted_fields"] = sorted(set(redacted))
    if truncated:
        out["truncated_fields"] = sorted(set(truncated))
    return out


def mask_pii_needed(text: str) -> bool:
    """Эвристика: есть ли смысл гонять mask_common_pii."""
    if _has_secret_pattern(text):
        return True
    if re.search(r"@|\d{8,}", text):
        return True
    return False
