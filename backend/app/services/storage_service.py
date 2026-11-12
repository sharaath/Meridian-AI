"""Private file storage service supporting Supabase Storage and local isolated storage."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from app.config import get_settings


class StorageService:
    """Stores and retrieves per-user private files."""

    def _safe_local_path(self, storage_path: str) -> Path:
        settings = get_settings()
        base = settings.local_storage_dir.resolve()
        candidate = (base / storage_path).resolve()
        if not str(candidate).startswith(str(base)):
            raise ValueError("Invalid storage path.")
        return candidate

    def save_bytes(self, user_id: str, file_id: str, safe_filename: str, data: bytes, mime_type: str) -> str:
        """Persist bytes under `<user_id>/<file_id>_<safe_filename>` and return storage_path."""
        storage_path = f"{user_id}/{file_id}_{safe_filename}"
        settings = get_settings()

        if settings.is_supabase_storage_configured:
            try:
                from supabase import create_client

                client = create_client(settings.supabase_url, settings.supabase_service_role_key)
                client.storage.from_(settings.supabase_storage_bucket).upload(
                    path=storage_path,
                    file=data,
                    file_options={"content-type": mime_type},
                )
                return storage_path
            except Exception as exc:
                raise RuntimeError(f"Failed to store file in Supabase Storage: {exc}") from exc

        local_path = self._safe_local_path(storage_path)
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_bytes(data)
        return storage_path

    def read_bytes(self, storage_path: str) -> Optional[bytes]:
        settings = get_settings()
        if settings.is_supabase_storage_configured:
            try:
                from supabase import create_client

                client = create_client(settings.supabase_url, settings.supabase_service_role_key)
                return client.storage.from_(settings.supabase_storage_bucket).download(storage_path)
            except Exception:
                return None

        local_path = self._safe_local_path(storage_path)
        if not local_path.exists():
            return None
        return local_path.read_bytes()

    def delete_object(self, storage_path: str) -> None:
        settings = get_settings()
        if settings.is_supabase_storage_configured:
            try:
                from supabase import create_client

                client = create_client(settings.supabase_url, settings.supabase_service_role_key)
                client.storage.from_(settings.supabase_storage_bucket).remove([storage_path])
                return
            except Exception:
                return

        local_path = self._safe_local_path(storage_path)
        if local_path.exists():
            local_path.unlink()


storage_service = StorageService()

