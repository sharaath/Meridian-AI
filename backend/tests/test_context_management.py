"""Tests for Phase 2: Context Management
- Token counting and estimation (words, chars, attachments, message framing)
- Context window monitoring (should_summarize_context)
- Rolling summarization of older turns with recent turns kept verbatim
- Prompt injection of rolling summary
- Subtle 'has_summary' / 'earlier messages summarized' status in meta event and conversation detail
- Latency and input/output token logging in UsageLog table and /api/user/usage
"""

from __future__ import annotations

import json
import uuid

from app.database import SessionLocal
from app.models.tables import Conversation, Message, UsageLog
from app.services.ai_service import (
    AIAttachment,
    AIGenerationConfig,
    AIModelInfo,
    AIStreamChunk,
    BaseAIProvider,
    ChatMessageInput,
    ai_registry,
)
from app.services.context_service import (
    build_rolling_summary,
    estimate_history_tokens,
    estimate_tokens,
    manage_conversation_context,
    should_summarize_context,
)
from tests.conftest import register_and_auth


def unique_auth(test_client, prefix: str):
    uid = uuid.uuid4().hex[:8]
    return register_and_auth(test_client, f"{prefix}_{uid}@example.com", f"{prefix}_{uid}")


class SmallContextMockProvider(BaseAIProvider):
    provider_id = "gemini"
    required_env_var = "GEMINI_API_KEY"
    captured_prompts = []

    def is_configured(self) -> bool:
        return True

    def list_models(self):
        # Model with small context window (e.g. 500 tokens) to trigger summarization in tests
        return [
            AIModelInfo(
                id="gemini-small-ctx",
                name="Gemini Small Context",
                provider="gemini",
                description="Small context test model",
                context_window=600,
                max_output_tokens=500,
                configured=True,
            )
        ]

    async def stream_chat(self, model_id: str, messages: list[ChatMessageInput], config: AIGenerationConfig):
        self.captured_prompts.append(
            {
                "model_id": model_id,
                "system": config.system_instruction,
                "messages": [(m.role, m.content) for m in messages],
            }
        )
        yield AIStreamChunk(delta="Response chunk from AI.")
        yield AIStreamChunk(done=True, prompt_tokens=42, completion_tokens=10, total_tokens=52)


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


def test_token_estimation_accuracy():
    # Empty string
    assert estimate_tokens("") == 0
    assert estimate_tokens("   ") == 0

    # Short sentence
    sentence = "The quick brown fox jumps over the lazy dog."
    tok = estimate_tokens(sentence)
    assert 9 <= tok <= 15

    # Code / technical block
    code = "def calculate_average(values: list[float]) -> float: return sum(values) / len(values)"
    code_tok = estimate_tokens(code)
    assert 18 <= code_tok <= 30

    # History estimation with attachments
    history = [
        ChatMessageInput(role="user", content="Here is my document."),
        ChatMessageInput(
            role="user",
            content="Please review this.",
            attachments=[
                AIAttachment(filename="report.txt", mime_type="text/plain", data=b"", extracted_text="Revenue was $10M.")
            ],
        ),
    ]
    total_est = estimate_history_tokens(history, system_instruction="You are a helpful assistant.")
    assert total_est > 20


def test_should_summarize_context_thresholds():
    # Less than 4 messages -> never summarize
    assert should_summarize_context(total_tokens=1000, context_window=1000, message_count=3) is False

    # Below 75% of context window -> False
    assert should_summarize_context(total_tokens=500, context_window=1000, message_count=6) is False

    # Above 75% of context window -> True
    assert should_summarize_context(total_tokens=760, context_window=1000, message_count=6) is True

    # Token ceiling threshold (>= 6000 tokens with >= 8 turns) -> True
    assert should_summarize_context(total_tokens=6500, context_window=1000000, message_count=8) is True


def test_build_rolling_summary():
    class DummyMsg:
        def __init__(self, role, content):
            self.role = role
            self.content = content

    older = [
        DummyMsg("user", "We are building an Expo mobile application with React Native Web."),
        DummyMsg("assistant", "Excellent choice. Expo SDK supports cross-platform builds with ease."),
        DummyMsg("user", "We decided to use SQLite for offline caching and Supabase for cloud syncing."),
        DummyMsg("assistant", "That architecture provides strong resilience and offline availability."),
    ]

    summary = build_rolling_summary(None, older)
    assert "Expo mobile application" in summary
    assert "SQLite for offline caching" in summary

    # Append subsequent turns
    even_older = [
        DummyMsg("user", "We also added SSE streaming for low-latency responses."),
        DummyMsg("assistant", "SSE ensures fast token delivery without WebSocket overhead."),
    ]
    updated_summary = build_rolling_summary(summary, even_older)
    assert "Expo mobile application" in updated_summary
    assert "SSE streaming" in updated_summary


def test_rolling_summarization_integration_and_indicators(test_client):
    user = unique_auth(test_client, "ctx_user")
    orig_providers = ai_registry.providers
    mock_provider = SmallContextMockProvider()
    mock_provider.captured_prompts = []
    ai_registry.providers = [mock_provider]

    try:
        # Create a conversation
        conv_res = test_client.post(
            "/api/conversations",
            headers=user["headers"],
            json={"title": "Context Test Conv"},
        )
        assert conv_res.status_code == 201
        conv_id = conv_res.json()["id"]

        # Populate conversation with several turns in database directly
        db = SessionLocal()
        try:
            conv = db.query(Conversation).filter(Conversation.id == conv_id).first()
            assert conv is not None

            # Add 6 historical messages (3 user-assistant pairs)
            m1 = Message(id=str(uuid.uuid4()), conversation_id=conv_id, role="user", content="Turn 1: Discuss project architecture requirements.", parent_id=None)
            m2 = Message(id=str(uuid.uuid4()), conversation_id=conv_id, role="assistant", content="Turn 1: Architecture requires React Native and FastAPI.", parent_id=m1.id)
            m3 = Message(id=str(uuid.uuid4()), conversation_id=conv_id, role="user", content="Turn 2: Discuss database migration strategy.", parent_id=m2.id)
            m4 = Message(id=str(uuid.uuid4()), conversation_id=conv_id, role="assistant", content="Turn 2: We use SQLite fallback and Supabase Postgres.", parent_id=m3.id)
            m5 = Message(id=str(uuid.uuid4()), conversation_id=conv_id, role="user", content="Turn 3: Discuss authentication security.", parent_id=m4.id)
            m6 = Message(id=str(uuid.uuid4()), conversation_id=conv_id, role="assistant", content="Turn 3: PBKDF2 with SHA256 and HS256 JWT tokens.", parent_id=m5.id)

            db.add_all([m1, m2, m3, m4, m5, m6])
            db.commit()
            last_msg_id = m6.id
        finally:
            db.close()

        # Send new message with a prompt long enough to exceed the small context window (600 tokens)
        long_prompt = "Turn 4: " + "We need to verify context window limits and rolling summarization. " * 15
        stream_res = test_client.post(
            "/api/chat/stream",
            headers=user["headers"],
            json={
                "conversation_id": conv_id,
                "content": long_prompt,
                "parent_id": last_msg_id,
                "model_id": "gemini-small-ctx",
            },
        )
        assert stream_res.status_code == 200
        events = dict(_parse_sse(stream_res.text))

        # Check meta event contains has_summary: True
        assert "meta" in events
        assert events["meta"]["has_summary"] is True
        assert events["meta"]["summary"] is not None

        # Verify rolling summary was injected into the model prompt's system instruction
        last_captured = mock_provider.captured_prompts[-1]
        assert "[Earlier conversation summary" in last_captured["system"]
        assert "Turn 1" in last_captured["system"]

        # Verify only recent messages were sent verbatim (older messages were summarized)
        sent_messages = last_captured["messages"]
        # The history sent should NOT include the earliest turns verbatim
        sent_contents = [content for _, content in sent_messages]
        assert not any("Turn 1: Discuss project architecture" in c for c in sent_contents)

        # Check GET /api/conversations/{id} returns has_summary: True
        detail_res = test_client.get(f"/api/conversations/{conv_id}", headers=user["headers"])
        assert detail_res.status_code == 200
        conv_data = detail_res.json()
        assert conv_data["has_summary"] is True
        assert conv_data["summary"] is not None
    finally:
        ai_registry.providers = orig_providers


def test_latency_and_usage_logging_per_request(test_client):
    user = unique_auth(test_client, "usage_user")
    orig_providers = ai_registry.providers
    ai_registry.providers = [SmallContextMockProvider()]

    try:
        # Send a chat request
        res = test_client.post(
            "/api/chat/stream",
            headers=user["headers"],
            json={"content": "Log my tokens and latency"},
        )
        assert res.status_code == 200
        events = dict(_parse_sse(res.text))
        usage_data = events["done"]["usage"]

        # Usage in done event
        assert usage_data["prompt_tokens"] > 0
        assert usage_data["completion_tokens"] > 0
        assert usage_data["total_tokens"] > 0
        assert usage_data["latency_ms"] >= 1

        # Verify persisted in database usage_logs table
        db = SessionLocal()
        try:
            log = (
                db.query(UsageLog)
                .filter(UsageLog.user_id == user["user"]["id"])
                .order_by(UsageLog.created_at.desc())
                .first()
            )
            assert log is not None
            assert log.prompt_tokens > 0
            assert log.completion_tokens > 0
            assert log.total_tokens == log.prompt_tokens + log.completion_tokens
            assert log.latency_ms is not None
            assert log.latency_ms >= 1
        finally:
            db.close()

        # Check GET /api/user/usage reflects latency and tokens
        usage_res = test_client.get("/api/user/usage", headers=user["headers"])
        assert usage_res.status_code == 200
        body = usage_res.json()
        assert body["thirty_day_summary"]["requests"] >= 1
        assert body["thirty_day_summary"]["total_tokens"] >= log.total_tokens
        assert body["thirty_day_summary"]["avg_latency_ms"] >= 1
        assert len(body["recent_requests"]) >= 1
        assert body["recent_requests"][0]["latency_ms"] >= 1
    finally:
        ai_registry.providers = orig_providers

