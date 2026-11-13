"""Precise Editing API routes (Phase 1B)."""

from __future__ import annotations

import uuid
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status

from app.middleware.auth import get_current_user
from app.models.tables import User
from app.schemas.edit import (
    CodeEditRequest,
    DiffSummary,
    PreciseEditRequest,
    PreciseEditResponse,
    SelectionEditRequest,
    VersionActionRequest,
    VersionHistoryResponse,
)
from app.services.editing_service import (
    apply_selection_edit,
    compute_diff,
    edit_docx_inplace,
    edit_pptx_inplace,
    execute_precise_edit,
    validate_code_syntax,
    version_store,
)

router = APIRouter(prefix="/api/edit", tags=["Precise Editing"])


@router.post("/precise", response_model=PreciseEditResponse)
async def precise_edit_endpoint(
    payload: PreciseEditRequest,
    current_user: User = Depends(get_current_user),
):
    """Execute a precise, minimal-change edit with checklist parsing and unified diff."""
    res = await execute_precise_edit(
        content=payload.content,
        instruction=payload.instruction,
        constraints=payload.constraints,
        model_id=payload.model_id or "gemini-2.5-flash",
        resource_id=payload.resource_id,
    )
    return res


@router.post("/selection", response_model=PreciseEditResponse)
async def selection_edit_endpoint(
    payload: SelectionEditRequest,
    current_user: User = Depends(get_current_user),
):
    """Edit specifically the selected text and splice back in-place, keeping surrounding text 100% byte-identical."""
    # 1. Edit the selection
    sel_res = await execute_precise_edit(
        content=payload.selection,
        instruction=payload.instruction,
        model_id=payload.model_id or "gemini-2.5-flash",
    )

    if not sel_res.success:
        return sel_res

    # 2. Splice edited selection back into full content
    new_full = apply_selection_edit(
        full_content=payload.full_content,
        selection=payload.selection,
        edited_selection=sel_res.edited_text,
        prefix_context=payload.prefix_context,
        suffix_context=payload.suffix_context,
    )

    # 3. Compute diff across full document
    full_diff = compute_diff(payload.full_content, new_full)

    res_id = payload.resource_id or str(uuid.uuid4())
    version = version_store.add_version(res_id, new_full, payload.instruction, full_diff)

    return PreciseEditResponse(
        success=True,
        original_text=payload.full_content,
        edited_text=new_full,
        checklist=sel_res.checklist,
        diff=full_diff,
        version_id=version.version_id,
        version_number=version.version_number,
    )


@router.post("/code", response_model=PreciseEditResponse)
async def code_edit_endpoint(
    payload: CodeEditRequest,
    current_user: User = Depends(get_current_user),
):
    """Execute code-aware editing with automatic post-edit syntax verification."""
    res = await execute_precise_edit(
        content=payload.code,
        instruction=payload.instruction,
        constraints={"keep_wording": True},
        model_id=payload.model_id or "gemini-2.5-flash",
    )

    if res.success:
        valid, err = validate_code_syntax(res.edited_text, payload.language)
        res.syntax_valid = valid
        res.syntax_error = err

    return res


@router.post("/docx")
async def edit_docx_endpoint(
    file: UploadFile = File(...),
    replacements_json: str = Form(..., description='JSON string of {"target": "replacement"}'),
    current_user: User = Depends(get_current_user),
):
    """Edit DOCX in-place preserving styles, fonts, images, and tables."""
    import json

    try:
        replacements = json.loads(replacements_json)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid replacements_json: {e}")

    content = await file.read()
    edited_bytes = edit_docx_inplace(content, replacements)

    return Response(
        content=edited_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="edited-{file.filename}"'},
    )


@router.post("/pptx")
async def edit_pptx_endpoint(
    file: UploadFile = File(...),
    replacements_json: str = Form(..., description='JSON string of {"target": "replacement"}'),
    current_user: User = Depends(get_current_user),
):
    """Edit PPTX in-place preserving slide layouts, themes, tables, and media."""
    import json

    try:
        replacements = json.loads(replacements_json)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid replacements_json: {e}")

    content = await file.read()
    edited_bytes = edit_pptx_inplace(content, replacements)

    return Response(
        content=edited_bytes,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={"Content-Disposition": f'attachment; filename="edited-{file.filename}"'},
    )


@router.post("/version/action")
async def version_action_endpoint(
    payload: VersionActionRequest,
    current_user: User = Depends(get_current_user),
):
    """Accept, reject, or undo an edit version."""
    action = payload.action.lower()
    if action == "accept":
        v = version_store.accept_version(payload.resource_id, payload.version_id)
        if not v:
            raise HTTPException(status_code=404, detail="Version not found.")
        return {"status": "accepted", "version": v}
    elif action == "reject":
        v = version_store.reject_version(payload.resource_id, payload.version_id)
        return {"status": "rejected", "restored_version": v}
    elif action == "undo":
        v = version_store.undo(payload.resource_id)
        return {"status": "undone", "restored_version": v}
    else:
        raise HTTPException(status_code=400, detail=f"Unknown action: {action}")


@router.get("/version/history/{resource_id}", response_model=VersionHistoryResponse)
def get_version_history_endpoint(
    resource_id: str,
    current_user: User = Depends(get_current_user),
):
    """Retrieve full version history and diffs for a resource."""
    return version_store.get_history_response(resource_id)
