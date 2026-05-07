"""FastAPI Admin API foundation (parallel to Streamlit admin_ui)."""

from admin_api.app import app, create_admin_api_app

__all__ = ["app", "create_admin_api_app"]
