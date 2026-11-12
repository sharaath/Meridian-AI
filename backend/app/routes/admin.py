"""Admin dashboard routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.middleware.auth import require_admin
from app.middleware.rate_limit import rate_limiter_store
from app.models.tables import Conversation, Message, UploadedFile, UsageLog, User
from app.services.ai_service import ai_registry

router = APIRouter(prefix="/api/admin", tags=["Admin"])


class PlanUpdateRequest(BaseModel):
    subscription_plan: str = Field(..., pattern="^(free|pro|enterprise)$")


@router.get("/overview")
def admin_overview(
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    total_users = db.query(func.count(User.id)).scalar() or 0
    total_conversations = db.query(func.count(Conversation.id)).scalar() or 0
    total_messages = db.query(func.count(Message.id)).scalar() or 0
    total_files = db.query(func.count(UploadedFile.id)).scalar() or 0
    total_tokens = db.query(func.coalesce(func.sum(UsageLog.total_tokens), 0)).scalar() or 0

    users = db.query(User).order_by(User.created_at.desc()).limit(50).all()
    return {
        "metrics": {
            "total_users": int(total_users),
            "total_conversations": int(total_conversations),
            "total_messages": int(total_messages),
            "total_files": int(total_files),
            "total_tokens": int(total_tokens),
            "rate_limit_blocked": rate_limiter_store.total_blocked,
        },
        "providers": ai_registry.provider_status_summary(),
        "users": [
            {
                "id": u.id,
                "email": u.email,
                "username": u.username,
                "role": u.role,
                "subscription_plan": u.subscription_plan,
                "email_verified": u.email_verified,
                "created_at": u.created_at,
            }
            for u in users
        ],
    }


@router.patch("/users/{user_id}/plan")
def update_user_plan(
    user_id: str,
    payload: PlanUpdateRequest,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    user.subscription_plan = payload.subscription_plan
    db.commit()
    return {"id": user.id, "subscription_plan": user.subscription_plan}

