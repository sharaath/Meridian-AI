"""Backend API test suite covering auth, models, SSE chat, documents, memory, security, and exports."""

from __future__ import annotations

import io
import json
import zipfile

from fpdf import FPDF

from app.middleware.rate_limit import rate_limiter_store
from app.services.ai_service import (
    AIGenerationConfig,
    AIModelInfo,
    AIStreamChunk,
    BaseAIProvider,
    ChatMessageInput,
    ai_registry,
)
from tests.conftest import register_and_auth


class MockConfiguredProvider(BaseAIProvider):
    """Test double registered temporarily to verify real SSE pipeline and context wiring."""

    provider_id = "gemini"
    required_env_var = "GEMINI_API_KEY"
    captured_prompts = []

    def is_configured(self) -> bool:
        return True

    def list_models(self):
        return [
            AIModelInfo(
                id="gemini-2.5-flash",
                name="Gemini 2.5 Flash",
                provider="gemini",
                description="Test Gemini model",
                context_window=1048576,
                max_output_tokens=8192,
                configured=True,
            )
        ]

    async def stream_chat(self, model_id: str, messages: list[ChatMessageInput], config: AIGenerationConfig):
        self.captured_prompts.append(
            {
                "model_id": model_id,
                "system": config.system_instruction,
                "messages": [(m.role, m.content, len(m.attachments)) for m in messages],
            }
        )
        yield AIStreamChunk(delta="Hello from ")
        yield AIStreamChunk(delta="Meridian AI!")
        yield AIStreamChunk(done=True, prompt_tokens=12, completion_tokens=6, total_tokens=18)


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
                data_obj = json.loads(line[6:])
        events.append((event_name, data_obj))
    return events


def test_health_and_unconfigured_models(test_client):
    res = test_client.get("/api/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["configured_models"] == 0

    models_res = test_client.get("/api/models")
    assert models_res.status_code == 200
    assert models_res.json()["models"] == []
    assert models_res.json()["any_configured"] is False


def test_auth_lifecycle_and_password_reset(test_client):
    # Weak password rejected
    bad = test_client.post(
        "/api/auth/register",
        json={"email": "weak@example.com", "username": "weak", "password": "123"},
    )
    assert bad.status_code in (400, 422)

    # Register user
    user_a = register_and_auth(test_client, "alice@example.com", "Alice")
    headers = user_a["headers"]

    # Duplicate email rejected
    dup = test_client.post(
        "/api/auth/register",
        json={"email": "alice@example.com", "username": "Alice2", "password": "StrongPass123!"},
    )
    assert dup.status_code == 409

    # Me endpoint
    me = test_client.get("/api/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["email"] == "alice@example.com"

    # Email verification flow
    ver_req = test_client.post("/api/auth/verify-email/request", headers=headers)
    assert ver_req.status_code == 200
    token = ver_req.json()["dev_verification_token"]
    ver_conf = test_client.post("/api/auth/verify-email/confirm", json={"token": token})
    assert ver_conf.status_code == 200

    # Password reset flow
    reset_req = test_client.post("/api/auth/password-reset/request", json={"email": "alice@example.com"})
    assert reset_req.status_code == 200
    reset_tok = reset_req.json()["dev_reset_token"]
    reset_conf = test_client.post(
        "/api/auth/password-reset/confirm",
        json={"token": reset_tok, "new_password": "NewStrongPass456!"},
    )
    assert reset_conf.status_code == 200

    # Old password fails, new password works
    old_login = test_client.post("/api/auth/login", json={"email": "alice@example.com", "password": "StrongPass123!"})
    assert old_login.status_code == 401
    new_login = test_client.post("/api/auth/login", json={"email": "alice@example.com", "password": "NewStrongPass456!"})
    assert new_login.status_code == 200


def test_unconfigured_chat_returns_503_never_fake(test_client):
    u = register_and_auth(test_client, "noai@example.com", "NoAI")
    res = test_client.post(
        "/api/chat/stream",
        headers=u["headers"],
        json={"content": "Hello?"},
    )
    assert res.status_code == 503
    assert "GEMINI_API_KEY" in res.json()["detail"]


def test_files_pdf_docx_txt_and_validation(test_client):
    u = register_and_auth(test_client, "docs@example.com", "DocsUser")
    headers = u["headers"]

    # 1. TXT upload
    txt_res = test_client.post(
        "/api/files/upload",
        headers=headers,
        files={"file": ("notes.txt", b"Meridian architecture notes line 1.", "text/plain")},
    )
    assert txt_res.status_code == 201, txt_res.text
    assert txt_res.json()["processing_status"] == "ready"
    assert "Meridian architecture notes" in txt_res.json()["extracted_text"]

    # 2. PDF upload (generated with fpdf)
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)
    pdf.cell(0, 10, "Quarterly Revenue Report 2026")
    pdf_bytes = bytes(pdf.output())

    pdf_res = test_client.post(
        "/api/files/upload",
        headers=headers,
        files={"file": ("report.pdf", pdf_bytes, "application/pdf")},
    )
    assert pdf_res.status_code == 201, pdf_res.text
    assert pdf_res.json()["page_count"] == 1
    assert "Quarterly Revenue Report" in pdf_res.json()["extracted_text"]

    # 3. DOCX upload (minimal valid OOXML zip with embedded logo image)
    from PIL import Image
    from app.services.document_service import extract_embedded_images

    logo_buf = io.BytesIO()
    Image.new("RGB", (12, 12), color=(13, 148, 136)).save(logo_buf, format="PNG")
    docx_buf = io.BytesIO()
    with zipfile.ZipFile(docx_buf, "w") as zf:
        zf.writestr(
            "word/document.xml",
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            "<w:body><w:p><w:r><w:t>Project Meridian Specification</w:t></w:r></w:p></w:body>"
            "</w:document>",
        )
        zf.writestr("word/media/logo.png", logo_buf.getvalue())

    embedded = extract_embedded_images(docx_buf.getvalue(), "docx")
    assert len(embedded) == 1
    assert embedded[0].mime_type == "image/png"
    docx_res = test_client.post(
        "/api/files/upload",
        headers=headers,
        files={
            "file": (
                "spec.docx",
                docx_buf.getvalue(),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )
    assert docx_res.status_code == 201, docx_res.text
    assert "Project Meridian Specification" in docx_res.json()["extracted_text"]

    # 4. Unsupported extension blocked
    bad_file = test_client.post(
        "/api/files/upload",
        headers=headers,
        files={"file": ("script.exe", b"MZ...", "application/octet-stream")},
    )
    assert bad_file.status_code == 400


def test_streaming_chat_edit_regenerate_export_share_and_isolation(test_client):
    alice = register_and_auth(test_client, "stream_alice@example.com", "StreamAlice")
    bob = register_and_auth(test_client, "stream_bob@example.com", "StreamBob")

    # Add memory and project for Alice
    mem_res = test_client.post(
        "/api/memories",
        headers=alice["headers"],
        json={"memory_content": "Prefers concise TypeScript examples.", "category": "coding"},
    )
    assert mem_res.status_code == 201

    proj_res = test_client.post(
        "/api/projects",
        headers=alice["headers"],
        json={"name": "Mobile App", "custom_instructions": "Always mention Expo compatibility."},
    )
    assert proj_res.status_code == 201
    project_id = proj_res.json()["id"]

    # Temporarily swap provider registry to test full SSE stream + persistence
    orig_providers = ai_registry.providers
    mock_provider = MockConfiguredProvider()
    ai_registry.providers = [mock_provider]
    try:
        # Verify models endpoint sees configured model
        m_res = test_client.get("/api/models")
        assert len(m_res.json()["models"]) == 1

        # Stream chat
        stream_res = test_client.post(
            "/api/chat/stream",
            headers=alice["headers"],
            json={
                "content": "Explain SSE in FastAPI",
                "project_id": project_id,
                "mode": "coding",
            },
        )
        assert stream_res.status_code == 200
        events = _parse_sse(stream_res.text)
        event_names = [e[0] for e in events]
        assert "meta" in event_names
        assert "delta" in event_names
        assert "done" in event_names

        meta = dict(events)["meta"]
        conv_id = meta["conversation_id"]
        user_msg_id = meta["user_message_id"]

        # Verify memory & project instructions were injected into AI call
        last_prompt = mock_provider.captured_prompts[-1]
        assert "Prefers concise TypeScript examples." in last_prompt["system"]
        assert "Always mention Expo compatibility." in last_prompt["system"]

        # Bob cannot access Alice's conversation (strict isolation)
        bob_get = test_client.get(f"/api/conversations/{conv_id}", headers=bob["headers"])
        assert bob_get.status_code == 404

        # Search conversations
        search_res = test_client.get("/api/conversations?q=FastAPI", headers=alice["headers"])
        assert search_res.status_code == 200
        assert len(search_res.json()) == 1

        # Edit and resend user message
        edit_res = test_client.post(
            f"/api/chat/messages/{user_msg_id}/edit",
            headers=alice["headers"],
            json={"content": "Explain WebSockets vs SSE in FastAPI"},
        )
        assert edit_res.status_code == 200
        assert any(name == "done" for name, _ in _parse_sse(edit_res.text))

        # Regenerate
        regen_res = test_client.post(
            f"/api/chat/conversations/{conv_id}/regenerate",
            headers=alice["headers"],
            json={},
        )
        assert regen_res.status_code == 200
        assert any(name == "done" for name, _ in _parse_sse(regen_res.text))

        # Export TXT and PDF
        txt_exp = test_client.get(f"/api/conversations/{conv_id}/export?format=txt", headers=alice["headers"])
        assert txt_exp.status_code == 200
        assert "WebSockets vs SSE" in txt_exp.text

        pdf_exp = test_client.get(f"/api/conversations/{conv_id}/export?format=pdf", headers=alice["headers"])
        assert pdf_exp.status_code == 200
        assert pdf_exp.content.startswith(b"%PDF")

        # Export single assistant message as standalone PDF, DOCX, and PPTX
        regen_done = dict(_parse_sse(regen_res.text))["done"]
        asst_msg_id = regen_done["assistant_message"]["id"]
        msg_pdf = test_client.get(f"/api/messages/{asst_msg_id}/export?format=pdf", headers=alice["headers"])
        assert msg_pdf.status_code == 200
        assert msg_pdf.content.startswith(b"%PDF")

        msg_docx = test_client.get(f"/api/messages/{asst_msg_id}/export?format=docx", headers=alice["headers"])
        assert msg_docx.status_code == 200
        with zipfile.ZipFile(io.BytesIO(msg_docx.content)) as zf:
            assert "word/document.xml" in zf.namelist()

        # Verify template DOCX preserves embedded media/logos and renders tables
        from app.services.export_service import export_message_docx
        tpl_buf = io.BytesIO()
        with zipfile.ZipFile(tpl_buf, "w") as zf:
            zf.writestr(
                "word/document.xml",
                '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                "<w:body><w:p><w:r><w:drawing/></w:r></w:p><w:sectPr/></w:body></w:document>",
            )
            zf.writestr("word/media/logo.png", b"PNGDATA")
        templated_docx = export_message_docx(
            "# Revised Title\n\n| Skill | Level |\n| --- | --- |\n| Python | Expert |",
            template_docx_bytes=tpl_buf.getvalue(),
        )
        with zipfile.ZipFile(io.BytesIO(templated_docx)) as zf:
            assert "word/media/logo.png" in zf.namelist()
            doc_xml = zf.read("word/document.xml").decode("utf-8")
            assert "<w:tbl>" in doc_xml
            assert "<w:drawing/>" in doc_xml

        msg_pptx = test_client.get(f"/api/messages/{asst_msg_id}/export?format=pptx", headers=alice["headers"])
        assert msg_pptx.status_code == 200
        with zipfile.ZipFile(io.BytesIO(msg_pptx.content)) as zf:
            assert "ppt/presentation.xml" in zf.namelist()
            assert "ppt/slides/slide1.xml" in zf.namelist()

        # Share & Revoke
        share_res = test_client.post(f"/api/conversations/{conv_id}/share", headers=alice["headers"])
        assert share_res.status_code == 200
        share_token = share_res.json()["share_token"]

        public_view = test_client.get(f"/api/shared/{share_token}")
        assert public_view.status_code == 200
        assert len(public_view.json()["messages"]) == 2

        revoke_res = test_client.delete(f"/api/conversations/{conv_id}/share", headers=alice["headers"])
        assert revoke_res.status_code == 204
        revoked_view = test_client.get(f"/api/shared/{share_token}")
        assert revoked_view.status_code == 404

        # Usage dashboard reflects logged tokens
        usage_res = test_client.get("/api/user/usage", headers=alice["headers"])
        assert usage_res.status_code == 200
        assert usage_res.json()["thirty_day_summary"]["total_tokens"] >= 18
    finally:
        ai_registry.providers = orig_providers


def test_admin_rbac_and_rate_limit(test_client):
    regular = register_and_auth(test_client, "nonadmin@example.com", "Regular")
    forbidden = test_client.get("/api/admin/overview", headers=regular["headers"])
    assert forbidden.status_code == 403

    # Rate limit check using store directly so we don't pollute other tests
    rate_limiter_store.reset()
    for _ in range(3):
        allowed, _ = rate_limiter_store.allow("test-ip", limit=3, window_seconds=60)
        assert allowed is True
    allowed, retry_after = rate_limiter_store.allow("test-ip", limit=3, window_seconds=60)
    assert allowed is False
    assert retry_after >= 1
    rate_limiter_store.reset()

