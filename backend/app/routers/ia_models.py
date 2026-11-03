"""Recommended models and their download on an Ollama server, for the admin."""
from fastapi import APIRouter, Depends, HTTPException

from .. import auth, ia_model_catalog, models
from .ia import _health_cache

router = APIRouter(prefix="/ia/model-catalog", tags=["IA"])


@router.get("")
async def model_catalog(url: str, admin: models.User = Depends(auth.get_current_admin)):
    return await ia_model_catalog.catalog_for(url.strip())


@router.post("/pull")
async def pull_model(body: dict, admin: models.User = Depends(auth.get_current_admin)):
    url = (body.get("url") or "").strip()
    model = body.get("model") or ""
    if model not in {m["name"] for m in ia_model_catalog.CATALOG}:
        raise HTTPException(status_code=400, detail="Model not in the recommended list")
    if not await ia_model_catalog.is_ollama(url):
        raise HTTPException(status_code=400, detail="Not an Ollama server")
    # The model lists shown in the settings must not wait for the health cache to expire
    return ia_model_catalog.start_pull(url, model, on_done=lambda u: _health_cache.pop(u, None))
