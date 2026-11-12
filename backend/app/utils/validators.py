"""Input validation and file upload sanitization helpers."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Set, Tuple

ALLOWED_DOC_EXTENSIONS: Set[str] = {".pdf", ".docx", ".txt", ".md", ".csv"}
ALLOWED_IMAGE_EXTENSIONS: Set[str] = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
ALLOWED_AUDIO_EXTENSIONS: Set[str] = {".webm", ".mp4", ".wav", ".mp3", ".m4a", ".ogg"}

ALLOWED_MIME_PREFIXES = (
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
    "text/markdown",
    "text/csv",
    "image/",
    "audio/",
)

EMAIL_REGEX = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")


def validate_email(email: str) -> str:
    cleaned = email.strip().lower()
    if not EMAIL_REGEX.match(cleaned):
        raise ValueError("Invalid email address format.")
    return cleaned


def validate_password_strength(password: str) -> str:
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters long.")
    if len(password) > 128:
        raise ValueError("Password must not exceed 128 characters.")
    return password


def sanitize_filename(filename: str) -> str:
    name = Path(filename or "upload").name
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", name).strip("._")
    return safe[:180] or "upload"


def validate_upload_file(filename: str, mime_type: str, size_bytes: int, max_bytes: int) -> Tuple[str, str]:
    """Validate uploaded file extension, MIME type, and size. Returns (file_category, extension)."""
    if size_bytes <= 0:
        raise ValueError("Uploaded file is empty.")
    if size_bytes > max_bytes:
        max_mb = max_bytes // (1024 * 1024)
        raise ValueError(f"File exceeds maximum allowed size of {max_mb} MB.")

    ext = Path(filename or "").suffix.lower()
    if ext in ALLOWED_DOC_EXTENSIONS:
        category = "document"
    elif ext in ALLOWED_IMAGE_EXTENSIONS:
        category = "image"
    elif ext in ALLOWED_AUDIO_EXTENSIONS:
        category = "audio"
    else:
        raise ValueError(
            "Unsupported file type. Allowed: PDF, DOCX, TXT, MD, CSV, PNG, JPG, WEBP, GIF, and standard audio."
        )

    normalized_mime = (mime_type or "").lower().split(";")[0].strip()
    if normalized_mime and normalized_mime != "application/octet-stream":
        if not any(normalized_mime.startswith(prefix) for prefix in ALLOWED_MIME_PREFIXES):
            raise ValueError(f"Unsupported MIME type: {normalized_mime}")

    return category, ext.lstrip(".")

