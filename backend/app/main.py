"""Meridian AI FastAPI application entrypoint."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import init_db
from app.middleware.logging import PrivacySafeLoggingMiddleware
from app.middleware.rate_limit import RateLimitMiddleware
from app.routes import admin, auth, chat, files, image, memory, models, projects, search, user, voice
from app.services.ai_service import ai_registry


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="Production API for Meridian AI — cross-platform AI assistant.",
        lifespan=lifespan,
    )

    cors_kwargs = {
        "allow_origins": settings.cors_origins,
        "allow_credentials": True,
        "allow_methods": ["*"],
        "allow_headers": ["*"],
        "allow_origin_regex": r"^https?://(localhost|127\.0\.0\.1|.*\.vercel\.app|.*\.onrender\.com|192\.168\.\d+\.\d+|10\.\d+\.\d+\.\d+)(:\d+)?$",
    }

    app.add_middleware(CORSMiddleware, **cors_kwargs)
    app.add_middleware(PrivacySafeLoggingMiddleware)
    app.add_middleware(RateLimitMiddleware)

    app.include_router(auth.router)
    app.include_router(models.router)
    app.include_router(chat.router)
    app.include_router(files.router)
    app.include_router(image.router)
    app.include_router(voice.router)
    app.include_router(search.router)
    app.include_router(memory.router)
    app.include_router(projects.router)
    app.include_router(user.router)
    app.include_router(admin.router)

    @app.exception_handler(Exception)
    async def global_exception_handler(_request, exc):
        import logging
        import traceback
        logging.getLogger("uvicorn.error").error("Unhandled exception: %s\n%s", exc, traceback.format_exc())
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=500,
            content={"detail": f"Internal server error: {str(exc)}"},
        )

    @app.get("/", tags=["System"])
    def root():
        return {
            "status": "ok",
            "message": "Meridian AI API is running.",
            "health": "/api/health",
            "docs": "/docs",
        }

    @app.get("/api/health", tags=["System"])
    def health():
        return {
            "status": "ok",
            "app": settings.app_name,
            "version": settings.app_version,
            "environment": settings.environment,
            "database": "postgresql" if settings.is_postgres else "sqlite",
            "auth_mode": "supabase" if settings.is_supabase_auth_configured else "local_jwt",
            "storage_mode": "supabase" if settings.is_supabase_storage_configured else "local",
            "configured_models": len(ai_registry.list_models(include_unconfigured=False)),
        }

    return app


app = create_app()

