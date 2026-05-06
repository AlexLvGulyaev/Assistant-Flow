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


# Человекочитаемые названия этапов/типов событий (processing_logs.stage/event_type)
_EVENT_TYPE_ALIASES: dict[str, str] = {
    "text_answer_done": "processing_done",
    "rag_answer_done": "processing_done",
    "image_answer_done": "processing_done",
    "rag_response": "processing_done",
}

_EVENT_TYPE_RU: dict[str, str] = {
    "intake_received": "Получено сообщение",
    "route_selected": "Определён тип запроса",
    "processing_done": "Обработка завершена",
    "processing_error": "Ошибка обработки",
    "database_schema": "Служебное событие схемы БД",
    "admin_document_uploaded": "Загрузка документа (админка)",
    "admin_reindex_started": "Переиндексация запущена",
    "admin_reindex_done": "Переиндексация завершена",
    "admin_reindex_error": "Ошибка переиндексации",
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


def _stage_to_action(stage: str | None) -> str:
    raw = (stage or "").strip()
    if raw == "text_answer_done":
        return "Текстовый ответ построен"
    if raw == "rag_answer_done":
        return "RAG-ответ построен"
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
        "действие": _stage_to_action(r.get("stage")),
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
LOGS_LIST_PREVIEW_MAX = 140
LOGS_EXEC_ID_SHORT_LEN = 8


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
    parts = [_stage_to_action(ev.get("stage")) for ev in events]
    return " → ".join(parts)


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


def _render_logs_timeline_detail(
    session: dict[str, Any],
    *,
    show_session_header: bool = True,
) -> None:
    """Правая панель: опциональный заголовок + читаемая цепочка + карточки событий."""
    eid = str(session.get("execution_id") or "—")
    events: list[dict[str, Any]] = session.get("events") or []
    if not isinstance(events, list):
        events = []
    last_at = session.get("last_at")
    route_raw = _logs_infer_route_from_events(events)
    status_s = _logs_session_final_status(events)
    flow_ru = _logs_timeline_flow_ru(events)

    if show_session_header:
        st.markdown(
            f"**Сессия:** {_format_dt_moscow_logs(last_at)} · "
            f"{get_route_badge(route_raw)} {get_log_status_badge(status_s)}",
            unsafe_allow_html=True,
        )
        st.markdown(
            f"<small>execution_id: <code>{html.escape(eid)}</code></small>",
            unsafe_allow_html=True,
        )
    if flow_ru and flow_ru.replace(" → ", "").strip():
        st.markdown(
            f'<div class="log-timeline-flow">{html.escape(flow_ru)}</div>',
            unsafe_allow_html=True,
        )

    st.markdown("**События**", unsafe_allow_html=True)
    for idx, ev in enumerate(events, 1):
        details = ev.get("details")
        details_dict: dict[str, Any] = details if isinstance(details, dict) else {}
        t_s = _format_dt_moscow_logs(ev.get("created_at"))
        action = _stage_to_action(str(ev.get("stage") or ""))
        st_l = get_russian_status(str(ev.get("status") or ""))
        preview = _details_to_description(details, max_len=LOGS_DETAILS_PREVIEW_MAX)
        tone = _status_tone(str(ev.get("status") or ""))
        st.markdown(
            f'<div class="log-timeline-card log-timeline-card--{tone}">'
            f'<div class="log-timeline-card-head">'
            f'<span class="log-timeline-idx">{idx}</span>'
            f'<span class="log-timeline-time">{html.escape(t_s)}</span>'
            "</div>"
            f'<div class="log-timeline-action">{html.escape(action)}</div>'
            f'<div class="log-timeline-status">{html.escape(st_l)}</div>'
            f'<div class="log-timeline-preview">{html.escape(preview)}</div>'
            "</div>",
            unsafe_allow_html=True,
        )
        with st.expander("Показать JSON", expanded=False):
            st.markdown('<div class="json-dark">', unsafe_allow_html=True)
            dump = json.dumps(details_dict, ensure_ascii=False, default=str, indent=2)
            st.code(dump, language="json")
            st.markdown("</div>", unsafe_allow_html=True)


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
    t1, t2 = st.columns((0.35, 0.65))
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
    with st.expander("Показать JSON", expanded=False):
        details_dump = json.dumps(
            details_dict,
            ensure_ascii=False,
            indent=2,
        )
        st.markdown(
            '<div class="json-dark">',
            unsafe_allow_html=True,
        )
        st.code(details_dump, language="json")
        st.markdown("</div>", unsafe_allow_html=True)

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
    with st.expander("Показать JSON", expanded=False):
        details_dump = json.dumps(details_dict, ensure_ascii=False, indent=2)
        st.markdown('<div class="json-dark">', unsafe_allow_html=True)
        st.code(details_dump, language="json")
        st.markdown("</div>", unsafe_allow_html=True)

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
                "этап": _stage_to_action(str(ev.get("stage") or "")),
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
        tab_docs,
        tab_logs,
    ) = st.tabs(
        ("Обзор", "Сводка", "Text-запросы", "RAG-запросы", "Документы", "Логи")
    )

    status = svc.get_knowledge_base_status()
    insights = svc.get_overview_insights()
    fs_txt_count = svc.get_documents_filesystem_count()
    dashboard_stats = svc.get_dashboard_stats(hours=24)

    with tab_overview:
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
            ls_action = _stage_to_action(last_succ.get("stage"))
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

        card_a = (
            '<div class="ops-dashboard-card">'
            '<div class="ops-dashboard-card-title">A. Состояние системы</div>'
            + _overview_ops_kv_mixed(
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
            )
            + _render_panel_footnote_html(
                "Chroma: только число записей в коллекции; сбои клиента могут дать 0 без "
                "отдельного статуса. Telegram из UI не проверяется."
            )
            + "</div>"
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

        card_b = (
            '<div class="ops-dashboard-card">'
            '<div class="ops-dashboard-card-title">B. AI-активность</div>'
            + activity_inner
            + _render_panel_footnote_html(
                "Text/RAG/Image — уникальные <code>execution_id</code> за 24 ч с нормализацией "
                "<code>route</code>/<code>mode</code>/<code>stage</code> (как в SQL "
                "<code>count_routes_since</code>)."
            )
            + "</div>"
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
        card_c = (
            '<div class="ops-dashboard-card">'
            '<div class="ops-dashboard-card-title">C. База знаний</div>'
            + _overview_ops_kv_html(kb_rows_plain)
            + '<div class="ops-inline-badge-row">'
            + sync_badge
            + "</div>"
            + _render_panel_footnote_html(
                "Метрики из <code>get_knowledge_base_status</code> и сводки документов; "
                "при расхождении чанков PostgreSQL и Chroma нужна переиндексация."
            )
            + "</div>"
        )

        card_d = (
            '<div class="ops-dashboard-card">'
            '<div class="ops-dashboard-card-title">D. Администрирование / безопасность</div>'
            + _overview_ops_kv_mixed(
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
            )
            + _render_panel_footnote_html(
                "Без реальной авторизации панель не считается защищённой."
            )
            + "</div>"
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
                '<div class="ops-dashboard-card ops-dashboard-card--warn" '
                'style="margin-top:10px;">'
                '<div class="ops-dashboard-card-title">Предупреждение синхронизации</div>'
                "<ul style=\"margin:0;padding-left:1.1rem;\">"
                + "".join(f"<li>{w}</li>" for w in warn_blocks)
                + "</ul></div>"
            )

        overview_html = (
            '<div class="ops-dashboard-wrap">'
            '<p class="ops-dashboard-intro">'
            "Компактный операционный дашборд: здоровье сервисов (честные статусы), "
            "активность AI, база знаний и ограничения безопасности админки."
            "</p>"
            '<div class="ops-dashboard-grid">'
            f"{card_a}{card_b}{card_c}{card_d}"
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

    with tab_summary:
        st.markdown(
            '<p class="ops-dashboard-intro">Операционная аналитика за последние 24 часа '
            "(компактные карточки; сырые таблицы — внизу, в свёртке).</p>",
            unsafe_allow_html=True,
        )
        if not (os.getenv("DATABASE_URL") or "").strip():
            st.info(
                "Сводка недоступна: задайте переменную окружения `DATABASE_URL` "
                "и убедитесь, что таблица `processing_logs` заполняется."
            )
        elif int(dashboard_stats.get("total_events") or 0) == 0:
            st.info(
                "За последние 24 часа в `processing_logs` нет записей. "
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

            card_a = (
                '<div class="ops-dashboard-card">'
                '<div class="ops-dashboard-card-title">A. Сводка активности</div>'
                + activity_chips
                + _render_panel_footnote_html(
                    "Агрегаты событий — из <code>get_dashboard_stats</code> (24 ч). "
                    "Уникальные <code>execution_id</code> — только по сессиям в выборке "
                    f"(до {SUMMARY_LOG_SAMPLE_CAP} последних строк журнала, отфильтровано по 24 ч); "
                    "полный DISTINCT по окну в UI без нового API недоступен."
                )
                + "</div>"
            )

            route_body = _summary_route_rows_html(
                by_route=by_route,
                sample_out=sample_out,
                unknown_sample_n=unknown_sample_n,
            )
            card_b = (
                '<div class="ops-dashboard-card">'
                '<div class="ops-dashboard-card-title">B. Маршруты</div>'
                + route_body
                + _render_panel_footnote_html(
                    "Счётчики Text / RAG / Image — уникальные <code>execution_id</code> за 24 ч "
                    "с нормализацией route/mode/stage (как в SQL <code>count_routes_since</code>). "
                    "Доля — от суммы Text+RAG+Image+«прочее» в выборке. "
                    "Успех/ошибка по маршруту — по итогу сессии в этой выборке (см. "
                    "<code>_logs_infer_route_from_events</code> / "
                    "<code>_logs_session_final_status</code>)."
                )
                + "</div>"
            )

            card_c = (
                '<div class="ops-dashboard-card">'
                '<div class="ops-dashboard-card-title">C. Этапы / lifecycle</div>'
                + _summary_lifecycle_list_html(by_stage)
                + _render_panel_footnote_html(
                    "Числа — сырые <code>stage</code> из журнала за 24 ч; подписи через "
                    "существующие хелперы нормализации."
                )
                + "</div>"
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

            card_d = (
                '<div class="ops-dashboard-card">'
                '<div class="ops-dashboard-card-title">D. Провайдеры и производительность</div>'
                + _overview_ops_kv_mixed(
                    [
                        _overview_ops_kv_item("Топ provider / model", tpm_line),
                        _overview_ops_kv_item("Токены (сумма по details)", tok_line),
                        _overview_ops_kv_item("Средняя latency", avg_line),
                        _overview_ops_kv_item("Макс. latency", max_line),
                    ]
                )
                + '<span class="panel-footnote-heading">Строки журнала по провайдеру</span>'
                + prov_html
                + _render_panel_footnote_html(
                    "По строкам журнала за 24 ч в выборке (поля <code>details</code>). "
                    "Если в логах нет provider/tokens/latency — отображается «нет данных»."
                )
                + "</div>"
            )

            summary_html = (
                '<div class="ops-dashboard-wrap">'
                '<div class="ops-dashboard-grid">'
                f"{card_a}{card_b}{card_c}{card_d}"
                "</div></div>"
            )
            st.markdown(summary_html, unsafe_allow_html=True)

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
                    st.info("Нет данных по маршрутам за выбранный период.")

    with tab_text:
        st.subheader("Text-запросы")
        st.caption("Обычные LLM-запросы без RAG-контекста.")
        if not (os.getenv("DATABASE_URL") or "").strip():
            st.info(
                "Раздел недоступен: задайте переменную окружения `DATABASE_URL` "
                "и убедитесь, что таблица `processing_logs` заполняется."
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
                st.info("Text-запросов за период пока нет.")
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
                list_col, detail_col = st.columns((0.35, 0.65))
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
                        st.info("Выберите Text-запрос слева")
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
                            st.info(
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
            st.info(
                "Раздел недоступен: задайте переменную окружения `DATABASE_URL` "
                "и убедитесь, что таблица `processing_logs` заполняется."
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
                st.info("RAG-события по выбранному фильтру не найдены.")
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
                list_col, detail_col = st.columns((0.35, 0.65))
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
                        st.info("Выберите RAG-запрос слева")
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
                            st.info(
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
            st.info("В таблице `documents` пока нет записей или не удалось загрузить данные.")
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
                st.info("Документы по текущему фильтру не найдены.")
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
            list_col, detail_col = st.columns((0.35, 0.65))
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
                    st.info("Выберите документ слева")
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
                        st.info("Выбранный документ не найден в текущем фильтре.")
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
            "Журнал обработки: одна строка списка = сессия (`execution_id`). "
            "Справа — timeline событий по времени (MSK)."
        )
        total_exec = int(svc.get_logs_execution_ids_total())
        if total_exec <= 0:
            st.info("Событий журнала пока нет.")
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
                list_title="Список сессий (execution_id)",
                detail_title="Детали выбранной сессии",
            )
            list_col, detail_col = st.columns((0.35, 0.65))
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
                    is_selected = bool(selected_logs_eid) and eid == selected_logs_eid
                    item_cls = (
                        "rag-list-item rag-list-item-selected"
                        if is_selected
                        else "rag-list-item"
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
                        f'<div class="route-badge-line">'
                        f'<code class="log-eid-short">{html.escape(eid_short)}</code> '
                        f"{get_route_badge(route_n)} {get_log_status_badge(status_s)}"
                        "</div>"
                        f'<div class="rag-list-query">{html.escape(preview)}</div>'
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
                    st.info("Выберите запрос слева.")
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
                        st.info("Выберите запрос слева.")
                    else:
                        evs = selected_sess.get("events") or []
                        if not isinstance(evs, list):
                            evs = []
                        route_n = _logs_infer_route_from_events(evs)
                        status_s = _logs_session_final_status(evs)
                        pv = _logs_session_preview(evs) or "—"
                        render_split_selected_summary(
                            short_id=_short_execution_id(selected_logs_eid),
                            status_line=get_russian_status(status_s),
                            route_or_type_html=(
                                f"{get_route_badge(route_n)} "
                                f"{get_log_status_badge(status_s)}"
                            ),
                            timestamp=_format_dt_moscow_logs(
                                selected_sess.get("last_at")
                            ),
                            preview=pv,
                        )
                        _render_logs_timeline_detail(
                            selected_sess,
                            show_session_header=False,
                        )


main()
