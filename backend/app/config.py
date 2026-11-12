"""Application configuration and environment validation for Meridian AI."""

from __future__ import annotations

import os
import secrets
from functools import lru_cache
from pathlib import Path
from typing import List

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


class Settings:
    """Centralized runtime settings loaded from environment variables."""

    def __init__(self) -> None:
        self.app_name: str = os.getenv("APP_NAME", "Meridian AI")
        self.app_version: str = "1.0.0"
        self.environment: str = os.getenv("ENVIRONMENT", "development").lower()
        self.host: str = os.getenv("HOST", "0.0.0.0")
        self.port: int = int(os.getenv("PORT", "8000"))

        raw_secret = os.getenv("SECRET_KEY", "").strip()
        if not raw_secret or raw_secret == "change-this-to-a-long-random-secret-in-production":
            if self.environment == "production":
                raise RuntimeError("SECRET_KEY must be set in production environment.")
            # Persist a per-workspace dev key across StatReload worker restarts so logins stay valid
            dev_secret_file = BASE_DIR / ".dev_secret"
            if dev_secret_file.exists():
                raw_secret = dev_secret_file.read_text(encoding="utf-8").strip()
            if not raw_secret:
                raw_secret = secrets.token_urlsafe(48)
                try:
                    dev_secret_file.write_text(raw_secret, encoding="utf-8")
                except Exception:
                    pass
        self.secret_key: str = raw_secret
        self.jwt_expire_minutes: int = int(os.getenv("JWT_EXPIRE_MINUTES", str(60 * 24 * 7)))

        raw_origins = os.getenv(
            "CORS_ORIGINS",
            "http://localhost:8081,http://localhost:19006,http://localhost:3000,http://127.0.0.1:8081,http://localhost:8000",
        )
        self.cors_origins: List[str] = [o.strip() for o in raw_origins.split(",") if o.strip()]

        # Database
        default_sqlite_path = (BASE_DIR / "meridian_dev.db").as_posix()
        raw_db_url = os.getenv("DATABASE_URL", "").strip()
        if raw_db_url.startswith("postgres://"):
            raw_db_url = "postgresql://" + raw_db_url[len("postgres://"):]
        self.database_url: str = raw_db_url or f"sqlite:///{default_sqlite_path}"

        # Supabase
        self.supabase_url: str = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
        self.supabase_anon_key: str = os.getenv("SUPABASE_ANON_KEY", "").strip()
        self.supabase_service_role_key: str = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
        self.supabase_jwt_secret: str = os.getenv("SUPABASE_JWT_SECRET", "").strip()
        self.supabase_storage_bucket: str = os.getenv("SUPABASE_STORAGE_BUCKET", "meridian-uploads").strip()

        # AI Providers
        self.gemini_api_key: str = os.getenv("GEMINI_API_KEY", "").strip()
        self.anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "").strip()
        self.openai_api_key: str = os.getenv("OPENAI_API_KEY", "").strip()

        # Search Providers
        self.tavily_api_key: str = os.getenv("TAVILY_API_KEY", "").strip()
        self.serper_api_key: str = os.getenv("SERPER_API_KEY", "").strip()
        self.enable_public_web_search_fallback: bool = (
            os.getenv("ENABLE_PUBLIC_WEB_SEARCH_FALLBACK", "true").lower() == "true"
        )

        # Storage & Limits
        self.local_storage_dir: Path = Path(os.getenv("LOCAL_STORAGE_DIR", str(BASE_DIR / "storage")))
        self.local_storage_dir.mkdir(parents=True, exist_ok=True)
        self.rate_limit_per_minute: int = int(os.getenv("RATE_LIMIT_PER_MINUTE", "60"))
        self.max_upload_mb: int = int(os.getenv("MAX_UPLOAD_MB", "20"))
        self.max_upload_bytes: int = self.max_upload_mb * 1024 * 1024
        self.free_daily_message_limit: int = int(os.getenv("FREE_DAILY_MESSAGE_LIMIT", "50"))
        self.free_daily_token_limit: int = int(os.getenv("FREE_DAILY_TOKEN_LIMIT", "100000"))

    @property
    def is_supabase_auth_configured(self) -> bool:
        return bool(self.supabase_url and self.supabase_anon_key)

    @property
    def is_supabase_storage_configured(self) -> bool:
        return bool(self.supabase_url and self.supabase_service_role_key)

    @property
    def is_gemini_configured(self) -> bool:
        return bool(self.gemini_api_key)

    @property
    def is_anthropic_configured(self) -> bool:
        return bool(self.anthropic_api_key)

    @property
    def is_openai_configured(self) -> bool:
        return bool(self.openai_api_key)

    @property
    def is_postgres(self) -> bool:
        return self.database_url.startswith("postgres")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

