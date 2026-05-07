"""Factory for asset repository backend selection."""

from __future__ import annotations

from services.asset_repository import (
    AssetRepository,
    AssetValidationError,
    FilesystemAssetRepository,
)
from utils.config import AppConfig


def create_asset_repository(config: AppConfig) -> AssetRepository:
    backend = (config.asset_storage_backend or "filesystem").strip().lower()
    if backend == "filesystem":
        return FilesystemAssetRepository(config.asset_storage_dir)
    raise AssetValidationError(f"unsupported asset storage backend: {backend}")
