"""Authentication dependency verifying local JWTs or Supabase Auth JWTs."""

from __future__ import annotations

from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models.tables import User, UserPreference
from app.utils.security import decode_jwt_token

bearer_scheme = HTTPBearer(auto_error=False)


def _verify_with_supabase(token: str) -> Optional[dict]:
    """Verify a token against Supabase JWT secret or Supabase Auth API if configured."""
    settings = get_settings()
    if settings.supabase_jwt_secret:
        payload = decode_jwt_token(token, settings.supabase_jwt_secret)
        if payload and payload.get("sub"):
            return {
                "sub": payload["sub"],
                "email": payload.get("email", ""),
                "user_metadata": payload.get("user_metadata") or {},
            }

    if settings.is_supabase_auth_configured:
        try:
            from supabase import create_client

            client = create_client(settings.supabase_url, settings.supabase_anon_key)
            resp = client.auth.get_user(token)
            if resp and resp.user:
                return {
                    "sub": str(resp.user.id),
                    "email": resp.user.email or "",
                    "user_metadata": resp.user.user_metadata or {},
                    "email_confirmed_at": getattr(resp.user, "email_confirmed_at", None),
                }
        except Exception:
            return None
    return None


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Resolve the authenticated User or raise HTTP 401."""
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    settings = get_settings()

    # 1. Try local application JWT
    payload = decode_jwt_token(token, settings.secret_key)
    if payload and payload.get("sub"):
        user = db.query(User).filter(User.id == payload["sub"]).first()
        if user:
            return user

    # 2. Try Supabase Auth token if configured
    supa_user = _verify_with_supabase(token)
    if supa_user and supa_user.get("sub"):
        user = db.query(User).filter(User.id == supa_user["sub"]).first()
        if not user and supa_user.get("email"):
            email = supa_user["email"].lower()
            user = db.query(User).filter(User.email == email).first()
        if not user:
            email = (supa_user.get("email") or f"{supa_user['sub']}@users.local").lower()
            username = (
                (supa_user.get("user_metadata") or {}).get("username")
                or email.split("@")[0]
            )
            user = User(
                id=supa_user["sub"],
                email=email,
                username=username,
                password_hash="",
                email_verified=bool(supa_user.get("email_confirmed_at")),
            )
            db.add(user)
            db.flush()
            db.add(UserPreference(user_id=user.id))
            db.commit()
            db.refresh(user)
        return user

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired authentication token.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """Ensure the authenticated user has admin role."""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator privileges required.",
        )
    return current_user

