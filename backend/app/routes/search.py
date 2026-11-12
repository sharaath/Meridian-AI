"""Web search route."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, status

from app.middleware.auth import get_current_user
from app.models.tables import User
from app.schemas.common import SearchRequest
from app.services.search_service import WebSearchUnavailableError, search_web_results

router = APIRouter(prefix="/api/search", tags=["Web Search"])


@router.post("")
async def run_web_search(
    payload: SearchRequest,
    _current_user: User = Depends(get_current_user),
):
    try:
        results = await search_web_results(payload.query, max_results=payload.max_results)
    except WebSearchUnavailableError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))

    return {
        "query": payload.query,
        "results": [asdict(r) for r in results],
    }

