"""
Сервис offline-диагностики retrieval (P6.8): агрегаты и smoke-checks без LLM.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from services.retrieval.base import RetrievalSearchResult
from services.retrieval_diagnostics.base import (
    RetrievalDiagnosticMetric,
    RetrievalDiagnosticResult,
    RetrievalDiagnosticSample,
)
from services.retrieval_security.context import (
    ROLE_GUEST,
    RetrievalSecurityContext,
)


def _preview(text: str, max_len: int = 200) -> str:
    t = " ".join((text or "").strip().split())
    if len(t) <= max_len:
        return t
    return t[: max_len - 3] + "..."


def _unique_sources(results: list[RetrievalSearchResult]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for r in results:
        src = str((r.chunk.metadata or {}).get("source") or "").strip()
        if not src:
            src = "unknown"
        key = src.lower()
        if key not in seen:
            seen.add(key)
            out.append(src)
    return out


def _combined_text(results: list[RetrievalSearchResult]) -> str:
    parts = [r.chunk.page_content or "" for r in results]
    return "\n".join(parts)


def _score_stats(results: list[RetrievalSearchResult]) -> tuple[float | None, float | None, float | None]:
    if not results:
        return None, None, None
    scores = [float(r.score) for r in results]
    return min(scores), max(scores), sum(scores) / len(scores)


def _expected_source_hit(sources: list[str], expected: tuple[str, ...]) -> bool:
    if not expected:
        return True
    norms = [s.lower() for s in sources]
    for exp in expected:
        e = exp.lower().strip()
        if not e:
            continue
        if any(e == n or e in n or n.endswith(e) for n in norms):
            return True
    return False


def _expected_keyword_hit(text: str, keywords: tuple[str, ...]) -> bool:
    if not keywords:
        return True
    low = text.lower()
    return all(kw.lower().strip() in low for kw in keywords if kw.strip())


def security_context_from_dict(raw: dict[str, Any] | None) -> RetrievalSecurityContext | None:
    """Десериализация из JSON dataset (опционально)."""
    if not raw or not isinstance(raw, dict):
        return None
    role = str(raw.get("role") or ROLE_GUEST).strip() or ROLE_GUEST
    allowed_raw = raw.get("allowed_sources")
    allowed: frozenset[str] | None
    if allowed_raw is None:
        allowed = None
    elif isinstance(allowed_raw, list):
        allowed = frozenset(str(x).strip() for x in allowed_raw if str(x).strip())
    else:
        allowed = None

    scope = str(raw.get("retrieval_scope") or "unrestricted").strip() or "unrestricted"
    mf_raw = raw.get("metadata_filters")
    mf_list: list[tuple[str, str]] = []
    if isinstance(mf_raw, list):
        for row in mf_raw:
            if isinstance(row, (list, tuple)) and len(row) >= 2:
                mf_list.append((str(row[0]).strip(), str(row[1]).strip()))
            elif isinstance(row, dict) and "key" in row and "value" in row:
                mf_list.append((str(row["key"]).strip(), str(row["value"]).strip()))
    req_raw = raw.get("required_tags")
    req: frozenset[str] = frozenset()
    if isinstance(req_raw, list):
        req = frozenset(str(x).strip() for x in req_raw if str(x).strip())

    return RetrievalSecurityContext(
        role=role,
        allowed_sources=allowed,
        retrieval_scope=scope,
        metadata_filters=tuple(mf_list),
        required_tags=req,
    )


class RetrievalDiagnosticsService:
    """Анализ результатов retrieval против ожиданий sample (без изменения pipeline)."""

    @staticmethod
    def load_samples(path: Path) -> list[RetrievalDiagnosticSample]:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise ValueError("dataset root must be a JSON array")
        out: list[RetrievalDiagnosticSample] = []
        for row in data:
            if not isinstance(row, dict):
                continue
            sid = str(row.get("id") or "").strip()
            q = str(row.get("query") or "").strip()
            if not sid or not q:
                continue
            ek = row.get("expected_keywords") or []
            if not isinstance(ek, list):
                ek = []
            es = row.get("expected_sources") or []
            if not isinstance(es, list):
                es = []
            tags = row.get("tags") or []
            if not isinstance(tags, list):
                tags = []
            sec = security_context_from_dict(row.get("security_context"))
            extra = {k: v for k, v in row.items() if k not in {
                "id", "query", "should_have_answer", "expected_keywords",
                "expected_sources", "tags", "security_context",
            }}
            out.append(
                RetrievalDiagnosticSample(
                    id=sid,
                    query=q,
                    should_have_answer=bool(row.get("should_have_answer", True)),
                    expected_keywords=tuple(str(x) for x in ek),
                    expected_sources=tuple(str(x) for x in es),
                    tags=tuple(str(t) for t in tags),
                    security_context=sec,
                    extra_metadata=extra,
                )
            )
        return out

    @staticmethod
    def analyze(
        *,
        sample: RetrievalDiagnosticSample,
        results: list[RetrievalSearchResult],
        security_context: RetrievalSecurityContext | None = None,
        extra_metadata: dict[str, Any] | None = None,
    ) -> RetrievalDiagnosticResult:
        """
        ``security_context`` в аргументах — явная передача для отчёта (совместимость с P6.7);
        может совпадать с ``sample.security_context``.
        """
        effective_sec = security_context if security_context is not None else sample.security_context
        sources = _unique_sources(results)
        retrieved_count = len(results)
        source_count = len(sources)
        combined = _combined_text(results)
        has_context = retrieved_count > 0 and bool(combined.strip())

        exp_src = sample.expected_sources
        exp_kw = sample.expected_keywords

        if exp_src:
            src_hit = _expected_source_hit(sources, exp_src)
        else:
            src_hit = None

        if exp_kw:
            kw_hit = _expected_keyword_hit(combined, exp_kw)
        else:
            kw_hit = None

        smin, smax, savg = _score_stats(results)
        warnings: list[str] = []
        metrics: list[RetrievalDiagnosticMetric] = []

        if sample.should_have_answer:
            if not has_context:
                warnings.append("empty_retrieval_when_should_have_answer")
            metrics.append(
                RetrievalDiagnosticMetric(
                    name="context_if_expected",
                    passed=has_context,
                    detail=None if has_context else "ожидался непустой retrieval",
                )
            )
        else:
            metrics.append(
                RetrievalDiagnosticMetric(
                    name="context_if_expected",
                    passed=True,
                    detail="should_have_answer=false — контекст не обязателен",
                )
            )

        if exp_src is not None and len(exp_src) > 0:
            ok = bool(src_hit)
            if not ok:
                warnings.append("expected_source_miss")
            metrics.append(
                RetrievalDiagnosticMetric(
                    name="expected_sources",
                    passed=ok,
                    detail=",".join(exp_src)[:200] or None,
                )
            )

        if exp_kw is not None and len(exp_kw) > 0:
            ok = bool(kw_hit)
            if not ok:
                warnings.append("expected_keyword_miss")
            metrics.append(
                RetrievalDiagnosticMetric(
                    name="expected_keywords",
                    passed=ok,
                    detail=",".join(exp_kw)[:200] or None,
                )
            )

        if not sample.should_have_answer and has_context:
            warnings.append("unexpected_non_empty_retrieval")

        passed = all(m.passed for m in metrics)

        meta: dict[str, Any] = {
            "tags": list(sample.tags),
            "should_have_answer": sample.should_have_answer,
            "security_context_summary": (
                effective_sec.to_cache_fingerprint_extra() if effective_sec else None
            ),
            "retrieved_sources_preview": [_preview(s, 120) for s in sources[:8]],
            "text_preview": _preview(combined, 400),
        }
        if sample.extra_metadata:
            meta["sample_extra"] = dict(sample.extra_metadata)
        if extra_metadata:
            meta["run_extra"] = dict(extra_metadata)

        return RetrievalDiagnosticResult(
            sample_id=sample.id,
            query_preview=_preview(sample.query, 240),
            retrieved_count=retrieved_count,
            source_count=source_count,
            has_context=has_context,
            expected_source_hit=src_hit,
            expected_keyword_hit=kw_hit,
            score_min=smin,
            score_max=smax,
            score_avg=savg,
            warnings=tuple(warnings),
            passed=passed,
            metrics=tuple(metrics),
            metadata=meta,
        )
