"""
Streamlit admin UI for RAG (documents, reindex, status, logs).

Run from repository root:
  streamlit run admin_ui/app.py
"""

from __future__ import annotations

import html
import json
import os
import sys
import uuid
from collections import defaultdict
from datetime import datetime, timezone
import zoneinfo
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import streamlit as st

from services.admin_service import AdminService

moscow_tz = zoneinfo.ZoneInfo("Europe/Moscow")


@st.cache_resource
def _admin_service() -> AdminService:
    return AdminService()


# Человекочитаемые названия этапов (processing_logs.stage)
_STAGE_ACTION_RU: dict[str, str] = {
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

_ROUTE_LABEL_RU: dict[str, str] = {
    "rag": "RAG",
    "text": "Текст",
    "image_generation": "Генерация изображений",
}


def _stage_to_action(stage: str | None) -> str:
    if not stage:
        return "—"
    return _STAGE_ACTION_RU.get(stage, stage)


_STATUS_RU: dict[str, str] = {
    "success": "успешно",
    "error": "ошибка",
    "skipped": "пропущено",
    "retry": "повтор",
    "started": "запущено",
}


def _status_label(raw: str | None) -> str:
    if not raw:
        return "—"
    return _STATUS_RU.get(raw.strip().lower(), raw)


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
        [data-testid="stHeader"] {
          position: sticky !important;
          top: 0 !important;
          z-index: 1000 !important;
          border-bottom: 1px solid var(--border) !important;
        }

        .main .block-container {
          padding-top: 0.15rem !important;
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
          background: var(--bg-card);
          border: 1px solid var(--border);
          border-radius: 10px;
          padding: 6px 10px;
          margin: 0 0 6px 0;
        }
        .topbar-updated {
          font-size: 0.76rem;
          color: var(--text-secondary) !important;
          text-align: right;
          margin-top: 3px;
        }
        h1 {
          margin-top: 0 !important;
          margin-bottom: 0.05rem !important;
          padding-top: 0 !important;
          font-size: 1.28rem !important;
          line-height: 1.2 !important;
        }
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
          position: sticky;
          top: 48px;
          z-index: 999;
          background: var(--bg-main);
          padding-top: 2px;
          border-bottom: 1px solid var(--border);
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
    top_left, top_right = st.columns((3.3, 1))
    with top_left:
        st.markdown(
            '<h1 class="compact-title">Assistant Flow — Админ-панель</h1>',
            unsafe_allow_html=True,
        )
        st.markdown(
            f'<div class="compact-subtitle">Файлы базы знаний: <code>{svc.documents_directory}</code></div>',
            unsafe_allow_html=True,
        )
    with top_right:
        b1, b2 = st.columns(2)
        with b1:
            if st.button("Обновить", key="topbar_refresh"):
                st.rerun()
        with b2:
            if st.button("Выход", key="topbar_logout"):
                st.warning(
                    "Авторизация пока не подключена. Кнопка выхода зарезервирована."
                )
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
        tab_index,
        tab_logs,
    ) = st.tabs(
        ("Обзор", "Сводка", "Text-запросы", "RAG-запросы", "Документы", "Индексация", "Логи")
    )

    status = svc.get_knowledge_base_status()
    insights = svc.get_overview_insights()
    fs_txt_count = svc.get_documents_filesystem_count()
    dashboard_stats = svc.get_dashboard_stats(hours=24)

    with tab_overview:
        st.write("Краткий статус базы знаний и обработки запросов.")

        st.subheader("Статус системы")
        sys_col1, sys_col2 = st.columns(2)
        if insights.db_logs_available:
            if insights.errors_last_24h == 0:
                sys_col1.markdown("**Система:** Работает")
            else:
                sys_col1.markdown("**Система:** обнаружены ошибки в журнале за сутки")
            sys_col2.metric(
                "Ошибки (последние 24 часа)",
                insights.errors_last_24h,
            )
        else:
            sys_col1.markdown("**Система:** нет данных о логах (проверьте подключение к БД)")
            sys_col2.metric("Ошибки (последние 24 часа)", "—")

        st.subheader("База знаний и синхронизация индекса")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric(
            "Документов в БД",
            status.postgres_documents if status.postgres_available else "—",
        )
        c2.metric("Файлов в каталоге", fs_txt_count)
        c3.metric(
            "Чанков в PostgreSQL",
            status.postgres_chunks_sum if status.postgres_available else "—",
        )
        c4.metric("Чанков в Chroma", status.collection_count)

        if (
            status.postgres_available
            and status.postgres_documents is not None
            and status.postgres_documents != fs_txt_count
        ):
            st.warning(
                "⚠ Рассинхронизация: база данных и файловая система не совпадают"
            )

        if status.postgres_available and status.postgres_chunks_sum is not None:
            if status.postgres_chunks_sum != status.collection_count:
                st.warning("⚠ Индекс устарел — требуется переиндексация")
            else:
                st.success("Индекс актуален")
        else:
            st.caption(
                "Сравнение PostgreSQL и Chroma недоступно: задайте `DATABASE_URL` "
                "и дождитесь заполнения метаданных документов."
            )

        st.subheader("Активность за последние 24 часа")
        if insights.db_logs_available:
            ac1, ac2 = st.columns(2)
            ac1.metric(
                "Завершённых обработок (processing_done)",
                insights.processing_done_last_24h,
            )
            ac2.metric(
                "Ошибок обработки (processing_error)",
                insights.errors_last_24h,
            )
        else:
            st.caption("Нет данных из `processing_logs`.")

        st.subheader("Последнее событие")
        if insights.db_logs_available and (
            insights.last_event_at is not None or insights.last_event_stage
        ):
            action = _stage_to_action(insights.last_event_stage)
            ts = _format_dt(insights.last_event_at)
            st.write(f"**{ts}** — {action}")
        else:
            st.caption("Событий пока нет или журнал недоступен.")

        if not status.postgres_available:
            st.info(
                "Чтобы видеть документы и чанки в PostgreSQL, задайте `DATABASE_URL` "
                "и примените схему из каталога `database/`."
            )

    with tab_summary:
        st.subheader("Активность за последние 24 часа")
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
            m1, m2, m3 = st.columns(3)
            m4, m5, m6 = st.columns(3)
            m1.metric("Всего событий", dashboard_stats["total_events"])
            m2.metric("Успешных", dashboard_stats["success_events"])
            m3.metric("Ошибок", dashboard_stats["error_events"])
            m4.metric("Админских операций", dashboard_stats["admin_events"])
            m5.metric("Генераций изображений", dashboard_stats["image_generations"])
            m6.metric("Переиндексаций", dashboard_stats["reindex_runs"])

            st.markdown("**События по статусам**")
            by_status = dashboard_stats.get("by_status") or {}
            if by_status:
                rows_s = [
                    {"статус": _status_label(k), "количество": v}
                    for k, v in sorted(by_status.items(), key=lambda x: (-x[1], x[0]))
                ]
                df_s = pd.DataFrame(rows_s)
                st.dataframe(df_s, use_container_width=True, hide_index=True)
            else:
                st.caption("Нет данных по статусам.")

            st.markdown("**События по этапам**")
            by_stage = dashboard_stats.get("by_stage") or {}
            if by_stage:
                rows_st = [
                    {
                        "этап": _stage_to_action(k),
                        "количество": v,
                    }
                    for k, v in sorted(by_stage.items(), key=lambda x: (-x[1], x[0]))
                ]
                df_st = pd.DataFrame(rows_st)
                st.dataframe(df_st, use_container_width=True, hide_index=True)
            else:
                st.caption("Нет данных по этапам.")

            st.markdown(
                "**Запросы по маршрутам** "
                "(этапы `route_selected` / `processing_done`, поле `route` в `details`)"
            )
            by_route = dashboard_stats.get("by_route") or {}
            route_total = sum(int(by_route.get(k, 0)) for k in ("rag", "text", "image_generation"))
            if route_total > 0:
                rows_r = [
                    {
                        "маршрут": _ROUTE_LABEL_RU.get(k, k),
                        "количество": int(by_route.get(k, 0)),
                    }
                    for k in ("rag", "text", "image_generation")
                ]
                df_r = pd.DataFrame(rows_r)
                st.dataframe(df_r, use_container_width=True, hide_index=True)
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
            text_rows = svc.get_recent_route_events("text", limit=50)
            if not text_rows:
                st.info("Text-запросов за период пока нет.")
            else:
                table_rows = [
                    {
                        "время": _format_dt_moscow_logs(r.get("created_at")),
                        "execution_id": r.get("execution_id") or "—",
                        "status": _status_label(str(r.get("status") or "")),
                        "details": _details_to_description(r.get("details"), max_len=600),
                    }
                    for r in text_rows
                ]
                st.dataframe(pd.DataFrame(table_rows), use_container_width=True, hide_index=True)

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
            limit_recent = int(
                rf2.selectbox(
                    "Сколько показать",
                    options=(10, 20, 50),
                    index=2,
                    key="rag_recent_limit",
                )
            )
            fallback_filter = None if selected_fallback == "Все" else selected_fallback
            recent_rag = svc.get_recent_rag_events(
                limit=limit_recent,
                fallback_reason=fallback_filter,
            )
            if not recent_rag:
                st.info("RAG-события по выбранному фильтру не найдены.")
            else:
                for ev in recent_rag:
                    dt_label = _format_dt_moscow_logs(ev.get("created_at"))
                    fb = str(ev.get("fallback_reason") or "none")
                    query_preview = str(ev.get("query_preview") or "—")
                    title = f"{dt_label} · {fb} · {query_preview}"
                    with st.expander(title, expanded=False):
                        details = ev.get("details")
                        details_dict: dict[str, Any] = (
                            details if isinstance(details, dict) else {}
                        )
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
                            retrieved_chunks = [
                                c for c in raw_chunks if isinstance(c, dict)
                            ]
                        used_chunks = [
                            c for c in retrieved_chunks if c.get("passed_filter")
                        ]
                        dropped_chunks = [
                            c for c in retrieved_chunks if not c.get("passed_filter")
                        ]

                        if not retrieved_chunks:
                            st.caption("Фрагменты не сохранены для этого события.")
                        else:
                            st.markdown(
                                '<p class="rag-section-label">Использованы в ответе</p>',
                                unsafe_allow_html=True,
                            )
                            if not used_chunks:
                                st.caption(
                                    "Нет фрагментов, прошедших порог релевантности."
                                )
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

    with tab_docs:
        st.write(
            "Загрузите .txt-файлы в базу знаний. После загрузки выполните переиндексацию."
        )
        uploaded = st.file_uploader("Файл (.txt)", type=["txt"])
        if uploaded is not None and st.button("Сохранить файл", key="save_upload"):
            try:
                dest = svc.save_uploaded_txt(uploaded.name, uploaded.getvalue())
                st.success(f"Файл сохранён: `{dest}`")
            except ValueError as exc:
                st.error(str(exc))

        st.divider()
        st.write("**Файлы в каталоге документов:**")
        files = svc.list_documents()
        if files:
            st.code("\n".join(files), language=None)
        else:
            st.info("Подходящих файлов пока нет.")

        st.divider()
        st.subheader("Документы в базе данных и версии")
        doc_rows = svc.get_documents_with_versions()
        if not doc_rows and not (os.getenv("DATABASE_URL") or "").strip():
            st.caption(
                "Таблица версий недоступна: задайте `DATABASE_URL` для просмотра метаданных."
            )
        elif not doc_rows:
            st.info("В таблице `documents` пока нет записей или не удалось загрузить данные.")
        else:
            table_data: list[dict[str, Any]] = []
            for dr in doc_rows:
                table_data.append(
                    {
                        "filename": dr.get("filename") or "—",
                        "status": dr.get("status") or "—",
                        "active_version": dr.get("active_version"),
                        "versions_count": dr.get("versions_count"),
                        "active_chunk_count": dr.get("active_chunk_count"),
                        "last_indexed_at": _format_dt_moscow_logs(
                            dr.get("last_indexed_at")
                        ),
                    }
                )
            df_docs = pd.DataFrame(table_data)
            df_docs = df_docs[
                [
                    "filename",
                    "status",
                    "active_version",
                    "versions_count",
                    "active_chunk_count",
                    "last_indexed_at",
                ]
            ]
            st.dataframe(df_docs, use_container_width=True, hide_index=True)

            for dr in doc_rows:
                raw_id = dr.get("document_id")
                if raw_id is None:
                    continue
                try:
                    doc_id = (
                        raw_id
                        if isinstance(raw_id, uuid.UUID)
                        else uuid.UUID(str(raw_id))
                    )
                except (ValueError, TypeError):
                    continue
                fname = str(dr.get("filename") or "документ")
                with st.expander(
                    f"Версии документа · {fname}",
                    expanded=False,
                ):
                    vers = svc.get_document_versions(doc_id)
                    if not vers:
                        st.caption("Версий не найдено.")
                    else:
                        vrows = []
                        for v in vers:
                            vrows.append(
                                {
                                    "version_number": v.get("version_number"),
                                    "is_active": v.get("is_active"),
                                    "chunk_count": v.get("chunk_count"),
                                    "file_hash": _short_file_hash(v.get("file_hash")),
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

    with tab_index:
        st.write(
            "Переиндексация очищает текущую Chroma-коллекцию и заново строит индекс по документам."
        )
        if st.button("Запустить переиндексацию", type="primary", key="run_reindex"):
            with st.spinner("Идёт переиндексация…"):
                result = svc.run_reindex()
            if result.success:
                st.success("**Статус:** переиндексация выполнена успешно.")
            else:
                st.error("**Статус:** переиндексация завершилась с ошибкой или не для всех файлов.")
            st.metric("Чанков в коллекции Chroma", result.collection_count)
            if result.error_message:
                st.warning(result.error_message)

    with tab_logs:
        st.write(
            "Журнал обработки: записи сгруппированы по запросу (`execution_id`). "
            "Внутри группы — цепочка событий по времени."
        )
        limit = st.selectbox(
            "Сколько записей журнала загрузить",
            options=(20, 50, 100),
            index=1,
            key="logs_limit",
        )
        rows = svc.get_recent_logs(limit=int(limit))
        if not rows:
            st.info(
                "Записей нет. Нужны подключение к базе и таблица `processing_logs`."
            )
        else:
            groups = group_logs_by_execution_id(rows)
            for eid, start_ts, events in groups:
                title = (
                    f"Запрос от {_format_dt_moscow_logs(start_ts)} · `{eid}`"
                    if start_ts is not None
                    else f"Запрос · `{eid}`"
                )
                with st.expander(title, expanded=False):
                    st.caption("Цепочка событий по времени:")
                    st.markdown("↓")
                    display_rows = [_event_display_row(r) for r in events]
                    df = pd.DataFrame(display_rows)
                    df = df[["время", "действие", "статус", "описание"]]
                    st.dataframe(df, use_container_width=True, hide_index=True)


main()
