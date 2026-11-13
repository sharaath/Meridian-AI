"""Pydantic schemas for Phase 1B precise editing, selection edits, diffs, and version history."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class EditChecklistItem(BaseModel):
    id: int
    instruction: str
    status: str = Field(default="done", description="'done', 'missed', 'clarification_needed'")
    summary: str = Field(default="", description="One-line summary e.g. 'Done: changed title'")


class DiffChunk(BaseModel):
    type: str = Field(description="'added', 'removed', 'unchanged'")
    text: str
    line_number_old: Optional[int] = None
    line_number_new: Optional[int] = None


class DiffSummary(BaseModel):
    unified_diff: str
    added_count: int
    removed_count: int
    chunks: List[DiffChunk] = Field(default_factory=list)


class AmbiguityCheck(BaseModel):
    is_ambiguous: bool = False
    clarifying_question: Optional[str] = None
    options: List[str] = Field(default_factory=list)


class PreciseEditRequest(BaseModel):
    content: str = Field(description="The full original document or message text")
    instruction: str = Field(description="User edit instruction(s)")
    context: Optional[str] = Field(default=None, description="Optional surrounding context or guidelines")
    constraints: Optional[Dict[str, Any]] = Field(default=None, description="e.g. max_words, preserve_headings, tone")
    model_id: Optional[str] = Field(default="gemini-2.5-flash")
    resource_id: Optional[str] = Field(default=None, description="Optional conversation or document ID for version tracking")


class SelectionEditRequest(BaseModel):
    full_content: str = Field(description="The full original document/message text")
    selection: str = Field(description="The specific text selected by user to be edited")
    instruction: str = Field(description="Edit instruction specifically for the selected text")
    prefix_context: Optional[str] = Field(default=None, description="Context immediately before selection")
    suffix_context: Optional[str] = Field(default=None, description="Context immediately after selection")
    model_id: Optional[str] = Field(default="gemini-2.5-flash")
    resource_id: Optional[str] = Field(default=None)


class CodeEditRequest(BaseModel):
    code: str
    language: str = Field(default="python")
    instruction: str
    model_id: Optional[str] = Field(default="gemini-2.5-flash")


class PreciseEditResponse(BaseModel):
    success: bool
    original_text: str
    edited_text: str
    checklist: List[EditChecklistItem] = Field(default_factory=list)
    diff: DiffSummary
    ambiguity: Optional[AmbiguityCheck] = None
    unrelated_notes: List[str] = Field(default_factory=list)
    syntax_valid: Optional[bool] = None
    syntax_error: Optional[str] = None
    version_id: Optional[str] = None
    version_number: int = 1


class VersionActionRequest(BaseModel):
    resource_id: str
    version_id: str
    action: str = Field(description="'accept', 'reject', 'undo'")


class VersionHistoryItem(BaseModel):
    version_id: str
    version_number: int
    timestamp: str
    instruction: str
    content: str
    diff_summary: Optional[DiffSummary] = None
    status: str = Field(default="active", description="'current', 'accepted', 'rejected', 'superseded'")


class VersionHistoryResponse(BaseModel):
    resource_id: str
    current_version_id: str
    versions: List[VersionHistoryItem]
