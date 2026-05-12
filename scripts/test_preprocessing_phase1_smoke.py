#!/usr/bin/env python3
"""Smoke test: preprocessing package (no DB, no Admin API)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.preprocessing import PreprocessingService  # noqa: E402


def main() -> None:
    svc = PreprocessingService()
    html = b"""<!doctype html><html><head><style>.x{}</style></head>
<body><nav>nav skip</nav><header>hdr</header><p>Hello world.</p>
<script>alert(1)</script><footer>All rights reserved</footer></body></html>"""
    text, d = svc.run(html, original_filename="t.html")
    assert d.extraction_success
    assert "alert" not in text
    assert "nav skip" not in text
    assert "Hello world" in text
    assert d.original_format == "html"

    t2, d2 = svc.run(b"line1\n\nline2\n", original_filename="x.txt")
    assert "line1" in t2 and "line2" in t2
    assert d2.original_format == "txt"
    assert d2.extraction_success

    print("preprocessing phase1 smoke: OK")


if __name__ == "__main__":
    main()
