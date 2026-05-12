from __future__ import annotations

import re
from typing import Pattern

# Conservative full-line junk (case-insensitive). Do not match partial lines.
_JUNK_LINE_RES: tuple[Pattern[str], ...] = (
    re.compile(r"^all rights reserved\.?$", re.IGNORECASE),
    re.compile(r"^copyright\s+©.*$", re.IGNORECASE),
    re.compile(r"^privacy policy$", re.IGNORECASE),
    re.compile(r"^terms (of|and) (use|service)$", re.IGNORECASE),
    re.compile(r"^cookie(s)? policy$", re.IGNORECASE),
    re.compile(r"^follow us on$", re.IGNORECASE),
    re.compile(r"^share (on|this)$", re.IGNORECASE),
    re.compile(r"^subscribe to our newsletter$", re.IGNORECASE),
    re.compile(r"^contact us:?\s*$", re.IGNORECASE),
    re.compile(r"^\+?\d[\d\s\-()]{7,}\s*$", re.IGNORECASE),  # lone phone-ish line
    re.compile(r"^[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}\s*$", re.IGNORECASE),  # lone email line
)


def _is_junk_line(line: str) -> bool:
    s = line.strip()
    if not s:
        return False
    if len(s) <= 2:
        return False
    for rx in _JUNK_LINE_RES:
        if rx.match(s):
            return True
    # Short navigation crumbs (very conservative)
    if s.lower() in {"home", "next", "previous", "back to top"}:
        return True
    return False


def clean_extracted_text(text: str) -> str:
    """
    Normalize whitespace, drop excessive blank lines, remove consecutive
    duplicate lines, apply conservative junk-line heuristics.
    """
    raw_lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    out_lines: list[str] = []
    prev_norm: str | None = None
    for line in raw_lines:
        if _is_junk_line(line):
            continue
        # collapse horizontal whitespace inside line (tabs → space)
        collapsed = re.sub(r"[ \t]+", " ", line).strip()
        if not collapsed:
            # preserve at most one blank line between content
            if out_lines and out_lines[-1] != "":
                out_lines.append("")
            continue
        if prev_norm is not None and collapsed == prev_norm:
            continue  # consecutive duplicate content line
        out_lines.append(collapsed)
        prev_norm = collapsed
    # trim leading/trailing empty
    while out_lines and out_lines[0] == "":
        out_lines.pop(0)
    while out_lines and out_lines[-1] == "":
        out_lines.pop()
    return "\n".join(out_lines)
