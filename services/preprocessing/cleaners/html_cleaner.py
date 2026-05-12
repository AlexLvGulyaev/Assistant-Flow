from __future__ import annotations

from services.preprocessing.cleaners.text_cleaner import clean_extracted_text


def clean_html_extracted_text(text: str) -> str:
    """
    Post-BeautifulSoup cleanup: delegate to conservative text cleaner.

    Kept as a separate module hook for future HTML-specific passes without
    growing the extractor.
    """
    return clean_extracted_text(text)
