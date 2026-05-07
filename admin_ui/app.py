"""
Streamlit admin UI for RAG (documents, reindex, status, logs).

Run from repository root:
  streamlit run admin_ui/app.py
"""

from __future__ import annotations

import html
import json
import math
import os
import sys
import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone
import zoneinfo
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import streamlit as st

from services.admin_service import AdminService
from services.asset_repository_factory import create_asset_repository
from services.healthcheck_service import (
    HealthSnapshot,
    format_health_badge_status,
    run_system_healthchecks,
)
from utils.config import load_config

moscow_tz = zoneinfo.ZoneInfo("Europe/Moscow")

# Документы: компактный превью текста (upload / сэмплы), не полный chunk в основном виде
MAX_CHUNK_PREVIEW_CHARS = 350
_RAW_METADATA_JSON_MAX = 12_000
_DISK_SAMPLE_READ_MAX = 256 * 1024


def _estimate_chunks(text: str, *, chunk_size: int, chunk_overlap: int) -> int:
    """
    Операционная оценка числа чангов (как sliding window RecursiveCharacterTextSplitter:
    шаг ≈ chunk_size − chunk_overlap). Точное совпадение с LangChain не требуется.
    """
    if not text or not str(text).strip():
        return 0
    L = len(text)
    if L <= max(1, chunk_size):
        return 1
    step = max(1, int(chunk_size) - int(chunk_overlap))
    return max(1, math.ceil((L - int(chunk_overlap)) / step))


def _doc_chunk_tier(chunk_count: int) -> str:
    """normal | medium | large — по active/estimated chunk count."""
    n = int(chunk_count)
    if n <= 50:
        return "normal"
    if n <= 150:
        return "medium"
    return "large"


def _doc_upload_tier_label(tier: str) -> str:
    if tier == "normal":
        return "Small document"
    if tier == "medium":
        return "Medium document"
    return "Large document warning"


def _format_bytes(num: int) -> str:
    n = float(max(0, int(num)))
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024.0 or unit == "GB":
            if unit == "B":
                return f"{int(n)} {unit}"
            return f"{n:.1f} {unit}"
        n /= 1024.0
    return f"{int(num)} B"


def _truncate_preview(text: str, max_len: int = MAX_CHUNK_PREVIEW_CHARS) -> str:
    s = str(text)
    if len(s) <= max_len:
        return s
    return s[: max_len - 1] + "…"


def get_doc_chunk_badge(chunk_count: int) -> str:
    """Компактный бейдж NORMAL / MEDIUM / LARGE (тот же язык, что route-badge)."""
    tier = _doc_chunk_tier(int(chunk_count))
    labels = {"normal": "NORMAL", "medium": "MEDIUM", "large": "LARGE"}
    return (
        f'<span class="doc-chunk-badge doc-chunk-badge--{tier}">'
        f"{html.escape(labels[tier])}</span>"
    )


def _documents_stats_strip_html(doc_rows: list[dict[str, Any]]) -> str:
    if not doc_rows:
        return ""
    n = len(doc_rows)
    chunks = [int(r.get("active_chunk_count") or 0) for r in doc_rows]
    total_ch = sum(chunks)
    avg = round(total_ch / n, 1) if n else 0.0
    largest = max(doc_rows, key=lambda r: int(r.get("active_chunk_count") or 0))
    max_ch = int(largest.get("active_chunk_count") or 0)
    max_name = str(largest.get("filename") or "—")
    tiles = [
        ("Документов", str(n)),
        ("Чанков (active)", str(total_ch)),
        ("Ср. чанков / док.", str(avg)),
        ("Макс. чанков", str(max_ch)),
        ("Крупнейший файл", max_name if len(max_name) <= 28 else max_name[:25] + "…"),
    ]
    parts = [
        '<div class="doc-stats-strip">',
        '<span class="doc-stats-strip-title">База знаний</span>',
        '<div class="doc-stats-strip-tiles">',
    ]
    for lbl, val in tiles:
        parts.append(
            '<div class="doc-stat-tile">'
            f'<span class="doc-stat-tile-val">{html.escape(str(val))}</span>'
            f'<span class="doc-stat-tile-lbl">{html.escape(lbl)}</span>'
            "</div>"
        )
    parts.append("</div></div>")
    return "".join(parts)


@st.cache_resource
def _admin_service() -> AdminService:
    return AdminService()


# =============================================================================
# Operational UI primitives (HTML helpers + Streamlit; single-file layer)
# =============================================================================

OPS_SPLIT_COLUMNS_RATIO = (0.35, 0.65)


def split_list_detail_columns() -> Any:
    """Единая сетка список / детали для операторских вкладок."""
    return st.columns(OPS_SPLIT_COLUMNS_RATIO)


def ops_dashboard_card_html(
    title: str,
    inner_html: str,
    *,
    footnote_html: str | None = None,
    extra_classes: str = "",
) -> str:
    """Компактная карточка обзора/сводки: заголовок + тело + опциональный footnote."""
    base = "ops-dashboard-card"
    if extra_classes.strip():
        cls = f"{base} {extra_classes.strip()}"
    else:
        cls = base
    parts = [
        f'<div class="{cls}">',
        f'<div class="ops-dashboard-card-title">{html.escape(title)}</div>',
        inner_html,
    ]
    if footnote_html:
        parts.append(footnote_html)
    parts.append("</div>")
    return "".join(parts)


def ops_trace_header_html(
    *,
    title: str,
    execution_id: str,
    badges_inner_html: str,
    kv_pairs: list[tuple[str, str]],
) -> str:
    """
    Заголовок трассы (logs-trace-header). kv_pairs: (label, value_html);
    label экранируется, value_html — доверенная разметка (уже с escape).
    """
    kv_body = "".join(
        f"<span>{html.escape(lab)}</span><span>{val}</span>" for lab, val in kv_pairs
    )
    return (
        '<div class="logs-trace-header">'
        f'<div class="logs-trace-header-title">{html.escape(title)}</div>'
        '<div class="logs-trace-header-row logs-trace-header-eid">'
        "<span>execution_id</span>"
        f'<code>{html.escape(execution_id)}</code>'
        "</div>"
        '<div class="logs-trace-header-badges">'
        f"{badges_inner_html}"
        "</div>"
        f'<div class="logs-trace-header-kv">{kv_body}</div>'
        "</div>"
    )


def ops_timeline_section_title_html(section_title: str) -> str:
    return (
        f'<div class="logs-trace-timeline-title">{html.escape(section_title)}</div>'
    )


def panel_section_title_html(title: str) -> str:
    """Секционный заголовок (тот же визуал, что image-section-title)."""
    return f'<div class="panel-section-title">{html.escape(title)}</div>'


def render_empty_state(message: str) -> None:
    """Единый компактный пустой / недоступный state (операторский, без st.info)."""
    st.markdown(
        f'<div class="panel-empty"><p>{html.escape(message)}</p></div>',
        unsafe_allow_html=True,
    )


def render_json_preview(
    data: Any,
    *,
    max_chars: int = _RAW_METADATA_JSON_MAX,
    language: str = "json",
) -> None:
    """Технический JSON в едином json-dark + code."""
    try:
        dump = json.dumps(data, ensure_ascii=False, default=str, indent=2)
    except TypeError:
        dump = str(data)
    if len(dump) > max_chars:
        dump = dump[: max_chars - 1] + "…"
    st.markdown('<div class="json-dark">', unsafe_allow_html=True)
    st.code(dump, language=language)
    st.markdown("</div>", unsafe_allow_html=True)


def render_metadata_expander(
    title: str,
    data: Any,
    *,
    expanded: bool = False,
) -> None:
    """Сырой metadata / details в стандартном expander."""
    with st.expander(title, expanded=expanded):
        render_json_preview(data)


def render_compact_meta_row(
    label: str,
    value: str,
    *,
    value_is_html: bool = False,
) -> None:
    """Одна строка метаданных (markdown; value по умолчанию экранируется)."""
    safe_label = html.escape(label)
    if value_is_html:
        inner = value
    else:
        inner = html.escape(value)
    st.markdown(
        f'<div class="panel-meta-row">'
        f'<span class="panel-meta-k">{safe_label}</span> '
        f'<span class="panel-meta-v">{inner}</span>'
        "</div>",
        unsafe_allow_html=True,
    )


# Человекочитаемые названия этапов/типов событий (processing_logs.stage/event_type)
_EVENT_TYPE_ALIASES: dict[str, str] = {
    "text_answer_done": "processing_done",
    "rag_answer_done": "processing_done",
    "image_answer_done": "processing_done",
    "rag_response": "processing_done",
}

_EVENT_TYPE_RU: dict[str, str] = {
    "intake_received": "Получен запрос",
    "route_selected": "Определён тип запроса",
    "processing_done": "Обработка завершена",
    "processing_error": "Ошибка обработки",
    "database_schema": "Служебное событие схемы БД",
    "admin_document_uploaded": "Загрузка документа (админка)",
    "admin_reindex_started": "Переиндексация запущена",
    "admin_reindex_done": "Переиндексация завершена",
    "admin_reindex_error": "Ошибка переиндексации",
    "image_generation_started": "Генерация изображения запущена",
    "image_text_enhancement_done": "Уточнение промпта (текст) завершено",
    "image_prompt_refinement_done": "Подготовка image prompt завершена",
    "image_provider_done": "Изображение получено от провайдера",
    "image_assets_persisted": "Файлы изображения сохранены",
    "rag_unavailable": "RAG недоступен",
    "system_degraded": "Деградация системы",
}

_ROUTE_ALIASES: dict[str, str] = {
    "text_response": "text",
    "text_answer_done": "text",
    "text_query": "text",
    "rag_response": "rag",
    "rag_answer_done": "rag",
    "image": "image_generation",
    "image_response": "image_generation",
}

_ROUTE_LABEL_RU: dict[str, str] = {
    "rag": "RAG",
    "text": "Текст",
    "image_generation": "Генерация изображений",
    "unknown": "Прочее",
}


def normalize_route(route: str | None) -> str:
    raw = (route or "").strip().lower()
    if not raw:
        return "unknown"
    return _ROUTE_ALIASES.get(raw, raw)


def normalize_event_type(event_type: str | None) -> str:
    raw = (event_type or "").strip().lower()
    if not raw:
        return ""
    return _EVENT_TYPE_ALIASES.get(raw, raw)


def _stage_to_action(stage: str | None, details: Any = None) -> str:
    raw = (stage or "").strip()
    if raw == "text_answer_done":
        return "Текстовый ответ построен"
    if raw == "rag_answer_done":
        return "RAG-ответ построен"
    if raw == "processing_done":
        dd = details if isinstance(details, dict) else {}
        if normalize_route(str(dd.get("route") or "")) == "image_generation":
            if dd.get("generation_completed"):
                return "Генерация завершена"
            return "Обработка завершена (изображение)"
    norm = normalize_event_type(stage)
    if not norm:
        return "—"
    return _EVENT_TYPE_RU.get(norm, norm)


_STATUS_RU: dict[str, str] = {
    "success": "успешно",
    "error": "ошибка",
    "skipped": "пропущено",
    "retry": "повтор",
    "started": "запущено",
}


def get_russian_status(raw: str | None) -> str:
    if not raw:
        return "—"
    return _STATUS_RU.get(raw.strip().lower(), raw)


def _status_label(raw: str | None) -> str:
    return get_russian_status(raw)


def _route_label(route: str | None) -> str:
    norm = normalize_route(route)
    return _ROUTE_LABEL_RU.get(norm, norm if norm else "—")


def get_route_badge(route: str | None) -> str:
    norm = normalize_route(route)
    label = _route_label(norm)
    tone = "muted"
    if norm == "rag":
        tone = "success"
    elif norm == "text":
        tone = "info"
    elif norm == "image_generation":
        tone = "warning"
    return (
        f'<span class="route-badge route-badge--{tone}">'
        f"{html.escape(label)}</span>"
    )


def _details_to_description(details: Any, *, max_len: int = 400) -> str:
    if details is None:
        return "—"
    if isinstance(details, dict) and len(details) == 0:
        return "—"
    try:
        if isinstance(details, dict):
            text = json.dumps(details, ensure_ascii=False, default=str)
        else:
            text = str(details)
    except Exception:
        text = str(details)
    text = text.strip()
    if not text:
        return "—"
    if len(text) > max_len:
        return text[: max_len - 1] + "…"
    return text


def _format_dt(dt: Any) -> str:
    if dt is None:
        return "—"
    try:
        if hasattr(dt, "strftime"):
            return dt.strftime("%d.%m.%Y %H:%M")
    except Exception:
        pass
    return str(dt)


def _format_dt_moscow_logs(dt: Any) -> str:
    """Время из processing_logs в Europe/Moscow; хранение в БД не меняется."""
    if dt is None:
        return "—"
    if not isinstance(dt, datetime):
        return str(dt)
    try:
        if dt.tzinfo is not None:
            dt_local = dt.astimezone(moscow_tz)
        else:
            dt_local = dt.replace(tzinfo=timezone.utc).astimezone(moscow_tz)
        return dt_local.strftime("%d.%m.%Y %H:%M:%S")
    except Exception:
        return str(dt)


def _format_dt_moscow_overview(dt: Any) -> str:
    """MSK для вкладки «Обзор»: DD.MM.YYYY HH (только час, без минут)."""
    if dt is None:
        return "—"
    if not isinstance(dt, datetime):
        return str(dt)
    try:
        if dt.tzinfo is not None:
            dt_local = dt.astimezone(moscow_tz)
        else:
            dt_local = dt.replace(tzinfo=timezone.utc).astimezone(moscow_tz)
        return dt_local.strftime("%d.%m.%Y %H")
    except Exception:
        return str(dt)


OVERVIEW_TELEMETRY_LOG_CAP = 400


def _overview_extract_latency_ms(details: dict[str, Any]) -> float | None:
    for key in ("latency_ms", "duration_ms", "elapsed_ms"):
        v = details.get(key)
        if v is None:
            continue
        try:
            return float(v)
        except (TypeError, ValueError):
            continue
    return None


def _overview_extract_tokens_increment(details: dict[str, Any]) -> int | None:
    """Возвращает вклад в сумму токенов из одной строки details или None."""
    v = details.get("total_tokens")
    if v is not None:
        try:
            return int(float(v))
        except (TypeError, ValueError):
            pass
    usage = details.get("token_usage")
    if isinstance(usage, dict):
        for a, b in (
            ("total_tokens", None),
            ("input_tokens", "output_tokens"),
            ("prompt_tokens", "completion_tokens"),
        ):
            if b is None:
                u = usage.get(a)
                if u is not None:
                    try:
                        return int(float(u))
                    except (TypeError, ValueError):
                        pass
            else:
                x = usage.get(a)
                y = usage.get(b)
                if x is not None or y is not None:
                    s = 0
                    ok = False
                    for part in (x, y):
                        if part is None:
                            continue
                        try:
                            s += int(float(part))
                            ok = True
                        except (TypeError, ValueError):
                            continue
                    if ok:
                        return s
    u_obj = details.get("usage")
    if isinstance(u_obj, dict):
        v2 = u_obj.get("total_tokens")
        if v2 is not None:
            try:
                return int(float(v2))
            except (TypeError, ValueError):
                pass
    return None


def _overview_telemetry_from_rows(
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Лёгкая телеметрия по последним строкам журнала (без новых запросов к БД).
    latency — среднее по полям details; токены и provider/model — если есть в details.
    """
    latencies: list[float] = []
    tokens_sum = 0
    tokens_any = False
    pm_counts: dict[tuple[str, str], int] = defaultdict(int)
    for r in rows:
        d = r.get("details")
        if not isinstance(d, dict):
            continue
        lm = _overview_extract_latency_ms(d)
        if lm is not None:
            latencies.append(lm)
        inc = _overview_extract_tokens_increment(d)
        if inc is not None:
            tokens_sum += inc
            tokens_any = True
        prov = str(d.get("provider") or d.get("llm_provider") or "").strip()
        model = str(d.get("model") or d.get("llm_model") or "").strip()
        if prov or model:
            pm_counts[(prov or "—", model or "—")] += 1

    avg_lat: float | None = None
    if latencies:
        avg_lat = round(sum(latencies) / len(latencies), 1)

    top_pm: str | None = None
    if pm_counts:
        (prov_t, model_t), _n = max(pm_counts.items(), key=lambda x: x[1])
        top_pm = f"{prov_t} / {model_t}"

    return {
        "avg_latency_ms": avg_lat,
        "tokens_total": int(tokens_sum) if tokens_any else None,
        "top_provider_model": top_pm,
    }


def _overview_find_last_success_row(
    rows: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Самая свежая запись со status=success (список уже от новых к старым)."""
    for r in rows:
        if str(r.get("status") or "").strip().lower() == "success":
            return r
    return None


def _overview_find_last_admin_row(
    rows: list[dict[str, Any]],
) -> dict[str, Any] | None:
    for r in rows:
        stg = str(r.get("stage") or "")
        if stg.startswith("admin_"):
            return r
    return None


def _overview_ops_kv_html(rows: list[tuple[str, str]]) -> str:
    parts = ['<div class="ops-kv">']
    for lbl, val in rows:
        parts.append(f'<span class="ops-kv-lbl">{html.escape(lbl)}</span>')
        parts.append(f'<span class="ops-kv-val">{html.escape(val)}</span>')
    parts.append("</div>")
    return "".join(parts)


def _overview_ops_kv_item(label: str, value_inner_html: str) -> str:
    """Одна пара label/value; value_inner_html — доверенная вёрстка (бейджи)."""
    return (
        f'<span class="ops-kv-lbl">{html.escape(label)}</span>'
        f'<span class="ops-kv-val">{value_inner_html}</span>'
    )


def _overview_ops_kv_mixed(items: list[str]) -> str:
    return '<div class="ops-kv">' + "".join(items) + "</div>"


def _render_panel_footnote_html(inner_html: str) -> str:
    """
    Служебное пояснение внизу карточки Overview/Summary.
    inner_html — доверенная разметка (фрагменты с <code> и т.п.).
    """
    return f'<div class="panel-footnote">{inner_html}</div>'


def _overview_metric_chips_html(items: list[tuple[str, str]]) -> str:
    parts = ['<div class="ops-metric-row">']
    for lbl, val in items:
        parts.append(
            '<div class="ops-metric-chip">'
            f'<span class="ops-metric-chip-val">{html.escape(val)}</span>'
            f'<span class="ops-metric-chip-lbl">{html.escape(lbl)}</span>'
            "</div>"
        )
    parts.append("</div>")
    return "".join(parts)


def _overview_log_status_badge_html(raw: str | None) -> str:
    s = str(raw or "").strip().lower()
    if s == "success":
        tone = "success"
    elif s == "error":
        tone = "error"
    elif s in ("skipped", "retry", "started"):
        tone = "warning"
    else:
        tone = "muted"
    label = _status_label(raw)
    return (
        f'<span class="log-status-badge log-status-badge--{tone}">'
        f"{html.escape(label)}</span>"
    )


SUMMARY_LOG_SAMPLE_CAP = 500
SUMMARY_HOURS_WINDOW = 24

SUMMARY_LIFECYCLE_ORDER: tuple[str, ...] = (
    "intake_received",
    "route_selected",
    "text_answer_done",
    "rag_answer_done",
    "processing_done",
    "admin_reindex_started",
    "admin_reindex_done",
    "processing_error",
)


def _summary_rows_since_hours(
    rows: list[dict[str, Any]], *, hours: int = SUMMARY_HOURS_WINDOW
) -> list[dict[str, Any]]:
    """Фильтр строк журнала по окну времени (UTC)."""
    delta = timedelta(hours=max(1, int(hours)))
    cutoff = datetime.now(timezone.utc) - delta
    out: list[dict[str, Any]] = []
    for r in rows:
        t = r.get("created_at")
        if not isinstance(t, datetime):
            continue
        tt = t if t.tzinfo else t.replace(tzinfo=timezone.utc)
        if tt >= cutoff:
            out.append(r)
    return out


def _summary_unique_execution_ids(rows: list[dict[str, Any]]) -> int:
    s: set[str] = set()
    for r in rows:
        eid = str(r.get("execution_id") or "").strip()
        if eid:
            s.add(eid)
    return len(s)


def _summary_route_sample_outcomes(
    rows: list[dict[str, Any]],
) -> dict[str, dict[str, int]]:
    """
    По сессиям в выборке: итоговый статус × нормализованный маршрут
    (как в списке логов: route/mode/stage).
    """
    packed = group_logs_by_execution_id(rows)
    out: dict[str, dict[str, int]] = {
        "text": {"success": 0, "error": 0, "other": 0},
        "rag": {"success": 0, "error": 0, "other": 0},
        "image_generation": {"success": 0, "error": 0, "other": 0},
        "unknown": {"success": 0, "error": 0, "other": 0},
    }
    for _eid, _start, events in packed:
        rt = _logs_infer_route_from_events(events)
        bucket = rt if rt in ("text", "rag", "image_generation") else "unknown"
        final = str(_logs_session_final_status(events)).strip().lower()
        if final == "success":
            out[bucket]["success"] += 1
        elif final == "error":
            out[bucket]["error"] += 1
        else:
            out[bucket]["other"] += 1
    return out


def _summary_telemetry_extended_from_rows(
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Токены, latency (avg/max), топ provider/model, число строк по provider."""
    latencies: list[float] = []
    tokens_sum = 0
    tokens_any = False
    pm_counts: dict[tuple[str, str], int] = defaultdict(int)
    prov_row_counts: dict[str, int] = defaultdict(int)
    for r in rows:
        d = r.get("details")
        if not isinstance(d, dict):
            continue
        lm = _overview_extract_latency_ms(d)
        if lm is not None:
            latencies.append(lm)
        inc = _overview_extract_tokens_increment(d)
        if inc is not None:
            tokens_sum += inc
            tokens_any = True
        prov = str(d.get("provider") or d.get("llm_provider") or "").strip()
        model = str(d.get("model") or d.get("llm_model") or "").strip()
        if prov:
            prov_row_counts[prov] += 1
        if prov or model:
            pm_counts[(prov or "—", model or "—")] += 1

    avg_lat = round(sum(latencies) / len(latencies), 1) if latencies else None
    max_lat = round(max(latencies), 1) if latencies else None
    top_pm: str | None = None
    if pm_counts:
        (prov_t, model_t), _n = max(pm_counts.items(), key=lambda x: x[1])
        top_pm = f"{prov_t} / {model_t}"

    by_prov = dict(sorted(prov_row_counts.items(), key=lambda x: (-x[1], x[0])))

    return {
        "avg_latency_ms": avg_lat,
        "max_latency_ms": max_lat,
        "tokens_total": int(tokens_sum) if tokens_any else None,
        "top_provider_model": top_pm,
        "by_provider_rows": by_prov,
    }


def _summary_lifecycle_list_html(by_stage: dict[str, Any]) -> str:
    parts = ['<div class="summary-lifecycle-list">']
    for stg in SUMMARY_LIFECYCLE_ORDER:
        cnt = int(by_stage.get(stg, 0) or 0)
        label = _stage_to_action(stg)
        if stg == "processing_error" and cnt > 0:
            item_cls = "summary-lifecycle-item summary-lifecycle-item--error"
        elif cnt > 0:
            item_cls = "summary-lifecycle-item summary-lifecycle-item--ok"
        else:
            item_cls = "summary-lifecycle-item summary-lifecycle-item--muted"
        parts.append(
            f'<div class="{item_cls}">'
            f'<span class="summary-lifecycle-lbl">{html.escape(label)}</span>'
            f'<span class="summary-lifecycle-cnt">{cnt}</span>'
            "</div>"
        )
    parts.append("</div>")
    return "".join(parts)


def _summary_route_rows_html(
    *,
    by_route: dict[str, int],
    sample_out: dict[str, dict[str, int]],
    unknown_sample_n: int,
) -> str:
    """Компактные карточки маршрутов: счётчики 24 ч из dashboard + исходы из выборки."""
    n_text = int(by_route.get("text", 0) or 0)
    n_rag = int(by_route.get("rag", 0) or 0)
    n_img = int(by_route.get("image_generation", 0) or 0)
    denom = max(1, n_text + n_rag + n_img + max(0, unknown_sample_n))

    def pct(n: int) -> str:
        return f"{round(100.0 * n / denom, 1)}%"

    def outcome_line(bucket: str) -> str:
        o = sample_out.get(bucket) or {}
        s_ok = int(o.get("success", 0))
        s_er = int(o.get("error", 0))
        s_ot = int(o.get("other", 0))
        if s_ok == 0 and s_er == 0 and s_ot == 0:
            return (
                '<span class="route-badge route-badge--muted">'
                "нет сессий в выборке"
                "</span>"
            )
        parts_o = [
            f'<span class="log-status-badge log-status-badge--success">успех {s_ok}</span>',
            f'<span class="log-status-badge log-status-badge--error">ошибка {s_er}</span>',
        ]
        if s_ot:
            parts_o.append(
                f'<span class="log-status-badge log-status-badge--warning">прочее {s_ot}</span>'
            )
        return '<span class="summary-route-outcomes">' + " · ".join(parts_o) + "</span>"

    cards: list[tuple[str, str, str, str]] = [
        ("Текст", str(n_text), pct(n_text), "text"),
        ("RAG", str(n_rag), pct(n_rag), "rag"),
        ("Генерация изображений", str(n_img), pct(n_img), "image_generation"),
        (
            "Прочее / без маршрута",
            str(max(0, unknown_sample_n)),
            pct(max(0, unknown_sample_n)),
            "unknown",
        ),
    ]

    blocks: list[str] = ['<div class="summary-route-grid">']
    for title, cnt_s, share_s, bucket in cards:
        blocks.append('<div class="summary-route-card">')
        blocks.append(f'<div class="summary-route-card-title">{html.escape(title)}</div>')
        blocks.append(
            '<div class="summary-route-card-meta">'
            f'<span class="summary-route-count">{html.escape(cnt_s)}</span>'
            f'<span class="summary-route-share">{html.escape(share_s)}</span>'
            "</div>"
        )
        blocks.append(
            '<div class="summary-route-card-outcomes">'
            f"{outcome_line(bucket)}"
            "</div>"
        )
        blocks.append("</div>")
    blocks.append("</div>")
    return "".join(blocks)


def _short_file_hash(raw: Any, *, prefix_len: int = 12) -> str:
    """Короткое отображение SHA256 для таблицы версий."""
    if raw is None:
        return "—"
    s = str(raw).strip()
    if not s:
        return "—"
    if len(s) <= prefix_len:
        return s
    return s[:prefix_len] + "…"


def _event_display_row(r: dict[str, Any]) -> dict[str, Any]:
    """Одна строка таблицы: время | действие | статус | описание."""
    return {
        "время": _format_dt_moscow_logs(r.get("created_at")),
        "действие": _stage_to_action(r.get("stage"), r.get("details")),
        "статус": _status_label(r.get("status")),
        "описание": _details_to_description(r.get("details")),
    }


def _event_sort_key(r: dict[str, Any]) -> Any:
    t = r.get("created_at")
    if isinstance(t, datetime):
        return t
    return datetime.min


def _group_sort_key(group: list[dict[str, Any]]) -> datetime:
    """Сортировка групп: сначала запросы с более поздней активностью."""
    times = [r.get("created_at") for r in group if isinstance(r.get("created_at"), datetime)]
    if not times:
        return datetime.min
    return max(times)


def group_logs_by_execution_id(
    rows: list[dict[str, Any]],
) -> list[tuple[str, datetime | None, list[dict[str, Any]]]]:
    """
    Группы по execution_id; внутри группы события по времени по возрастанию.
    Порядок групп: по времени последнего события (новые сверху).
    """
    by_eid: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        raw = r.get("execution_id")
        eid = str(raw).strip() if raw is not None else ""
        if not eid:
            eid = "—"
        by_eid[eid].append(r)

    packed: list[tuple[str, datetime | None, list[dict[str, Any]]]] = []
    for eid, group in by_eid.items():
        ordered = sorted(group, key=_event_sort_key)
        starts = [r.get("created_at") for r in ordered if isinstance(r.get("created_at"), datetime)]
        start_ts: datetime | None = min(starts) if starts else None
        packed.append((eid, start_ts, ordered))

    packed.sort(key=lambda x: _group_sort_key(x[2]), reverse=True)
    return packed


LOGS_DETAILS_PREVIEW_MAX = 200
LOGS_TIMELINE_PREVIEW_MAX = 120
LOGS_LIST_PREVIEW_MAX = 140
LOGS_EXEC_ID_SHORT_LEN = 8
IMAGE_LIST_LOG_CAP = 500
_IMAGE_PROMPT_PREVIEW_MAX = 200
_IMAGE_STAGE_MARKERS: frozenset[str] = frozenset(
    {
        "image_generation_started",
        "image_generation_done",
        "image_generation_error",
        "image_answer_done",
        "image_text_enhancement_done",
        "image_prompt_refinement_done",
        "image_provider_done",
        "image_assets_persisted",
    }
)
_IMAGE_FILE_SUFFIXES: tuple[str, ...] = (
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".gif",
)


def _short_execution_id(eid: str | None) -> str:
    s = str(eid or "").strip()
    if not s or s == "—":
        return "—"
    n = LOGS_EXEC_ID_SHORT_LEN
    if len(s) <= n:
        return s
    return s[:n] + "…"


def _logs_infer_route_from_events(events: list[dict[str, Any]]) -> str:
    """Нормализованный route/mode/stage для бейджа (presentation only)."""
    for ev in reversed(events):
        details = ev.get("details")
        dd: dict[str, Any] = details if isinstance(details, dict) else {}
        r_raw = str(dd.get("route") or "").strip()
        if r_raw:
            norm = normalize_route(r_raw)
            if norm != "unknown":
                return norm
        mode = str(dd.get("mode") or "").strip().lower()
        if mode == "text":
            return "text"
        if mode == "rag":
            return "rag"
        if mode == "image":
            return "image_generation"
    for ev in reversed(events):
        stg = str(ev.get("stage") or "")
        if stg == "rag_answer_done":
            return "rag"
        if stg == "text_answer_done":
            return "text"
    return "unknown"


def _logs_session_final_status(events: list[dict[str, Any]]) -> str:
    for ev in reversed(events):
        stg = str(ev.get("stage") or "")
        if stg in (
            "processing_done",
            "processing_error",
            "rag_answer_done",
            "text_answer_done",
            "image_answer_done",
        ):
            return str(ev.get("status") or "—")
    if events:
        return str(events[-1].get("status") or "—")
    return "—"


def _logs_session_preview(events: list[dict[str, Any]]) -> str:
    for ev in events:
        details = ev.get("details")
        dd: dict[str, Any] = details if isinstance(details, dict) else {}
        p = _first_non_empty(
            dd,
            (
                "user_text",
                "message_text",
                "query_preview",
                "text",
                "answer_preview",
            ),
        )
        if p:
            p = p.strip()
            if len(p) > LOGS_LIST_PREVIEW_MAX:
                return p[: LOGS_LIST_PREVIEW_MAX - 1] + "…"
            return p
    return ""


def _logs_timeline_flow_ru(events: list[dict[str, Any]]) -> str:
    parts = [
        _stage_to_action(ev.get("stage"), ev.get("details")) for ev in events
    ]
    return " → ".join(parts)


def infer_event_severity(
    stage: str | None,
    status: str | None,
    details: Any = None,
) -> str:
    """
    Семантика события только для UI (цвет trace / border).
    Возвращает: success | error | warning | muted.
    """
    stg = str(stage or "").strip().lower()
    stat = str(status or "").strip().lower()
    dd: dict[str, Any] = details if isinstance(details, dict) else {}
    fb = str(dd.get("fallback_reason") or "").strip().lower()
    if fb == "llm_error":
        return "error"
    if fb in ("low_relevance", "empty_retrieval", "empty_context"):
        return "warning"

    if stat == "error":
        return "error"
    if stg == "processing_error" or stg.endswith("_error"):
        return "error"

    if stg in (
        "text_answer_done",
        "rag_answer_done",
        "image_answer_done",
        "image_generation_done",
        "image_text_enhancement_done",
        "image_prompt_refinement_done",
        "image_assets_persisted",
        "processing_done",
        "admin_reindex_done",
        "admin_document_uploaded",
    ):
        if stat == "success":
            return "success"
    if stg in ("image_generation_started",):
        return "warning"
    if stg == "image_provider_done":
        return "error" if stat == "error" else "success"
    if stg in ("image_generation_error",):
        return "error"
    if stg == "admin_reindex_started":
        return "warning"
    if stat == "success":
        return "success"
    if stat in ("started", "skipped", "retry"):
        return "warning"
    return "muted"


def _logs_session_wall_duration_ms(
    events: list[dict[str, Any]],
) -> int | None:
    times = [
        r.get("created_at")
        for r in events
        if isinstance(r.get("created_at"), datetime)
    ]
    if len(times) < 2:
        return None
    t0, t1 = min(times), max(times)
    a = t0 if t0.tzinfo else t0.replace(tzinfo=timezone.utc)
    b = t1 if t1.tzinfo else t1.replace(tzinfo=timezone.utc)
    return int((b - a).total_seconds() * 1000)


def _logs_format_duration_ms(ms: int | None) -> str:
    if ms is None:
        return "—"
    if ms < 1000:
        return f"{ms} мс"
    return f"{round(ms / 1000.0, 2)} с"


def _logs_session_provider_model(events: list[dict[str, Any]]) -> str | None:
    for ev in reversed(events):
        d = ev.get("details")
        if not isinstance(d, dict):
            continue
        prov = str(d.get("provider") or d.get("llm_provider") or "").strip()
        model = str(d.get("model") or d.get("llm_model") or "").strip()
        if prov or model:
            return f"{prov or '—'} / {model or '—'}"
    return None


def _logs_session_max_step_latency_ms(
    events: list[dict[str, Any]],
) -> int | None:
    """Макс. latency из полей details по шагам (если есть)."""
    best: float | None = None
    for ev in events:
        d = ev.get("details")
        if not isinstance(d, dict):
            continue
        lm = _overview_extract_latency_ms(d)
        if lm is None:
            continue
        best = lm if best is None else max(best, lm)
    return int(round(best)) if best is not None else None


def _image_log_row_matches(row: dict[str, Any]) -> bool:
    """Строка журнала относится к image-generation (нормализация без новых запросов к БД)."""
    stg = str(row.get("stage") or "").strip().lower()
    if stg in _IMAGE_STAGE_MARKERS:
        return True
    details = row.get("details")
    if not isinstance(details, dict):
        return False
    mode = str(details.get("mode") or "").strip().lower()
    if mode == "image":
        return True
    r_raw = str(details.get("route") or "").strip()
    return normalize_route(r_raw) == "image_generation"


def _image_build_sessions_from_rows(
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Сессии генерации: группировка по execution_id среди отфильтрованных строк."""
    filtered = [r for r in rows if _image_log_row_matches(r)]
    if not filtered:
        return []
    groups = group_logs_by_execution_id(filtered)
    sessions: list[dict[str, Any]] = []
    for eid, start_ts, events in groups:
        last_times = [
            r.get("created_at")
            for r in events
            if isinstance(r.get("created_at"), datetime)
        ]
        last_at = max(last_times) if last_times else None
        sessions.append(
            {
                "execution_id": eid,
                "start_ts": start_ts,
                "last_at": last_at,
                "sample_events": events,
            }
        )
    sessions.sort(
        key=lambda s: s.get("last_at") or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    return sessions


def _image_prompt_preview_from_events(events: list[dict[str, Any]]) -> str:
    for ev in events:
        d = ev.get("details")
        if not isinstance(d, dict):
            continue
        p = _first_non_empty(
            d,
            (
                "query_preview",
                "user_text",
                "message_text",
                "original_prompt",
                "prompt",
                "text",
                "image_prompt",
            ),
        )
        if p and str(p).strip():
            s = str(p).strip()
            if len(s) > _IMAGE_PROMPT_PREVIEW_MAX:
                return s[: _IMAGE_PROMPT_PREVIEW_MAX - 1] + "…"
            return s
    return ""


def _image_extract_prompts_from_events(
    events: list[dict[str, Any]],
) -> dict[str, str | None]:
    original: str | None = None
    enhanced: str | None = None
    image_prompt: str | None = None
    negative: str | None = None
    for ev in events:
        d = ev.get("details")
        if not isinstance(d, dict):
            continue
        stg = str(ev.get("stage") or "").strip().lower()
        if original is None:
            for key in (
                "user_text",
                "message_text",
                "query_preview",
                "original_prompt",
                "prompt",
                "text",
            ):
                v = d.get(key)
                if isinstance(v, str) and v.strip():
                    original = v.strip()
                    break
        if stg == "image_text_enhancement_done":
            v = d.get("enhanced_prompt")
            if isinstance(v, str) and v.strip():
                enhanced = v.strip()
        elif stg == "image_prompt_refinement_done":
            for key in ("image_prompt", "rewritten_prompt"):
                v = d.get(key)
                if isinstance(v, str) and v.strip():
                    image_prompt = v.strip()
                    break
        else:
            if enhanced is None:
                v = d.get("enhanced_prompt")
                if isinstance(v, str) and v.strip():
                    enhanced = v.strip()
            if image_prompt is None:
                for key in ("image_prompt", "rewritten_prompt", "final_prompt"):
                    v = d.get(key)
                    if isinstance(v, str) and v.strip():
                        image_prompt = v.strip()
                        break
        v = d.get("negative_prompt")
        if isinstance(v, str) and v.strip():
            negative = v.strip()
    return {
        "original": original,
        "enhanced": enhanced,
        "image_prompt": image_prompt,
        "negative": negative,
    }


def _image_details_collect_paths(details: dict[str, Any]) -> list[str]:
    raw: list[str] = []
    for key in ("image_path", "output_path", "result_path", "file_path", "path"):
        v = details.get(key)
        if isinstance(v, str) and v.strip():
            raw.append(v.strip())
    fl = (
        details.get("files")
        or details.get("generated_files")
        or details.get("output_images")
        or details.get("image_paths")
    )
    if isinstance(fl, list):
        for x in fl:
            if isinstance(x, str) and x.strip():
                raw.append(x.strip())
            elif isinstance(x, dict):
                p = x.get("path") or x.get("file") or x.get("filename")
                if isinstance(p, str) and p.strip():
                    raw.append(p.strip())
    seen: set[str] = set()
    out: list[str] = []
    for p in raw:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def _image_collect_assets_from_events(
    events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    assets: list[dict[str, Any]] = []
    seen_keys: set[str] = set()

    def _append_asset(rec: dict[str, Any]) -> None:
        p = str(rec.get("path") or "").strip()
        asset_ref = str(rec.get("asset_ref") or "").strip()
        if not p and not asset_ref:
            return
        if p:
            pl = p.lower().replace("\\", "/")
            if not (
                any(pl.endswith(sfx) for sfx in _IMAGE_FILE_SUFFIXES)
                or "/outputs/" in pl
                or "/storage/assets/" in pl
            ):
                return
        key = p or f"asset_ref:{asset_ref}"
        if key in seen_keys:
            return
        seen_keys.add(key)
        assets.append(rec)

    for ev in events:
        d = ev.get("details")
        if not isinstance(d, dict):
            continue
        for key in ("output_images", "generated_files", "image_paths"):
            fl = d.get(key)
            if not isinstance(fl, list):
                continue
            for x in fl:
                if isinstance(x, dict):
                    p = str(x.get("path") or "").strip()
                    aref = str(
                        x.get("asset_ref")
                        or x.get("asset_key")
                        or x.get("relative_path")
                        or d.get("asset_ref")
                        or ""
                    ).strip()
                    if not p and not aref:
                        continue
                    url_raw = x.get("provider_url") or x.get("url")
                    url_s = str(url_raw).strip() if url_raw else ""
                    _append_asset(
                        {
                            "path": p,
                            "asset_ref": aref or None,
                            "filename": x.get("filename"),
                            "provider_url": url_s or None,
                            "size": x.get("size"),
                            "stage": ev.get("stage"),
                            "created_at": ev.get("created_at"),
                        }
                    )
                elif isinstance(x, str) and x.strip():
                    _append_asset(
                        {
                            "path": x.strip(),
                            "stage": ev.get("stage"),
                            "created_at": ev.get("created_at"),
                        }
                    )
        for p in _image_details_collect_paths(d):
            pl = p.lower().replace("\\", "/")
            if (
                any(pl.endswith(sfx) for sfx in _IMAGE_FILE_SUFFIXES)
                or "/outputs/" in pl
                or "/storage/assets/" in pl
            ):
                _append_asset(
                    {
                        "path": p,
                        "asset_ref": str(d.get("asset_ref") or "").strip() or None,
                        "stage": ev.get("stage"),
                        "created_at": ev.get("created_at"),
                    }
                )
    return assets


def _image_generation_count_hint(events: list[dict[str, Any]], n_assets: int) -> int:
    for ev in reversed(events):
        d = ev.get("details")
        if not isinstance(d, dict):
            continue
        for key in ("generation_count", "n_images", "images_count", "count"):
            v = d.get(key)
            if v is not None:
                try:
                    return max(int(v), n_assets)
                except (TypeError, ValueError):
                    pass
    return n_assets


def _safe_image_http_url(url: str | None) -> str | None:
    if not url or not str(url).strip():
        return None
    u = str(url).strip()
    low = u.lower()
    if low.startswith("https://") or low.startswith("http://"):
        return u
    return None


def _image_text_stage_token_totals(
    events: list[dict[str, Any]],
) -> tuple[int, int, int | None]:
    tin = 0
    tout = 0
    totals: list[int] = []
    for ev in events:
        stg = str(ev.get("stage") or "").strip().lower()
        if stg not in ("image_text_enhancement_done", "image_prompt_refinement_done"):
            continue
        d = ev.get("details")
        if not isinstance(d, dict):
            continue
        if "input_tokens" in d:
            try:
                tin += int(float(d["input_tokens"]))
            except (TypeError, ValueError):
                pass
        if "output_tokens" in d:
            try:
                tout += int(float(d["output_tokens"]))
            except (TypeError, ValueError):
                pass
        if "total_tokens" in d:
            try:
                totals.append(int(float(d["total_tokens"])))
            except (TypeError, ValueError):
                pass
    tsum: int | None = sum(totals) if totals else None
    return tin, tout, tsum


def _image_text_stage_latencies_ms(
    events: list[dict[str, Any]],
) -> tuple[int | None, int | None]:
    enh: int | None = None
    ref: int | None = None
    for ev in events:
        d = ev.get("details")
        if not isinstance(d, dict):
            continue
        stg = str(ev.get("stage") or "").strip().lower()
        if stg == "image_text_enhancement_done":
            v = d.get("enhancement_latency_ms")
            if v is not None:
                try:
                    enh = int(float(v))
                except (TypeError, ValueError):
                    pass
        elif stg == "image_prompt_refinement_done":
            v = d.get("refinement_latency_ms")
            if v is not None:
                try:
                    ref = int(float(v))
                except (TypeError, ValueError):
                    pass
    return enh, ref


def _image_provider_stage_usage(
    events: list[dict[str, Any]],
) -> dict[str, Any] | None:
    for ev in events:
        if str(ev.get("stage") or "").strip().lower() != "image_provider_done":
            continue
        d = ev.get("details")
        if not isinstance(d, dict):
            continue
        out: dict[str, Any] = {
            "provider": d.get("provider"),
            "model": d.get("model"),
            "duration_ms": d.get("duration_ms"),
        }
        for k in (
            "input_tokens",
            "output_tokens",
            "total_tokens",
            "image_tokens",
            "cost_usd",
        ):
            if k in d and d.get(k) is not None:
                out[k] = d[k]
        if isinstance(d.get("usage"), dict):
            out["usage"] = d["usage"]
        return out
    return None


def _format_token_usage_line(
    tin: int, tout: int, ttot: int | None, *, empty: str = "н/д"
) -> str:
    if not tin and not tout and ttot is None:
        return empty
    if ttot is None:
        ttot = tin + tout
    return f"{tin} in · {tout} out · {ttot} Σ"


def _format_image_provider_usage_line(u: dict[str, Any] | None) -> str:
    if not u:
        return "н/д"
    parts: list[str] = []
    prov = str(u.get("provider") or "").strip()
    model = str(u.get("model") or "").strip()
    if prov or model:
        parts.append(f"{prov or '—'} / {model or '—'}")
    dur = u.get("duration_ms")
    if dur is not None:
        try:
            parts.append(f"{int(float(dur))} мс")
        except (TypeError, ValueError):
            pass
    tok_bits: list[str] = []
    for label, key in (
        ("in", "input_tokens"),
        ("out", "output_tokens"),
        ("Σ", "total_tokens"),
        ("img", "image_tokens"),
    ):
        if key not in u:
            continue
        try:
            tok_bits.append(f"{label} {int(float(u[key]))}")
        except (TypeError, ValueError):
            continue
    if u.get("cost_usd") is not None:
        try:
            tok_bits.append(f"${float(u['cost_usd']):.4f}")
        except (TypeError, ValueError):
            pass
    if tok_bits:
        parts.append(", ".join(tok_bits))
    elif not parts:
        return "н/д"
    return " · ".join(parts)


def _safe_resolved_asset_path(path_str: str | None) -> Path | None:
    """
    Безопасный путь к asset-файлу.
    Разрешает:
    - корень проекта (legacy outputs/...)
    - configured ASSET_STORAGE_DIR (новый AssetRepository layout)
    """
    if not path_str or not str(path_str).strip():
        return None
    try:
        raw = str(path_str).strip()
        p = Path(raw)
        if not p.is_absolute():
            p = (ROOT / p).resolve()
        else:
            p = p.resolve()
        allowed_roots: list[Path] = [ROOT.resolve()]
        try:
            cfg = load_config()
            cfg_asset = Path(cfg.asset_storage_dir)
            if not cfg_asset.is_absolute():
                cfg_asset = (ROOT / cfg_asset).resolve()
            else:
                cfg_asset = cfg_asset.resolve()
            if cfg_asset not in allowed_roots:
                allowed_roots.append(cfg_asset)
        except Exception:
            # Keep legacy behavior if config cannot be read.
            pass

        in_allowed_root = False
        for ar in allowed_roots:
            try:
                p.relative_to(ar)
                in_allowed_root = True
                break
            except ValueError:
                continue
        if not in_allowed_root:
            return None
        if p.is_file():
            return p
    except (OSError, ValueError, RuntimeError):
        return None
    return None


@st.cache_resource
def _asset_repository_ui() -> Any:
    try:
        return create_asset_repository(load_config())
    except Exception:
        return None


def _safe_resolved_asset_ref(asset_ref: str | None) -> Path | None:
    if not asset_ref or not str(asset_ref).strip():
        return None
    repo = _asset_repository_ui()
    if repo is None:
        return None
    try:
        p = repo.resolve_path(str(asset_ref).strip())
        if isinstance(p, Path) and p.is_file():
            return p
    except Exception:
        return None
    return None


def _render_image_generation_summary_html(
    *,
    execution_id: str,
    events: list[dict[str, Any]],
    assets: list[dict[str, Any]],
) -> None:
    status_s = _logs_session_final_status(events)
    pm = _logs_session_provider_model(events)
    lat = _logs_session_max_step_latency_ms(events)
    wall = _logs_session_wall_duration_ms(events)
    n_ev = len(events)
    n_files = len(assets)
    n_hint = _image_generation_count_hint(events, n_files)
    pm_line = html.escape(pm) if pm else "—"
    lat_s = f"{lat} мс" if lat is not None else "—"
    tin, tout, ttot_sum = _image_text_stage_token_totals(events)
    text_tok_s = html.escape(
        _format_token_usage_line(tin, tout, ttot_sum, empty="н/д")
    )
    img_usage = _image_provider_stage_usage(events)
    img_usage_s = html.escape(_format_image_provider_usage_line(img_usage))
    enh_ms, ref_ms = _image_text_stage_latencies_ms(events)
    text_lat_parts: list[str] = []
    if enh_ms is not None:
        text_lat_parts.append(f"улучшение {enh_ms} мс")
    if ref_ms is not None:
        text_lat_parts.append(f"refine {ref_ms} мс")
    text_lat_s = (
        html.escape(" · ".join(text_lat_parts)) if text_lat_parts else "—"
    )
    img_dur = None
    if img_usage and img_usage.get("duration_ms") is not None:
        try:
            img_dur = int(float(img_usage["duration_ms"]))
        except (TypeError, ValueError):
            img_dur = None
    img_lat_s = html.escape(f"{img_dur} мс" if img_dur is not None else "—")
    img_tok_line = "н/д"
    if img_usage:
        bits: list[str] = []
        for label, key in (
            ("in", "input_tokens"),
            ("out", "output_tokens"),
            ("Σ", "total_tokens"),
            ("img", "image_tokens"),
        ):
            if key not in img_usage:
                continue
            try:
                bits.append(f"{label} {int(float(img_usage[key]))}")
            except (TypeError, ValueError):
                continue
        if bits:
            img_tok_line = ", ".join(bits)
    img_tok_s = html.escape(img_tok_line)
    total_usage_parts: list[str] = []
    if ttot_sum is not None:
        total_usage_parts.append(f"текст Σ {ttot_sum}")
    if img_usage:
        for key in ("total_tokens", "image_tokens"):
            if key not in img_usage:
                continue
            try:
                total_usage_parts.append(f"изобр. {int(float(img_usage[key]))}")
            except (TypeError, ValueError):
                continue
    total_usage_s = (
        html.escape(" · ".join(total_usage_parts)) if total_usage_parts else "—"
    )
    st.markdown(
        ops_trace_header_html(
            title="Сводка генерации",
            execution_id=execution_id,
            badges_inner_html=f'{get_route_badge("image_generation")} {get_log_status_badge(status_s)}',
            kv_pairs=[
                ("Событий", html.escape(str(n_ev))),
                ("Файлов (обнаружено)", html.escape(str(n_files))),
                ("Оценка генераций", html.escape(str(n_hint))),
                ("Provider / model (последн.)", pm_line),
                ("Этап текста (latency)", text_lat_s),
                ("Этап изображения (latency)", img_lat_s),
                ("Latency (шаг, max)", html.escape(lat_s)),
                (
                    "Длительность (стена)",
                    html.escape(_logs_format_duration_ms(wall)),
                ),
                ("Токены текста (GigaChat)", text_tok_s),
                ("Токены / usage (image API)", img_tok_s),
                ("Провайдер изображения", img_usage_s),
                ("Сводно usage", total_usage_s),
            ],
        ),
        unsafe_allow_html=True,
    )


def _render_prompt_subsection(
    title: str,
    text: str | None,
    *,
    preview_len: int = 320,
    empty_label: str = "—",
) -> None:
    st.markdown(f"**{html.escape(title)}**", unsafe_allow_html=True)
    if not text or not str(text).strip():
        st.markdown(
            f'<p class="panel-footnote muted-path">{html.escape(empty_label)}</p>',
            unsafe_allow_html=True,
        )
        return
    s = str(text).strip()
    if len(s) <= preview_len:
        st.markdown(
            f'<div class="image-prompt-box">{html.escape(s)}</div>',
            unsafe_allow_html=True,
        )
        return
    short = s[: preview_len - 1] + "…"
    st.markdown(
        f'<div class="image-prompt-box">{html.escape(short)}</div>',
        unsafe_allow_html=True,
    )
    with st.expander("Полный текст", expanded=False):
        st.text(s)


def _render_trace_flow_timeline(
    events: list[dict[str, Any]],
    *,
    section_title: str = "События (trace flow)",
) -> None:
    """Компактный вертикальный trace (тот же стиль, что вкладка «Логи»)."""
    st.markdown(ops_timeline_section_title_html(section_title), unsafe_allow_html=True)
    for idx, ev in enumerate(events, 1):
        details = ev.get("details")
        details_dict: dict[str, Any] = details if isinstance(details, dict) else {}
        t_s = _format_dt_moscow_logs(ev.get("created_at"))
        action = _stage_to_action(str(ev.get("stage") or ""), details)
        st_raw = str(ev.get("status") or "")
        sev = infer_event_severity(str(ev.get("stage") or ""), st_raw, details)
        preview = _details_to_description(details, max_len=LOGS_TIMELINE_PREVIEW_MAX)
        badge_html = get_log_status_badge(st_raw)
        st.markdown(
            f'<div class="log-trace-step log-trace-step--{sev}">'
            '<div class="log-trace-step-marker"></div>'
            '<div class="log-trace-step-body">'
            '<div class="log-trace-step-head">'
            f'<span class="log-trace-step-idx">{idx}</span>'
            f'<span class="log-trace-step-time">{html.escape(t_s)}</span>'
            f'<span class="log-trace-step-badges">{badge_html}</span>'
            "</div>"
            f'<div class="log-trace-step-stage">{html.escape(action)}</div>'
            f'<div class="log-trace-step-preview">{html.escape(preview)}</div>'
            "</div>"
            "</div>",
            unsafe_allow_html=True,
        )
        render_metadata_expander("Показать raw details", details_dict, expanded=False)


def get_log_status_badge(status: str | None) -> str:
    """Компактный бейдж статуса (тот же тон, что rag-status-card)."""
    tone = _status_tone(status)
    label = get_russian_status(status)
    return (
        f'<span class="log-status-badge log-status-badge--{tone}">'
        f"{html.escape(label)}</span>"
    )


def _logs_build_session_rows(
    groups: list[tuple[str, datetime | None, list[dict[str, Any]]]],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for eid, start_ts, events in groups:
        last_times = [
            r.get("created_at")
            for r in events
            if isinstance(r.get("created_at"), datetime)
        ]
        last_at = max(last_times) if last_times else None
        out.append(
            {
                "execution_id": eid,
                "start_ts": start_ts,
                "last_at": last_at,
                "events": events,
            }
        )
    return out


def _render_logs_trace_header(session: dict[str, Any]) -> None:
    """Компактный операторский заголовок трассы (правая панель, сверху)."""
    eid = str(session.get("execution_id") or "—")
    events: list[dict[str, Any]] = session.get("events") or []
    if not isinstance(events, list):
        events = []
    last_at = session.get("last_at")
    route_raw = _logs_infer_route_from_events(events)
    status_s = _logs_session_final_status(events)
    n_ev = len(events)
    dur_ms = _logs_session_wall_duration_ms(events)
    pm = _logs_session_provider_model(events)
    flow_ru = _logs_timeline_flow_ru(events)
    pm_line = html.escape(pm) if pm else "—"
    st.markdown(
        ops_trace_header_html(
            title="Трасса execution-сессии",
            execution_id=eid,
            badges_inner_html=f"{get_route_badge(route_raw)} {get_log_status_badge(status_s)}",
            kv_pairs=[
                (
                    "Последняя активность (MSK)",
                    html.escape(_format_dt_moscow_logs(last_at)),
                ),
                ("Событий в трассе", html.escape(str(n_ev))),
                (
                    "Длительность (стена)",
                    html.escape(_logs_format_duration_ms(dur_ms)),
                ),
                ("Provider / model", pm_line),
            ],
        ),
        unsafe_allow_html=True,
    )
    if flow_ru and flow_ru.replace(" → ", "").strip():
        st.markdown(
            f'<div class="logs-trace-flow-compact">{html.escape(flow_ru)}</div>',
            unsafe_allow_html=True,
        )


def _render_logs_timeline_detail(
    session: dict[str, Any],
    *,
    show_session_header: bool = True,
) -> None:
    """Правая панель: заголовок трассы + вертикальный компактный timeline событий."""
    events: list[dict[str, Any]] = session.get("events") or []
    if not isinstance(events, list):
        events = []

    if show_session_header:
        _render_logs_trace_header(session)

    _render_trace_flow_timeline(events, section_title="События (trace flow)")


def _status_tone(raw: str | None) -> str:
    v = (raw or "").strip().lower()
    if v in ("success", "успешно"):
        return "success"
    if v in ("error", "ошибка", "llm_error"):
        return "error"
    if v in ("warning", "low_relevance", "empty_retrieval", "empty_context"):
        return "warning"
    return "muted"


def _rag_fallback_outcome(fallback_reason: str | None) -> tuple[str, str]:
    """Human label + CSS variant (success | warning | error | muted)."""
    fb = (fallback_reason or "none").strip().lower()
    if fb == "none":
        return "Ответ построен по базе знаний", "success"
    if fb == "low_relevance":
        return "Недостаточно релевантных фрагментов", "warning"
    if fb == "empty_retrieval":
        return "Ничего не найдено в индексе", "warning"
    if fb == "empty_context":
        return "Контекст не сформирован", "warning"
    if fb == "llm_error":
        return "Ошибка LLM", "error"
    return fb or "—", "muted"


def _rag_metric_display(val: Any) -> str | int | float:
    if val is None:
        return "—"
    if isinstance(val, (int, float)):
        if isinstance(val, float):
            return round(val, 4)
        return val
    return str(val)


def _rag_chunk_score_str(score_val: Any) -> str:
    if score_val is None:
        return "—"
    try:
        return f"{float(score_val):.3f}"
    except (TypeError, ValueError):
        return "—"


def _rag_quality_compact_html(rq: dict[str, Any]) -> str:
    """HTML for horizontal compact RAG quality strip (full width)."""
    rag_n = int(rq.get("rag_events") or 0)
    if rag_n == 0:
        return (
            '<div class="rag-quality-strip rag-quality-strip--empty">'
            '<span class="rag-quality-strip-title">Качество RAG</span>'
            '<span class="rag-quality-empty">RAG-метрик за период пока нет.</span>'
            "</div>"
        )
    tiles: list[tuple[str, str]] = [
        ("RAG-событий", str(rag_n)),
        ("Low relevance", str(int(rq.get("low_relevance") or 0))),
        ("Empty retrieval", str(int(rq.get("empty_retrieval") or 0))),
        ("LLM errors", str(int(rq.get("llm_error") or 0))),
        (
            "Avg retrieved",
            f"{round(float(rq.get('avg_retrieved_count') or 0), 2)}",
        ),
        (
            "Avg used",
            f"{round(float(rq.get('avg_filtered_count') or 0), 2)}",
        ),
        (
            "Avg context",
            f"{round(float(rq.get('avg_context_chars') or 0), 2)}",
        ),
    ]
    parts: list[str] = [
        '<div class="rag-quality-strip">',
        '<span class="rag-quality-strip-title">Качество RAG</span>',
        '<div class="rag-quality-strip-tiles">',
    ]
    for label, val in tiles:
        esc_l = html.escape(label)
        esc_v = html.escape(val)
        parts.append(
            '<div class="rag-tile">'
            f'<div class="rag-tile-val">{esc_v}</div>'
            f'<div class="rag-tile-lbl">{esc_l}</div>'
            "</div>"
        )
    parts.append("</div></div>")
    return "".join(parts)


def _rag_fragment_card_html(chunk: dict[str, Any]) -> str:
    src = html.escape(str(chunk.get("source") or "unknown"))
    passed = bool(chunk.get("passed_filter"))
    badge_cls = "chunk-badge-success" if passed else "chunk-badge-muted"
    badge_text = html.escape(
        "использован в ответе" if passed else "отфильтрован",
    )
    score_s = html.escape(_rag_chunk_score_str(chunk.get("score")))
    preview = html.escape(str(chunk.get("text_preview") or "—"))
    return (
        f'<div class="rag-frag-card">'
        f'<div class="rag-frag-card-header">'
        f'<span class="rag-frag-source">{src}</span>'
        f'<span class="chunk-badge {badge_cls}">{badge_text}</span>'
        f'<span class="rag-frag-score">score={score_s}</span>'
        f"</div>"
        f'<div class="rag-frag-preview">{preview}</div>'
        f"</div>"
    )


def _rag_inline_metrics_html(ev: dict[str, Any]) -> str:
    items = (
        ("retrieved_count", _rag_metric_display(ev.get("retrieved_count"))),
        ("filtered_count", _rag_metric_display(ev.get("filtered_count"))),
        ("context_chars", _rag_metric_display(ev.get("context_chars"))),
        ("relevance_threshold", _rag_metric_display(ev.get("relevance_threshold"))),
    )
    parts = ['<div class="rag-inline-metrics">']
    for lbl, val in items:
        parts.append(
            '<div class="rag-inline-metric">'
            f'<div class="rag-inline-metric-val">{html.escape(str(val))}</div>'
            f'<div class="rag-inline-metric-lbl">{html.escape(lbl)}</div>'
            "</div>"
        )
    parts.append("</div>")
    return "".join(parts)


def get_paginated_slice(
    items: list[Any],
    page: int,
    page_size: int,
) -> tuple[list[Any], int, int]:
    """Return slice, total_items, total_pages."""
    total_items = len(items)
    total_pages = max(1, math.ceil(total_items / max(1, page_size)))
    page_norm = max(0, min(int(page), total_pages - 1))
    start = page_norm * page_size
    end = start + page_size
    return items[start:end], total_items, total_pages


def reset_invalid_selection(
    items: list[Any],
    selected_state_key: str,
    id_getter: Any,
) -> None:
    selected = str(st.session_state.get(selected_state_key, "")).strip()
    if not selected:
        return
    if not any(str(id_getter(it)) == selected for it in items):
        st.session_state.pop(selected_state_key, None)


def render_pagination_controls(
    state_prefix: str,
    *,
    total_items: int,
    has_next: bool,
    page_size_label: str = "На странице",
) -> tuple[int, int]:
    """Unified compact pagination bar with session_state."""
    page_key = f"{state_prefix}_page"
    size_key = f"{state_prefix}_page_size"
    if size_key not in st.session_state:
        st.session_state[size_key] = 50
    if page_key not in st.session_state:
        st.session_state[page_key] = 0

    prev_size = int(st.session_state[size_key])
    c1, c2, c3, c4 = st.columns((1.2, 1, 1, 2.2))
    with c1:
        page_size = int(
            st.selectbox(
                page_size_label,
                options=(20, 50, 100),
                key=size_key,
                label_visibility="collapsed",
            )
        )
    if page_size != prev_size:
        st.session_state[page_key] = 0

    page = max(0, int(st.session_state[page_key]))
    known_pages = max(1, math.ceil(total_items / max(1, page_size)))
    if page >= known_pages and not has_next:
        page = known_pages - 1
        st.session_state[page_key] = page
    with c2:
        if st.button("← Предыдущая", key=f"{state_prefix}_prev", disabled=page <= 0):
            st.session_state[page_key] = max(0, page - 1)
            st.rerun()
    with c3:
        if st.button("Следующая →", key=f"{state_prefix}_next", disabled=not has_next):
            st.session_state[page_key] = page + 1
            st.rerun()
    with c4:
        pages_text = (
            f"Страница {page + 1} из {known_pages}"
            if not has_next
            else f"Страница {page + 1} из ≥ {max(known_pages, page + 2)}"
        )
        st.caption(pages_text)
    return int(st.session_state[page_key]), page_size


# --- Unified split-layout selection feedback (P4.7.4b) ---
_SPLIT_TOAST_KEYS: dict[str, str] = {
    "text": "split_toast_text",
    "rag": "split_toast_rag",
    "image": "split_toast_image",
    "docs": "split_toast_docs",
    "logs": "split_toast_logs",
}


def show_split_selection_toast(tab_key: str) -> None:
    sk = _SPLIT_TOAST_KEYS.get(tab_key)
    if sk and st.session_state.pop(sk, False):
        st.toast("Открыто справа")


def flag_split_selection_toast(tab_key: str) -> None:
    sk = _SPLIT_TOAST_KEYS.get(tab_key)
    if sk:
        st.session_state[sk] = True


def render_split_pane_titles(*, list_title: str, detail_title: str) -> None:
    """Заголовки над колонками списка и деталей (35/65)."""
    t1, t2 = st.columns(OPS_SPLIT_COLUMNS_RATIO)
    with t1:
        st.markdown(f"**{list_title}**")
    with t2:
        st.markdown(f"**{detail_title}**")


def split_open_button_label(is_selected: bool) -> str:
    return "Открыто" if is_selected else "Открыть"


def render_split_selected_summary(
    *,
    short_id: str,
    status_line: str,
    route_or_type_html: str,
    timestamp: str,
    preview: str,
    preview_max: int = 220,
) -> None:
    """
    Компактная сводка выбранной сущности над деталями (правая панель).
    ``route_or_type_html`` — готовый HTML (бейджи), остальное экранируется.
    """
    pv = (preview or "").strip()
    if len(pv) > preview_max:
        pv = pv[: preview_max - 1] + "…"
    safe_preview = html.escape(pv) if pv else "—"
    st.markdown(
        '<div class="split-detail-summary">'
        '<div class="split-detail-summary-title">Выбрано</div>'
        '<div class="split-detail-summary-row">'
        '<span class="split-detail-k">id</span> '
        f'<span class="split-detail-v"><code>{html.escape(short_id)}</code></span>'
        "</div>"
        '<div class="split-detail-summary-row">'
        '<span class="split-detail-k">статус</span> '
        f'<span class="split-detail-v">{html.escape(status_line)}</span>'
        "</div>"
        '<div class="split-detail-summary-row split-detail-badges">'
        '<span class="split-detail-k">маршрут / тип</span> '
        f'<span class="split-detail-v">{route_or_type_html}</span>'
        "</div>"
        '<div class="split-detail-summary-row">'
        '<span class="split-detail-k">время</span> '
        f'<span class="split-detail-v">{html.escape(timestamp)}</span>'
        "</div>"
        '<div class="split-detail-summary-row split-detail-preview">'
        '<span class="split-detail-k">превью</span> '
        f'<span class="split-detail-v">{safe_preview}</span>'
        "</div>"
        "</div>",
        unsafe_allow_html=True,
    )


def _first_non_empty(details: dict[str, Any], keys: tuple[str, ...]) -> str:
    for k in keys:
        v = details.get(k)
        if v is None:
            continue
        s = str(v).strip()
        if s:
            return s
    return ""


def _text_inline_metrics_html(details: dict[str, Any]) -> str:
    provider = _first_non_empty(details, ("provider", "llm_provider")) or "—"
    model = _first_non_empty(details, ("model", "model_name", "llm_model")) or "—"
    in_tok = _first_non_empty(
        details, ("input_tokens", "prompt_tokens", "tokens_input")
    ) or "—"
    out_tok = _first_non_empty(
        details, ("output_tokens", "completion_tokens", "tokens_output")
    ) or "—"
    total_tok = _first_non_empty(details, ("total_tokens", "tokens_total")) or "—"
    latency = _first_non_empty(details, ("latency_ms", "duration_ms", "elapsed_ms")) or "—"
    items = (
        ("provider", provider),
        ("model", model),
        ("input_tokens", in_tok),
        ("output_tokens", out_tok),
        ("total_tokens", total_tok),
        ("latency_ms", latency),
    )
    parts = ['<div class="rag-inline-metrics">']
    for lbl, val in items:
        parts.append(
            '<div class="rag-inline-metric">'
            f'<div class="rag-inline-metric-val">{html.escape(str(val))}</div>'
            f'<div class="rag-inline-metric-lbl">{html.escape(lbl)}</div>'
            "</div>"
        )
    parts.append("</div>")
    return "".join(parts)


def _build_text_requests_from_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        eid = str(r.get("execution_id") or "").strip()
        if not eid:
            continue
        grouped.setdefault(eid, []).append(r)

    out: list[dict[str, Any]] = []
    for eid, events in grouped.items():
        ordered = sorted(
            events,
            key=lambda x: x.get("created_at")
            if isinstance(x.get("created_at"), datetime)
            else datetime.min,
        )
        latest = ordered[-1] if ordered else {}
        last_at = latest.get("created_at")

        preview = ""
        for ev in ordered:
            details = ev.get("details")
            details_dict = details if isinstance(details, dict) else {}
            if str(ev.get("stage") or "") == "intake_received":
                preview = _first_non_empty(
                    details_dict,
                    ("message_preview", "text", "query_preview"),
                )
                if preview:
                    break
        if not preview:
            for ev in ordered:
                details = ev.get("details")
                details_dict = details if isinstance(details, dict) else {}
                preview = _first_non_empty(
                    details_dict,
                    ("message_preview", "text", "query_preview"),
                )
                if preview:
                    break
        if not preview:
            preview = "Текстовый запрос"

        final_event = None
        for ev in reversed(ordered):
            if str(ev.get("stage") or "") == "processing_done":
                final_event = ev
                break
        if final_event is None and ordered:
            final_event = ordered[-1]
        final_status = str((final_event or {}).get("status") or "—")
        route_norm = "text"
        for ev in reversed(ordered):
            details = ev.get("details")
            details_dict = details if isinstance(details, dict) else {}
            route_candidate = normalize_route(str(details_dict.get("route") or ""))
            if route_candidate != "unknown":
                route_norm = route_candidate
                break

        out.append(
            {
                "execution_id": eid,
                "last_at": last_at,
                "preview": preview,
                "status": final_status,
                "route": route_norm,
                "events": ordered,
            }
        )

    out.sort(
        key=lambda x: x.get("last_at")
        if isinstance(x.get("last_at"), datetime)
        else datetime.min,
        reverse=True,
    )
    return out


def _render_rag_event_detail(ev: dict[str, Any]) -> None:
    """Master-detail right pane for one selected RAG event."""
    details = ev.get("details")
    details_dict: dict[str, Any] = details if isinstance(details, dict) else {}
    fb_reason = str(
        details_dict.get("fallback_reason")
        or ev.get("fallback_reason")
        or "none",
    )
    qp = str(
        details_dict.get("query_preview")
        or ev.get("query_preview")
        or "—",
    )

    answer_text = str(
        details_dict.get("answer_text")
        or details_dict.get("answer_preview")
        or details_dict.get("answer")
        or details_dict.get("response_text")
        or ""
    ).strip()
    q_col, a_col = st.columns(2)
    with q_col:
        st.markdown(
            '<p class="rag-section-label">Что спросил пользователь</p>',
            unsafe_allow_html=True,
        )
        st.markdown(
            '<div class="rag-top-card">'
            f'<div class="rag-top-card-text">{html.escape(qp)}</div>'
            "</div>",
            unsafe_allow_html=True,
        )
    with a_col:
        st.markdown(
            '<p class="rag-section-label">Что ответила система</p>',
            unsafe_allow_html=True,
        )
        answer_view = (
            answer_text
            if answer_text
            else "Ответ не сохранён для этого события."
        )
        st.markdown(
            '<div class="rag-top-card">'
            f'<div class="rag-top-card-text">{html.escape(answer_view)}</div>'
            "</div>",
            unsafe_allow_html=True,
        )

    outcome_msg, outcome_variant = _rag_fallback_outcome(fb_reason)
    st.markdown(
        '<p class="rag-section-label">Итог обработки</p>',
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<div class="rag-status-card rag-status-card--{outcome_variant}">'
        f"{html.escape(outcome_msg)}</div>",
        unsafe_allow_html=True,
    )

    st.markdown(
        '<p class="rag-section-label">Ключевые метрики</p>',
        unsafe_allow_html=True,
    )
    st.markdown(
        _rag_inline_metrics_html(ev),
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div class="rag-section-title">Источники ответа</div>',
        unsafe_allow_html=True,
    )
    raw_chunks = details_dict.get("retrieved_chunks")
    retrieved_chunks: list[dict[str, Any]] = []
    if isinstance(raw_chunks, list):
        retrieved_chunks = [c for c in raw_chunks if isinstance(c, dict)]
    used_chunks = [c for c in retrieved_chunks if c.get("passed_filter")]
    dropped_chunks = [c for c in retrieved_chunks if not c.get("passed_filter")]

    if not retrieved_chunks:
        st.caption("Фрагменты не сохранены для этого события.")
    else:
        st.markdown(
            '<p class="rag-section-label">Использованы в ответе</p>',
            unsafe_allow_html=True,
        )
        if not used_chunks:
            st.caption("Нет фрагментов, прошедших порог релевантности.")
        else:
            for idx, ch in enumerate(used_chunks, 1):
                src = str(ch.get("source") or "unknown")
                score_s = _rag_chunk_score_str(ch.get("score"))
                title_ch = f"✅ {src} · score={score_s}"
                preview = str(ch.get("text_preview") or "—")
                with st.expander(title_ch, expanded=False):
                    meta_col, text_col = st.columns((0.38, 0.62))
                    with meta_col:
                        st.markdown(
                            '<div class="rag-frag-meta-card">'
                            f'<div class="rag-frag-meta-line"><b>source:</b> {html.escape(src)}</div>'
                            f'<div class="rag-frag-meta-line"><b>score:</b> {html.escape(score_s)}</div>'
                            '<div class="rag-frag-meta-line"><b>статус:</b> '
                            '<span class="chunk-badge chunk-badge-success">использован</span></div>'
                            '<div class="rag-frag-meta-line"><b>passed_filter:</b> true</div>'
                            f'<div class="rag-frag-meta-line"><b>rank:</b> {idx}</div>'
                            "</div>",
                            unsafe_allow_html=True,
                        )
                    with text_col:
                        st.markdown(
                            '<div class="rag-frag-text-card">'
                            f"<p>{html.escape(preview)}</p>"
                            "</div>",
                            unsafe_allow_html=True,
                        )
        st.markdown(
            '<p class="rag-section-label">Отфильтрованы</p>',
            unsafe_allow_html=True,
        )
        if not dropped_chunks:
            st.caption("Отфильтрованных фрагментов нет.")
        else:
            for idx, ch in enumerate(dropped_chunks, 1):
                src = str(ch.get("source") or "unknown")
                score_s = _rag_chunk_score_str(ch.get("score"))
                title_ch = f"⚪ {src} · score={score_s}"
                preview = str(ch.get("text_preview") or "—")
                with st.expander(title_ch, expanded=False):
                    meta_col, text_col = st.columns((0.38, 0.62))
                    with meta_col:
                        st.markdown(
                            '<div class="rag-frag-meta-card">'
                            f'<div class="rag-frag-meta-line"><b>source:</b> {html.escape(src)}</div>'
                            f'<div class="rag-frag-meta-line"><b>score:</b> {html.escape(score_s)}</div>'
                            '<div class="rag-frag-meta-line"><b>статус:</b> '
                            '<span class="chunk-badge chunk-badge-muted">отфильтрован</span></div>'
                            '<div class="rag-frag-meta-line"><b>passed_filter:</b> false</div>'
                            f'<div class="rag-frag-meta-line"><b>rank:</b> {idx}</div>'
                            "</div>",
                            unsafe_allow_html=True,
                        )
                    with text_col:
                        st.markdown(
                            '<div class="rag-frag-text-card">'
                            f"<p>{html.escape(preview)}</p>"
                            "</div>",
                            unsafe_allow_html=True,
                        )

    st.markdown(
        '<p class="rag-section-title">Технические детали</p>',
        unsafe_allow_html=True,
    )
    render_metadata_expander("Показать JSON", details_dict, expanded=False)

    eid_footer = html.escape(str(ev.get("execution_id") or "—"))
    st.markdown(
        f'<div class="rag-exec-footer">execution_id: {eid_footer}</div>',
        unsafe_allow_html=True,
    )


def _render_text_event_detail(ev: dict[str, Any]) -> None:
    details = ev.get("details")
    details_dict: dict[str, Any] = details if isinstance(details, dict) else {}
    prompt = _first_non_empty(
        details_dict, ("query_preview", "prompt", "user_prompt", "text", "input_text")
    ) or "Запрос не сохранён для этого события."
    answer = _first_non_empty(
        details_dict,
        ("answer_text", "answer", "response_text", "result_text", "output_text"),
    ) or "Ответ пока не сохраняется для text_response"
    status_text = _status_label(str(ev.get("status") or ""))
    status_cls = _status_tone(str(ev.get("status") or ""))

    p_col, a_col = st.columns(2)
    with p_col:
        st.markdown(
            '<p class="rag-section-label">Что спросил пользователь</p>',
            unsafe_allow_html=True,
        )
        st.markdown(
            '<div class="rag-top-card">'
            f'<div class="rag-top-card-text">{html.escape(prompt)}</div>'
            "</div>",
            unsafe_allow_html=True,
        )
    with a_col:
        st.markdown(
            '<p class="rag-section-label">Что ответила система</p>',
            unsafe_allow_html=True,
        )
        st.markdown(
            '<div class="rag-top-card">'
            f'<div class="rag-top-card-text">{html.escape(answer)}</div>'
            "</div>",
            unsafe_allow_html=True,
        )

    st.markdown('<p class="rag-section-label">Итог обработки</p>', unsafe_allow_html=True)
    st.markdown(
        f'<div class="rag-status-card rag-status-card--{status_cls}">'
        f"{html.escape(status_text)}</div>",
        unsafe_allow_html=True,
    )
    st.markdown('<p class="rag-section-label">Ключевые метрики</p>', unsafe_allow_html=True)
    st.markdown(_text_inline_metrics_html(details_dict), unsafe_allow_html=True)

    st.markdown('<p class="rag-section-title">Технические детали</p>', unsafe_allow_html=True)
    render_metadata_expander("Показать JSON", details_dict, expanded=False)

    eid_footer = html.escape(str(ev.get("execution_id") or "—"))
    st.markdown(
        f'<div class="rag-exec-footer">execution_id: {eid_footer}</div>',
        unsafe_allow_html=True,
    )


def _render_text_request_detail(req: dict[str, Any]) -> None:
    events = req.get("events")
    event_list: list[dict[str, Any]] = events if isinstance(events, list) else []
    final_ev = event_list[-1] if event_list else {}
    _render_text_event_detail(final_ev)

    st.markdown('<p class="rag-section-title">Цепочка событий</p>', unsafe_allow_html=True)
    if not event_list:
        st.caption("События не найдены.")
        return
    chain_rows = []
    for ev in event_list:
        chain_rows.append(
            {
                "время": _format_dt_moscow_logs(ev.get("created_at")),
                "этап": _stage_to_action(
                    str(ev.get("stage") or ""), ev.get("details")
                ),
                "status": _status_label(str(ev.get("status") or "")),
                "details": _details_to_description(ev.get("details"), max_len=400),
            }
        )
    st.dataframe(pd.DataFrame(chain_rows), use_container_width=True, hide_index=True)


def _inject_theme_css() -> None:
    st.markdown(
        """
        <style>
        :root {
          --bg-main: #0B1220;
          --bg-card: #0F172A;
          --bg-elevated: #111827;
          --border: #1F2A44;
          --text-primary: #E5E7EB;
          --text-secondary: #9CA3AF;
          --text-muted: #9CA3AF;
          --accent: #22C55E;
          --success: #22C55E;
          --muted: #9CA3AF;
          --warning: #F59E0B;
          --error: #EF4444;
        }

        body, .stApp {
          background-color: var(--bg-main) !important;
          color: var(--text-primary) !important;
        }

        [data-testid="stAppViewContainer"],
        [data-testid="stMain"],
        [data-testid="stHeader"] {
          background: var(--bg-main) !important;
        }
        .main .block-container {
          padding-top: 0.02rem !important;
          padding-bottom: 0.6rem !important;
          max-width: 100% !important;
        }
        [data-testid="stVerticalBlock"] {
          gap: 0.2rem !important;
        }
        .compact-title {
          margin: 0 !important;
          padding: 0 !important;
        }
        .compact-subtitle {
          margin: 0 !important;
          font-size: 0.8rem !important;
          color: var(--text-secondary) !important;
        }
        .topbar-box {
          background: #0B1220;
          border: none;
          border-radius: 10px;
          padding: 8px 10px;
          margin: 0 0 6px 0;
          position: static;
          top: auto;
          z-index: auto;
          backdrop-filter: none;
          box-shadow: none;
        }
        .topbar-box [data-testid="column"] {
          display: flex;
          align-items: center;
        }
        .topbar-box [data-testid="stHorizontalBlock"] {
          align-items: center;
        }
        .topbar-title-wrap {
          display: flex;
          flex-direction: row;
          justify-content: center;
          align-items: center;
          gap: 10px;
          min-width: 0;
          white-space: nowrap;
        }
        .topbar-app-title {
          font-size: 1.02rem;
          font-weight: 700;
          color: var(--accent) !important;
          line-height: 1.25;
          margin: 0;
        }
        .topbar-db-path {
          font-size: 0.77rem;
          color: var(--text-secondary) !important;
          overflow: hidden;
          text-overflow: ellipsis;
        }
        .topbar-updated {
          font-size: 0.76rem;
          color: var(--text-secondary) !important;
          text-align: right;
          margin-top: 0;
          white-space: nowrap;
        }
        h1 { margin-top: 0 !important; margin-bottom: 0.05rem !important; }
        h2, h3 {
          margin-top: 0.28rem !important;
          margin-bottom: 0.2rem !important;
        }
        [data-testid="stCaptionContainer"] {
          margin-top: 0 !important;
          margin-bottom: 0.1rem !important;
        }
        .stTabs {
          margin-top: 0.05rem !important;
          position: static !important;
          top: auto !important;
          z-index: auto !important;
          background: var(--bg-main);
          padding-top: 0;
          border-bottom: none;
        }
        .stTabs [data-baseweb="tab-list"] {
          background: var(--bg-main) !important;
        }

        h1, h2, h3 {
          color: var(--accent) !important;
          font-weight: 650 !important;
        }

        p, span, label, div, .stMarkdown, [data-testid="stMarkdownContainer"] p {
          color: var(--text-primary);
        }
        .stCaption, [data-testid="stCaptionContainer"], small {
          color: var(--text-secondary) !important;
        }

        div[data-testid="stMetric"],
        div[data-testid="stDataFrame"],
        div[data-testid="stExpander"],
        div[data-testid="stAlert"],
        div[data-testid="stCodeBlock"],
        [data-testid="stJson"] {
          background: var(--bg-card) !important;
          border: 1px solid var(--border) !important;
          border-radius: 12px;
          padding: 10px;
          margin-bottom: 6px;
        }

        div[data-testid="stMetric"] label,
        div[data-testid="stMetricValue"] * {
          color: var(--text-primary) !important;
        }

        div[data-testid="stDataFrame"] [role="grid"],
        div[data-testid="stDataFrame"] [role="grid"] * {
          color: var(--text-primary) !important;
          border-color: var(--border) !important;
          background: var(--bg-card) !important;
        }

        div[data-testid="stDataFrame"] {
          background: var(--bg-card) !important;
        }

        /* Selectbox + input + textarea + json/code area shell */
        [data-baseweb="select"] > div,
        [data-baseweb="base-input"] > div,
        [data-baseweb="textarea"] > div,
        .stTextInput input,
        .stTextArea textarea,
        .stSelectbox [data-baseweb="select"] > div {
          background: var(--bg-elevated) !important;
          color: var(--text-primary) !important;
          border: 1px solid var(--border) !important;
        }

        .stTextInput input::placeholder,
        .stTextArea textarea::placeholder {
          color: var(--text-secondary) !important;
        }

        .stSelectbox label,
        .stTextInput label,
        .stTextArea label {
          color: var(--text-secondary) !important;
        }

        [data-baseweb="popover"] *,
        [role="listbox"] * {
          background: var(--bg-elevated) !important;
          color: var(--text-primary) !important;
          border-color: var(--border) !important;
        }

        .stExpander {
          background: var(--bg-card) !important;
          border: 1px solid var(--border) !important;
          border-radius: 12px !important;
        }
        .stExpander details,
        .stExpander summary {
          background: var(--bg-card) !important;
          color: var(--text-primary) !important;
        }

        pre, code, [data-testid="stCodeBlock"] pre, [data-testid="stJson"] pre {
          background: var(--bg-elevated) !important;
          color: var(--text-primary) !important;
          border: 1px solid var(--border) !important;
        }

        .stButton > button {
          background: var(--accent) !important;
          color: #04120a !important;
          border-radius: 8px !important;
          border: 1px solid var(--accent) !important;
          font-weight: 600 !important;
          min-height: 2rem !important;
          padding: 0.2rem 0.8rem !important;
        }
        .stButton > button:hover {
          filter: brightness(1.1);
        }

        .status-success { color: var(--success); font-weight: 600; }
        .status-error { color: var(--error); font-weight: 600; }
        .status-warning { color: var(--warning); font-weight: 600; }
        .status-muted { color: var(--muted); font-weight: 600; }

        .chunk-badge {
          display: inline-block;
          padding: 2px 10px;
          border-radius: 999px;
          font-size: 12px;
          font-weight: 700;
          line-height: 1.4;
          border: 1px solid transparent;
        }
        .chunk-badge-success {
          color: var(--success);
          background: rgba(34, 197, 94, 0.16);
          border-color: var(--success);
        }
        .chunk-badge-muted {
          color: var(--muted);
          background: rgba(100, 116, 139, 0.18);
          border-color: var(--muted);
        }
        .json-dark pre {
          background: #0F172A !important;
          color: #E5E7EB !important;
          border: 1px solid #1F2A44 !important;
          border-radius: 10px !important;
        }

        .rag-section-label {
          font-size: 0.8rem;
          text-transform: uppercase;
          letter-spacing: 0.04em;
          color: var(--text-secondary) !important;
          margin: 0 0 6px 0;
          font-weight: 600;
        }
        .rag-section-title {
          font-size: 1rem;
          font-weight: 600;
          color: var(--text-primary) !important;
          margin: 20px 0 10px 0;
        }
        .rag-query-block {
          background: var(--bg-elevated);
          border: 1px solid var(--border);
          border-radius: 12px;
          padding: 16px 18px;
          margin-bottom: 8px;
        }
        .rag-query-preview {
          font-size: 1.2rem;
          line-height: 1.45;
          color: var(--text-primary) !important;
          font-weight: 500;
        }
        .rag-top-card {
          background: var(--bg-elevated);
          border: 1px solid var(--border);
          border-radius: 12px;
          padding: 14px 16px;
          min-height: 120px;
          max-height: 220px;
          overflow: auto;
          margin-bottom: 8px;
          box-sizing: border-box;
        }
        .rag-top-card-text {
          color: var(--text-primary) !important;
          font-size: 0.98rem;
          line-height: 1.42;
          white-space: pre-wrap;
          word-break: break-word;
        }
        .rag-status-card {
          border-radius: 12px;
          padding: 10px 14px;
          margin: 6px 0 10px 0;
          font-size: 0.95rem;
          font-weight: 600;
          border: 1px solid var(--border);
        }
        .rag-status-card--success {
          color: var(--success) !important;
          background: rgba(34, 197, 94, 0.12);
          border-color: rgba(34, 197, 94, 0.45);
        }
        .rag-status-card--warning {
          color: var(--warning) !important;
          background: rgba(245, 158, 11, 0.12);
          border-color: rgba(245, 158, 11, 0.45);
        }
        .rag-status-card--error {
          color: var(--error) !important;
          background: rgba(239, 68, 68, 0.12);
          border-color: rgba(239, 68, 68, 0.45);
        }
        .rag-status-card--muted {
          color: var(--muted) !important;
          background: rgba(100, 116, 139, 0.12);
          border-color: var(--border);
        }
        .rag-frag-card {
          background: var(--bg-elevated);
          border: 1px solid var(--border);
          border-radius: 12px;
          padding: 12px 14px;
          margin-bottom: 10px;
        }
        .rag-frag-card-header {
          display: flex;
          flex-wrap: wrap;
          align-items: center;
          gap: 8px 12px;
          margin-bottom: 8px;
        }
        .rag-frag-source {
          font-weight: 600;
          color: var(--text-primary) !important;
          flex: 1 1 auto;
          min-width: 120px;
        }
        .rag-frag-score {
          font-size: 0.85rem;
          color: var(--text-secondary) !important;
          font-variant-numeric: tabular-nums;
        }
        .rag-frag-preview {
          font-size: 0.9rem;
          line-height: 1.45;
          color: var(--text-secondary) !important;
        }
        .rag-frag-meta-card {
          background: var(--bg-elevated);
          border: 1px solid var(--border);
          border-radius: 10px;
          padding: 10px 12px;
          margin-bottom: 8px;
        }
        .rag-frag-meta-line {
          font-size: 0.84rem;
          line-height: 1.35;
          color: var(--text-primary) !important;
          margin-bottom: 4px;
          word-break: break-word;
        }
        .rag-frag-text-card {
          background: var(--bg-elevated);
          border: 1px solid var(--border);
          border-radius: 10px;
          padding: 10px 12px;
          max-height: 220px;
          overflow-y: auto;
          overflow-x: hidden;
        }
        .rag-frag-text-card p {
          margin: 0;
          font-size: 0.92rem;
          line-height: 1.42;
          color: var(--text-secondary) !important;
          white-space: pre-wrap;
          word-break: break-word;
        }
        .rag-exec-footer {
          font-size: 0.75rem;
          color: var(--text-secondary) !important;
          margin-top: 16px;
          opacity: 0.85;
        }
        .rag-inline-metrics {
          display: grid;
          grid-template-columns: repeat(4, minmax(0, 1fr));
          gap: 8px;
          margin: 2px 0 10px 0;
        }
        .rag-inline-metric {
          background: var(--bg-elevated);
          border: 1px solid var(--border);
          border-radius: 8px;
          padding: 7px 8px;
          min-height: 0;
        }
        .rag-inline-metric-val {
          font-size: 0.9rem;
          font-weight: 700;
          color: var(--text-primary) !important;
          line-height: 1.15;
        }
        .rag-inline-metric-lbl {
          font-size: 0.64rem;
          color: var(--text-secondary) !important;
          text-transform: uppercase;
          letter-spacing: 0.03em;
          margin-top: 2px;
          line-height: 1.1;
        }

        .rag-quality-strip {
          display: flex;
          flex-direction: row;
          flex-wrap: wrap;
          align-items: stretch;
          align-content: flex-start;
          gap: 6px 8px;
          max-height: 160px;
          min-height: 0;
          overflow: hidden;
          box-sizing: border-box;
          background: var(--bg-card);
          border: 1px solid var(--border);
          border-radius: 10px;
          padding: 6px 10px 8px 10px;
          margin: 0 0 8px 0;
        }
        .rag-quality-strip--empty {
          max-height: 120px;
          align-items: center;
        }
        .rag-quality-strip-title {
          flex: 0 0 auto;
          align-self: center;
          font-size: 0.7rem;
          font-weight: 700;
          text-transform: uppercase;
          letter-spacing: 0.05em;
          color: var(--accent) !important;
          margin: 0;
          padding: 2px 6px 2px 0;
          white-space: nowrap;
        }
        .rag-quality-strip-tiles {
          display: flex;
          flex-wrap: wrap;
          flex: 1 1 0;
          gap: 6px;
          align-content: flex-start;
          min-width: 0;
          max-height: 140px;
          overflow: hidden;
        }
        .rag-tile {
          flex: 0 1 auto;
          min-width: 76px;
          max-width: 118px;
          background: var(--bg-elevated);
          border: 1px solid var(--border);
          border-radius: 8px;
          padding: 4px 7px;
          min-height: 0;
          line-height: 1.15;
          box-sizing: border-box;
        }
        .rag-tile-val {
          font-size: 0.82rem;
          font-weight: 700;
          color: var(--text-primary) !important;
          display: block;
        }
        .rag-tile-lbl {
          font-size: 0.58rem;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.02em;
          color: var(--text-secondary) !important;
          margin-top: 1px;
          display: block;
          line-height: 1.1;
        }
        .rag-quality-empty {
          font-size: 0.78rem;
          color: var(--text-secondary) !important;
          margin: 0;
          padding: 2px 0;
          flex: 1 1 auto;
        }
        .rag-list-item {
          background: var(--bg-elevated);
          border: 1px solid var(--border);
          border-radius: 10px;
          padding: 8px 10px;
          margin-bottom: 8px;
        }
        .rag-list-item-selected {
          border-color: var(--success) !important;
          background: rgba(34, 197, 94, 0.08) !important;
        }
        .rag-list-item-head {
          display: flex;
          justify-content: space-between;
          align-items: center;
          gap: 8px;
          margin-bottom: 3px;
        }
        .rag-selected-badge {
          font-size: 0.62rem;
          font-weight: 700;
          color: var(--success) !important;
          border: 1px solid var(--success);
          background: rgba(34, 197, 94, 0.14);
          border-radius: 999px;
          padding: 1px 7px;
          line-height: 1.2;
          white-space: nowrap;
        }
        .rag-list-time {
          font-size: 0.76rem;
          color: var(--text-secondary) !important;
          margin: 0;
        }
        .rag-list-fallback {
          font-size: 0.74rem;
          text-transform: uppercase;
          letter-spacing: 0.03em;
          margin-bottom: 5px;
          color: var(--accent) !important;
          font-weight: 700;
        }
        .rag-list-query {
          font-size: 0.86rem;
          line-height: 1.32;
          color: var(--text-primary) !important;
          margin-bottom: 8px;
          max-height: 3.9em;
          overflow: hidden;
        }
        .route-badge-line {
          margin: 0 0 5px 0;
        }
        .route-badge {
          display: inline-flex;
          align-items: center;
          border-radius: 999px;
          padding: 1px 8px;
          font-size: 0.62rem;
          font-weight: 700;
          letter-spacing: 0.03em;
          text-transform: uppercase;
          border: 1px solid var(--border);
          color: var(--text-secondary) !important;
          background: rgba(156, 163, 175, 0.12);
        }
        .route-badge--success {
          color: var(--success) !important;
          border-color: var(--success);
          background: rgba(34, 197, 94, 0.12);
        }
        .route-badge--info {
          color: #38BDF8 !important;
          border-color: #38BDF8;
          background: rgba(56, 189, 248, 0.12);
        }
        .route-badge--warning {
          color: var(--warning) !important;
          border-color: var(--warning);
          background: rgba(245, 158, 11, 0.12);
        }
        .route-badge--muted {
          color: var(--text-secondary) !important;
          border-color: var(--border);
          background: rgba(156, 163, 175, 0.08);
        }
        .doc-chunk-badge {
          display: inline-flex;
          align-items: center;
          border-radius: 999px;
          padding: 1px 8px;
          font-size: 0.62rem;
          font-weight: 700;
          letter-spacing: 0.03em;
          text-transform: uppercase;
          border: 1px solid var(--border);
          margin-left: 6px;
          vertical-align: middle;
        }
        .doc-chunk-badge--normal {
          color: var(--success) !important;
          border-color: var(--success);
          background: rgba(34, 197, 94, 0.12);
        }
        .doc-chunk-badge--medium {
          color: var(--warning) !important;
          border-color: var(--warning);
          background: rgba(245, 158, 11, 0.12);
        }
        .doc-chunk-badge--large {
          color: var(--error) !important;
          border-color: var(--error);
          background: rgba(239, 68, 68, 0.1);
        }
        .doc-stats-strip {
          display: flex;
          flex-wrap: wrap;
          align-items: stretch;
          gap: 8px;
          background: var(--bg-card);
          border: 1px solid var(--border);
          border-radius: 10px;
          padding: 8px 10px;
          margin: 0 0 10px 0;
          box-sizing: border-box;
        }
        .doc-stats-strip-title {
          flex: 0 0 auto;
          align-self: center;
          font-size: 0.68rem;
          font-weight: 700;
          text-transform: uppercase;
          letter-spacing: 0.05em;
          color: var(--accent) !important;
          margin-right: 6px;
        }
        .doc-stats-strip-tiles {
          display: flex;
          flex-wrap: wrap;
          flex: 1 1 0;
          gap: 6px;
          min-width: 0;
        }
        .doc-stat-tile {
          flex: 0 1 auto;
          min-width: 72px;
          max-width: 140px;
          background: var(--bg-elevated);
          border: 1px solid var(--border);
          border-radius: 8px;
          padding: 4px 8px;
          line-height: 1.15;
        }
        .doc-stat-tile-val {
          font-size: 0.78rem;
          font-weight: 700;
          color: var(--text-primary) !important;
          display: block;
          word-break: break-word;
        }
        .doc-stat-tile-lbl {
          font-size: 0.55rem;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.02em;
          color: var(--text-secondary) !important;
          margin-top: 2px;
          display: block;
        }

        /* --- ops: dashboard cards, KV, metrics (operational summary) --- */
        .ops-dashboard-wrap {
          margin: 0 0 10px 0;
        }
        .ops-dashboard-intro {
          font-size: 0.8rem;
          color: var(--text-secondary) !important;
          margin: 0 0 8px 0;
          line-height: 1.35;
        }
        .ops-dashboard-grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(272px, 1fr));
          gap: 10px;
          align-items: stretch;
        }
        .ops-dashboard-card {
          display: flex;
          flex-direction: column;
          background: var(--bg-card);
          border: 1px solid var(--border);
          border-radius: 10px;
          padding: 10px 12px;
          margin: 0;
          box-sizing: border-box;
        }
        .ops-dashboard-card--warn {
          border-color: var(--warning);
          background: rgba(245, 158, 11, 0.07);
        }
        .ops-dashboard-card-title {
          font-size: 0.74rem;
          font-weight: 700;
          letter-spacing: 0.02em;
          color: var(--accent) !important;
          margin: 0 0 8px 0;
          line-height: 1.25;
        }
        .panel-footnote {
          margin-top: auto;
          padding-top: 0.5rem;
          margin-bottom: 0;
          border-top: 1px solid rgba(31, 42, 68, 0.85);
          font-size: 0.72rem !important;
          line-height: 1.28 !important;
          font-weight: 400;
          color: var(--text-muted) !important;
        }
        .panel-footnote code {
          font-size: 0.68rem;
          color: var(--text-secondary) !important;
          background: rgba(156, 163, 175, 0.12);
          padding: 0 0.2rem;
          border-radius: 3px;
        }
        .panel-footnote-heading {
          display: block;
          font-size: 0.68rem;
          font-weight: 600;
          letter-spacing: 0.03em;
          text-transform: uppercase;
          color: var(--text-muted) !important;
          margin: 0.45rem 0 0.35rem 0;
          line-height: 1.2;
        }
        .ops-dashboard-card-note {
          font-size: 0.72rem !important;
          line-height: 1.28 !important;
          color: var(--text-muted) !important;
          margin: 0.65rem 0 0 0;
          padding-top: 0.5rem;
          border-top: 1px solid rgba(31, 42, 68, 0.85);
          font-weight: 400;
        }
        .ops-kv {
          display: grid;
          grid-template-columns: minmax(0, 1fr) minmax(0, 1.1fr);
          gap: 5px 10px;
          font-size: 0.78rem;
          align-items: baseline;
        }
        .ops-kv-lbl {
          color: var(--text-secondary) !important;
        }
        .ops-kv-val {
          color: var(--text-primary) !important;
          text-align: right;
          word-break: break-word;
        }
        .ops-metric-row {
          display: flex;
          flex-wrap: wrap;
          gap: 6px;
          margin-top: 4px;
        }
        .ops-metric-chip {
          flex: 0 1 auto;
          min-width: 76px;
          background: var(--bg-elevated);
          border: 1px solid var(--border);
          border-radius: 8px;
          padding: 4px 8px;
          line-height: 1.12;
        }
        .ops-metric-chip-val {
          font-size: 0.8rem;
          font-weight: 700;
          color: var(--text-primary) !important;
          display: block;
        }
        .ops-metric-chip-lbl {
          font-size: 0.55rem;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.02em;
          color: var(--text-secondary) !important;
          margin-top: 2px;
          display: block;
        }
        .ops-inline-badge-row {
          display: flex;
          flex-wrap: wrap;
          align-items: center;
          gap: 6px;
          margin-top: 6px;
        }

        .summary-lifecycle-list {
          display: flex;
          flex-direction: column;
          gap: 5px;
          margin-top: 4px;
        }
        .summary-lifecycle-item {
          display: flex;
          justify-content: space-between;
          align-items: center;
          gap: 10px;
          background: var(--bg-elevated);
          border: 1px solid var(--border);
          border-radius: 8px;
          padding: 5px 9px;
          font-size: 0.78rem;
          line-height: 1.25;
        }
        .summary-lifecycle-item--ok {
          border-left: 3px solid var(--success);
        }
        .summary-lifecycle-item--error {
          border-left: 3px solid var(--error);
        }
        .summary-lifecycle-item--muted {
          opacity: 0.72;
          border-left: 3px solid var(--border);
        }
        .summary-lifecycle-lbl {
          color: var(--text-primary) !important;
        }
        .summary-lifecycle-cnt {
          font-weight: 700;
          color: var(--accent) !important;
          flex-shrink: 0;
        }
        .summary-route-grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
          gap: 8px;
          margin-top: 4px;
        }
        .summary-route-card {
          background: var(--bg-elevated);
          border: 1px solid var(--border);
          border-radius: 9px;
          padding: 8px 10px;
        }
        .summary-route-card-title {
          font-size: 0.68rem;
          font-weight: 700;
          text-transform: uppercase;
          letter-spacing: 0.04em;
          color: var(--text-secondary) !important;
          margin-bottom: 6px;
        }
        .summary-route-card-meta {
          display: flex;
          align-items: baseline;
          justify-content: space-between;
          gap: 8px;
        }
        .summary-route-count {
          font-size: 1.05rem;
          font-weight: 700;
          color: var(--text-primary) !important;
        }
        .summary-route-share {
          font-size: 0.72rem;
          font-weight: 600;
          color: var(--warning) !important;
        }
        .summary-route-card-outcomes {
          margin-top: 6px;
          font-size: 0.72rem;
          line-height: 1.45;
        }
        .summary-route-outcomes .log-status-badge {
          margin-right: 4px;
        }
        .summary-provider-chips {
          display: flex;
          flex-wrap: wrap;
          gap: 5px;
          margin-top: 6px;
        }
        .summary-provider-chip {
          font-size: 0.68rem;
          padding: 2px 7px;
          border-radius: 999px;
          border: 1px solid var(--border);
          background: rgba(156, 163, 175, 0.1);
          color: var(--text-primary) !important;
        }

        .doc-chunk-preview {
          max-height: 220px;
          overflow-y: auto;
          font-size: 0.82rem;
          line-height: 1.35;
          color: var(--text-primary) !important;
          background: var(--bg-elevated);
          border: 1px solid var(--border);
          border-radius: 8px;
          padding: 8px 10px;
          margin: 4px 0 8px 0;
          white-space: pre-wrap;
          word-break: break-word;
        }
        .log-status-badge {
          display: inline-flex;
          align-items: center;
          border-radius: 999px;
          padding: 1px 8px;
          font-size: 0.62rem;
          font-weight: 700;
          letter-spacing: 0.03em;
          text-transform: uppercase;
          border: 1px solid var(--border);
          margin-left: 6px;
          vertical-align: middle;
        }
        .log-status-badge--success {
          color: var(--success) !important;
          border-color: var(--success);
          background: rgba(34, 197, 94, 0.12);
        }
        .log-status-badge--error {
          color: var(--error) !important;
          border-color: var(--error);
          background: rgba(239, 68, 68, 0.1);
        }
        .log-status-badge--warning {
          color: var(--warning) !important;
          border-color: var(--warning);
          background: rgba(245, 158, 11, 0.12);
        }
        .log-status-badge--muted {
          color: var(--text-secondary) !important;
          border-color: var(--border);
          background: rgba(156, 163, 175, 0.08);
        }
        .log-timeline-flow {
          font-size: 0.78rem;
          line-height: 1.45;
          color: var(--text-secondary) !important;
          background: var(--bg-elevated);
          border: 1px solid var(--border);
          border-radius: 8px;
          padding: 8px 10px;
          margin: 6px 0 12px 0;
          word-break: break-word;
        }
        .log-timeline-card {
          background: var(--bg-elevated);
          border: 1px solid var(--border);
          border-radius: 8px;
          padding: 8px 10px;
          margin-bottom: 8px;
          border-left: 3px solid var(--border);
        }
        .log-timeline-card--success {
          border-left-color: var(--success);
        }
        .log-timeline-card--error {
          border-left-color: var(--error);
        }
        .log-timeline-card--warning {
          border-left-color: var(--warning);
        }
        .log-timeline-card--muted {
          border-left-color: var(--muted);
        }
        .log-timeline-card-head {
          display: flex;
          align-items: center;
          gap: 8px;
          margin-bottom: 4px;
        }
        .log-timeline-idx {
          font-size: 0.65rem;
          font-weight: 700;
          color: var(--text-secondary) !important;
          min-width: 1.2rem;
        }
        .log-timeline-time {
          font-size: 0.72rem;
          color: var(--text-secondary) !important;
        }
        .log-timeline-action {
          font-size: 0.84rem;
          font-weight: 600;
          color: var(--text-primary) !important;
          margin-bottom: 2px;
        }
        .log-timeline-status {
          font-size: 0.72rem;
          color: var(--muted) !important;
          margin-bottom: 4px;
        }
        .log-timeline-preview {
          font-size: 0.76rem;
          line-height: 1.3;
          color: var(--text-secondary) !important;
          max-height: 4.2em;
          overflow: hidden;
        }

        /* --- timeline: trace header + vertical steps --- */
        .logs-trace-header {
          background: var(--bg-elevated);
          border: 1px solid var(--border);
          border-radius: 10px;
          padding: 8px 10px;
          margin: 0 0 8px 0;
          box-sizing: border-box;
        }
        .logs-trace-header-title {
          font-size: 0.62rem;
          font-weight: 700;
          text-transform: uppercase;
          letter-spacing: 0.05em;
          color: var(--accent) !important;
          margin-bottom: 6px;
        }
        .logs-trace-header-row.logs-trace-header-eid {
          display: flex;
          flex-wrap: wrap;
          align-items: center;
          gap: 6px;
          font-size: 0.7rem;
          color: var(--text-secondary) !important;
          margin-bottom: 6px;
        }
        .logs-trace-header-eid code {
          font-size: 0.72rem;
          color: var(--text-primary) !important;
          word-break: break-all;
        }
        .logs-trace-header-badges {
          margin-bottom: 6px;
        }
        .logs-trace-header-kv {
          display: grid;
          grid-template-columns: minmax(0, 1fr) minmax(0, 1.2fr);
          gap: 3px 10px;
          font-size: 0.72rem;
          line-height: 1.25;
        }
        .logs-trace-header-kv span:nth-child(odd) {
          color: var(--text-secondary) !important;
        }
        .logs-trace-header-kv span:nth-child(even) {
          color: var(--text-primary) !important;
          text-align: right;
          word-break: break-word;
        }
        .logs-trace-flow-compact {
          font-size: 0.68rem;
          line-height: 1.3;
          color: var(--text-muted) !important;
          padding: 2px 0 6px 0;
          margin: 0 0 2px 0;
          border-bottom: 1px solid rgba(31, 42, 68, 0.55);
          word-break: break-word;
        }
        .logs-trace-timeline-title {
          font-size: 0.65rem;
          font-weight: 700;
          letter-spacing: 0.04em;
          text-transform: uppercase;
          color: var(--text-secondary) !important;
          margin: 2px 0 5px 0;
        }
        .log-trace-step {
          display: flex;
          gap: 7px;
          align-items: flex-start;
          margin-bottom: 2px;
          padding-bottom: 5px;
          border-bottom: 1px solid rgba(31, 42, 68, 0.35);
        }
        .log-trace-step:last-child {
          border-bottom: none;
          margin-bottom: 0;
          padding-bottom: 2px;
        }
        .log-trace-step-marker {
          width: 5px;
          min-width: 5px;
          align-self: stretch;
          min-height: 1.5rem;
          border-radius: 3px;
          background: var(--border);
          margin-top: 3px;
        }
        .log-trace-step--success .log-trace-step-marker {
          background: var(--success);
        }
        .log-trace-step--error .log-trace-step-marker {
          background: var(--error);
        }
        .log-trace-step--warning .log-trace-step-marker {
          background: var(--warning);
        }
        .log-trace-step--muted .log-trace-step-marker {
          background: var(--muted);
        }
        .log-trace-step-body {
          flex: 1;
          min-width: 0;
        }
        .log-trace-step-head {
          display: flex;
          flex-wrap: wrap;
          align-items: center;
          gap: 5px;
          margin-bottom: 1px;
        }
        .log-trace-step-idx {
          font-size: 0.58rem;
          font-weight: 700;
          color: var(--text-secondary) !important;
        }
        .log-trace-step-time {
          font-size: 0.66rem;
          color: var(--text-secondary) !important;
        }
        .log-trace-step-badges .log-status-badge {
          margin-left: 0 !important;
        }
        .log-trace-step-stage {
          font-size: 0.76rem;
          font-weight: 600;
          color: var(--text-primary) !important;
          line-height: 1.2;
          margin-bottom: 1px;
        }
        .log-trace-step-preview {
          font-size: 0.66rem;
          line-height: 1.26;
          color: var(--text-secondary) !important;
          max-height: 2.6em;
          overflow: hidden;
        }

        .image-prompt-box {
          font-size: 0.78rem;
          line-height: 1.32;
          color: var(--text-primary) !important;
          background: var(--bg-elevated);
          border: 1px solid var(--border);
          border-radius: 8px;
          padding: 6px 9px;
          margin: 2px 0 8px 0;
          max-height: 7.5em;
          overflow-y: auto;
          white-space: pre-wrap;
          word-break: break-word;
        }
        .image-preview-compact {
          max-width: 320px;
          margin: 6px 0 4px 0;
          border-radius: 8px;
          border: 1px solid var(--border);
          overflow: hidden;
        }
        .image-asset-meta {
          font-size: 0.68rem;
          line-height: 1.3;
          color: var(--text-secondary) !important;
          background: var(--bg-elevated);
          border: 1px solid var(--border);
          border-radius: 8px;
          padding: 6px 9px;
          margin: 4px 0 6px 0;
          word-break: break-all;
        }
        .image-asset-meta .muted-path {
          color: var(--text-muted) !important;
          font-size: 0.64rem;
        }
        /* panel-*: общие секции / пустые состояния (операторский стиль) */
        .panel-section-title,
        .image-section-title {
          font-size: 0.68rem;
          font-weight: 700;
          letter-spacing: 0.04em;
          text-transform: uppercase;
          color: var(--accent) !important;
          margin: 10px 0 4px 0;
        }
        .panel-empty {
          font-size: 0.8rem;
          line-height: 1.35;
          color: var(--text-muted) !important;
          background: var(--bg-elevated);
          border: 1px solid var(--border);
          border-radius: 9px;
          padding: 8px 11px;
          margin: 4px 0 8px 0;
        }
        .panel-empty p {
          margin: 0;
        }
        .panel-meta-row {
          font-size: 0.78rem;
          line-height: 1.35;
          margin: 2px 0 4px 0;
          color: var(--text-primary) !important;
        }
        .panel-meta-k {
          color: var(--text-secondary) !important;
          font-weight: 600;
          margin-right: 6px;
        }
        .panel-meta-v {
          word-break: break-word;
        }

        .logs-session-card .rag-list-item-head .rag-list-time {
          font-weight: 650;
        }
        .logs-session-badges-row {
          margin: 0 0 4px 0;
        }
        .logs-session-meta {
          font-size: 0.64rem;
          line-height: 1.28;
          color: var(--text-secondary) !important;
          margin-top: 5px;
          padding-top: 4px;
          border-top: 1px solid rgba(31, 42, 68, 0.45);
        }
        .logs-session-meta code {
          font-size: 0.64rem !important;
          color: var(--text-secondary) !important;
          background: transparent !important;
        }

        .logs-list-pane .stButton > button {
          background: var(--bg-card) !important;
          color: var(--text-primary) !important;
          border: 1px solid var(--border) !important;
          border-radius: 7px !important;
          min-height: 1.6rem !important;
          padding: 0.1rem 0.55rem !important;
          font-size: 0.78rem !important;
          font-weight: 600 !important;
          box-shadow: none !important;
        }
        .logs-list-pane .stButton > button:hover {
          border-color: var(--accent) !important;
          color: var(--accent) !important;
          filter: none !important;
        }
        code.log-eid-short {
          font-size: 0.72rem !important;
          color: var(--text-secondary) !important;
          background: transparent !important;
          padding: 0 !important;
          border: none !important;
        }
        .split-detail-summary {
          background: var(--bg-elevated);
          border: 1px solid var(--border);
          border-radius: 10px;
          padding: 8px 10px 10px 10px;
          margin: 0 0 10px 0;
          box-sizing: border-box;
        }
        .split-detail-summary-title {
          font-size: 0.62rem;
          font-weight: 700;
          text-transform: uppercase;
          letter-spacing: 0.06em;
          color: var(--accent) !important;
          margin-bottom: 6px;
        }
        .split-detail-summary-row {
          font-size: 0.78rem;
          line-height: 1.35;
          margin-bottom: 4px;
          color: var(--text-primary) !important;
        }
        .split-detail-k {
          color: var(--text-secondary) !important;
          font-weight: 600;
          margin-right: 6px;
        }
        .split-detail-v {
          color: var(--text-primary) !important;
          word-break: break-word;
        }
        .split-detail-badges .split-detail-v {
          display: inline-flex;
          flex-wrap: wrap;
          align-items: center;
          gap: 4px;
        }
        .split-detail-preview .split-detail-v {
          display: block;
          max-height: 3.6em;
          overflow: hidden;
          color: var(--text-secondary) !important;
        }
        .text-list-pane .stButton > button {
          background: var(--bg-card) !important;
          color: var(--text-primary) !important;
          border: 1px solid var(--border) !important;
          border-radius: 7px !important;
          min-height: 1.6rem !important;
          padding: 0.1rem 0.55rem !important;
          font-size: 0.78rem !important;
          font-weight: 600 !important;
          box-shadow: none !important;
        }
        .text-list-pane .stButton > button:hover {
          border-color: var(--accent) !important;
          color: var(--accent) !important;
          filter: none !important;
        }
        .rag-list-pane .stButton > button {
          background: var(--bg-card) !important;
          color: var(--text-primary) !important;
          border: 1px solid var(--border) !important;
          border-radius: 7px !important;
          min-height: 1.6rem !important;
          padding: 0.1rem 0.55rem !important;
          font-size: 0.78rem !important;
          font-weight: 600 !important;
          box-shadow: none !important;
        }
        .rag-list-pane .stButton > button:hover {
          border-color: var(--accent) !important;
          color: var(--accent) !important;
          filter: none !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_summary_technical_tables_expander(
    *,
    by_status: dict[str, Any],
    by_stage: dict[str, Any],
    by_route: dict[str, Any],
) -> None:
    """Секция Summary: сырые таблицы агрегатов в едином expander."""
    with st.expander("Показать технические таблицы", expanded=False):
        st.caption(
            "Сырые агрегаты из `processing_logs` (как в прежней сводке)."
        )
        st.markdown("**События по статусам**")
        if by_status:
            rows_s = [
                {"статус": _status_label(k), "количество": v}
                for k, v in sorted(
                    by_status.items(), key=lambda x: (-x[1], str(x[0]))
                )
            ]
            st.dataframe(
                pd.DataFrame(rows_s), use_container_width=True, hide_index=True
            )
        else:
            st.caption("Нет данных по статусам.")

        st.markdown("**События по этапам (все stage)**")
        if by_stage:
            rows_st_raw = [
                {
                    "этап (raw)": str(k),
                    "подпись": _stage_to_action(str(k)),
                    "количество": int(v or 0),
                }
                for k, v in sorted(
                    by_stage.items(), key=lambda x: (-int(x[1] or 0), str(x[0]))
                )
            ]
            st.dataframe(
                pd.DataFrame(rows_st_raw),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.caption("Нет данных по этапам.")

        st.markdown("**Маршруты (raw, dashboard)**")
        normalized_route_counts: dict[str, int] = {}
        for raw_route, count in by_route.items():
            norm_route = normalize_route(str(raw_route))
            normalized_route_counts[norm_route] = normalized_route_counts.get(
                norm_route, 0
            ) + int(count or 0)
        route_total = sum(
            int(normalized_route_counts.get(k, 0))
            for k in ("rag", "text", "image_generation")
        )
        if route_total > 0:
            rows_r = [
                {
                    "маршрут": _route_label(k),
                    "уникальных execution_id (24 ч)": int(
                        normalized_route_counts.get(k, 0)
                    ),
                }
                for k in ("text", "rag", "image_generation")
            ]
            st.dataframe(
                pd.DataFrame(rows_r), use_container_width=True, hide_index=True
            )
        else:
            render_empty_state("Нет данных по маршрутам за выбранный период.")


def _overview_health_badge_class(status: str) -> str:
    s = (status or "").strip().lower()
    if s in ("ok", "configured"):
        return "route-badge--success"
    if s == "degraded":
        return "route-badge--warning"
    if s == "not_configured":
        return "route-badge--muted"
    return "route-badge--error"


def _overview_system_health_snap_html(snap: Any) -> str:
    if not isinstance(snap, HealthSnapshot):
        return html.escape("—")
    bcls = _overview_health_badge_class(snap.status)
    lbl = format_health_badge_status(snap.status)
    parts: list[str] = [
        f'<span class="route-badge {bcls}">{html.escape(lbl)}</span>',
    ]
    if snap.latency_ms is not None:
        parts.append(html.escape(f" {snap.latency_ms} ms"))
    if snap.detail:
        parts.append(html.escape(f" · {snap.detail}"))
    if snap.error_message:
        parts.append(html.escape(f" · {snap.error_message[:140]}"))
    cnt = snap.extras.get("collection_count")
    if cnt is not None:
        parts.append(html.escape(f" · chunks={cnt}"))
    return "".join(parts)


def _overview_system_health_card_html(svc: AdminService) -> str:
    rep = run_system_healthchecks(
        svc.app_config,
        chroma_persist_path=str(svc.chroma_persist_path),
    )
    llm_line = " · ".join(
        f"{html.escape(str(name))}: "
        f"{html.escape(format_health_badge_status(snap.status))}"
        for name, snap in rep.llm.items()
    )
    inner = _overview_ops_kv_mixed(
        [
            _overview_ops_kv_item("PostgreSQL", _overview_system_health_snap_html(rep.postgres)),
            _overview_ops_kv_item("Chroma", _overview_system_health_snap_html(rep.chroma)),
            _overview_ops_kv_item(
                "Готовность RAG", _overview_system_health_snap_html(rep.rag)
            ),
            _overview_ops_kv_item("LLM (только конфигурация)", llm_line),
        ]
    )
    return ops_dashboard_card_html(
        "S. Состояние системы (live)",
        inner,
        footnote_html=_render_panel_footnote_html(
            "Короткие таймауты; без вызовов LLM. PostgreSQL: SELECT 1. "
            "Chroma: heartbeat (HTTP) + count в отдельном потоке."
        ),
    )


def _render_tab_overview(
    svc: AdminService,
    dashboard_stats: dict[str, Any],
) -> None:
    status = svc.get_knowledge_base_status()
    fs_txt_count = svc.get_documents_filesystem_count()
    overview_recent = svc.get_recent_logs(OVERVIEW_TELEMETRY_LOG_CAP)
    overview_docs = svc.get_documents_with_versions()
    telemetry = _overview_telemetry_from_rows(overview_recent)
    by_route = dashboard_stats.get("by_route") or {}
    text_n = int(by_route.get("text", 0))
    rag_n = int(by_route.get("rag", 0))
    img_n = int(by_route.get("image_generation", 0))
    total_req_24h = text_n + rag_n + img_n

    db_url_set = bool((os.getenv("DATABASE_URL") or "").strip())
    err_24h = (
        int(dashboard_stats.get("error_events", 0)) if db_url_set else None
    )
    if err_24h is None:
        err_line = "нет данных"
    else:
        err_line = str(err_24h)

    last_succ = _overview_find_last_success_row(overview_recent)
    if last_succ:
        ls_time = _format_dt_moscow_overview(last_succ.get("created_at"))
        ls_action = _stage_to_action(
            last_succ.get("stage"), last_succ.get("details")
        )
        last_success_inner = (
            f"{html.escape(ls_time)} — {html.escape(ls_action)} "
            f'{_overview_log_status_badge_html("success")}'
        )
    elif overview_recent:
        last_success_inner = html.escape(
            f"нет успешных среди последних {len(overview_recent)} записей"
        )
    elif db_url_set:
        last_success_inner = html.escape("журнал пуст или недоступен")
    else:
        last_success_inner = html.escape("нет данных")

    lat_ms = telemetry.get("avg_latency_ms")
    if lat_ms is not None:
        lat_line = html.escape(
            f"{lat_ms} мс (среднее по latency/duration в выборке журнала)"
        )
    else:
        lat_line = html.escape("нет данных")

    tok = telemetry.get("tokens_total")
    tok_line = html.escape(str(tok)) if tok is not None else html.escape("нет данных")

    tpm = telemetry.get("top_provider_model")
    tpm_line = html.escape(tpm) if tpm else html.escape("нет данных")

    if status.postgres_available:
        pg_val = (
            f'{html.escape("подключение доступно")} '
            '<span class="route-badge route-badge--success">OK</span>'
        )
    else:
        pg_val = (
            f'{html.escape("нет данных / недоступен")} '
            '<span class="route-badge route-badge--muted">—</span>'
        )

    chroma_count = str(int(status.collection_count))
    chroma_val = (
        f"{html.escape(chroma_count + ' чанков в коллекции')} "
        '<span class="route-badge route-badge--muted">НЕТ HEALTH</span>'
    )

    doc_mismatch = (
        status.postgres_available
        and status.postgres_documents is not None
        and status.postgres_documents != fs_txt_count
    )
    chunk_mismatch = (
        status.postgres_available
        and status.postgres_chunks_sum is not None
        and status.postgres_chunks_sum != status.collection_count
    )
    if not status.postgres_available:
        sync_label = "не сравнивается"
        sync_badge = '<span class="route-badge route-badge--muted">—</span>'
    elif doc_mismatch or chunk_mismatch:
        sync_label = "расхождение"
        sync_badge = '<span class="route-badge route-badge--warning">WARN</span>'
    else:
        sync_label = "OK"
        sync_badge = '<span class="route-badge route-badge--success">OK</span>'

    last_idx_dt: datetime | None = None
    for r in overview_docs:
        t = r.get("last_indexed_at")
        if isinstance(t, datetime):
            if last_idx_dt is None or t > last_idx_dt:
                last_idx_dt = t
    last_idx_str = (
        _format_dt_moscow_overview(last_idx_dt) if last_idx_dt else "—"
    )

    if overview_docs:
        largest = max(
            overview_docs,
            key=lambda r: int(r.get("active_chunk_count") or 0),
        )
        max_ch = int(largest.get("active_chunk_count") or 0)
        max_name = str(largest.get("filename") or "—")
        largest_str = f"{max_name} · {max_ch} чанков"
    else:
        largest_str = "—"

    last_adm = _overview_find_last_admin_row(overview_recent)
    if last_adm:
        adm_disp = (
            f"{_format_dt_moscow_overview(last_adm.get('created_at'))} — "
            f"{_stage_to_action(last_adm.get('stage'))}"
        )
    elif overview_recent:
        adm_disp = "нет admin_* в выборке журнала"
    else:
        adm_disp = "нет данных"

    card_a = ops_dashboard_card_html(
        "A. Состояние системы",
        _overview_ops_kv_mixed(
            [
                _overview_ops_kv_item(
                    "Telegram / бот",
                    html.escape("не проверяется")
                    + ' <span class="route-badge route-badge--muted">N/A</span>',
                ),
                _overview_ops_kv_item(
                    "Assistant Flow / админ UI",
                    html.escape("сессия Streamlit активна")
                    + ' <span class="route-badge route-badge--info">UI</span>',
                ),
                _overview_ops_kv_item("PostgreSQL", pg_val),
                _overview_ops_kv_item("Chroma", chroma_val),
                _overview_ops_kv_item(
                    "Последнее успешное событие (журнал)", last_success_inner
                ),
                _overview_ops_kv_item(
                    "Ошибки за 24 ч (статус error)",
                    html.escape(err_line),
                ),
                _overview_ops_kv_item("Средняя latency (выборка)", lat_line),
            ]
        ),
        footnote_html=_render_panel_footnote_html(
            "Chroma: только число записей в коллекции; сбои клиента могут дать 0 без "
            "отдельного статуса. Telegram из UI не проверяется."
        ),
    )

    activity_inner = _overview_metric_chips_html(
        [
            ("Text (норм.)", str(text_n)),
            ("RAG (норм.)", str(rag_n)),
            ("Image / gen", str(img_n)),
            ("Всего запросов", str(total_req_24h)),
        ]
    ) + _overview_ops_kv_mixed(
        [
            _overview_ops_kv_item("Токены (из details)", tok_line),
            _overview_ops_kv_item("Топ provider / model", tpm_line),
        ]
    )

    card_b = ops_dashboard_card_html(
        "B. AI-активность",
        activity_inner,
        footnote_html=_render_panel_footnote_html(
            "Text/RAG/Image — уникальные <code>execution_id</code> за 24 ч с нормализацией "
            "<code>route</code>/<code>mode</code>/<code>stage</code> (как в SQL "
            "<code>count_routes_since</code>)."
        ),
    )

    kb_rows_plain: list[tuple[str, str]] = [
        (
            "Документов в БД",
            str(status.postgres_documents)
            if status.postgres_available and status.postgres_documents is not None
            else "—",
        ),
        ("Файлов в каталоге", str(fs_txt_count)),
        (
            "Активных чанков PostgreSQL",
            str(status.postgres_chunks_sum)
            if status.postgres_available and status.postgres_chunks_sum is not None
            else "—",
        ),
        ("Чанков Chroma", chroma_count),
        ("Синхронизация (БД / FS / Chroma)", sync_label),
        ("Последняя индексация (метаданные)", last_idx_str),
        ("Крупнейший документ", largest_str),
    ]
    card_c = ops_dashboard_card_html(
        "C. База знаний",
        _overview_ops_kv_html(kb_rows_plain)
        + '<div class="ops-inline-badge-row">'
        + sync_badge
        + "</div>",
        footnote_html=_render_panel_footnote_html(
            "Метрики из <code>get_knowledge_base_status</code> и сводки документов; "
            "при расхождении чанков PostgreSQL и Chroma нужна переиндексация."
        ),
    )

    card_d = ops_dashboard_card_html(
        "D. Администрирование / безопасность",
        _overview_ops_kv_mixed(
            [
                _overview_ops_kv_item(
                    "Admin auth",
                    html.escape("не подключена")
                    + ' <span class="route-badge route-badge--muted">OFF</span>',
                ),
                _overview_ops_kv_item(
                    "Кнопка «Выход»",
                    html.escape("зарезервирована")
                    + ' <span class="route-badge route-badge--warning">RES</span>',
                ),
                _overview_ops_kv_item(
                    "Последнее admin-действие",
                    html.escape(adm_disp),
                ),
                _overview_ops_kv_item(
                    "Публичная экспозиция",
                    html.escape("Streamlit UI по умолчанию :8501"),
                ),
                _overview_ops_kv_item(
                    "Security status",
                    html.escape("требуется усиление (MVP)")
                    + ' <span class="route-badge route-badge--warning">HARDEN</span>',
                ),
            ]
        ),
        footnote_html=_render_panel_footnote_html(
            "Без реальной авторизации панель не считается защищённой."
        ),
    )

    warn_blocks: list[str] = []
    if doc_mismatch:
        warn_blocks.append(
            "<strong>Документы</strong>: число записей в PostgreSQL и .txt на диске "
            "не совпадает."
        )
    if chunk_mismatch:
        warn_blocks.append(
            "<strong>Индекс</strong>: сумма чанков в PostgreSQL и Chroma различается — "
            "нужна переиндексация."
        )
    warn_html = ""
    if warn_blocks:
        warn_html = (
            '<div style="margin-top:10px;">'
            + ops_dashboard_card_html(
                "Предупреждение синхронизации",
                "<ul style=\"margin:0;padding-left:1.1rem;\">"
                + "".join(f"<li>{w}</li>" for w in warn_blocks)
                + "</ul>",
                extra_classes="ops-dashboard-card--warn",
            )
            + "</div>"
        )

    try:
        card_s = _overview_system_health_card_html(svc)
    except Exception as exc:
        card_s = ops_dashboard_card_html(
            "S. Состояние системы (live)",
            f'<p class="panel-footnote">{html.escape(str(exc))}</p>',
        )

    overview_html = (
        '<div class="ops-dashboard-wrap">'
        '<p class="ops-dashboard-intro">'
        "Компактный операционный дашборд: здоровье сервисов (честные статусы), "
        "активность AI, база знаний и ограничения безопасности админки."
        "</p>"
        '<div class="ops-dashboard-grid">'
        f"{card_s}{card_a}{card_b}{card_c}{card_d}"
        "</div>"
        f"{warn_html}"
        "</div>"
    )
    st.markdown(overview_html, unsafe_allow_html=True)

    if not status.postgres_available:
        st.caption(
            "PostgreSQL: задайте `DATABASE_URL` и схему из каталога `database/`, "
            "чтобы видеть документы и чанки."
        )



def main() -> None:
    st.set_page_config(page_title="Assistant Flow — Админ-панель", layout="wide")
    _inject_theme_css()
    svc = _admin_service()
    now_msk = datetime.now(moscow_tz).strftime("%H:%M:%S")

    st.markdown('<div class="topbar-box">', unsafe_allow_html=True)
    top_left, top_btn_refresh, top_btn_logout, top_time = st.columns((5.4, 1, 1, 1.4))
    with top_left:
        st.markdown(
            '<div class="topbar-title-wrap">'
            '<div class="topbar-app-title">Assistant Flow — Админ-панель</div>'
            f'<div class="topbar-db-path">Файлы базы знаний: {html.escape(str(svc.documents_directory))}</div>'
            "</div>",
            unsafe_allow_html=True,
        )
    with top_btn_refresh:
        if st.button("Обновить", key="topbar_refresh"):
            st.rerun()
    with top_btn_logout:
        if st.button("Выход", key="topbar_logout"):
            st.toast(
                "Авторизация пока не подключена. Кнопка выхода зарезервирована.",
                icon="⚠️",
            )
    with top_time:
        st.markdown(
            f'<div class="topbar-updated">обновлено: {now_msk}</div>',
            unsafe_allow_html=True,
        )
    st.markdown("</div>", unsafe_allow_html=True)

    (
        tab_overview,
        tab_summary,
        tab_text,
        tab_rag,
        tab_images,
        tab_docs,
        tab_logs,
    ) = st.tabs(
        (
            "Обзор",
            "Сводка",
            "Text-запросы",
            "RAG-запросы",
            "Изображения",
            "Документы",
            "Логи",
        )
    )

    dashboard_stats = svc.get_dashboard_stats(hours=24)

    with tab_overview:
        _render_tab_overview(svc, dashboard_stats)

    with tab_summary:
        st.markdown(
            '<p class="ops-dashboard-intro">Операционная аналитика за последние 24 часа '
            "(компактные карточки; сырые таблицы — внизу, в свёртке).</p>",
            unsafe_allow_html=True,
        )
        if not (os.getenv("DATABASE_URL") or "").strip():
            render_empty_state(
                "Сводка недоступна: задайте переменную окружения DATABASE_URL "
                "и убедитесь, что таблица processing_logs заполняется."
            )
        elif int(dashboard_stats.get("total_events") or 0) == 0:
            render_empty_state(
                "За последние 24 часа в processing_logs нет записей. "
                "После работы бота и админки здесь появятся метрики."
            )
        else:
            summary_sample = svc.get_recent_logs(SUMMARY_LOG_SAMPLE_CAP)
            rows_24 = _summary_rows_since_hours(
                summary_sample, hours=SUMMARY_HOURS_WINDOW
            )
            uniq_exec = _summary_unique_execution_ids(rows_24)
            sample_out = _summary_route_sample_outcomes(rows_24)
            unk_o = sample_out.get("unknown") or {}
            unknown_sample_n = sum(int(unk_o.get(k, 0)) for k in ("success", "error", "other"))
            telem = _summary_telemetry_extended_from_rows(rows_24)
            by_status = dashboard_stats.get("by_status") or {}
            by_stage = dashboard_stats.get("by_stage") or {}
            by_route = dashboard_stats.get("by_route") or {}

            def _ds_int(key: str) -> int:
                return int(dashboard_stats.get(key) or 0)

            activity_chips = _overview_metric_chips_html(
                [
                    ("Всего событий", str(_ds_int("total_events"))),
                    ("Успешных", str(_ds_int("success_events"))),
                    ("Ошибок", str(_ds_int("error_events"))),
                    ("Уникальных execution_id", str(uniq_exec)),
                    ("Админ операции", str(_ds_int("admin_events"))),
                    ("Переиндексации", str(_ds_int("reindex_runs"))),
                    ("Генерации изображений", str(_ds_int("image_generations"))),
                ]
            )

            card_a = ops_dashboard_card_html(
                "A. Сводка активности",
                activity_chips,
                footnote_html=_render_panel_footnote_html(
                    "Агрегаты событий — из <code>get_dashboard_stats</code> (24 ч). "
                    "Уникальные <code>execution_id</code> — только по сессиям в выборке "
                    f"(до {SUMMARY_LOG_SAMPLE_CAP} последних строк журнала, отфильтровано по 24 ч); "
                    "полный DISTINCT по окну в UI без нового API недоступен."
                ),
            )

            route_body = _summary_route_rows_html(
                by_route=by_route,
                sample_out=sample_out,
                unknown_sample_n=unknown_sample_n,
            )
            card_b = ops_dashboard_card_html(
                "B. Маршруты",
                route_body,
                footnote_html=_render_panel_footnote_html(
                    "Счётчики Text / RAG / Image — уникальные <code>execution_id</code> за 24 ч "
                    "с нормализацией route/mode/stage (как в SQL <code>count_routes_since</code>). "
                    "Доля — от суммы Text+RAG+Image+«прочее» в выборке. "
                    "Успех/ошибка по маршруту — по итогу сессии в этой выборке (см. "
                    "<code>_logs_infer_route_from_events</code> / "
                    "<code>_logs_session_final_status</code>)."
                ),
            )

            card_c = ops_dashboard_card_html(
                "C. Этапы / lifecycle",
                _summary_lifecycle_list_html(by_stage),
                footnote_html=_render_panel_footnote_html(
                    "Числа — сырые <code>stage</code> из журнала за 24 ч; подписи через "
                    "существующие хелперы нормализации."
                ),
            )

            top_pm = telem.get("top_provider_model")
            tok = telem.get("tokens_total")
            avg_lat = telem.get("avg_latency_ms")
            max_lat = telem.get("max_latency_ms")
            by_prov = telem.get("by_provider_rows") or {}

            tok_line = (
                html.escape(str(tok)) if tok is not None else html.escape("нет данных")
            )
            tpm_line = (
                html.escape(str(top_pm))
                if top_pm
                else html.escape("нет данных")
            )
            if avg_lat is not None:
                avg_line = html.escape(f"{avg_lat} мс")
            else:
                avg_line = html.escape("нет данных")
            if max_lat is not None:
                max_line = html.escape(f"{max_lat} мс")
            else:
                max_line = html.escape("нет данных")

            if by_prov:
                prov_parts = ['<div class="summary-provider-chips">']
                for pk, pv in list(by_prov.items())[:12]:
                    prov_parts.append(
                        '<span class="summary-provider-chip">'
                        f"{html.escape(str(pk))}: {int(pv)}"
                        "</span>"
                    )
                prov_parts.append("</div>")
                prov_html = "".join(prov_parts)
            else:
                prov_html = (
                    '<span class="route-badge route-badge--muted">'
                    "нет данных"
                    "</span>"
                )

            card_d = ops_dashboard_card_html(
                "D. Провайдеры и производительность",
                _overview_ops_kv_mixed(
                    [
                        _overview_ops_kv_item("Топ provider / model", tpm_line),
                        _overview_ops_kv_item("Токены (сумма по details)", tok_line),
                        _overview_ops_kv_item("Средняя latency", avg_line),
                        _overview_ops_kv_item("Макс. latency", max_line),
                    ]
                )
                + '<span class="panel-footnote-heading">Строки журнала по провайдеру</span>'
                + prov_html,
                footnote_html=_render_panel_footnote_html(
                    "По строкам журнала за 24 ч в выборке (поля <code>details</code>). "
                    "Если в логах нет provider/tokens/latency — отображается «нет данных»."
                ),
            )

            summary_html = (
                '<div class="ops-dashboard-wrap">'
                '<div class="ops-dashboard-grid">'
                f"{card_a}{card_b}{card_c}{card_d}"
                "</div></div>"
            )
            st.markdown(summary_html, unsafe_allow_html=True)

            _render_summary_technical_tables_expander(
                by_status=by_status,
                by_stage=by_stage,
                by_route=by_route,
            )

    with tab_text:
        st.subheader("Text-запросы")
        st.caption("Обычные LLM-запросы без RAG-контекста.")
        if not (os.getenv("DATABASE_URL") or "").strip():
            render_empty_state(
                "Раздел недоступен: задайте переменную окружения DATABASE_URL "
                "и убедитесь, что таблица processing_logs заполняется."
            )
        else:
            t_f1, t_f2 = st.columns(2)
            status_filter_opt = t_f2.selectbox(
                "Статус",
                options=("Все", "success", "error"),
                index=0,
                key="text_recent_status_filter",
            )
            text_page = int(st.session_state.get("text_page", 0))
            text_page_size_seed = int(st.session_state.get("text_page_size", 50))
            text_limit = min(500, max(20, (text_page + 1) * text_page_size_seed + 1))
            text_rows = svc.get_recent_text_events(limit=text_limit)
            text_requests = _build_text_requests_from_rows(text_rows)
            if status_filter_opt != "Все":
                text_requests = [
                    r
                    for r in text_requests
                    if str(r.get("status") or "").strip().lower() == status_filter_opt
                ]

            if not text_requests:
                st.session_state.pop("selected_text_execution_id", None)
                render_empty_state("Text-запросов за период пока нет.")
            else:
                selected_text_eid = str(
                    st.session_state.get("selected_text_execution_id", "")
                )
                has_next_text = len(text_requests) > (text_page + 1) * text_page_size_seed
                text_page, text_page_size = render_pagination_controls(
                    "text", total_items=len(text_requests), has_next=has_next_text
                )
                page_items, _, _ = get_paginated_slice(
                    text_requests, text_page, text_page_size
                )
                show_split_selection_toast("text")
                render_split_pane_titles(
                    list_title="Список Text-запросов",
                    detail_title="Детали выбранного запроса",
                )
                list_col, detail_col = split_list_detail_columns()
                with list_col:
                    st.markdown('<div class="text-list-pane">', unsafe_allow_html=True)
                    for idx, req in enumerate(page_items):
                        dt_label = _format_dt_moscow_logs(req.get("last_at"))
                        status_raw = str(req.get("status") or "")
                        status_label = _status_label(status_raw)
                        route_badge = get_route_badge(str(req.get("route") or "text"))
                        preview = str(req.get("preview") or "Текстовый запрос")
                        eid = str(req.get("execution_id") or "")
                        is_selected = bool(selected_text_eid) and eid == selected_text_eid
                        item_cls = (
                            "rag-list-item rag-list-item-selected"
                            if is_selected
                            else "rag-list-item"
                        )
                        badge_html = (
                            '<span class="rag-selected-badge">выбрано</span>'
                            if is_selected
                            else ""
                        )
                        st.markdown(
                            f'<div class="{item_cls}">'
                            '<div class="rag-list-item-head">'
                            f'<div class="rag-list-time">{html.escape(dt_label)}</div>'
                            f"{badge_html}</div>"
                            f'<div class="route-badge-line">{route_badge}</div>'
                            f'<div class="rag-list-fallback">{html.escape(status_label)}</div>'
                            f'<div class="rag-list-query">{html.escape(preview)}</div>'
                            "</div>",
                            unsafe_allow_html=True,
                        )
                        if st.button(
                            split_open_button_label(is_selected),
                            key=f"text_open_{idx}_{eid}",
                            help="Открыть детали справа",
                        ):
                            st.session_state["selected_text_execution_id"] = eid
                            flag_split_selection_toast("text")
                            st.rerun()
                    st.markdown("</div>", unsafe_allow_html=True)

                with detail_col:
                    reset_invalid_selection(
                        page_items,
                        "selected_text_execution_id",
                        lambda it: str(it.get("execution_id") or ""),
                    )
                    selected_text_eid = str(
                        st.session_state.get("selected_text_execution_id", "")
                    )
                    if not selected_text_eid:
                        render_empty_state("Выберите Text-запрос слева.")
                    else:
                        selected_req = next(
                            (
                                req
                                for req in page_items
                                if str(req.get("execution_id") or "") == selected_text_eid
                            ),
                            None,
                        )
                        if selected_req is None:
                            st.session_state.pop("selected_text_execution_id", None)
                            render_empty_state(
                                "Выбранный запрос не найден в текущем фильтре. "
                                "Выберите Text-запрос слева."
                            )
                        else:
                            opened_dt = _format_dt_moscow_logs(selected_req.get("last_at"))
                            opened_status = _status_label(str(selected_req.get("status") or ""))
                            render_split_selected_summary(
                                short_id=_short_execution_id(selected_text_eid),
                                status_line=opened_status,
                                route_or_type_html=get_route_badge(
                                    str(selected_req.get("route") or "text")
                                ),
                                timestamp=opened_dt,
                                preview=str(selected_req.get("preview") or ""),
                            )
                            _render_text_request_detail(selected_req)

    with tab_rag:
        if not (os.getenv("DATABASE_URL") or "").strip():
            st.subheader("RAG-запросы")
            render_empty_state(
                "Раздел недоступен: задайте переменную окружения DATABASE_URL "
                "и убедитесь, что таблица processing_logs заполняется."
            )
        else:
            rq = dashboard_stats.get("rag_quality") or {}
            st.subheader("RAG-запросы")
            st.caption(
                "Журнал ответов RAG: запрос пользователя, итог, метрики retrieval "
                "и фрагменты базы знаний."
            )
            st.markdown(_rag_quality_compact_html(rq), unsafe_allow_html=True)
            st.markdown("**Последние RAG-запросы**")
            rf1, rf2 = st.columns(2)
            fallback_options = (
                "Все",
                "none",
                "low_relevance",
                "empty_retrieval",
                "empty_context",
                "llm_error",
            )
            selected_fallback = rf1.selectbox(
                "Фильтр по fallback_reason",
                options=fallback_options,
                index=0,
                key="rag_recent_fallback_filter",
            )
            rag_page = int(st.session_state.get("rag_page", 0))
            rag_page_size_seed = int(st.session_state.get("rag_page_size", 50))
            limit_recent = min(500, max(20, (rag_page + 1) * rag_page_size_seed + 1))
            fallback_filter = None if selected_fallback == "Все" else selected_fallback
            recent_rag = svc.get_recent_rag_events(
                limit=limit_recent,
                fallback_reason=fallback_filter,
            )
            if not recent_rag:
                st.session_state.pop("selected_rag_execution_id", None)
                render_empty_state("RAG-события по выбранному фильтру не найдены.")
            else:
                has_next_rag = len(recent_rag) > (rag_page + 1) * rag_page_size_seed
                rag_page, rag_page_size = render_pagination_controls(
                    "rag", total_items=len(recent_rag), has_next=has_next_rag
                )
                page_items, _, _ = get_paginated_slice(recent_rag, rag_page, rag_page_size)
                show_split_selection_toast("rag")
                render_split_pane_titles(
                    list_title="Список RAG-запросов",
                    detail_title="Детали выбранного запроса",
                )
                selected_eid = str(
                    st.session_state.get("selected_rag_execution_id", "")
                )
                list_col, detail_col = split_list_detail_columns()
                with list_col:
                    st.markdown('<div class="rag-list-pane">', unsafe_allow_html=True)
                    for idx, ev in enumerate(page_items):
                        dt_label = _format_dt_moscow_logs(ev.get("created_at"))
                        fb = str(ev.get("fallback_reason") or "none")
                        fb_ru, _ = _rag_fallback_outcome(fb)
                        qp = str(ev.get("query_preview") or "—")
                        route_badge = get_route_badge("rag")
                        eid = str(ev.get("execution_id") or "")
                        is_selected = bool(selected_eid) and eid == selected_eid
                        item_cls = (
                            "rag-list-item rag-list-item-selected"
                            if is_selected
                            else "rag-list-item"
                        )
                        badge_html = (
                            '<span class="rag-selected-badge">выбрано</span>'
                            if is_selected
                            else ""
                        )
                        st.markdown(
                            f'<div class="{item_cls}">'
                            '<div class="rag-list-item-head">'
                            f'<div class="rag-list-time">{html.escape(dt_label)}</div>'
                            f"{badge_html}"
                            "</div>"
                            f'<div class="route-badge-line">{route_badge}</div>'
                            f'<div class="rag-list-fallback">{html.escape(fb_ru)}</div>'
                            f'<div class="rag-list-query">{html.escape(qp)}</div>'
                            "</div>",
                            unsafe_allow_html=True,
                        )
                        if st.button(
                            split_open_button_label(is_selected),
                            key=f"rag_open_{idx}_{eid}",
                            help="Открыть детали справа",
                        ):
                            st.session_state["selected_rag_execution_id"] = eid
                            flag_split_selection_toast("rag")
                            st.rerun()
                    st.markdown("</div>", unsafe_allow_html=True)

                with detail_col:
                    reset_invalid_selection(
                        page_items,
                        "selected_rag_execution_id",
                        lambda it: str(it.get("execution_id") or ""),
                    )
                    selected_eid = str(
                        st.session_state.get("selected_rag_execution_id", "")
                    )
                    if not selected_eid:
                        render_empty_state("Выберите RAG-запрос слева.")
                    else:
                        selected_ev = next(
                            (
                                ev
                                for ev in page_items
                                if str(ev.get("execution_id") or "") == selected_eid
                            ),
                            None,
                        )
                        if selected_ev is None:
                            st.session_state.pop("selected_rag_execution_id", None)
                            render_empty_state(
                                "Выбранный запрос не найден в текущем фильтре. "
                                "Выберите RAG-запрос слева."
                            )
                        else:
                            opened_dt = _format_dt_moscow_logs(selected_ev.get("created_at"))
                            opened_fb = str(selected_ev.get("fallback_reason") or "none")
                            opened_fb_ru, _ = _rag_fallback_outcome(opened_fb)
                            st_rag = _status_label(str(selected_ev.get("status") or ""))
                            render_split_selected_summary(
                                short_id=_short_execution_id(selected_eid),
                                status_line=st_rag,
                                route_or_type_html=f'{get_route_badge("rag")} '
                                f'<span class="log-status-badge log-status-badge--muted">'
                                f"{html.escape(opened_fb_ru)}</span>",
                                timestamp=opened_dt,
                                preview=str(selected_ev.get("query_preview") or ""),
                            )
                            _render_rag_event_detail(selected_ev)

    with tab_images:
        st.subheader("Изображения")
        st.caption(
            "Операторский журнал генераций из `processing_logs`. Список строится по последним "
            f"{IMAGE_LIST_LOG_CAP} строкам журнала; превью файла загружается только для выбранной сессии."
        )
        if not (os.getenv("DATABASE_URL") or "").strip():
            render_empty_state(
                "Раздел недоступен: задайте переменную окружения DATABASE_URL "
                "и убедитесь, что таблица processing_logs заполняется."
            )
        else:
            img_sample = svc.get_recent_logs(IMAGE_LIST_LOG_CAP)
            all_image_sessions = _image_build_sessions_from_rows(img_sample)
            if not all_image_sessions:
                st.markdown(
                    ops_dashboard_card_html(
                        "Генерации изображений",
                        '<p class="panel-footnote" style="border:none;padding-top:0;margin:0;">'
                        "Генерации изображений пока отсутствуют.</p>",
                    ),
                    unsafe_allow_html=True,
                )
            else:
                img_page = int(st.session_state.get("image_page", 0))
                img_page_size_seed = int(st.session_state.get("image_page_size", 50))
                n_total = len(all_image_sessions)
                has_next_img = (img_page + 1) * img_page_size_seed < n_total
                img_page, img_page_size = render_pagination_controls(
                    "image",
                    total_items=n_total,
                    has_next=has_next_img,
                    page_size_label="Сколько сессий показать",
                )
                page_items, _, _ = get_paginated_slice(
                    all_image_sessions, img_page, img_page_size
                )
                st.caption(f"Сессий генерации в выборке журнала: {n_total}")
                show_split_selection_toast("image")
                render_split_pane_titles(
                    list_title="Журнал генераций изображений",
                    detail_title="Трассировка выбранной генерации",
                )
                list_col, detail_col = split_list_detail_columns()
                selected_img_eid = str(
                    st.session_state.get("selected_image_execution_id", "")
                )
                with list_col:
                    st.markdown('<div class="logs-list-pane">', unsafe_allow_html=True)
                    for idx, sess in enumerate(page_items):
                        eid = str(sess.get("execution_id") or "")
                        sample_evs = sess.get("sample_events") or []
                        if not isinstance(sample_evs, list):
                            sample_evs = []
                        last_at = sess.get("last_at")
                        route_n = _logs_infer_route_from_events(sample_evs)
                        status_s = _logs_session_final_status(sample_evs)
                        preview = _image_prompt_preview_from_events(sample_evs) or "—"
                        pm = _logs_session_provider_model(sample_evs)
                        assets_s = _image_collect_assets_from_events(sample_evs)
                        gen_n = _image_generation_count_hint(sample_evs, len(assets_s))
                        dt_label = _format_dt_moscow_logs(last_at)
                        is_selected = bool(selected_img_eid) and eid == selected_img_eid
                        item_cls = (
                            "rag-list-item logs-session-card rag-list-item-selected"
                            if is_selected
                            else "rag-list-item logs-session-card"
                        )
                        badge_sel = (
                            '<span class="rag-selected-badge">выбрано</span>'
                            if is_selected
                            else ""
                        )
                        eid_short = _short_execution_id(eid)
                        pm_block = ""
                        if pm:
                            pmt = pm if len(pm) <= 100 else pm[:99] + "…"
                            pm_block = (
                                '<div class="logs-session-meta" style="border-top:none;'
                                'padding-top:3px;margin-top:2px;">'
                                f"{html.escape(pmt)}</div>"
                            )
                        st.markdown(
                            f'<div class="{item_cls}">'
                            '<div class="rag-list-item-head">'
                            f'<div class="rag-list-time">{html.escape(dt_label)}</div>'
                            f"{badge_sel}</div>"
                            '<div class="logs-session-badges-row">'
                            '<div class="route-badge-line">'
                            f"{get_route_badge(route_n)} {get_log_status_badge(status_s)}"
                            "</div></div>"
                            f'<div class="rag-list-query">{html.escape(preview)}</div>'
                            f"{pm_block}"
                            '<div class="logs-session-meta">'
                            f'<code class="log-eid-short">{html.escape(eid_short)}</code>'
                            f" · событий (в выборке): {len(sample_evs)}"
                            f" · файлов/оценка: {gen_n}"
                            "</div></div>",
                            unsafe_allow_html=True,
                        )
                        if st.button(
                            split_open_button_label(is_selected),
                            key=f"image_open_{idx}_{eid}",
                            help="Открыть трассировку справа",
                        ):
                            st.session_state["selected_image_execution_id"] = eid
                            flag_split_selection_toast("image")
                            st.rerun()
                    st.markdown("</div>", unsafe_allow_html=True)

                with detail_col:
                    reset_invalid_selection(
                        page_items,
                        "selected_image_execution_id",
                        lambda s: str(s.get("execution_id") or ""),
                    )
                    selected_img_eid = str(
                        st.session_state.get("selected_image_execution_id", "")
                    )
                    if not selected_img_eid:
                        render_empty_state("Выберите генерацию слева.")
                    else:
                        full_rows = svc.get_logs_events_for_execution_ids(
                            [selected_img_eid]
                        )
                        if not full_rows:
                            st.warning("Не удалось загрузить события для execution_id.")
                        else:
                            events = list(full_rows)
                            if not any(_image_log_row_matches(r) for r in events):
                                st.markdown(
                                    '<span class="route-badge route-badge--warning">'
                                    "В полной трассе нет признаков image-generation"
                                    "</span>",
                                    unsafe_allow_html=True,
                                )
                            last_times = [
                                r.get("created_at")
                                for r in events
                                if isinstance(r.get("created_at"), datetime)
                            ]
                            last_at = max(last_times) if last_times else None
                            assets = _image_collect_assets_from_events(events)
                            prompts = _image_extract_prompts_from_events(events)
                            _render_image_generation_summary_html(
                                execution_id=selected_img_eid,
                                events=events,
                                assets=assets,
                            )
                            st.markdown(
                                panel_section_title_html("A. Prompt"),
                                unsafe_allow_html=True,
                            )
                            _render_prompt_subsection(
                                "Исходный запрос", prompts.get("original")
                            )
                            _render_prompt_subsection(
                                "Уточнённый промпт (текст)",
                                prompts.get("enhanced"),
                                empty_label="не сохранён",
                            )
                            _render_prompt_subsection(
                                "Image prompt (провайдер)",
                                prompts.get("image_prompt"),
                                empty_label="не сохранён",
                            )
                            _render_prompt_subsection(
                                "Негативный prompt", prompts.get("negative")
                            )
                            st.markdown(
                                panel_section_title_html("B. Сгенерированные ассеты"),
                                unsafe_allow_html=True,
                            )
                            if not assets:
                                render_empty_state(
                                    "В логах не найдено путей к файлам изображений."
                                )
                            for a in assets:
                                raw_path = a.get("path")
                                rs = str(raw_path) if raw_path else ""
                                asset_ref_s = str(a.get("asset_ref") or "").strip()
                                url_hint = a.get("provider_url") or a.get("url")
                                http_url = _safe_image_http_url(
                                    str(url_hint) if url_hint else None
                                )
                                fn_meta = a.get("filename")
                                if isinstance(fn_meta, str) and fn_meta.strip():
                                    fn = fn_meta.strip()
                                else:
                                    try:
                                        fn = Path(rs).name if rs else "—"
                                    except Exception:
                                        fn = "—"
                                p_resolved = _safe_resolved_asset_ref(asset_ref_s)
                                if p_resolved is None:
                                    p_resolved = _safe_resolved_asset_path(rs or None)
                                sz_s = ""
                                sz_meta = a.get("size")
                                if sz_meta is not None:
                                    try:
                                        sz_s = _format_bytes(int(sz_meta))
                                    except (TypeError, ValueError, OSError):
                                        sz_s = ""
                                if p_resolved and not sz_s:
                                    try:
                                        sz_s = _format_bytes(p_resolved.stat().st_size)
                                    except OSError:
                                        sz_s = ""
                                ca = a.get("created_at")
                                ca_s = (
                                    _format_dt_moscow_logs(ca)
                                    if ca is not None
                                    else "—"
                                )
                                url_line = (
                                    f'<br/>URL: <span class="muted-path">{html.escape(http_url)}</span>'
                                    if http_url
                                    else ""
                                )
                                st.markdown(
                                    f'<div class="image-asset-meta">'
                                    f"<strong>{html.escape(fn)}</strong><br/>"
                                    f'<span class="muted-path">{html.escape(rs or "—")}</span>'
                                    f'{(f"<br/>asset_ref: <span class=\"muted-path\">{html.escape(asset_ref_s)}</span>") if asset_ref_s else ""}'
                                    f"{url_line}"
                                    f"{('<br/>размер: ' + html.escape(sz_s)) if sz_s else ''}"
                                    f"<br/>создано (событие): {html.escape(ca_s)}"
                                    "</div>",
                                    unsafe_allow_html=True,
                                )
                                preview_ok = False
                                if p_resolved:
                                    try:
                                        st.image(str(p_resolved), width=320)
                                        with st.expander("Полный размер превью", expanded=False):
                                            st.image(str(p_resolved))
                                        preview_ok = True
                                    except Exception:
                                        preview_ok = False
                                if not preview_ok and http_url:
                                    try:
                                        st.image(http_url, width=320)
                                        with st.expander("Полный размер (URL)", expanded=False):
                                            st.image(http_url)
                                        preview_ok = True
                                    except Exception:
                                        preview_ok = False
                                if not preview_ok:
                                    st.markdown(
                                        '<span class="route-badge route-badge--muted">'
                                        "изображение недоступно"
                                        "</span>",
                                        unsafe_allow_html=True,
                                    )
                            st.markdown(
                                panel_section_title_html("C. Технические метаданные"),
                                unsafe_allow_html=True,
                            )
                            render_metadata_expander(
                                "Показать агрегированные метаданные",
                                {
                                    "execution_id": selected_img_eid,
                                    "n_events": len(events),
                                    "last_at_msk": _format_dt_moscow_logs(last_at),
                                    "assets_detected": [a.get("path") for a in assets],
                                    "final_status": _logs_session_final_status(events),
                                },
                                expanded=False,
                            )
                            st.markdown(
                                panel_section_title_html("D. Timeline"),
                                unsafe_allow_html=True,
                            )
                            _render_trace_flow_timeline(
                                events, section_title="Цепочка событий"
                            )

    with tab_docs:
        st.subheader("Документы")
        st.caption("Управление базой знаний: загрузка, поиск, версии и переиндексация.")

        rag_cfg = load_config()
        doc_rows = svc.get_documents_with_versions()
        files = svc.list_documents()

        if doc_rows:
            st.markdown(_documents_stats_strip_html(doc_rows), unsafe_allow_html=True)

        has_any_large_doc = any(
            _doc_chunk_tier(int(r.get("active_chunk_count") or 0)) == "large"
            for r in doc_rows
        )
        if has_any_large_doc:
            st.warning(
                "В системе обнаружены большие документы. "
                "Переиндексация может занять длительное время и увеличить нагрузку на ChromaDB."
            )

        all_statuses = sorted(
            {str(r.get("status") or "—").strip() for r in doc_rows if r is not None}
        )

        tb1, tb2, tb3, tb4 = st.columns((2.4, 1.1, 1.3, 1.2))
        with tb1:
            uploaded = st.file_uploader("Загрузить .txt", type=["txt"], key="docs_upload")
            if uploaded is not None:
                u_bytes = uploaded.getvalue()
                u_text = u_bytes.decode("utf-8", errors="replace")
                u_est = _estimate_chunks(
                    u_text,
                    chunk_size=rag_cfg.rag_chunk_size,
                    chunk_overlap=rag_cfg.rag_chunk_overlap,
                )
                u_tier = _doc_chunk_tier(u_est)
                u_lbl = _doc_upload_tier_label(u_tier)
                st.caption(
                    f"{u_lbl} · {_format_bytes(len(u_bytes))} · ~{u_est} чанков "
                    f"(оценка; chunk_size={rag_cfg.rag_chunk_size}, overlap={rag_cfg.rag_chunk_overlap})"
                )
                st.markdown(
                    f'<div class="route-badge-line">{get_doc_chunk_badge(u_est)}</div>',
                    unsafe_allow_html=True,
                )
                if u_tier == "large":
                    st.caption(
                        "Переиндексация может занять заметное время и увеличить нагрузку на ChromaDB."
                    )
                st.markdown(
                    '<p class="rag-section-label">Превью текста (обрезано)</p>',
                    unsafe_allow_html=True,
                )
                st.markdown(
                    f'<div class="doc-chunk-preview">{html.escape(_truncate_preview(u_text))}</div>',
                    unsafe_allow_html=True,
                )
                with st.expander("Полный текст загружаемого файла", expanded=False):
                    cap = 200_000
                    if len(u_text) <= cap:
                        st.text(u_text)
                    else:
                        st.text(u_text[:cap] + "\n… [обрезано для отображения в UI]")
            if uploaded is not None and st.button("Upload", key="save_upload"):
                try:
                    dest = svc.save_uploaded_txt(uploaded.name, uploaded.getvalue())
                    st.success(f"Файл сохранён: `{dest}`")
                except ValueError as exc:
                    st.error(str(exc))
        with tb2:
            st.markdown("&nbsp;", unsafe_allow_html=True)
            if st.button("Reindex all", type="primary", key="run_reindex_embedded"):
                with st.spinner("Идёт переиндексация…"):
                    result = svc.run_reindex()
                if result.success:
                    st.success("Переиндексация выполнена успешно.")
                else:
                    st.error("Переиндексация завершилась с ошибкой или не для всех файлов.")
                st.caption(f"Чанков в коллекции Chroma: {result.collection_count}")
                if result.error_message:
                    st.warning(result.error_message)
        with tb3:
            search_query = st.text_input(
                "Search",
                value=str(st.session_state.get("docs_search_query", "")),
                key="docs_search_query",
                placeholder="filename...",
            )
        with tb4:
            status_filter = st.selectbox(
                "Статус",
                options=("Все", *all_statuses) if all_statuses else ("Все",),
                index=0,
                key="docs_status_filter",
            )

        if files:
            st.caption(f"Файлов в каталоге: {len(files)}")
            with st.expander("Показать файлы каталога", expanded=False):
                st.code("\n".join(files), language=None)
        else:
            st.caption("Файлы в каталоге пока не найдены.")

        if not doc_rows and not (os.getenv("DATABASE_URL") or "").strip():
            st.caption(
                "Таблица версий недоступна: задайте `DATABASE_URL` для просмотра метаданных."
            )
        elif not doc_rows:
            render_empty_state(
                "В таблице documents пока нет записей или не удалось загрузить данные."
            )
        else:
            query_norm = (search_query or "").strip().lower()
            filtered_docs = doc_rows
            if query_norm:
                filtered_docs = [
                    r
                    for r in filtered_docs
                    if query_norm in str(r.get("filename") or "").lower()
                ]
            if status_filter != "Все":
                filtered_docs = [
                    r
                    for r in filtered_docs
                    if str(r.get("status") or "—").strip() == status_filter
                ]

            if not filtered_docs:
                st.session_state.pop("selected_document", None)
                render_empty_state("Документы по текущему фильтру не найдены.")
                filtered_docs = []

            docs_page, docs_page_size = render_pagination_controls(
                "docs", total_items=len(filtered_docs), has_next=False
            )
            docs_page_items, _, _ = get_paginated_slice(
                filtered_docs, docs_page, docs_page_size
            )
            show_split_selection_toast("docs")
            render_split_pane_titles(
                list_title="Список документов",
                detail_title="Детали выбранного документа",
            )
            list_col, detail_col = split_list_detail_columns()
            selected_doc = str(st.session_state.get("selected_document", ""))
            with list_col:
                st.markdown('<div class="text-list-pane">', unsafe_allow_html=True)
                for idx, dr in enumerate(docs_page_items):
                    doc_key = str(dr.get("document_id") or "")
                    is_selected = bool(selected_doc) and doc_key == selected_doc
                    item_cls = (
                        "rag-list-item rag-list-item-selected"
                        if is_selected
                        else "rag-list-item"
                    )
                    badge_html = (
                        '<span class="rag-selected-badge">выбрано</span>'
                        if is_selected
                        else ""
                    )
                    fname = str(dr.get("filename") or "—")
                    st_label = str(dr.get("status") or "—")
                    active_ver = str(dr.get("active_version") or "—")
                    chunk_n = int(dr.get("active_chunk_count") or 0)
                    chunks = str(chunk_n)
                    chunk_badge = get_doc_chunk_badge(chunk_n)
                    st.markdown(
                        f'<div class="{item_cls}">'
                        '<div class="rag-list-item-head">'
                        f'<div class="rag-list-time">{html.escape(fname)}</div>'
                        f"{badge_html}</div>"
                        f'<div class="route-badge-line">{chunk_badge}</div>'
                        f'<div class="rag-list-fallback">Статус: {html.escape(st_label)}</div>'
                        f'<div class="rag-list-query">Активная версия: {html.escape(active_ver)} · '
                        f'Чанков: {html.escape(chunks)}</div>'
                        "</div>",
                        unsafe_allow_html=True,
                    )
                    if st.button(
                        split_open_button_label(is_selected),
                        key=f"doc_open_{idx}_{doc_key}",
                        help="Открыть детали справа",
                    ):
                        st.session_state["selected_document"] = doc_key
                        flag_split_selection_toast("docs")
                        st.rerun()
                st.markdown("</div>", unsafe_allow_html=True)

            with detail_col:
                reset_invalid_selection(
                    docs_page_items,
                    "selected_document",
                    lambda it: str(it.get("document_id") or ""),
                )
                selected_doc = str(st.session_state.get("selected_document", ""))
                if not selected_doc:
                    render_empty_state("Выберите документ слева.")
                else:
                    selected_row = next(
                        (
                            r
                            for r in docs_page_items
                            if str(r.get("document_id") or "") == selected_doc
                        ),
                        None,
                    )
                    if selected_row is None:
                        st.session_state.pop("selected_document", None)
                        render_empty_state(
                            "Выбранный документ не найден в текущем фильтре."
                        )
                    else:
                        fname = str(selected_row.get("filename") or "документ")
                        active_chunks_n = int(selected_row.get("active_chunk_count") or 0)
                        render_split_selected_summary(
                            short_id=_short_execution_id(selected_doc),
                            status_line=str(selected_row.get("status") or "—"),
                            route_or_type_html=(
                                '<span class="route-badge route-badge--muted">'
                                "Документ</span> "
                                f"{get_doc_chunk_badge(active_chunks_n)}"
                            ),
                            timestamp=_format_dt_moscow_logs(
                                selected_row.get("last_indexed_at")
                            ),
                            preview=fname,
                        )
                        m1, m2, m3, m4 = st.columns(4)
                        m1.metric("Статус", str(selected_row.get("status") or "—"))
                        m2.metric("Активная версия", selected_row.get("active_version") or "—")
                        m3.metric("Чанков (active)", active_chunks_n)
                        m4.metric(
                            "Индексирован",
                            _format_dt_moscow_logs(selected_row.get("last_indexed_at")),
                        )

                        raw_id = selected_row.get("document_id")
                        doc_id: uuid.UUID | None = None
                        if raw_id is not None:
                            try:
                                doc_id = (
                                    raw_id
                                    if isinstance(raw_id, uuid.UUID)
                                    else uuid.UUID(str(raw_id))
                                )
                            except (ValueError, TypeError):
                                doc_id = None

                        with st.expander("Версии документа", expanded=False):
                            if doc_id is None:
                                st.caption("Некорректный document_id.")
                            else:
                                vers = svc.get_document_versions(doc_id)
                                if not vers:
                                    st.caption("Версий не найдено.")
                                else:
                                    vrows = []
                                    for v in vers:
                                        vrows.append(
                                            {
                                                "версия": v.get("version_number"),
                                                "активна": "да" if v.get("is_active") else "нет",
                                                "чанки": v.get("chunk_count"),
                                                "hash": _short_file_hash(v.get("file_hash")),
                                                "indexed_at": _format_dt_moscow_logs(
                                                    v.get("indexed_at")
                                                ),
                                            }
                                        )
                                    st.dataframe(
                                        pd.DataFrame(vrows),
                                        use_container_width=True,
                                        hide_index=True,
                                    )

                        with st.expander("Сэмпл текста с диска (до 256 KiB)", expanded=False):
                            fp = Path(svc.documents_directory) / fname
                            if not fp.is_file():
                                st.caption("Файл не найден в каталоге документов по имени.")
                            else:
                                raw_sample = fp.read_bytes()[:_DISK_SAMPLE_READ_MAX]
                                sample_text = raw_sample.decode("utf-8", errors="replace")
                                sample_est = _estimate_chunks(
                                    sample_text,
                                    chunk_size=rag_cfg.rag_chunk_size,
                                    chunk_overlap=rag_cfg.rag_chunk_overlap,
                                )
                                st.caption(
                                    f"Прочитано байт: {len(raw_sample)} · "
                                    f"оценка чанков по сэмплу: ~{sample_est}"
                                )
                                st.markdown(
                                    '<p class="rag-section-label">Превью сэмпла (обрезано)</p>',
                                    unsafe_allow_html=True,
                                )
                                st.markdown(
                                    f'<div class="doc-chunk-preview">'
                                    f"{html.escape(_truncate_preview(sample_text))}</div>",
                                    unsafe_allow_html=True,
                                )
                                with st.expander("Полный сэмпл (в пределах лимита чтения)", expanded=False):
                                    st.text(sample_text)

                        with st.expander("Raw metadata", expanded=False):
                            st.markdown('<div class="json-dark">', unsafe_allow_html=True)
                            dump = json.dumps(
                                selected_row, ensure_ascii=False, default=str, indent=2
                            )
                            if len(dump) <= _RAW_METADATA_JSON_MAX:
                                st.code(dump, language="json")
                            else:
                                st.code(
                                    dump[:_RAW_METADATA_JSON_MAX] + "\n…",
                                    language="json",
                                )
                                st.caption(
                                    f"Сокращённый просмотр: {_RAW_METADATA_JSON_MAX} символов из {len(dump)}."
                                )
                                with st.expander("Полный JSON (может быть тяжёлым для UI)", expanded=False):
                                    st.code(dump, language="json")
                            st.markdown("</div>", unsafe_allow_html=True)

    with tab_logs:
        st.subheader("Логи")
        st.caption(
            "Операторская консоль аудита: слева — журнал execution-сессий, справа — трассировка "
            "событий (MSK). Технические raw details — только в свёртках."
        )
        total_exec = int(svc.get_logs_execution_ids_total())
        if total_exec <= 0:
            render_empty_state("Событий журнала пока нет.")
        else:
            logs_page = int(st.session_state.get("logs_page", 0))
            logs_page_size_seed = int(st.session_state.get("logs_page_size", 50))
            logs_page, logs_page_size = render_pagination_controls(
                "logs",
                total_items=int(total_exec),
                has_next=(logs_page + 1) * logs_page_size_seed < int(total_exec),
                page_size_label="Сколько запросов показать",
            )
            exec_page, total_exec = svc.get_logs_execution_ids_page(
                page=logs_page,
                page_size=logs_page_size,
            )
            execution_ids = [str(x.get("execution_id") or "") for x in exec_page]
            rows = svc.get_logs_events_for_execution_ids(execution_ids)
            groups = group_logs_by_execution_id(rows)
            order_map = {eid: i for i, eid in enumerate(execution_ids)}
            groups.sort(key=lambda g: order_map.get(g[0], 10**9))
            page_sessions = _logs_build_session_rows(groups)
            st.caption(f"Показано запросов: {len(page_sessions)} из {int(total_exec)}")

            show_split_selection_toast("logs")
            render_split_pane_titles(
                list_title="Журнал execution-сессий",
                detail_title="Трассировка выбранной execution-сессии",
            )
            list_col, detail_col = split_list_detail_columns()
            selected_logs_eid = str(
                st.session_state.get("selected_logs_execution_id", "")
            )
            with list_col:
                st.markdown('<div class="logs-list-pane">', unsafe_allow_html=True)
                for idx, sess in enumerate(page_sessions):
                    eid = str(sess.get("execution_id") or "")
                    last_at = sess.get("last_at")
                    events = sess.get("events") or []
                    if not isinstance(events, list):
                        events = []
                    route_n = _logs_infer_route_from_events(events)
                    status_s = _logs_session_final_status(events)
                    preview = _logs_session_preview(events) or "—"
                    n_ev = len(events)
                    dur_s = _logs_format_duration_ms(
                        _logs_session_wall_duration_ms(events)
                    )
                    max_lat = _logs_session_max_step_latency_ms(events)
                    lat_part = (
                        f" · макс. шаг: {max_lat} мс"
                        if max_lat is not None
                        else ""
                    )
                    is_selected = bool(selected_logs_eid) and eid == selected_logs_eid
                    item_cls = (
                        "rag-list-item logs-session-card rag-list-item-selected"
                        if is_selected
                        else "rag-list-item logs-session-card"
                    )
                    badge_sel = (
                        '<span class="rag-selected-badge">выбрано</span>'
                        if is_selected
                        else ""
                    )
                    eid_short = _short_execution_id(eid)
                    dt_label = _format_dt_moscow_logs(last_at)
                    st.markdown(
                        f'<div class="{item_cls}">'
                        '<div class="rag-list-item-head">'
                        f'<div class="rag-list-time">{html.escape(dt_label)}</div>'
                        f"{badge_sel}</div>"
                        '<div class="logs-session-badges-row">'
                        f'<div class="route-badge-line">'
                        f"{get_route_badge(route_n)} {get_log_status_badge(status_s)}"
                        "</div></div>"
                        f'<div class="rag-list-query">{html.escape(preview)}</div>'
                        '<div class="logs-session-meta">'
                        f'<code class="log-eid-short">{html.escape(eid_short)}</code>'
                        f" · событий: {n_ev}"
                        f" · длит.: {html.escape(dur_s)}"
                        f"{lat_part if lat_part else ''}"
                        "</div>"
                        "</div>",
                        unsafe_allow_html=True,
                    )
                    if st.button(
                        split_open_button_label(is_selected),
                        key=f"logs_open_{idx}_{eid}",
                        help="Открыть детали справа",
                    ):
                        st.session_state["selected_logs_execution_id"] = eid
                        flag_split_selection_toast("logs")
                        st.rerun()
                st.markdown("</div>", unsafe_allow_html=True)

            with detail_col:
                reset_invalid_selection(
                    page_sessions,
                    "selected_logs_execution_id",
                    lambda s: str(s.get("execution_id") or ""),
                )
                selected_logs_eid = str(
                    st.session_state.get("selected_logs_execution_id", "")
                )
                if not selected_logs_eid:
                    render_empty_state("Выберите execution-сессию слева.")
                else:
                    selected_sess = next(
                        (
                            s
                            for s in page_sessions
                            if str(s.get("execution_id") or "") == selected_logs_eid
                        ),
                        None,
                    )
                    if selected_sess is None:
                        st.session_state.pop("selected_logs_execution_id", None)
                        render_empty_state("Выберите execution-сессию слева.")
                    else:
                        _render_logs_timeline_detail(
                            selected_sess,
                            show_session_header=True,
                        )


main()
