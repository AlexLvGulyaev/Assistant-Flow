"""
Консервативная очистка текста после извлечения из PDF (до общего text_cleaner).

Правила только для **полных строк** (после strip сравнение с шаблоном `^...$`),
без lowercasing всего документа. Не вызывается для TXT/HTML.
"""

from __future__ import annotations

import re
from typing import Pattern

# --- Полная строка: колонтитулы / номера страниц (RU/EN) ---
_PAGE_LINE_PATTERNS: tuple[Pattern[str], ...] = (
    re.compile(r"^\s*страница\s+\d+\s+из\s+\d+\s*$", re.IGNORECASE),
    re.compile(r"^\s*стр\.?\s*\d+\s*(из\s*\d+)?\s*$", re.IGNORECASE),
    re.compile(r"^\s*page\s+\d+(\s+of\s+\d+)?\s*$", re.IGNORECASE),
    re.compile(r"^\s*page\s+\d+\s*/\s*\d+\s*$", re.IGNORECASE),
    re.compile(r"^\s*-\s*\d+\s*-\s*$"),
    re.compile(r"^\s*page\s+\d+\s*$", re.IGNORECASE),
)

# --- Служебный шум / реклама / короткие промо-строки ---
_MISC_JUNK: tuple[Pattern[str], ...] = (
    re.compile(r"^\s*footer\s+noise", re.IGNORECASE),
    re.compile(r"^\s*реклама\s*$", re.IGNORECASE),
    re.compile(r"^\s*(advertisement|sponsored\s+content|рекламный\s+материал)\s*$", re.IGNORECASE),
    re.compile(r"^\s*(subscribe|подпишитесь|unsubscribe|отписаться)\s*$", re.IGNORECASE),
)

# --- Header/footer однострочный шум ---
_HEADER_FOOTER: tuple[Pattern[str], ...] = (
    re.compile(r"^\s*header\s+noise", re.IGNORECASE),
    re.compile(
        r"^\s*(all\s+rights\s+reserved|все\s+права\s+защищены)\s*([™®]?\s*)?$",
        re.IGNORECASE,
    ),
    re.compile(r"^\s*(cookie|cookies)\s+(policy|settings|preferences)\s*$", re.IGNORECASE),
    re.compile(r"^\s*(privacy\s+policy|политика\s+конфиденциальности)\s*$", re.IGNORECASE),
    re.compile(
        r"^\s*(terms\s+(of\s+)?(use|service)|пользовательское\s+соглашение)\s*$",
        re.IGNORECASE,
    ),
    re.compile(r"^\s*(follow\s+us|follow|подписаться)\s+(@\w+)?\s*$", re.IGNORECASE),
    re.compile(r"^\s*(download|скачать)\s+(pdf|документ)\s*$", re.IGNORECASE),
)

# Только «украшение» строки (тире, точки, пробелы)
_DECOR_ONLY = re.compile(r"^[\s.\u00b7\-_=~·‧]{6,}$")

# --- Навигация: только «крошки» с известным первым сегментом и ≥2 символов `>` ---
_NAV_HEAD = re.compile(
    r"^\s*(home|главная|main|меню|archive|архив|news|новости|docs|документация|"
    r"catalog|каталог|search|поиск|shop|магазин|products|товары|about|о\s+нас|login|войти)\s*>",
    re.IGNORECASE,
)


def _is_breadcrumb_noise(line: str) -> bool:
    s = line.strip()
    if len(s) > 160 or s.count(">") < 2:
        return False
    return bool(_NAV_HEAD.match(s))


def _is_social_or_link_only_line(line: str) -> bool:
    """Строка почти целиком из URL/соц. ссылок (короткая)."""
    s = line.strip()
    if len(s) > 220 or ("http://" not in s and "https://" not in s):
        return False
    rest = re.sub(r"https?://\S+", "", s)
    rest = re.sub(r"\s+", "", rest)
    return len(rest) <= 14


_SUPPORT_LINE_RES: tuple[Pattern[str], ...] = (
    re.compile(r"^\s*technical\s+support\s*([.:]?\s*)?$", re.IGNORECASE),
    re.compile(r"^\s*техподдержка\s*([.:]?\s*)?$", re.IGNORECASE),
    re.compile(r"^\s*customer\s+service\s*([.:]?\s*)?$", re.IGNORECASE),
    re.compile(r"^\s*служба\s+поддержки\s*([.:]?\s*)?$", re.IGNORECASE),
    re.compile(r"^\s*helpdesk\s*([.:]?\s*)?$", re.IGNORECASE),
    re.compile(r"^\s*contact\s+us\s*([.:]?\s*)?$", re.IGNORECASE),
    re.compile(r"^\s*связаться\s+с\s+нами\s*([.:]?\s*)?$", re.IGNORECASE),
    re.compile(r"^\s*support\s+team\s*([.:]?\s*)?$", re.IGNORECASE),
    re.compile(r"^\s*команда\s+поддержки\s*([.:]?\s*)?$", re.IGNORECASE),
)


def _is_support_footer_line(line: str) -> bool:
    s = line.strip()
    if not s or len(s) > 120:
        return False
    return any(rx.match(s) for rx in _SUPPORT_LINE_RES)


def _is_junk_line(line: str) -> bool:
    s = line.strip()
    if not s:
        return False
    for rx in _PAGE_LINE_PATTERNS:
        if rx.match(s):
            return True
    for rx in _MISC_JUNK:
        if rx.match(s):
            return True
    for rx in _HEADER_FOOTER:
        if rx.match(s):
            return True
    if _DECOR_ONLY.match(s):
        return True
    if _is_breadcrumb_noise(line):
        return True
    if _is_social_or_link_only_line(line):
        return True
    if _is_support_footer_line(line):
        return True
    return False


def _collapse_consecutive_duplicate_short_lines(lines: list[str], *, max_len: int = 100) -> list[str]:
    """Подряд идущие одинаковые короткие непустые строки → одна копия."""
    out: list[str] = []
    for ln in lines:
        st = ln.strip()
        if (
            st
            and len(st) <= max_len
            and out
            and out[-1].strip() == st
        ):
            continue
        out.append(ln)
    return out


def clean_pdf_extracted_text(text: str) -> str:
    """
    Удаляет шумовые полные строки и схлопывает повторяющиеся короткие строки подряд.
    Вход/выход: обычная UTF-8 строка (сохраняет регистр содержательного текста).
    """
    raw = text.replace("\r\n", "\n").replace("\r", "\n")
    raw_lines = raw.split("\n")
    kept: list[str] = []
    for ln in raw_lines:
        if _is_junk_line(ln):
            continue
        kept.append(ln)
    merged = _collapse_consecutive_duplicate_short_lines(kept)
    # не более двух пустых подряд на границах блока
    out: list[str] = []
    empty_run = 0
    for ln in merged:
        if not ln.strip():
            empty_run += 1
            if empty_run <= 2:
                out.append("")
        else:
            empty_run = 0
            out.append(ln)
    while out and not out[0].strip():
        out.pop(0)
    while out and not out[-1].strip():
        out.pop()
    return "\n".join(out)
