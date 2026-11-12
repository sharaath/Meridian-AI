"""Voice assistant speech-to-text transcription route."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.middleware.auth import get_current_user
from app.models.tables import UsageLog, User
from app.services.ai_service import AIProviderError, AIProviderNotConfiguredError, ai_registry
from app.utils.validators import validate_upload_file

router = APIRouter(prefix="/api/voice", tags=["Voice"])


@router.post("/transcribe")
async def transcribe_audio(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    settings = get_settings()
    audio_bytes = await file.read()
    mime_type = file.content_type or "audio/webm"
    try:
        category, _ = validate_upload_file(file.filename or "voice.webm", mime_type, len(audio_bytes), settings.max_upload_bytes)
        if category != "audio":
            raise ValueError("Please upload a valid audio recording.")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    try:
        provider, model = ai_registry.resolve_provider(None)
        transcript = await provider.transcribe_audio(model.id, audio_bytes, mime_type)
    except AIProviderNotConfiguredError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    except AIProviderError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    db.add(
        UsageLog(
            user_id=current_user.id,
            provider=provider.provider_id,
            model_id=model.id,
            action_type="voice_transcribe",
        )
    )
    db.commit()
    return {"transcript": transcript, "model_id": model.id}

