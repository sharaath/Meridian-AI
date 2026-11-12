"""File, memory, project, user, search, and model schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class UploadedFileOut(BaseModel):
    id: str
    user_id: str
    conversation_id: Optional[str]
    project_id: Optional[str]
    filename: str
    file_type: str
    mime_type: str
    file_size: int
    processing_status: str
    page_count: int
    error_message: str
    created_at: datetime

    model_config = {"from_attributes": True}


class UploadedFileDetailOut(UploadedFileOut):
    extracted_text: str
    pages_json: List[Dict[str, Any]]


class MemoryCreate(BaseModel):
    memory_content: str = Field(..., min_length=1, max_length=2000)
    category: str = Field(default="general", max_length=64)


class MemoryUpdate(BaseModel):
    memory_content: Optional[str] = Field(default=None, min_length=1, max_length=2000)
    category: Optional[str] = Field(default=None, max_length=64)


class MemoryOut(BaseModel):
    id: str
    user_id: str
    memory_content: str
    category: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=160)
    description: str = Field(default="", max_length=2000)
    custom_instructions: str = Field(default="", max_length=8000)
    color: str = Field(default="#0D9488", max_length=24)


class ProjectUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=160)
    description: Optional[str] = Field(default=None, max_length=2000)
    custom_instructions: Optional[str] = Field(default=None, max_length=8000)
    color: Optional[str] = Field(default=None, max_length=24)


class ProjectOut(BaseModel):
    id: str
    user_id: str
    name: str
    description: str
    custom_instructions: str
    color: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PreferencesUpdate(BaseModel):
    theme: Optional[str] = Field(default=None, pattern="^(light|dark|system)$")
    preferred_model: Optional[str] = Field(default=None, max_length=120)
    custom_instructions: Optional[str] = Field(default=None, max_length=8000)
    memory_enabled: Optional[bool] = None
    web_search_enabled: Optional[bool] = None
    voice_auto_play: Optional[bool] = None
    settings: Optional[Dict[str, Any]] = None


class PreferencesOut(BaseModel):
    theme: str
    preferred_model: str
    custom_instructions: str
    memory_enabled: bool
    web_search_enabled: bool
    voice_auto_play: bool
    settings: Dict[str, Any]
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProfileUpdate(BaseModel):
    username: Optional[str] = Field(default=None, min_length=2, max_length=100)


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    max_results: int = Field(default=5, ge=1, le=10)


class ImageAnalyzeRequest(BaseModel):
    file_id: str
    prompt: str = Field(default="Analyze this image in detail, extract any visible text, and explain charts or diagrams if present.", max_length=4000)
    model_id: Optional[str] = None

