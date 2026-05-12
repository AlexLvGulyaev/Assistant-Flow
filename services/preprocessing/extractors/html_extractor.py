from __future__ import annotations

from bs4 import BeautifulSoup

from services.preprocessing.extractors.base_extractor import BaseExtractor


class HtmlExtractor(BaseExtractor):
    """
    HTML → readable text using BeautifulSoup.

    Removes structural noise tags (script, style, nav, footer, header),
    preserves block boundaries (paragraphs / newlines), does not collapse
    the whole document into a single line.
    """

    _STRIP_TAGS = ("script", "style", "nav", "footer", "header")

    def extract(self, raw: bytes, *, original_filename: str) -> str:
        html = raw.decode("utf-8", errors="replace")
        soup = BeautifulSoup(html, "html.parser")
        for tag in self._STRIP_TAGS:
            for el in soup.find_all(tag):
                el.decompose()
        # Newline-separated blocks; cleaning pass will collapse excess blanks.
        return soup.get_text("\n")
