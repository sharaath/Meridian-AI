"""User memory management routes."""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.middleware.auth import get_current_user
from app.models.tables import Memory, User
from app.schemas.common import MemoryCreate, MemoryOut, MemoryUpdate

router = APIRouter(prefix="/api/memories", tags=["Memory"])


@router.get("", response_model=List[MemoryOut])
def list_memories(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return (
        db.query(Memory)
        .filter(Memory.user_id == current_user.id)
        .order_by(Memory.updated_at.desc())
        .all()
    )


@router.post("", response_model=MemoryOut, status_code=status.HTTP_201_CREATED)
def create_memory(
    payload: MemoryCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    mem = Memory(
        user_id=current_user.id,
        memory_content=payload.memory_content.strip(),
        category=payload.category.strip() or "general",
    )
    db.add(mem)
    db.commit()
    db.refresh(mem)
    return mem


@router.patch("/{memory_id}", response_model=MemoryOut)
def update_memory(
    memory_id: str,
    payload: MemoryUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    mem = db.query(Memory).filter(Memory.id == memory_id, Memory.user_id == current_user.id).first()
    if not mem:
        raise HTTPException(status_code=404, detail="Memory not found.")
    if payload.memory_content is not None:
        mem.memory_content = payload.memory_content.strip()
    if payload.category is not None:
        mem.category = payload.category.strip() or "general"
    db.commit()
    db.refresh(mem)
    return mem


@router.delete("/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_memory(
    memory_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    mem = db.query(Memory).filter(Memory.id == memory_id, Memory.user_id == current_user.id).first()
    if not mem:
        raise HTTPException(status_code=404, detail="Memory not found.")
    db.delete(mem)
    db.commit()

