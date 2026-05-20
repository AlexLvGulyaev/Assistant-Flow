from __future__ import annotations

from fastapi import APIRouter, Depends

from admin_api.deps import (
    config_readiness_summary,
    get_admin_service,
    run_health_report,
    snapshot_to_public_dict,
)
from admin_api.schemas.common import OverviewResponse
from admin_api.security.deps import require_permission
from services.security.rbac import PERM_DOCUMENTS_READ
from utils.config import load_config

router = APIRouter(prefix="/api", tags=["overview"])

_SUPPORTED_MODALITIES = ["text", "rag", "image", "audio", "documents"]


@router.get("/overview", response_model=OverviewResponse)
def api_overview(
    _principal=Depends(require_permission(PERM_DOCUMENTS_READ)),
) -> OverviewResponse:
    cfg = load_config()
    svc = get_admin_service()
    _, rep = run_health_report()
    kb = svc.get_knowledge_base_status()
    retrieval = svc.get_retrieval_platform_compact()

    return OverviewResponse(
        database={
            "postgres_available": kb.postgres_available,
            "postgres_documents": kb.postgres_documents,
            "postgres_chunks_sum": kb.postgres_chunks_sum,
            "collection_chunk_count": kb.collection_count,
            "vector_index_chunk_count": kb.collection_count,
        },
        chroma=snapshot_to_public_dict(rep.chroma),
        rag=snapshot_to_public_dict(rep.rag),
        retrieval=retrieval,
        supported_modalities=list(_SUPPORTED_MODALITIES),
        providers={
            name: {"status": snap.status, "detail": snap.detail}
            for name, snap in rep.llm.items()
        },
        asset_storage={
            "backend": cfg.asset_storage_backend,
            "dir": cfg.asset_storage_dir,
        },
        audio={
            "enabled": cfg.audio_enabled,
            "stt_provider": cfg.stt_provider,
            "tts_provider": cfg.tts_provider,
            "storage_namespace": cfg.audio_storage_namespace,
        },
        config_readiness=config_readiness_summary(cfg),
    )
