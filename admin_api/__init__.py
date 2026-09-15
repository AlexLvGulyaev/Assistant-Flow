"""FastAPI Admin API — бэкенд операционной консоли (frontend/admin-ui)."""

from admin_api.app import app, create_admin_api_app

__all__ = ["app", "create_admin_api_app"]
