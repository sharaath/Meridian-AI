"""Document & file upload, extraction, private download, and document Q&A routes."""

from __future__ import annotations

import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.middleware.auth import get_current_user
from app.models.tables import UploadedFile, UsageLog, User
from app.schemas.common import UploadedFileDetailOut, UploadedFileOut
from pathlib import Path

from app.services.ai_service import (
    AIAttachment,
    AIGenerationConfig,
    AIProviderError,
    AIProviderNotConfiguredError,
    ChatMessageInput,
    ai_registry,
)
from app.services.document_service import extract_document_content, extract_embedded_images
from app.services.storage_service import storage_service
from app.utils.validators import sanitize_filename, validate_upload_file

router = APIRouter(prefix="/api/files", tags=["Files & Documents"])


class DocumentAnalyzeRequest(BaseModel):
    file_ids: List[str] = Field(..., min_length=1, max_length=10)
    question: str = Field(
        default="Provide a clear summary of these documents and highlight key points with page references.",
        min_length=1,
        max_length=8000,
    )
    model_id: Optional[str] = None


@router.post("/upload", response_model=UploadedFileDetailOut, status_code=status.HTTP_201_CREATED)
async def upload_file(
    file: UploadFile = File(...),
    conversation_id: Optional[str] = Form(default=None),
    project_id: Optional[str] = Form(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    settings = get_settings()
    raw_bytes = await file.read()
    safe_name = sanitize_filename(file.filename or "document")
    mime_type = file.content_type or "application/octet-stream"

    try:
        category, ext = validate_upload_file(safe_name, mime_type, len(raw_bytes), settings.max_upload_bytes)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    file_id = str(uuid.uuid4())
    storage_path = storage_service.save_bytes(current_user.id, file_id, safe_name, raw_bytes, mime_type)

    record = UploadedFile(
        id=file_id,
        user_id=current_user.id,
        conversation_id=conversation_id or None,
        project_id=project_id or None,
        filename=safe_name,
        file_type=category,
        mime_type=mime_type,
        file_size=len(raw_bytes),
        storage_path=storage_path,
        processing_status="processing",
    )
    db.add(record)
    db.commit()

    try:
        if category == "document":
            extracted = extract_document_content(raw_bytes, ext)
            record.extracted_text = extracted.text
            record.page_count = extracted.page_count
            record.pages_json = extracted.pages
        record.processing_status = "ready"
    except Exception as exc:
        record.processing_status = "failed"
        record.error_message = str(exc)

    db.commit()
    db.refresh(record)
    return record


@router.get("", response_model=List[UploadedFileOut])
def list_files(
    file_type: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(UploadedFile).filter(UploadedFile.user_id == current_user.id)
    if file_type:
        query = query.filter(UploadedFile.file_type == file_type)
    return query.order_by(UploadedFile.created_at.desc()).all()


@router.get("/{file_id}", response_model=UploadedFileDetailOut)
def get_file_detail(
    file_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    record = db.query(UploadedFile).filter(UploadedFile.id == file_id, UploadedFile.user_id == current_user.id).first()
    if not record:
        raise HTTPException(status_code=404, detail="File not found.")
    return record


@router.get("/{file_id}/download")
def download_file(
    file_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    record = db.query(UploadedFile).filter(UploadedFile.id == file_id, UploadedFile.user_id == current_user.id).first()
    if not record:
        raise HTTPException(status_code=404, detail="File not found.")
    data = storage_service.read_bytes(record.storage_path)
    if data is None:
        raise HTTPException(status_code=404, detail="Stored file object not found.")
    return Response(
        content=data,
        media_type=record.mime_type,
        headers={"Content-Disposition": f'attachment; filename="{record.filename}"'},
    )


@router.get("/{file_id}/raw")
def view_file_raw(
    file_id: str,
    db: Session = Depends(get_db),
):
    """Public stream for rendering images and previewable assets in markdown or presentation slides."""
    record = db.query(UploadedFile).filter(UploadedFile.id == file_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="File not found.")
    data = storage_service.read_bytes(record.storage_path)
    if data is None:
        raise HTTPException(status_code=404, detail="Stored file object not found.")
    return Response(
        content=data,
        media_type=record.mime_type or "image/jpeg",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@router.delete("/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_file(
    file_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    record = db.query(UploadedFile).filter(UploadedFile.id == file_id, UploadedFile.user_id == current_user.id).first()
    if not record:
        raise HTTPException(status_code=404, detail="File not found.")
    storage_service.delete_object(record.storage_path)
    db.delete(record)
    db.commit()


@router.post("/analyze")
async def analyze_documents(
    payload: DocumentAnalyzeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    files = (
        db.query(UploadedFile)
        .filter(UploadedFile.id.in_(payload.file_ids), UploadedFile.user_id == current_user.id)
        .all()
    )
    if not files:
        raise HTTPException(status_code=404, detail="No matching uploaded documents found.")

    try:
        provider, model = ai_registry.resolve_provider(payload.model_id)
    except AIProviderNotConfiguredError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    except AIProviderError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    context_blocks = []
    references = []
    embedded_attachments: List[AIAttachment] = []
    for f in files:
        if f.processing_status != "ready":
            continue
        if f.extracted_text:
            context_blocks.append(f"=== Document: {f.filename} (Pages: {f.page_count}) ===\n{f.extracted_text[:20000]}")
        doc_bytes = storage_service.read_bytes(f.storage_path)
        if doc_bytes:
            ext = Path(f.filename).suffix.lstrip(".")
            for emb in extract_embedded_images(doc_bytes, ext):
                embedded_attachments.append(
                    AIAttachment(
                        filename=f"{f.filename} ({emb.filename})",
                        mime_type=emb.mime_type,
                        data=emb.data,
                    )
                )
        references.append({"file_id": f.id, "filename": f.filename, "page_count": f.page_count})

    if not context_blocks and not embedded_attachments:
        raise HTTPException(status_code=400, detail="Selected files do not contain extracted text or images.")

    prompt = (
        "Answer the user's request strictly grounded in the uploaded documents and any embedded visual images/logos below. "
        "Cite document filenames and page numbers (e.g., [filename, Page 2]) whenever referencing facts.\n\n"
        + "\n\n".join(context_blocks)
        + f"\n\nUser Question: {payload.question}"
    )

    chunks = []
    prompt_tokens = 0
    completion_tokens = 0
    total_tokens = 0
    try:
        async for chunk in provider.stream_chat(
            model_id=model.id,
            messages=[ChatMessageInput(role="user", content=prompt, attachments=embedded_attachments)],
            config=AIGenerationConfig(
                temperature=0.3,
                max_tokens=4096,
                system_instruction="You are Meridian Document Intelligence. Ground every claim in the supplied pages.",
            ),
        ):
            if chunk.delta:
                chunks.append(chunk.delta)
            if chunk.done:
                prompt_tokens = chunk.prompt_tokens
                completion_tokens = chunk.completion_tokens
                total_tokens = chunk.total_tokens
    except AIProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    db.add(
        UsageLog(
            user_id=current_user.id,
            provider=provider.provider_id,
            model_id=model.id,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            action_type="document_analysis",
        )
    )
    db.commit()

    return {
        "answer": "".join(chunks),
        "model_id": model.id,
        "references": references,
        "usage": {"total_tokens": total_tokens},
    }

