"""Model configuration and availability endpoints."""

from __future__ import annotations

from dataclasses import asdict
from fastapi import APIRouter

from app.services.ai_service import ai_registry

router = APIRouter(prefix="/api/models", tags=["Models"])


@router.get("")
def list_available_models():
    """Return ONLY configured and actually selectable AI models."""
    models = ai_registry.list_models(include_unconfigured=False)
    return {
        "models": [asdict(m) for m in models],
        "default_model": ai_registry.get_default_model_id(),
        "any_configured": len(models) > 0,
    }


@router.get("/catalog")
def list_model_catalog():
    """Return full model catalog with accurate configured/unconfigured flags."""
    models = ai_registry.list_models(include_unconfigured=True)
    return {
        "models": [asdict(m) for m in models],
        "providers": ai_registry.provider_status_summary(),
    }

