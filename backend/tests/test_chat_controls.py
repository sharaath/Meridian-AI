"""Tests for Phase 1 Chat Controls:
- Stream cancellation and partial reply persistence
- Non-destructive message editing with tree branching (parent_id)
- Non-destructive regeneration with sibling branch creation
- Message feedback (thumbs up / thumbs down) persistence and isolation
- Branch history traversal (_get_branch_messages)
"""

from __future__ import annotations

import asyncio
import json
import uuid
from unittest.mock import patch

from app.database import SessionLocal
from app.models.tables import Message
from app.routes.chat import _get_branch_messages, active_cancellations
from app.services.ai_service import (
    AIGenerationConfig,
    AIModelInfo,
    AIStreamChunk,
    BaseAIProvider,
    ChatMessageInput,
    ai_registry,
)
from tests.conftest import register_and_auth


def unique_auth(test_client, prefix: str):
    uid = uuid.uuid4().hex[:8]
    return register_and_auth(test_client, f"{prefix}_{uid}@example.com", f"{prefix}_{uid}")


class Phase1MockProvider(BaseAIProvider):
    provider_id = "gemini"
    required_env_var = "GEMINI_API_KEY"

    def is_configured(self) -> bool:
        return True

    def list_models(self):
        return [
            AIModelInfo(
                id="gemini-2.5-flash",
                name="Gemini 2.5 Flash",
                provider="gemini",
                description="Phase 1 test model",
                context_window=1048576,
                max_output_tokens=8192,
                configured=True,
            )
        ]

    async def stream_chat(self, model_id: str, messages: list[ChatMessageInput], config: AIGenerationConfig):
        yield AIStreamChunk(delta="First chunk. ")
        yield AIStreamChunk(delta="Second chunk.")
        yield AIStreamChunk(done=True, prompt_tokens=10, completion_tokens=5, total_tokens=15)


def _parse_sse(raw_text: str):
    events = []
    for block in raw_text.strip().split("\n\n"):
        if not block.strip():
            continue
        event_name = "message"
        data_obj = {}
        for line in block.splitlines():
            if line.startswith("event: "):
                event_name = line[7:].strip()
            elif line.startswith("data: "):
                try:
                    data_obj = json.loads(line[6:])
                except Exception:
                    data_obj = {}
        events.append((event_name, data_obj))
    return events


def test_message_feedback_lifecycle(test_client):
    user_a = unique_auth(test_client, "fdbk_a")
    user_b = unique_auth(test_client, "fdbk_b")

    # Send a message to create conversation and assistant message
    orig_providers = ai_registry.providers
    ai_registry.providers = [Phase1MockProvider()]
    try:
        res = test_client.post(
            "/api/chat/stream",
            headers=user_a["headers"],
            json={"content": "Hello for feedback test"},
        )
        assert res.status_code == 200
        events = _parse_sse(res.text)
        done_payload = dict(events)["done"]
        assistant_msg_id = done_payload["assistant_message"]["id"]

        # 1. Thumbs up
        fb_up = test_client.post(
            f"/api/messages/{assistant_msg_id}/feedback",
            headers=user_a["headers"],
            json={"feedback": "thumbs_up"},
        )
        assert fb_up.status_code == 200
        assert fb_up.json()["feedback"] == "thumbs_up"

        # Verify DB directly
        db = SessionLocal()
        try:
            msg = db.query(Message).filter(Message.id == assistant_msg_id).first()
            assert msg is not None
            assert msg.feedback == "thumbs_up"
        finally:
            db.close()

        # 2. Thumbs down
        fb_down = test_client.post(
            f"/api/messages/{assistant_msg_id}/feedback",
            headers=user_a["headers"],
            json={"feedback": "thumbs_down"},
        )
        assert fb_down.status_code == 200
        assert fb_down.json()["feedback"] == "thumbs_down"

        # 3. Clear feedback (null)
        fb_clear = test_client.post(
            f"/api/messages/{assistant_msg_id}/feedback",
            headers=user_a["headers"],
            json={"feedback": None},
        )
        assert fb_clear.status_code == 200
        assert fb_clear.json()["feedback"] is None

        # 4. Invalid feedback rejected
        bad_fb = test_client.post(
            f"/api/messages/{assistant_msg_id}/feedback",
            headers=user_a["headers"],
            json={"feedback": "super_like"},
        )
        assert bad_fb.status_code == 422

        # 5. Isolation: User B cannot modify User A's message feedback
        bob_fb = test_client.post(
            f"/api/messages/{assistant_msg_id}/feedback",
            headers=user_b["headers"],
            json={"feedback": "thumbs_up"},
        )
        assert bob_fb.status_code == 404
    finally:
        ai_registry.providers = orig_providers


def test_edit_message_creates_tree_branch(test_client):
    user = unique_auth(test_client, "branch_user")
    orig_providers = ai_registry.providers
    ai_registry.providers = [Phase1MockProvider()]

    try:
        # Step 1: Send initial message
        r1 = test_client.post(
            "/api/chat/stream",
            headers=user["headers"],
            json={"content": "Turn 1 question"},
        )
        assert r1.status_code == 200
        events1 = dict(_parse_sse(r1.text))
        conv_id = events1["meta"]["conversation_id"]
        user_msg1_id = events1["meta"]["user_message_id"]
        asst_msg1_id = events1["done"]["assistant_message"]["id"]

        # Step 2: Edit the first message (creates a branch)
        edit_res = test_client.post(
            f"/api/chat/messages/{user_msg1_id}/edit",
            headers=user["headers"],
            json={"content": "Turn 1 question edited"},
        )
        assert edit_res.status_code == 200
        events_edit = dict(_parse_sse(edit_res.text))
        new_user_msg_id = events_edit["meta"]["user_message_id"]
        new_asst_msg_id = events_edit["done"]["assistant_message"]["id"]

        assert new_user_msg_id != user_msg1_id

        # Step 3: Fetch conversation detail and verify tree persistence
        conv_detail = test_client.get(f"/api/conversations/{conv_id}", headers=user["headers"])
        assert conv_detail.status_code == 200
        messages = conv_detail.json()["messages"]

        # All 4 messages should exist in DB: original user, original asst, branch user, branch asst
        msg_map = {m["id"]: m for m in messages}
        assert user_msg1_id in msg_map
        assert asst_msg1_id in msg_map
        assert new_user_msg_id in msg_map
        assert new_asst_msg_id in msg_map

        # Verify parent_id relationships
        # Sibling user messages share the same parent_id (None for root)
        assert msg_map[user_msg1_id]["parent_id"] is None
        assert msg_map[new_user_msg_id]["parent_id"] is None
        assert msg_map[new_user_msg_id]["is_edited"] is True

        # Each assistant message points to its respective user message
        assert msg_map[asst_msg1_id]["parent_id"] == user_msg1_id
        assert msg_map[new_asst_msg_id]["parent_id"] == new_user_msg_id
    finally:
        ai_registry.providers = orig_providers


def test_regenerate_creates_sibling_assistant_branch(test_client):
    user = unique_auth(test_client, "regen_user")
    orig_providers = ai_registry.providers
    ai_registry.providers = [Phase1MockProvider()]

    try:
        # Step 1: Initial chat turn
        r1 = test_client.post(
            "/api/chat/stream",
            headers=user["headers"],
            json={"content": "Tell me a fact"},
        )
        assert r1.status_code == 200
        events1 = dict(_parse_sse(r1.text))
        conv_id = events1["meta"]["conversation_id"]
        user_msg_id = events1["meta"]["user_message_id"]
        asst_msg1_id = events1["done"]["assistant_message"]["id"]

        # Step 2: Regenerate response
        r2 = test_client.post(
            f"/api/chat/conversations/{conv_id}/regenerate",
            headers=user["headers"],
            json={},
        )
        assert r2.status_code == 200
        events2 = dict(_parse_sse(r2.text))
        asst_msg2_id = events2["done"]["assistant_message"]["id"]

        assert asst_msg2_id != asst_msg1_id

        # Step 3: Verify both assistant messages exist and share the same parent_id
        conv_detail = test_client.get(f"/api/conversations/{conv_id}", headers=user["headers"])
        assert conv_detail.status_code == 200
        messages = conv_detail.json()["messages"]
        msg_map = {m["id"]: m for m in messages}

        assert asst_msg1_id in msg_map
        assert asst_msg2_id in msg_map
        assert msg_map[asst_msg1_id]["parent_id"] == user_msg_id
        assert msg_map[asst_msg2_id]["parent_id"] == user_msg_id
    finally:
        ai_registry.providers = orig_providers


def test_cancel_stream_endpoint(test_client):
    user = unique_auth(test_client, "cancel_user")

    # Create a conversation
    conv_res = test_client.post(
        "/api/conversations",
        headers=user["headers"],
        json={"title": "Cancel Stream Test"},
    )
    assert conv_res.status_code == 201
    conv_id = conv_res.json()["id"]

    # Call cancel on non-active conversation should succeed gracefully
    cancel_res = test_client.post(
        f"/api/chat/cancel/{conv_id}",
        headers=user["headers"],
    )
    assert cancel_res.status_code == 200
    assert cancel_res.json()["status"] in ("ok", "not_active")

    # Simulate an active cancellation event
    active_cancellations[conv_id] = asyncio.Event()
    assert not active_cancellations[conv_id].is_set()

    cancel_res2 = test_client.post(
        f"/api/chat/cancel/{conv_id}",
        headers=user["headers"],
    )
    assert cancel_res2.status_code == 200
    assert cancel_res2.json()["status"] == "cancelled"
    assert active_cancellations[conv_id].is_set()


def test_get_branch_messages_reconstruction(test_client):
    """Verify that _get_branch_messages walks parent_id correctly to isolate a branch."""
    user = unique_auth(test_client, "branch_recon")

    conv_res = test_client.post(
        "/api/conversations",
        headers=user["headers"],
        json={"title": "Branch Reconstruction Test"},
    )
    assert conv_res.status_code == 201
    conv_id = conv_res.json()["id"]

    db = SessionLocal()
    try:
        # Generate unique IDs
        u1_id = str(uuid.uuid4())
        a1_id = str(uuid.uuid4())
        u2_id = str(uuid.uuid4())
        a2_orig_id = str(uuid.uuid4())
        a2_regen_id = str(uuid.uuid4())
        u1_br_id = str(uuid.uuid4())
        a1_br_id = str(uuid.uuid4())

        # Tree:
        # u1 (root) -> a1 -> u2 -> a2_orig
        #                      \-> a2_regen
        #   \-> u1_branch -> a1_branch
        u1 = Message(id=u1_id, conversation_id=conv_id, role="user", content="hi", parent_id=None)
        a1 = Message(id=a1_id, conversation_id=conv_id, role="assistant", content="hello", parent_id=u1_id)
        u2 = Message(id=u2_id, conversation_id=conv_id, role="user", content="what is 2+2", parent_id=a1_id)
        a2_orig = Message(id=a2_orig_id, conversation_id=conv_id, role="assistant", content="4", parent_id=u2_id)
        a2_regen = Message(id=a2_regen_id, conversation_id=conv_id, role="assistant", content="four", parent_id=u2_id)
        u1_branch = Message(id=u1_br_id, conversation_id=conv_id, role="user", content="hi edited", parent_id=None)
        a1_branch = Message(id=a1_br_id, conversation_id=conv_id, role="assistant", content="hello edited", parent_id=u1_br_id)

        db.add_all([u1, a1, u2, a2_orig, a2_regen, u1_branch, a1_branch])
        db.commit()

        # Trace branch ending at a2_orig
        branch_orig = _get_branch_messages(db, conv_id, a2_orig)
        assert [m.id for m in branch_orig] == [u1_id, a1_id, u2_id, a2_orig_id]

        # Trace branch ending at a2_regen
        branch_regen = _get_branch_messages(db, conv_id, a2_regen)
        assert [m.id for m in branch_regen] == [u1_id, a1_id, u2_id, a2_regen_id]

        # Trace branch ending at a1_branch
        branch_edit = _get_branch_messages(db, conv_id, a1_branch)
        assert [m.id for m in branch_edit] == [u1_br_id, a1_br_id]
    finally:
        db.close()
