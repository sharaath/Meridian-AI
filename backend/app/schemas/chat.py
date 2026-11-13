"""Chat, conversation, and message schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ConversationCreate(BaseModel):
    title: str = Field(default="New Conversation", max_length=255)
    project_id: Optional[str] = None
    model_id: str = ""
    mode: str = Field(default="general", pattern="^(general|coding|writing|tutor|math|translation|email)$")


class ConversationUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=255)
    project_id: Optional[str] = None
    model_id: Optional[str] = None
    mode: Optional[str] = Field(default=None, pattern="^(general|coding|writing|tutor|math|translation|email)$")
    is_pinned: Optional[bool] = None


class MessageOut(BaseModel):
    id: str
    conversation_id: str
    role: str
    content: str
    model_id: str
    citations_json: List[Dict[str, Any]]
    attachments_json: List[Dict[str, Any]]
    token_count: int
    is_edited: bool
    parent_id: Optional[str] = None
    feedback: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ConversationOut(BaseModel):
    id: str
    user_id: str
    project_id: Optional[str]
    title: str
    model_id: str
    mode: str
    is_pinned: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ConversationDetailOut(ConversationOut):
    messages: List[MessageOut] = []


class ChatSendRequest(BaseModel):
    conversation_id: Optional[str] = None
    project_id: Optional[str] = None
    content: str = Field(..., min_length=1, max_length=60000)
    model_id: Optional[str] = None
    mode: str = Field(default="general", pattern="^(general|coding|writing|tutor|math|translation|email)$")
    attachment_ids: List[str] = Field(default_factory=list)
    use_web_search: bool = False
    temperature: Optional[float] = Field(default=None, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(default=None, ge=64, le=32768)
    top_p: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    parent_id: Optional[str] = None


class MessageEditRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=60000)
    model_id: Optional[str] = None
    use_web_search: bool = False
    parent_id: Optional[str] = None


class RegenerateRequest(BaseModel):
    model_id: Optional[str] = None
    use_web_search: bool = False
    parent_id: Optional[str] = None


class MessageFeedbackRequest(BaseModel):
    feedback: Optional[str] = Field(default=None, pattern="^(thumbs_up|thumbs_down|like|dislike|)$")


class ShareOut(BaseModel):
    share_token: str
    conversation_id: str
    is_active: bool
    created_at: datetime

