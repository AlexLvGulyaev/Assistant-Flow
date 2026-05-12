from __future__ import annotations

import re
import unicodedata


def normalize_text(text: str) -> str:
    """
    Unified line endings, stable paragraph spacing, trimmed whitespace per line,
    Unicode NFC. Does NOT lowercase the document.
    """
    t = text.replace("\r\n", "\n").replace("\r", "\n")
    # NFC for stable comparison / indexing
    t = unicodedata.normalize("NFC", t)
    lines = t.split("\n")
    stripped = [ln.rstrip() for ln in lines]
    # collapse 3+ blank lines to double newline max (paragraph gap)
    joined = "\n".join(stripped)
    joined = re.sub(r"\n{3,}", "\n\n", joined)
    return joined.strip()
