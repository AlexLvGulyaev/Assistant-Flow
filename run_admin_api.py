#!/usr/bin/env python3
"""Run Admin API with: python run_admin_api.py (or uvicorn admin_api.app:app)."""

from __future__ import annotations

import uvicorn


def main() -> None:
    uvicorn.run(
        "admin_api.app:app",
        host="0.0.0.0",
        port=8600,
        factory=False,
    )


if __name__ == "__main__":
    main()
