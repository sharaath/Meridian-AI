# Meridian AI

**Meridian AI** is a production-ready, cross-platform AI assistant built with **React Native + Expo (TypeScript / React Native Web)** on the frontend, **Python + FastAPI (SSE streaming)** on the backend, **Google Gemini API** (with a provider-independent adapter layer for Anthropic Claude and OpenAI), and **Supabase (PostgreSQL, Auth, Private Storage)** with an automatic local SQLite fallback for high reliability.

---

## Live Deployments & Status

| Service | Platform | URL | Status |
| :--- | :--- | :--- | :---: |
| **Frontend Web App** | **Vercel** | [https://meridian-ai-frontend.vercel.app](https://meridian-ai-frontend.vercel.app) | **Live** (Verified) |
| **Backend API** | **Render** | [https://meridian-ai-vvvv.onrender.com](https://meridian-ai-vvvv.onrender.com) | **Live** (Verified) |
| **Health Endpoint** | **Render** | [https://meridian-ai-vvvv.onrender.com/api/health](https://meridian-ai-vvvv.onrender.com/api/health) | **HTTP 200 OK** |
| **Database** | **Supabase** | `ocqnzkjcffaicqhymwvm` + SQLite Fallback | **Operational** |
| **AI Provider** | **Google Gemini** | `gemini-2.5-flash`, `gemini-2.5-pro`, `gemini-2.0-flash` | **Streaming Active** |

---

## What Has Been Completed & Verified

### 1. Cloud Deployment (100% Operational)
- [x] **Backend deployed on Render**: Python 3.11 runtime, Uvicorn ASGI server with `$PORT` binding, and automatic health monitoring at `GET /` and `GET /api/health`.
- [x] **Frontend deployed on Vercel**: Exported via `npx expo export --platform web` to static distribution, configured with single-page app rewrites in `frontend/vercel.json`.
- [x] **Database & Schema**: Supabase PostgreSQL schema and Row Level Security initialized (`supabase/schema.sql`, `supabase/rls.sql`) with seamless SQLite resilience if the cloud database undergoes network failover.
- [x] **CORS & Preflight**: Fully configured CORS middleware supporting cross-origin credentials and wildcard Vercel preview domains (`https://*.vercel.app`).
- [x] **Gemini API Integration**: Pinned to `api_version: "v1beta"` to support developer system instructions across all 7 assistant modes.

### 2. Core Capabilities
- [x] **Real-Time Streaming Chat**: Low-latency token streaming over Server-Sent Events (SSE) via `POST /api/chat/stream`.
- [x] **Multi-Mode AI Assistance**: Mode pills for **General**, **Coding**, **Writing**, **Email**, **Translate**, **Tutor**, and **Math**.
- [x] **Document Intelligence & Vision**:
  - Full extraction of PDF, DOCX, TXT, MD, and CSV files.
  - Automatic extraction of embedded diagrams and logos from Word (`word/media/*`) and PDF documents, forwarded to Gemini vision models.
  - Page-referenced question answering and document summaries.
- [x] **Multi-Format Export & In-App Artifacts**:
  - Export single messages and full conversations to **PDF**, **DOCX** (Microsoft Word), **PPTX** (PowerPoint presentation slides), and **TXT**.
  - Interactive split-screen preview modal with download buttons.
- [x] **Workspace & Projects**:
  - Custom project workspaces with dedicated custom instructions.
  - Pinned conversations, search chats, and recent chat history with auto-generated titles.
- [x] **Long-Term Memory System**:
  - User memory management (`GET/POST/PATCH/DELETE /api/memories`) injected contextually into conversations.
- [x] **Voice Capabilities**:
  - Speech-to-text recording via `expo-av` and Web Speech API routed to `/api/voice/transcribe`.
  - Text-to-speech reply playback via `expo-speech` / Web Speech Synthesis.
- [x] **Security & Isolation**:
  - PBKDF2-HMAC-SHA256 password hashing.
  - HS256 JWT authentication tokens with per-user data isolation.
  - Sliding-window rate limiting and privacy-safe logging.

### 3. Production QA Suite Results (18 / 18 Passed)
The live production deployment was verified with an automated end-to-end test suite against `https://meridian-ai-frontend.vercel.app` and `https://meridian-ai-vvvv.onrender.com`:

| Test Case | Action Verified | Result |
| :--- | :--- | :---: |
| **Vercel Frontend** | Verified HTTP 200 and static bundle delivery | **PASS** |
| **Render Health** | Probed `GET /api/health` (models & DB status) | **PASS** |
| **Authentication** | User registration and JWT login lifecycle | **PASS** |
| **Profile** | Verified `/api/auth/me` user metadata | **PASS** |
| **Model Catalog** | Verified `/api/models` returns active Gemini models | **PASS** |
| **Projects List** | Fetched user projects | **PASS** |
| **Create Project** | Created custom workspace project | **PASS** |
| **User Settings** | Verified preferences and theme update to `dark` | **PASS** |
| **Memory List** | Listed persisted memories | **PASS** |
| **Add Memory** | Created and stored new memory item | **PASS** |
| **Usage Tracking** | Verified daily quotas and token logs | **PASS** |
| **Live SSE Chat** | Streamed real tokens from Gemini 2.5 Flash | **PASS** |
| **Recent Chats** | Persisted and reloaded conversation history | **PASS** |
| **PDF Export** | Generated valid `%PDF` binary document | **PASS** |
| **DOCX Export** | Generated valid Microsoft Word document | **PASS** |
| **PPTX Export** | Generated valid Microsoft PowerPoint presentation | **PASS** |
| **TXT Export** | Generated clean transcript file | **PASS** |
| **CORS Validation** | Verified preflight and error response headers | **PASS** |

---

### 4. Phase 1B — Precise Editing Engine (100% Implemented & Verified)
Designed specifically to adhere to the strict **Minimal-Change Rule** (change only what was requested, nothing more, nothing less):

- [x] **Instruction Parsing**: Automatically decomposes multi-part user instructions into a structured, numbered checklist with status tracking and per-item summaries (`Done: changed title`).
- [x] **Minimal-Change Rule & Byte-Identical Preservation**: Surgical edits target only requested sentences, paragraphs, or words. Unaffected sections remain 100% byte-for-byte identical. No unsolicited "improvements" or document regenerations.
- [x] **Ambiguity Detection & Handling**: Automatically detects under-specified requests (e.g., "make it better", "fix it") or ambiguous references ("change the paragraph") and returns clarifying questions with labeled options (Option A, Option B, Option C) instead of guessing.
- [x] **Constraint Enforcement**: Strictly respects negative and quantitative constraints: `preserve_headings`, `keep_wording`, and `max_words`.
- [x] **Selection-Based Editing (UI & Backend)**: Lets users select specific text in documents or messages. Slices and splices only that target range back into place, even disambiguating duplicate occurrences using prefix and suffix context.
- [x] **Show What Changed (Diff View & Version History)**:
  - Line-level diff viewer highlighting added lines (green) and removed lines (red).
  - Version management with **Accept**, **Reject**, and **Undo** controls with rollback to any prior version.
- [x] **File-Aware Editing**: In-place modification of DOCX (Microsoft Word), PPTX (PowerPoint), and code files preserving original styles, images (`word/media/*`), fonts, layouts, and tables.
- [x] **Code Syntax Validation**: Automatic AST parsing for Python, JSON validation, and balanced delimiter checking for JavaScript/TypeScript.
- [x] **Automated Evaluation Suite (`eval_precise_editing.py` & pytest)**: 19 / 19 test cases passing (100%).

---

### 5. Phase 1 — Chat Controls (100% Implemented & Verified)
Brings the chat interaction, responsiveness, and conversation branching to parity with top-tier AI assistants:

- [x] **Client & Server Stream Cancellation (Stop Button)**:
  - Real-time Stop button cancels the active SSE stream on both frontend (`AbortController`) and backend (`POST /api/chat/cancel/{conversation_id}` with `asyncio.Event` cancellation tracker).
  - Automatically captures and saves partial replies to the database upon cancellation.
- [x] **Tree Branching & Message Navigation (`parent_id`)**:
  - Full tree structure stored via `messages.parent_id` (indexed, foreign-key self-referential).
  - Editing a user message or regenerating an assistant message creates a non-destructive sibling branch without deleting conversation history.
  - Sibling switcher (`< 1/2 >`) in the UI lets users freely browse alternative response branches.
  - Server-side branch isolation algorithm (`_get_branch_messages`) walks the message tree backwards to prevent cross-branch context contamination.
- [x] **Message Feedback & Copying**:
  - Copy button with animated clipboard feedback on all messages.
  - Per-message Thumbs Up / Thumbs Down feedback (`POST /api/messages/{message_id}/feedback`) persisted to PostgreSQL/SQLite with per-user data isolation.
- [x] **Incremental Markdown & Code Block Controls**:
  - Incremental markdown rendering during streaming without layout shifts or flicker.
  - Multi-language syntax highlighting across Python, TypeScript/JavaScript, SQL, Go, Rust, HTML, CSS, JSON, and Shell.
  - One-click copy code button on all rendered code snippets.
- [x] **Automated Chat Controls Test Suite (`backend/tests/test_chat_controls.py`)**: 5 / 5 automated integration tests passing (100%).

---

### 6. Phase 2 — Context Management & Telemetry (100% Implemented & Verified)
Prevents model context-window exhaustion and maintains crisp conversation history through intelligent compression:

- [x] **Per-Request Token Counting & Estimation**:
  - Implemented token estimation module (`app.services.context_service.estimate_tokens` and `estimate_history_tokens`) evaluating prompt tokens across multi-turn histories, file attachment extractions, system instructions, and framing envelopes.
- [x] **Rolling Summarization of Older Turns**:
  - Context monitor triggers summarization when conversation approaches model context window limits (>= 75%) or exceeds token thresholds (>= 6,000 tokens with 8+ turns).
  - Summarizes older messages into a structured, factual rolling summary stored in `conversations.summary` (`conversations.has_summary = True`).
  - Keeps recent conversation turns (last 4 messages / 2 turns) completely verbatim.
  - Automatically injects the rolling summary into the system instruction `[Earlier conversation summary]: ...` for subsequent turns without prompt bloat.
- [x] **Subtle "Earlier messages summarized" UI Indicator**:
  - Sent via SSE `meta` event (`has_summary: true`, `summary: ...`) and returned in `GET /api/conversations/{id}`.
  - Renders a clean pill indicator (`Earlier messages summarized`) in `ChatWorkspace` directly above verbatim messages.
- [x] **Per-Request Input/Output Tokens & Latency Logging**:
  - Added `latency_ms` tracking via high-resolution performance timers (`time.perf_counter()`) on every completion stream.
  - Logs `prompt_tokens`, `completion_tokens`, `total_tokens`, and `latency_ms` to `usage_logs` table in Supabase PostgreSQL and SQLite.
  - Enhanced `/api/user/usage` and the frontend usage dashboard to display `30-Day Avg Latency` (in ms), `Input / Output Tokens` breakdown, and recent request logs.
- [x] **Automated Context Management Test Suite (`backend/tests/test_context_management.py`)**: 5 / 5 automated integration tests passing (100%).

---

---

## Architecture Overview

```
├── backend/                  # FastAPI + SQLAlchemy + SSE + AI Provider Layer
│   ├── app/
│   │   ├── main.py           # FastAPI entrypoint, CORS, exception handling, rate limiting
│   │   ├── config.py         # Resilient settings, DB URL normalizer, JWT secret generator
│   │   ├── database.py       # Dual engine: PostgreSQL (Supabase) + SQLite fallback
│   │   ├── models/tables.py  # Users, Projects, Conversations, Messages, Files, Memories, Usage
│   │   ├── middleware/       # Auth (JWT), RateLimit, PrivacySafeLogging
│   │   ├── routes/           # auth, chat, files, image, voice, search, memory, projects, user, models, admin
│   │   └── services/         # ai_service, document_service, storage_service, memory_service, search_service, export_service
│   ├── tests/                # Pytest integration suite
│   ├── requirements.txt      # Pinned production Python dependencies
│   ├── .python-version       # Pinned to Python 3.11.9
│   ├── .env.example
│   └── render.yaml           # Render deployment blueprint
├── supabase/
│   ├── schema.sql            # PostgreSQL tables, indexes, triggers
│   └── rls.sql               # Row Level Security & private Storage bucket policies
├── frontend/                 # Expo Router + TypeScript (Web, Android, iOS)
│   ├── app/                  # (app) chat, documents, memory, models, profile, projects, settings, usage, login, register
│   ├── src/
│   │   ├── components/       # MeridianLogo, MarkdownRenderer, ChatWorkspace, SidebarShell, DocumentPreviewModal
│   │   ├── contexts/         # ThemeContext, AuthContext, ChatContext
│   │   ├── services/api.ts   # Typed REST & cross-platform SSE streaming client
│   │   ├── theme/colors.ts   # Light & dark palettes
│   │   └── types/api.ts      # TypeScript domain contracts
│   ├── app.json
│   ├── eas.json              # Expo EAS Android APK & AAB build profiles
│   ├── vercel.json           # Vercel static web export configuration
│   └── .env.example
├── render.yaml               # Root deployment blueprint (rootDir: backend)
└── .python-version           # Root Python runtime pin (3.11.9)
```

---

## Environment Variables

### Backend (`backend/.env` & Render)

| Variable | Required | Description |
|---|---|---|
| `ENVIRONMENT` | Yes | Set to `production` on Render, `development` locally |
| `PYTHON_VERSION` | Yes | `3.11.9` |
| `SECRET_KEY` | Yes | Random 64-character secret for signing JWTs |
| `CORS_ORIGINS` | Yes | `*` or comma-separated frontend URLs (`https://meridian-ai-frontend.vercel.app`) |
| `DATABASE_URL` | Optional | Supabase PostgreSQL URI (leave blank for built-in high-speed SQLite) |
| `SUPABASE_URL` | Optional | `https://ocqnzkjcffaicqhymwvm.supabase.co` |
| `SUPABASE_ANON_KEY` | Optional | Supabase public API key |
| `SUPABASE_SERVICE_ROLE_KEY` | Optional | Supabase service role key (for server-side storage) |
| `GEMINI_API_KEY` | Yes | Google Gemini API key (enables Flash and Pro models) |
| `ANTHROPIC_API_KEY` | Optional | Enables Anthropic Claude models when provided |
| `OPENAI_API_KEY` | Optional | Enables OpenAI models when provided |
| `TAVILY_API_KEY` | Optional | Live web search provider (falls back to DuckDuckGo if empty) |

### Frontend (`frontend/.env` & Vercel)

| Variable | Required | Description |
|---|---|---|
| `EXPO_PUBLIC_API_URL` | Yes | `https://meridian-ai-vvvv.onrender.com` |

---

## Local Development Quickstart

### 1. Backend
```powershell
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
# Set GEMINI_API_KEY in backend/.env
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```
- API Docs: `http://localhost:8000/docs`
- Health check: `http://localhost:8000/api/health`

### 2. Frontend (Web)
```powershell
cd frontend
npm install
copy .env.example .env
npx expo start --web
```
- Open in browser at `http://localhost:8081`

### 3. Android Mobile Build (Expo EAS)
```powershell
cd frontend
# Build standalone APK for direct installation:
eas build -p android --profile preview

# Build production Android App Bundle (AAB) for Google Play:
eas build -p android --profile production
```

---

## License

This project is licensed under the MIT License.
