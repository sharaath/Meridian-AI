"""Conversation memory service for retrieving and formatting user memories."""

from __future__ import annotations

from typing import List

from sqlalchemy.orm import Session

from app.models.tables import Memory


def get_user_memories(db: Session, user_id: str, limit: int = 25) -> List[Memory]:
    return (
        db.query(Memory)
        .filter(Memory.user_id == user_id)
        .order_by(Memory.updated_at.desc())
        .limit(limit)
        .all()
    )


def format_memories_for_prompt(memories: List[Memory]) -> str:
    if not memories:
        return ""
    lines = ["Saved user context & preferences (respect privacy, apply only when relevant):"]
    for mem in memories:
        lines.append(f"- [{mem.category}] {mem.memory_content}")
    return "\n".join(lines)

