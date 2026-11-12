"""Image understanding route."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.middleware.auth import get_current_user
from app.models.tables import UploadedFile, UsageLog, User
from app.schemas.common import ImageAnalyzeRequest
from app.services.ai_service import (
    AIAttachment,
    AIGenerationConfig,
    AIProviderError,
    AIProviderNotConfiguredError,
    ChatMessageInput,
    ai_registry,
)
from app.services.storage_service import storage_service

router = APIRouter(prefix="/api/image", tags=["Image Understanding"])


@router.post("/analyze")
async def analyze_image(
    payload: ImageAnalyzeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    record = (
        db.query(UploadedFile)
        .filter(UploadedFile.id == payload.file_id, UploadedFile.user_id == current_user.id)
        .first()
    )
    if not record or record.file_type != "image":
        raise HTTPException(status_code=404, detail="Uploaded image not found.")

    img_bytes = storage_service.read_bytes(record.storage_path)
    if not img_bytes:
        raise HTTPException(status_code=404, detail="Image data missing from storage.")

    try:
        provider, model = ai_registry.resolve_provider(payload.model_id)
    except AIProviderNotConfiguredError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    except AIProviderError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    parts = []
    total_tokens = 0
    prompt_tokens = 0
    completion_tokens = 0
    try:
        async for chunk in provider.stream_chat(
            model_id=model.id,
            messages=[
                ChatMessageInput(
                    role="user",
                    content=payload.prompt,
                    attachments=[
                        AIAttachment(
                            filename=record.filename,
                            mime_type=record.mime_type,
                            data=img_bytes,
                        )
                    ],
                )
            ],
            config=AIGenerationConfig(temperature=0.4, max_tokens=4096),
        ):
            if chunk.delta:
                parts.append(chunk.delta)
            if chunk.done:
                prompt_tokens = chunk.prompt_tokens
                completion_tokens = chunk.completion_tokens
                total_tokens = chunk.total_tokens
    except AIProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    db.add(
        UsageLog(
            user_id=current_user.id,
            provider=provider.provider_id,
            model_id=model.id,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            action_type="image_analysis",
        )
    )
    db.commit()

    return {
        "analysis": "".join(parts),
        "model_id": model.id,
        "filename": record.filename,
    }

