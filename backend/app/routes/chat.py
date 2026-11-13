"""Conversations, real-time SSE streaming chat, edit/resend, regenerate, export, and sharing routes."""

from __future__ import annotations

import asyncio
import json
import secrets
import time
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.middleware.auth import get_current_user
from app.models.tables import (
    Conversation,
    Message,
    Project,
    SharedConversation,
    UploadedFile,
    UsageLog,
    User,
    UserPreference,
)
from app.schemas.chat import (
    ChatSendRequest,
    ConversationCreate,
    ConversationDetailOut,
    ConversationOut,
    ConversationUpdate,
    MessageEditRequest,
    MessageFeedbackRequest,
    MessageOut,
    RegenerateRequest,
    ShareOut,
)
from app.services.ai_service import (
    AIAttachment,
    AIGenerationConfig,
    AIProviderError,
    AIProviderNotConfiguredError,
    ChatMessageInput,
    MODE_SYSTEM_PROMPTS,
    ai_registry,
)
from pathlib import Path

from app.services.context_service import estimate_tokens, manage_conversation_context
from app.services.document_service import extract_embedded_images
from app.services.export_service import (
    export_conversation_pdf,
    export_conversation_txt,
    export_message_docx,
    export_message_pdf,
    export_message_pptx,
)
from app.services.memory_service import format_memories_for_prompt, get_user_memories
from app.services.search_service import WebSearchUnavailableError, format_search_context, search_web_results
from app.services.storage_service import storage_service

router = APIRouter(prefix="/api", tags=["Chat & Conversations"])


def _sse_event(event: str, data: Dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _derive_title(content: str) -> str:
    cleaned = " ".join(content.strip().split())
    if len(cleaned) <= 52:
        return cleaned or "New Conversation"
    return cleaned[:49].rstrip() + "..."


def _derive_follow_ups(mode: str, user_prompt: str) -> List[str]:
    if mode == "coding":
        return [
            "Write unit tests for this solution",
            "Explain time and space complexity",
            "Show how to optimize or refactor it",
        ]
    if mode == "tutor":
        return [
            "Give me a practice problem to test my understanding",
            "Explain the core intuition with a simpler analogy",
            "Summarize the key takeaways",
        ]
    if mode == "math":
        return [
            "Verify the answer with an alternative method",
            "Walk through a similar example problem",
        ]
    if len(user_prompt) > 20:
        return [
            "Summarize the key points concisely",
            "Go deeper into the most important trade-offs",
            "Give a concrete real-world example",
        ]
    return ["Tell me more about this", "Give me a practical example"]


def _check_free_tier_limits(db: Session, user: User) -> None:
    if user.subscription_plan != "free":
        return
    settings = get_settings()
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    row = (
        db.query(
            func.count(UsageLog.id),
            func.coalesce(func.sum(UsageLog.total_tokens), 0),
        )
        .filter(UsageLog.user_id == user.id, UsageLog.created_at >= today_start)
        .first()
    )
    msg_count = int(row[0] or 0)
    token_count = int(row[1] or 0)
    if msg_count >= settings.free_daily_message_limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Daily free plan message limit ({settings.free_daily_message_limit}) reached.",
        )
    if token_count >= settings.free_daily_token_limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Daily free plan token limit ({settings.free_daily_token_limit}) reached.",
        )


def _get_owned_conversation(db: Session, conversation_id: str, user_id: str) -> Conversation:
    conv = (
        db.query(Conversation)
        .filter(Conversation.id == conversation_id, Conversation.user_id == user_id)
        .first()
    )
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return conv


def _build_system_instruction(
    db: Session,
    user: User,
    conversation: Conversation,
    search_context: str = "",
) -> str:
    parts = [
        MODE_SYSTEM_PROMPTS.get(conversation.mode, MODE_SYSTEM_PROMPTS["general"]),
        (
            "Meridian Platform Capabilities: Users can download any of your responses directly as a "
            "standalone formatted PDF, Word document (.docx), or PowerPoint presentation (.pptx) using the "
            "'PDF', 'DOCX', and 'PPTX' buttons directly beneath your message (or export the conversation "
            "from the header). When a user asks for a PDF, Word document (.doc/.docx), or PowerPoint (.ppt/.pptx), "
            "NEVER say you cannot generate those files. When revising an uploaded document or template, preserve "
            "its exact sections, headings, tables, and structure faithfully unless asked to change them. "
            "For presentations, structure each slide clearly with '## Slide 1: <Title>' and concise bullet points "
            "(separated by '---'). Tell the user to click 'PDF', 'DOCX', or 'PPTX' right below your message.\n\n"
            "Phase 1B Precise Editing Protocol: When the user asks for edits or revisions on previously generated "
            "content, documents, code, or selected passages:\n"
            "1. Split the request into a numbered checklist of individual edit instructions.\n"
            "2. Apply the Minimal-Change Rule: Change ONLY what was requested. Preserve everything else character-for-character "
            "(wording, tone, structure, numbering, formatting, headings, code style, and language).\n"
            "3. Never silently skip an instruction. Verify every checklist item before finishing.\n"
            "4. Never add, remove, or 'improve' content that was not mentioned. If you notice an unrelated problem, "
            "mention it in one line at the end and leave it unchanged.\n"
            "5. If an instruction is ambiguous or could match multiple places, ask one short clarifying question or offer 2-3 options.\n"
            "6. Honor all constraints exactly (word counts, tone, format, 'keep my wording', 'don't touch headings').\n"
            "7. Return the full edited result cleanly without conversational chatter inside the edited content body."
        ),
    ]

    prefs = db.query(UserPreference).filter(UserPreference.user_id == user.id).first()
    if prefs and prefs.custom_instructions.strip():
        parts.append(f"User Custom Instructions:\n{prefs.custom_instructions.strip()}")

    if conversation.project_id:
        project = (
            db.query(Project)
            .filter(Project.id == conversation.project_id, Project.user_id == user.id)
            .first()
        )
        if project and project.custom_instructions.strip():
            parts.append(f"Project ({project.name}) Instructions:\n{project.custom_instructions.strip()}")

    if not prefs or prefs.memory_enabled:
        memories = get_user_memories(db, user.id, limit=20)
        mem_block = format_memories_for_prompt(memories)
        if mem_block:
            parts.append(mem_block)

    if search_context:
        parts.append(search_context)

    return "\n\n".join(parts)


def _load_attachments_for_ids(db: Session, user_id: str, file_ids: List[str]) -> tuple[List[AIAttachment], List[Dict[str, Any]]]:
    if not file_ids:
        return [], []
    records = (
        db.query(UploadedFile)
        .filter(UploadedFile.id.in_(file_ids), UploadedFile.user_id == user_id)
        .all()
    )
    ai_attachments: List[AIAttachment] = []
    meta_list: List[Dict[str, Any]] = []
    for rec in records:
        raw_bytes = b""
        if rec.file_type == "image":
            raw_bytes = storage_service.read_bytes(rec.storage_path) or b""
        ai_attachments.append(
            AIAttachment(
                filename=rec.filename,
                mime_type=rec.mime_type,
                data=raw_bytes,
                extracted_text=rec.extracted_text,
                pages=rec.pages_json or [],
            )
        )
        if rec.file_type == "document":
            doc_bytes = storage_service.read_bytes(rec.storage_path)
            if doc_bytes:
                ext = Path(rec.filename).suffix.lstrip(".")
                for emb in extract_embedded_images(doc_bytes, ext):
                    ai_attachments.append(
                        AIAttachment(
                            filename=f"{rec.filename} ({emb.filename})",
                            mime_type=emb.mime_type,
                            data=emb.data,
                        )
                    )
        meta_list.append(
            {
                "file_id": rec.id,
                "filename": rec.filename,
                "file_type": rec.file_type,
                "mime_type": rec.mime_type,
                "page_count": rec.page_count,
            }
        )
    return ai_attachments, meta_list


def _build_history_inputs(db: Session, user_id: str, messages: List[Message]) -> List[ChatMessageInput]:
    history: List[ChatMessageInput] = []
    for msg in messages:
        att_ids = [a.get("file_id") for a in (msg.attachments_json or []) if a.get("file_id")]
        atts, _ = _load_attachments_for_ids(db, user_id, att_ids)
        history.append(ChatMessageInput(role=msg.role, content=msg.content, attachments=atts))
    return history


# Active SSE stream cancellation tokens (keyed by conversation_id and stream_id)
active_cancellations: Dict[str, asyncio.Event] = {}


def _get_branch_messages(db: Session, conversation_id: str, leaf_message: Message) -> List[Message]:
    """Traverse from leaf_message up via parent_id to reconstruct the exact linear branch history."""
    all_msgs = {
        m.id: m
        for m in db.query(Message)
        .filter(Message.conversation_id == conversation_id)
        .all()
    }
    branch: List[Message] = []
    curr: Optional[Message] = leaf_message
    visited = set()

    while curr and curr.id not in visited:
        visited.add(curr.id)
        branch.append(curr)
        if curr.parent_id and curr.parent_id in all_msgs:
            curr = all_msgs[curr.parent_id]
        else:
            break

    branch.reverse()
    return branch


@router.get("/conversations", response_model=List[ConversationOut])
def list_conversations(
    q: Optional[str] = Query(default=None, max_length=200),
    project_id: Optional[str] = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(Conversation).filter(Conversation.user_id == current_user.id)
    if project_id:
        query = query.filter(Conversation.project_id == project_id)
    if q and q.strip():
        term = f"%{q.strip()}%"
        matching_conv_ids = (
            db.query(Message.conversation_id)
            .filter(Message.content.ilike(term))
            .distinct()
        )
        query = query.filter(
            or_(Conversation.title.ilike(term), Conversation.id.in_(matching_conv_ids))
        )
    return query.order_by(Conversation.is_pinned.desc(), Conversation.updated_at.desc()).all()


@router.post("/conversations", response_model=ConversationOut, status_code=status.HTTP_201_CREATED)
def create_conversation(
    payload: ConversationCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if payload.project_id:
        proj = db.query(Project).filter(Project.id == payload.project_id, Project.user_id == current_user.id).first()
        if not proj:
            raise HTTPException(status_code=404, detail="Project not found.")

    conv = Conversation(
        user_id=current_user.id,
        project_id=payload.project_id,
        title=payload.title.strip() or "New Conversation",
        model_id=payload.model_id or (ai_registry.get_default_model_id() or ""),
        mode=payload.mode,
    )
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return conv


@router.get("/conversations/{conversation_id}", response_model=ConversationDetailOut)
def get_conversation(
    conversation_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conv = _get_owned_conversation(db, conversation_id, current_user.id)
    messages = (
        db.query(Message)
        .filter(Message.conversation_id == conv.id)
        .order_by(Message.created_at.asc())
        .all()
    )
    return ConversationDetailOut(
        **ConversationOut.model_validate(conv).model_dump(),
        messages=[MessageOut.model_validate(m) for m in messages],
    )


@router.patch("/conversations/{conversation_id}", response_model=ConversationOut)
def update_conversation(
    conversation_id: str,
    payload: ConversationUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conv = _get_owned_conversation(db, conversation_id, current_user.id)
    if payload.title is not None:
        conv.title = payload.title.strip()
    if payload.project_id is not None:
        if payload.project_id == "":
            conv.project_id = None
        else:
            proj = db.query(Project).filter(Project.id == payload.project_id, Project.user_id == current_user.id).first()
            if not proj:
                raise HTTPException(status_code=404, detail="Project not found.")
            conv.project_id = payload.project_id
    if payload.model_id is not None:
        conv.model_id = payload.model_id
    if payload.mode is not None:
        conv.mode = payload.mode
    if payload.is_pinned is not None:
        conv.is_pinned = payload.is_pinned
    db.commit()
    db.refresh(conv)
    return conv


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(
    conversation_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conv = _get_owned_conversation(db, conversation_id, current_user.id)
    db.delete(conv)
    db.commit()


async def _stream_completion(
    db: Session,
    user: User,
    conversation: Conversation,
    user_message: Message,
    model_id: Optional[str],
    use_web_search: bool,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    top_p: Optional[float] = None,
) -> AsyncIterator[str]:
    provider, model = ai_registry.resolve_provider(model_id or conversation.model_id or None)

    citations: List[Dict[str, Any]] = []
    search_context = ""
    if use_web_search:
        try:
            search_results = await search_web_results(user_message.content, max_results=5)
            citations = [asdict(r) for r in search_results]
            search_context = format_search_context(search_results)
        except WebSearchUnavailableError as exc:
            citations = [{"title": "Web search unavailable", "url": "", "snippet": str(exc), "source": "system"}]

    start_time = time.perf_counter()
    system_instruction = _build_system_instruction(db, user, conversation, search_context=search_context)

    # Phase 1: Reconstruct history strictly along the active branch up to user_message
    branch_messages = _get_branch_messages(db, conversation.id, user_message)

    # Phase 2: Context management & rolling summarization
    active_branch_messages, rolling_summary, is_summarized, est_tokens = manage_conversation_context(
        db=db,
        conversation=conversation,
        branch_messages=branch_messages,
        system_instruction=system_instruction,
        context_window=model.context_window,
    )

    if is_summarized and rolling_summary:
        system_instruction = (
            f"{system_instruction}\n\n"
            f"[Earlier conversation summary (compressed earlier turns)]:\n{rolling_summary}\n"
        )

    history = _build_history_inputs(db, user.id, active_branch_messages)

    # Register cancellation event for this stream
    stream_id = str(uuid.uuid4())
    cancel_event = asyncio.Event()
    active_cancellations[conversation.id] = cancel_event
    active_cancellations[stream_id] = cancel_event

    yield _sse_event(
        "meta",
        {
            "conversation_id": conversation.id,
            "conversation_title": conversation.title,
            "user_message_id": user_message.id,
            "stream_id": stream_id,
            "parent_id": user_message.parent_id,
            "model_id": model.id,
            "citations": citations,
            "has_summary": is_summarized,
            "summary": rolling_summary if is_summarized else None,
            "estimated_tokens": est_tokens,
        },
    )

    prefs = db.query(UserPreference).filter(UserPreference.user_id == user.id).first()
    pref_settings = (prefs.settings or {}) if prefs else {}
    cfg = AIGenerationConfig(
        temperature=temperature if temperature is not None else float(pref_settings.get("temperature", 0.7)),
        max_tokens=min(
            max_tokens if max_tokens is not None else int(pref_settings.get("max_tokens", 4096)),
            model.max_output_tokens,
        ),
        top_p=top_p if top_p is not None else float(pref_settings.get("top_p", 0.95)),
        system_instruction=system_instruction,
    )

    accumulated: List[str] = []
    prompt_tokens = 0
    completion_tokens = 0
    total_tokens = 0
    is_cancelled = False

    try:
        async for chunk in provider.stream_chat(model_id=model.id, messages=history, config=cfg):
            if cancel_event.is_set():
                is_cancelled = True
                break
            if chunk.delta:
                accumulated.append(chunk.delta)
                yield _sse_event("delta", {"text": chunk.delta})
            if chunk.done:
                prompt_tokens = chunk.prompt_tokens
                completion_tokens = chunk.completion_tokens
                total_tokens = chunk.total_tokens
    except (asyncio.CancelledError, GeneratorExit):
        is_cancelled = True
    except AIProviderError as exc:
        yield _sse_event("error", {"detail": str(exc)})
        return
    finally:
        active_cancellations.pop(conversation.id, None)
        active_cancellations.pop(stream_id, None)

    # Phase 1 & 2: Always persist reply — whether full or partial — and compute latency & tokens
    full_text = "".join(accumulated).strip()
    if not full_text:
        full_text = "(Stopped)" if is_cancelled else "(No response generated)"

    latency_ms = max(1, int((time.perf_counter() - start_time) * 1000))
    if not prompt_tokens:
        prompt_tokens = est_tokens
    if not completion_tokens:
        completion_tokens = estimate_tokens(full_text)
    if not total_tokens:
        total_tokens = prompt_tokens + completion_tokens

    assistant_msg = Message(
        conversation_id=conversation.id,
        role="assistant",
        content=full_text,
        model_id=model.id,
        citations_json=citations,
        token_count=total_tokens,
        parent_id=user_message.id,
    )
    db.add(assistant_msg)
    conversation.model_id = model.id
    conversation.updated_at = datetime.now(timezone.utc)
    db.add(
        UsageLog(
            user_id=user.id,
            provider=provider.provider_id,
            model_id=model.id,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            latency_ms=latency_ms,
            action_type="chat",
        )
    )
    db.commit()
    db.refresh(assistant_msg)

    if is_cancelled:
        yield _sse_event(
            "cancelled",
            {
                "conversation_id": conversation.id,
                "assistant_message": MessageOut.model_validate(assistant_msg).model_dump(mode="json"),
                "partial": True,
                "has_summary": is_summarized,
            },
        )
        return

    yield _sse_event(
        "done",
        {
            "conversation_id": conversation.id,
            "assistant_message": MessageOut.model_validate(assistant_msg).model_dump(mode="json"),
            "follow_ups": _derive_follow_ups(conversation.mode, user_message.content),
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
                "latency_ms": latency_ms,
            },
            "has_summary": is_summarized,
        },
    )


@router.post("/chat/stream")
async def stream_chat(
    payload: ChatSendRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _check_free_tier_limits(db, current_user)

    try:
        _, model = ai_registry.resolve_provider(payload.model_id)
    except AIProviderNotConfiguredError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    except AIProviderError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    if payload.conversation_id:
        conv = _get_owned_conversation(db, payload.conversation_id, current_user.id)
        conv.mode = payload.mode
    else:
        conv = Conversation(
            user_id=current_user.id,
            project_id=payload.project_id or None,
            title=_derive_title(payload.content),
            model_id=model.id,
            mode=payload.mode,
        )
        db.add(conv)
        db.commit()
        db.refresh(conv)

    # Determine parent_id for message branching tree
    parent_id = payload.parent_id
    if not parent_id and payload.conversation_id:
        latest_msg = (
            db.query(Message)
            .filter(Message.conversation_id == conv.id)
            .order_by(Message.created_at.desc())
            .first()
        )
        if latest_msg:
            parent_id = latest_msg.id

    _, att_meta = _load_attachments_for_ids(db, current_user.id, payload.attachment_ids)
    user_msg = Message(
        conversation_id=conv.id,
        role="user",
        content=payload.content,
        model_id=model.id,
        attachments_json=att_meta,
        parent_id=parent_id,
    )
    db.add(user_msg)
    conv.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(user_msg)

    return StreamingResponse(
        _stream_completion(
            db=db,
            user=current_user,
            conversation=conv,
            user_message=user_msg,
            model_id=model.id,
            use_web_search=payload.use_web_search,
            temperature=payload.temperature,
            max_tokens=payload.max_tokens,
            top_p=payload.top_p,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/chat/cancel/{conversation_id}")
def cancel_chat_stream(
    conversation_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Explicitly cancel active SSE stream for a conversation and trigger server partial save."""
    _get_owned_conversation(db, conversation_id, current_user.id)
    event = active_cancellations.get(conversation_id)
    if event:
        event.set()
        return {"status": "cancelled", "conversation_id": conversation_id}
    return {"status": "not_active", "conversation_id": conversation_id}


@router.post("/chat/messages/{message_id}/edit")
async def edit_and_resend_message(
    message_id: str,
    payload: MessageEditRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _check_free_tier_limits(db, current_user)
    target = (
        db.query(Message)
        .join(Conversation, Message.conversation_id == Conversation.id)
        .filter(Message.id == message_id, Conversation.user_id == current_user.id)
        .first()
    )
    if not target or target.role != "user":
        raise HTTPException(status_code=404, detail="User message not found.")

    conv = _get_owned_conversation(db, target.conversation_id, current_user.id)

    try:
        _, model = ai_registry.resolve_provider(payload.model_id or conv.model_id or None)
    except AIProviderNotConfiguredError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    except AIProviderError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    # Phase 1: Message Tree Branching:
    # Instead of deleting subsequent messages, create a new sibling user message sharing target's parent_id.
    parent_id = payload.parent_id if payload.parent_id is not None else target.parent_id
    new_user_msg = Message(
        conversation_id=conv.id,
        role="user",
        content=payload.content,
        model_id=model.id,
        attachments_json=target.attachments_json,
        parent_id=parent_id,
        is_edited=True,
    )
    db.add(new_user_msg)
    conv.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(new_user_msg)

    return StreamingResponse(
        _stream_completion(
            db=db,
            user=current_user,
            conversation=conv,
            user_message=new_user_msg,
            model_id=model.id,
            use_web_search=payload.use_web_search,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/chat/conversations/{conversation_id}/regenerate")
async def regenerate_last_response(
    conversation_id: str,
    payload: RegenerateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _check_free_tier_limits(db, current_user)
    conv = _get_owned_conversation(db, conversation_id, current_user.id)

    try:
        _, model = ai_registry.resolve_provider(payload.model_id or conv.model_id or None)
    except AIProviderNotConfiguredError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    except AIProviderError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    # Phase 1: Branching message tree:
    # If parent_id provided, regenerate off that user message; otherwise find the last user message.
    if payload.parent_id:
        target_user = (
            db.query(Message)
            .filter(Message.id == payload.parent_id, Message.conversation_id == conv.id, Message.role == "user")
            .first()
        )
    else:
        target_user = (
            db.query(Message)
            .filter(Message.conversation_id == conv.id, Message.role == "user")
            .order_by(Message.created_at.desc())
            .first()
        )

    if not target_user:
        raise HTTPException(status_code=400, detail="No user message found to regenerate from.")

    return StreamingResponse(
        _stream_completion(
            db=db,
            user=current_user,
            conversation=conv,
            user_message=target_user,
            model_id=model.id,
            use_web_search=payload.use_web_search,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/messages/{message_id}/feedback")
def set_message_feedback(
    message_id: str,
    payload: MessageFeedbackRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Store or clear thumbs up / thumbs down feedback per message."""
    msg = (
        db.query(Message)
        .join(Conversation, Message.conversation_id == Conversation.id)
        .filter(Message.id == message_id, Conversation.user_id == current_user.id)
        .first()
    )
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found.")

    msg.feedback = payload.feedback if payload.feedback else None
    db.commit()
    db.refresh(msg)
    return {"id": msg.id, "feedback": msg.feedback}

    return StreamingResponse(
        _stream_completion(
            db=db,
            user=current_user,
            conversation=conv,
            user_message=last_user,
            model_id=model.id,
            use_web_search=payload.use_web_search,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/conversations/{conversation_id}/export")
def export_conversation(
    conversation_id: str,
    format: str = Query(default="txt", pattern="^(txt|pdf)$"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conv = _get_owned_conversation(db, conversation_id, current_user.id)
    messages = (
        db.query(Message)
        .filter(Message.conversation_id == conv.id)
        .order_by(Message.created_at.asc())
        .all()
    )
    if format == "pdf":
        data = export_conversation_pdf(conv, messages)
        return Response(
            content=data,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="meridian-{conv.id[:8]}.pdf"'},
        )
    data = export_conversation_txt(conv, messages)
    return Response(
        content=data,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="meridian-{conv.id[:8]}.txt"'},
    )


@router.get("/messages/{message_id}/export")
def export_single_message(
    message_id: str,
    format: str = Query(default="pdf", pattern="^(txt|pdf|docx|pptx)$"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    msg = (
        db.query(Message)
        .join(Conversation, Message.conversation_id == Conversation.id)
        .filter(Message.id == message_id, Conversation.user_id == current_user.id)
        .first()
    )
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found.")
    if format == "txt":
        return Response(
            content=msg.content.encode("utf-8"),
            media_type="text/plain; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="meridian-document-{msg.id[:8]}.txt"'},
        )

    # Locate any uploaded DOCX/PDF in this conversation to preserve template styles & embedded logos
    conv_files = (
        db.query(UploadedFile)
        .filter(UploadedFile.conversation_id == msg.conversation_id, UploadedFile.user_id == current_user.id)
        .order_by(UploadedFile.created_at.desc())
        .all()
    )
    if not conv_files:
        conv_msgs = (
            db.query(Message)
            .filter(Message.conversation_id == msg.conversation_id)
            .order_by(Message.created_at.desc())
            .all()
        )
        attached_ids = [
            att.get("file_id")
            for m in conv_msgs
            for att in (m.attachments_json or [])
            if att.get("file_id")
        ]
        if attached_ids:
            conv_files = (
                db.query(UploadedFile)
                .filter(UploadedFile.id.in_(attached_ids), UploadedFile.user_id == current_user.id)
                .order_by(UploadedFile.created_at.desc())
                .all()
            )

    if format == "docx":
        template_bytes = None
        for f in conv_files:
            if f.filename.lower().endswith(".docx"):
                template_bytes = storage_service.read_bytes(f.storage_path)
                if template_bytes:
                    break
        docx_bytes = export_message_docx(msg.content, template_docx_bytes=template_bytes)
        return Response(
            content=docx_bytes,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f'attachment; filename="meridian-document-{msg.id[:8]}.docx"'},
        )
    if format == "pptx":
        pptx_bytes = export_message_pptx(msg.content)
        return Response(
            content=pptx_bytes,
            media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            headers={"Content-Disposition": f'attachment; filename="meridian-slides-{msg.id[:8]}.pptx"'},
        )

    embedded_logos = []
    for f in conv_files:
        ext = Path(f.filename).suffix.lstrip(".").lower()
        if ext in ("docx", "pdf"):
            doc_bytes = storage_service.read_bytes(f.storage_path)
            if doc_bytes:
                imgs = extract_embedded_images(doc_bytes, ext, max_images=1)
                if imgs:
                    embedded_logos = [imgs[0].data]
                    break
    pdf_bytes = export_message_pdf(msg.content, embedded_logos=embedded_logos or None)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="meridian-document-{msg.id[:8]}.pdf"'},
    )


@router.post("/conversations/{conversation_id}/share", response_model=ShareOut)
def share_conversation(
    conversation_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conv = _get_owned_conversation(db, conversation_id, current_user.id)
    existing = (
        db.query(SharedConversation)
        .filter(
            SharedConversation.conversation_id == conv.id,
            SharedConversation.user_id == current_user.id,
            SharedConversation.is_active.is_(True),
        )
        .first()
    )
    if existing:
        return ShareOut(
            share_token=existing.share_token,
            conversation_id=existing.conversation_id,
            is_active=existing.is_active,
            created_at=existing.created_at,
        )
    share = SharedConversation(
        conversation_id=conv.id,
        user_id=current_user.id,
        share_token=secrets.token_urlsafe(18),
        is_active=True,
    )
    db.add(share)
    db.commit()
    db.refresh(share)
    return ShareOut(
        share_token=share.share_token,
        conversation_id=share.conversation_id,
        is_active=share.is_active,
        created_at=share.created_at,
    )


@router.delete("/conversations/{conversation_id}/share", status_code=status.HTTP_204_NO_CONTENT)
def revoke_share_conversation(
    conversation_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conv = _get_owned_conversation(db, conversation_id, current_user.id)
    shares = (
        db.query(SharedConversation)
        .filter(SharedConversation.conversation_id == conv.id, SharedConversation.user_id == current_user.id)
        .all()
    )
    for s in shares:
        s.is_active = False
    db.commit()


@router.get("/shared/{share_token}")
def view_shared_conversation(share_token: str, db: Session = Depends(get_db)):
    share = (
        db.query(SharedConversation)
        .filter(SharedConversation.share_token == share_token, SharedConversation.is_active.is_(True))
        .first()
    )
    if not share:
        raise HTTPException(status_code=404, detail="Shared conversation not found or link revoked.")

    conv = db.query(Conversation).filter(Conversation.id == share.conversation_id).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    messages = (
        db.query(Message)
        .filter(Message.conversation_id == conv.id)
        .order_by(Message.created_at.asc())
        .all()
    )
    return {
        "title": conv.title,
        "mode": conv.mode,
        "created_at": conv.created_at,
        "messages": [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "citations_json": m.citations_json,
                "created_at": m.created_at,
            }
            for m in messages
        ],
    }

