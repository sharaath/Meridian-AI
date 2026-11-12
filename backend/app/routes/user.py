"""User profile, preferences, and usage statistics routes."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.middleware.auth import get_current_user
from app.models.tables import Conversation, Message, UploadedFile, UsageLog, User, UserPreference
from app.schemas.auth import UserSummary
from app.schemas.common import PreferencesOut, PreferencesUpdate, ProfileUpdate

router = APIRouter(prefix="/api/user", tags=["User"])


def _get_or_create_prefs(db: Session, user_id: str) -> UserPreference:
    prefs = db.query(UserPreference).filter(UserPreference.user_id == user_id).first()
    if not prefs:
        prefs = UserPreference(user_id=user_id)
        db.add(prefs)
        db.commit()
        db.refresh(prefs)
    return prefs


@router.get("/preferences", response_model=PreferencesOut)
def get_preferences(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _get_or_create_prefs(db, current_user.id)


@router.patch("/preferences", response_model=PreferencesOut)
def update_preferences(
    payload: PreferencesUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    prefs = _get_or_create_prefs(db, current_user.id)
    if payload.theme is not None:
        prefs.theme = payload.theme
    if payload.preferred_model is not None:
        prefs.preferred_model = payload.preferred_model
    if payload.custom_instructions is not None:
        prefs.custom_instructions = payload.custom_instructions
    if payload.memory_enabled is not None:
        prefs.memory_enabled = payload.memory_enabled
    if payload.web_search_enabled is not None:
        prefs.web_search_enabled = payload.web_search_enabled
    if payload.voice_auto_play is not None:
        prefs.voice_auto_play = payload.voice_auto_play
    if payload.settings is not None:
        merged = dict(prefs.settings or {})
        merged.update(payload.settings)
        prefs.settings = merged
    db.commit()
    db.refresh(prefs)
    return prefs


@router.patch("/profile", response_model=UserSummary)
def update_profile(
    payload: ProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if payload.username is not None:
        cleaned = payload.username.strip()
        if len(cleaned) < 2:
            raise HTTPException(status_code=400, detail="Username must be at least 2 characters.")
        current_user.username = cleaned
    db.commit()
    db.refresh(current_user)
    return UserSummary.model_validate(current_user)


@router.get("/usage")
def get_usage_stats(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    settings = get_settings()
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)

    today_logs = (
        db.query(
            func.count(UsageLog.id),
            func.coalesce(func.sum(UsageLog.total_tokens), 0),
        )
        .filter(UsageLog.user_id == current_user.id, UsageLog.created_at >= today_start)
        .first()
    )
    today_requests = int(today_logs[0] or 0)
    today_tokens = int(today_logs[1] or 0)

    month_totals = (
        db.query(
            func.count(UsageLog.id),
            func.coalesce(func.sum(UsageLog.prompt_tokens), 0),
            func.coalesce(func.sum(UsageLog.completion_tokens), 0),
            func.coalesce(func.sum(UsageLog.total_tokens), 0),
        )
        .filter(UsageLog.user_id == current_user.id, UsageLog.created_at >= thirty_days_ago)
        .first()
    )

    by_model_rows = (
        db.query(
            UsageLog.model_id,
            func.count(UsageLog.id),
            func.coalesce(func.sum(UsageLog.total_tokens), 0),
        )
        .filter(UsageLog.user_id == current_user.id, UsageLog.created_at >= thirty_days_ago)
        .group_by(UsageLog.model_id)
        .all()
    )

    total_conversations = db.query(func.count(Conversation.id)).filter(Conversation.user_id == current_user.id).scalar() or 0
    total_files = db.query(func.count(UploadedFile.id)).filter(UploadedFile.user_id == current_user.id).scalar() or 0
    total_messages = (
        db.query(func.count(Message.id))
        .join(Conversation, Message.conversation_id == Conversation.id)
        .filter(Conversation.user_id == current_user.id)
        .scalar()
        or 0
    )

    is_free = current_user.subscription_plan == "free"
    return {
        "subscription_plan": current_user.subscription_plan,
        "daily_limits": {
            "messages_used": today_requests,
            "messages_limit": settings.free_daily_message_limit if is_free else None,
            "tokens_used": today_tokens,
            "tokens_limit": settings.free_daily_token_limit if is_free else None,
        },
        "thirty_day_summary": {
            "requests": int(month_totals[0] or 0),
            "prompt_tokens": int(month_totals[1] or 0),
            "completion_tokens": int(month_totals[2] or 0),
            "total_tokens": int(month_totals[3] or 0),
        },
        "totals": {
            "conversations": int(total_conversations),
            "messages": int(total_messages),
            "files": int(total_files),
        },
        "by_model": [
            {"model_id": r[0] or "unknown", "requests": int(r[1]), "total_tokens": int(r[2])}
            for r in by_model_rows
        ],
    }

