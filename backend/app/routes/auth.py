"""Authentication endpoints: register, login, email verification, password reset, Google OAuth, profile."""

from __future__ import annotations

import os
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.middleware.auth import get_current_user
from app.models.tables import User, UserPreference
from app.schemas.auth import (
    AuthResponse,
    LoginRequest,
    OAuthExchangeRequest,
    PasswordResetConfirmRequest,
    PasswordResetRequest,
    RegisterRequest,
    UserSummary,
    VerifyEmailRequest,
)
from app.utils.security import create_jwt_token, hash_password, verify_password
from app.utils.validators import validate_email, validate_password_strength

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


def _issue_local_token(user: User) -> str:
    settings = get_settings()
    return create_jwt_token(
        {"sub": user.id, "email": user.email, "role": user.role},
        secret=settings.secret_key,
        expires_minutes=settings.jwt_expire_minutes,
    )


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    try:
        email = validate_email(payload.email)
        password = validate_password_strength(payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    settings = get_settings()
    username = payload.username.strip()

    # If Supabase Auth is configured, register with Supabase first
    if settings.is_supabase_auth_configured:
        try:
            from supabase import create_client

            client = create_client(settings.supabase_url, settings.supabase_anon_key)
            resp = client.auth.sign_up(
                {"email": email, "password": password, "options": {"data": {"username": username}}}
            )
            if not resp.user:
                raise HTTPException(status_code=400, detail="Supabase registration failed.")

            user = db.query(User).filter(User.email == email).first()
            if not user:
                user = User(
                    id=str(resp.user.id),
                    email=email,
                    username=username,
                    password_hash="",
                    email_verified=bool(getattr(resp.user, "email_confirmed_at", None)),
                )
                db.add(user)
                db.flush()
                db.add(UserPreference(user_id=user.id))
                db.commit()
                db.refresh(user)

            access_token = resp.session.access_token if resp.session else _issue_local_token(user)
            notice = (
                None
                if resp.session
                else "Verification email sent via Supabase Auth. Please check your inbox to verify your account."
            )
            return AuthResponse(
                access_token=access_token,
                auth_provider="supabase",
                user=UserSummary.model_validate(user),
                verification_notice=notice,
            )
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Registration failed: {exc}")

    # Local PostgreSQL / SQLite authentication mode
    existing = db.query(User).filter(User.email == email).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An account with this email already exists.")

    admin_email = os.getenv("ADMIN_EMAIL", "").strip().lower()
    role = "admin" if admin_email and email == admin_email else "user"
    verification_token = secrets.token_urlsafe(24)

    user = User(
        email=email,
        username=username,
        password_hash=hash_password(password),
        role=role,
        email_verified=False,
        verification_token=verification_token,
    )
    try:
        db.add(user)
        db.flush()
        db.add(UserPreference(user_id=user.id))
        db.commit()
        db.refresh(user)
    except Exception as exc:
        db.rollback()
        # If foreign key constraint failed on un-migrated database, attempt drop and retry once
        if "users_id_fkey" in str(exc) or "foreign key constraint" in str(exc).lower():
            try:
                db.execute(text("ALTER TABLE public.users DROP CONSTRAINT IF EXISTS users_id_fkey;"))
                db.commit()
                db.add(user)
                db.flush()
                db.add(UserPreference(user_id=user.id))
                db.commit()
                db.refresh(user)
            except Exception as retry_exc:
                db.rollback()
                raise HTTPException(status_code=500, detail=f"Database user creation failed: {retry_exc}")
        else:
            raise HTTPException(status_code=500, detail=f"Account creation failed: {exc}")

    token = _issue_local_token(user)
    return AuthResponse(
        access_token=token,
        auth_provider="local_jwt",
        user=UserSummary.model_validate(user),
        verification_notice="Account created. Check your profile settings to verify your email.",
    )


@router.post("/login", response_model=AuthResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    try:
        email = validate_email(payload.email)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    settings = get_settings()

    if settings.is_supabase_auth_configured:
        try:
            from supabase import create_client

            client = create_client(settings.supabase_url, settings.supabase_anon_key)
            resp = client.auth.sign_in_with_password({"email": email, "password": payload.password})
            if not resp.user or not resp.session:
                raise HTTPException(status_code=401, detail="Invalid email or password.")
            user = db.query(User).filter(User.id == str(resp.user.id)).first()
            if not user:
                username = (resp.user.user_metadata or {}).get("username") or email.split("@")[0]
                user = User(
                    id=str(resp.user.id),
                    email=email,
                    username=username,
                    password_hash="",
                    email_verified=bool(getattr(resp.user, "email_confirmed_at", None)),
                )
                db.add(user)
                db.flush()
                db.add(UserPreference(user_id=user.id))
                db.commit()
                db.refresh(user)
            return AuthResponse(
                access_token=resp.session.access_token,
                auth_provider="supabase",
                user=UserSummary.model_validate(user),
            )
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password.")

    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password.")

    return AuthResponse(
        access_token=_issue_local_token(user),
        auth_provider="local_jwt",
        user=UserSummary.model_validate(user),
    )


@router.get("/me", response_model=UserSummary)
def me(current_user: User = Depends(get_current_user)):
    return UserSummary.model_validate(current_user)


@router.post("/logout")
def logout(current_user: User = Depends(get_current_user)):
    # Stateless JWT logout handled client-side; endpoint confirms valid session teardown.
    return {"status": "logged_out", "user_id": current_user.id}


@router.post("/verify-email/request")
def request_email_verification(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.email_verified:
        return {"status": "already_verified"}
    token = secrets.token_urlsafe(24)
    current_user.verification_token = token
    db.commit()
    settings = get_settings()
    response = {"status": "verification_issued", "message": "Verification token generated."}
    if settings.environment != "production":
        response["dev_verification_token"] = token
    return response


@router.post("/verify-email/confirm")
def confirm_email_verification(payload: VerifyEmailRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.verification_token == payload.token).first()
    if not user:
        raise HTTPException(status_code=400, detail="Invalid verification token.")
    user.email_verified = True
    user.verification_token = ""
    db.commit()
    return {"status": "verified", "email": user.email}


@router.post("/password-reset/request")
def request_password_reset(payload: PasswordResetRequest, db: Session = Depends(get_db)):
    try:
        email = validate_email(payload.email)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    settings = get_settings()
    if settings.is_supabase_auth_configured:
        try:
            from supabase import create_client

            client = create_client(settings.supabase_url, settings.supabase_anon_key)
            client.auth.reset_password_email(email)
            return {"status": "sent", "message": "If an account exists, a password reset email has been sent."}
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Password reset error: {exc}")

    user = db.query(User).filter(User.email == email).first()
    response = {"status": "sent", "message": "If an account exists, a password reset instruction has been generated."}
    if user:
        token = secrets.token_urlsafe(24)
        user.reset_token = token
        user.reset_token_expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
        db.commit()
        if settings.environment != "production":
            response["dev_reset_token"] = token
    return response


@router.post("/password-reset/confirm")
def confirm_password_reset(payload: PasswordResetConfirmRequest, db: Session = Depends(get_db)):
    try:
        new_pw = validate_password_strength(payload.new_password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    user = db.query(User).filter(User.reset_token == payload.token).first()
    if not user or not user.reset_token_expires_at:
        raise HTTPException(status_code=400, detail="Invalid or expired password reset token.")

    exp = user.reset_token_expires_at
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) > exp:
        raise HTTPException(status_code=400, detail="Password reset token has expired.")

    user.password_hash = hash_password(new_pw)
    user.reset_token = ""
    user.reset_token_expires_at = None
    db.commit()
    return {"status": "password_updated"}


@router.get("/oauth/google")
def google_oauth_url(redirect_to: str = "http://localhost:8081/login"):
    settings = get_settings()
    if not settings.is_supabase_auth_configured:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Google Sign-In requires Supabase Auth configuration (SUPABASE_URL and SUPABASE_ANON_KEY).",
        )
    try:
        from supabase import create_client

        client = create_client(settings.supabase_url, settings.supabase_anon_key)
        res = client.auth.sign_in_with_oauth({"provider": "google", "options": {"redirect_to": redirect_to}})
        return {"url": res.url}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to initialize Google OAuth: {exc}")


@router.post("/oauth/exchange", response_model=AuthResponse)
def exchange_oauth_code(payload: OAuthExchangeRequest, db: Session = Depends(get_db)):
    """Exchange PKCE code from OAuth provider redirect for an authenticated session."""
    settings = get_settings()
    if not settings.is_supabase_auth_configured:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Google Sign-In requires Supabase Auth configuration (SUPABASE_URL and SUPABASE_ANON_KEY).",
        )
    try:
        from supabase import create_client

        client = create_client(settings.supabase_url, settings.supabase_anon_key)
        resp = client.auth.exchange_code_for_session({"auth_code": payload.code})
        if not resp.session or not resp.user:
            raise HTTPException(status_code=400, detail="Failed to exchange OAuth code for user session.")

        email = (resp.user.email or f"{resp.user.id}@users.local").lower()
        user = db.query(User).filter(User.id == str(resp.user.id)).first()
        if not user:
            user = db.query(User).filter(User.email == email).first()

        if not user:
            username = (resp.user.user_metadata or {}).get("username") or email.split("@")[0]
            user = User(
                id=str(resp.user.id),
                email=email,
                username=username,
                password_hash="",
                email_verified=bool(getattr(resp.user, "email_confirmed_at", True)),
            )
            db.add(user)
            db.flush()
            db.add(UserPreference(user_id=user.id))
            db.commit()
            db.refresh(user)

        return AuthResponse(
            access_token=resp.session.access_token,
            auth_provider="supabase",
            user=UserSummary.model_validate(user),
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"OAuth exchange failed: {exc}")

