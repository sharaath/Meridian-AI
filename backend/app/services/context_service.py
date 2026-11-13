"""Context Management Service for Meridian AI (Phase 2):
- Token counting and estimation across multi-turn histories and system instructions.
- Rolling summarization of older turns when approaching context limits.
- Preservation of recent turns verbatim.
- Latency and token tracking utilities.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence, Tuple
from sqlalchemy.orm import Session

from app.models.tables import Conversation, Message
from app.services.ai_service import ChatMessageInput


# Standard token estimation: average 3.8 chars per token for Latin, ~1.33 tokens per word
def estimate_tokens(text: Optional[str]) -> int:
    """Accurately estimate token count for raw text without external tokenizer dependencies."""
    if not text:
        return 0
    clean = text.strip()
    if not clean:
        return 0
    words = clean.split()
    by_char = max(1, int(len(clean) / 3.8))
    by_word = max(1, int(len(words) * 1.33))
    return max(by_char, by_word)


def estimate_history_tokens(
    messages: Sequence[ChatMessageInput],
    system_instruction: str = "",
) -> int:
    """Estimate total prompt tokens for history messages, attachments, and system instruction.
    Includes framing overhead (~4 tokens per message)."""
    total = estimate_tokens(system_instruction) + 4
    for msg in messages:
        # Message frame overhead
        total += 4
        total += estimate_tokens(msg.content)
        for att in getattr(msg, "attachments", []):
            if att.extracted_text:
                total += estimate_tokens(att.extracted_text)
            elif att.filename:
                total += estimate_tokens(att.filename) + 5
    return total


def should_summarize_context(
    total_tokens: int,
    context_window: int,
    message_count: int,
    threshold_ratio: float = 0.75,
    token_ceiling: int = 6000,
) -> bool:
    """Determine whether the conversation needs summarization:
    - Exceeds threshold_ratio (default 75%) of model context_window, OR
    - Exceeds token_ceiling (default 6,000 tokens) with at least 8 message turns.
    """
    if message_count < 4:
        return False
    window_threshold = int(context_window * threshold_ratio)
    if total_tokens >= window_threshold:
        return True
    if total_tokens >= token_ceiling and message_count >= 8:
        return True
    return False


def build_rolling_summary(
    existing_summary: Optional[str],
    older_messages: Sequence[Message],
) -> str:
    """Generate a structured rolling summary of older conversation turns."""
    turn_summaries: List[str] = []
    current_user_content = ""

    for m in older_messages:
        text = m.content.strip()
        if m.role == "user":
            current_user_content = text
        elif m.role == "assistant":
            # Extract key takeaways / facts from user prompt and assistant response
            user_snippet = (current_user_content[:140] + "...") if len(current_user_content) > 140 else current_user_content
            # First 1-2 sentences of assistant response
            sentences = re.split(r"(?<=[.!?])\s+", text)
            asst_snippet = " ".join(sentences[:2])
            if len(asst_snippet) > 180:
                asst_snippet = asst_snippet[:180] + "..."
            turn_summaries.append(f"- User inquired: '{user_snippet}'. Assistant established: '{asst_snippet}'.")
            current_user_content = ""

    # If there's an orphaned trailing user message
    if current_user_content:
        turn_summaries.append(f"- User asked: '{current_user_content[:140]}'.")

    new_turn_block = "\n".join(turn_summaries)

    if existing_summary and existing_summary.strip():
        # Merge rolling summary
        combined = (
            f"{existing_summary.strip()}\n"
            f"Subsequently:\n{new_turn_block}"
        )
    else:
        combined = f"Prior Conversation Summary:\n{new_turn_block}"

    # Keep summary bounded and focused
    lines = [line.strip() for line in combined.splitlines() if line.strip()]
    if len(lines) > 20:
        lines = lines[:4] + ["... [intermediate context preserved] ..."] + lines[-12:]
    return "\n".join(lines)


def manage_conversation_context(
    db: Session,
    conversation: Conversation,
    branch_messages: List[Message],
    system_instruction: str,
    context_window: int,
    verbatim_turn_count: int = 4,
    force_summarize: bool = False,
) -> Tuple[List[Message], Optional[str], bool, int]:
    """Manage conversation context window.
    Returns:
        (active_messages_to_send, rolling_summary, is_summarized, total_estimated_tokens)
    """
    from app.routes.chat import _build_history_inputs

    # 1. Estimate current full token footprint
    full_history_inputs = _build_history_inputs(db, conversation.user_id, branch_messages)
    total_tokens = estimate_history_tokens(full_history_inputs, system_instruction)

    # 2. Check if we need to summarize older turns
    needs_summary = force_summarize or should_summarize_context(
        total_tokens=total_tokens,
        context_window=context_window,
        message_count=len(branch_messages),
    )

    if needs_summary and len(branch_messages) > verbatim_turn_count:
        split_idx = len(branch_messages) - verbatim_turn_count
        older_messages = branch_messages[:split_idx]
        recent_messages = branch_messages[split_idx:]

        # Build / update rolling summary
        new_summary = build_rolling_summary(conversation.summary, older_messages)
        conversation.summary = new_summary
        conversation.has_summary = True
        db.commit()

        # Recalculate tokens with summarized history
        recent_history_inputs = _build_history_inputs(db, conversation.user_id, recent_messages)
        summarized_system = f"{system_instruction}\n\n[Earlier conversation summary]:\n{new_summary}"
        new_total_tokens = estimate_history_tokens(recent_history_inputs, summarized_system)

        return recent_messages, new_summary, True, new_total_tokens

    # Context is within limits
    return branch_messages, conversation.summary, bool(conversation.has_summary), total_tokens
