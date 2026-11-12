# Meridian AI

**Meridian AI** is an original, cross-platform AI assistant built with **React Native + Expo (TypeScript / React Native Web)** on the frontend, **Python + FastAPI (SSE streaming)** on the backend, **Google Gemini API** (with a provider-independent adapter layer for Anthropic Claude and OpenAI), and **Supabase (PostgreSQL, Auth, Private Storage)** with a local SQLite/JWT development fallback.

---

## Architecture Overview

```
├── backend/                  # FastAPI + SQLAlchemy + SSE + AI Provider Layer
│   ├── app/
│   │   ├── main.py           # FastAPI app, CORS, rate limiting, logging
│   │   ├── config.py         # Environment variable & secret management
│   │   ├── database.py       # PostgreSQL (Supabase) & SQLite session engine
│   │   ├── models/tables.py  # Users, Projects, Conversations, Messages, Files, Memories, Usage
│   │   ├── middleware/       # Auth (Local JWT + Supabase JWT), RateLimit, PrivacySafeLogging
│   │   ├── routes/           # auth, chat, files, image, voice, search, memory, projects, user, models, admin
│   │   └── services/         # ai_service, document_service, storage_service, memory_service, search_service, export_service
│   ├── tests/                # Pytest integration suite
│   ├── requirements.txt
│   ├── .env.example
│   └── render.yaml           # Render deployment blueprint
├── supabase/
│   ├── schema.sql            # PostgreSQL tables, indexes, triggers
│   └── rls.sql               # Row Level Security & private Storage bucket policies
└── frontend/                 # Expo Router + TypeScript (Web, Android, iOS)
    ├── app/                  # Landing, Login, Register, Reset Password, Share Viewer, Chat, Documents, Profile, Settings, Models, Memory, Usage, Admin
    ├── src/
    │   ├── components/       # MeridianLogo, MarkdownRenderer, ChatWorkspace, SidebarShell
    │   ├── contexts/         # ThemeContext, AuthContext, ChatContext
    │   ├── services/api.ts   # Typed REST & cross-platform SSE streaming client
    │   ├── theme/colors.ts   # Light & dark palettes
    │   └── types/api.ts      # TypeScript domain contracts
    ├── app.json
    ├── eas.json              # Expo EAS Android APK & AAB build profiles
    ├── vercel.json           # Vercel static web export configuration
    └── .env.example
```

---

## Key Capabilities

- **Real-Time Streaming Chat**: Server-Sent Events (`POST /api/chat/stream`), stop generation, edit & resend user messages, regenerate replies, copy response, follow-up suggestions, timestamps, error retry.
- **Rich Markdown & Coding Assistant**: Native cross-platform Markdown renderer supporting headings, lists, blockquotes, formatted tables, and syntax-highlighted code blocks with one-click copy.
- **Document Intelligence**: Upload PDF, DOCX, TXT, MD, and CSV files; extracts text with page references; summarize and ask questions across multiple files (`POST /api/files/analyze`).
- **Image Understanding**: Upload images (PNG, JPG, WEBP, GIF) for multimodal vision analysis, OCR, and chart/diagram explanation.
- **Voice Assistant**: Speech-to-text (Web Speech API on supported browsers + `expo-av` recording -> `/api/voice/transcribe`) and text-to-speech (`expo-speech` / `window.speechSynthesis`).
- **Web Search**: Live search integration (`TAVILY_API_KEY`, `SERPER_API_KEY`, or DuckDuckGo HTML fallback) with clickable source citations.
- **Memory & Workspaces**: Manage saved memories (`GET/POST/PATCH/DELETE /api/memories`), project workspaces with custom instructions, and global custom instructions.
- **Multi-Mode Assistant**: General, Coding, Writing, Email, Translation, Tutor, and Math modes.
- **Export & Sharing**: Export conversations to TXT or PDF, and create/revoke explicit read-only share links (`/share/[token]`).
- **Security**: Zero frontend API keys, PBKDF2-HMAC-SHA256 password hashing, HS256 JWT / Supabase Auth, strict per-user resource ownership, private storage paths, MIME/extension/size upload validation, sliding-window rate limiting, and privacy-safe logging.

---

## Environment Variables

### Backend (`backend/.env`)

Copy `backend/.env.example` to `backend/.env`:

| Variable | Required | Description |
|---|---|---|
| `SECRET_KEY` | Yes (prod) | Secret key for signing JWTs in local auth mode |
| `CORS_ORIGINS` | Yes | Comma-separated allowed frontend origins |
| `DATABASE_URL` | Optional | PostgreSQL connection string (defaults to local SQLite `meridian_dev.db` if empty) |
| `SUPABASE_URL` | Optional | Supabase project URL |
| `SUPABASE_ANON_KEY` | Optional | Supabase anonymous/public key |
| `SUPABASE_SERVICE_ROLE_KEY` | Optional | Supabase service role key (used server-side for private storage) |
| `SUPABASE_JWT_SECRET` | Optional | Supabase JWT secret for local token verification |
| `GEMINI_API_KEY` | Recommended | Google Gemini API key (enables `gemini-2.5-flash`, `gemini-2.5-pro`, `gemini-2.0-flash`) |
| `ANTHROPIC_API_KEY` | Optional | Enables Anthropic Claude models when set |
| `OPENAI_API_KEY` | Optional | Enables OpenAI models when set |
| `TAVILY_API_KEY` | Optional | Tavily web search API key |
| `SERPER_API_KEY` | Optional | Serper web search API key |
| `ADMIN_EMAIL` | Optional | Email promoted to `admin` role upon registration |

> **Important**: Only AI models whose API key is configured on the backend are exposed in the model selector. If no key is set, `/api/models` returns an empty list and chat requests return `503 Service Unavailable` with setup instructions.

### Frontend (`frontend/.env`)

Copy `frontend/.env.example` to `frontend/.env`:

| Variable | Description |
|---|---|
| `EXPO_PUBLIC_API_URL` | URL of your FastAPI backend (e.g. `http://localhost:8000` or your Render URL) |

---

## Setup & Local Development

### 1. Supabase Setup (Optional for local dev, Recommended for production)
1. Create a free project at [supabase.com](https://supabase.com).
2. Open **SQL Editor** and run `supabase/schema.sql`.
3. Then run `supabase/rls.sql` to enable Row Level Security and create the private `meridian-uploads` bucket.
4. Copy your Project URL, Anon Key, Service Role Key, JWT Secret, and PostgreSQL connection string into `backend/.env`.

### 2. Backend Setup
```powershell
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
# Add GEMINI_API_KEY in backend/.env
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```
API docs are available at `http://localhost:8000/docs`.

### 3. Frontend Setup (Web & Mobile)
```powershell
cd frontend
npm install
copy .env.example .env
npx expo start --web
```
To test on Android via Expo Go or an emulator:
```powershell
npx expo start --android
```
*(When testing on a physical Android device over Wi-Fi, set `EXPO_PUBLIC_API_URL` to your computer's LAN IP, e.g. `http://192.168.1.10:8000`.)*

---

## API Reference Summary

- **System**: `GET /api/health`
- **Auth**: `POST /api/auth/register`, `POST /api/auth/login`, `POST /api/auth/logout`, `GET /api/auth/me`, `POST /api/auth/verify-email/request`, `POST /api/auth/verify-email/confirm`, `POST /api/auth/password-reset/request`, `POST /api/auth/password-reset/confirm`, `GET /api/auth/oauth/google`
- **Models**: `GET /api/models` (configured only), `GET /api/models/catalog` (all providers + status)
- **Chat & Conversations**: `GET /api/conversations`, `POST /api/conversations`, `GET /api/conversations/{id}`, `PATCH /api/conversations/{id}`, `DELETE /api/conversations/{id}`, `POST /api/chat/stream` (SSE), `POST /api/chat/messages/{id}/edit` (SSE), `POST /api/chat/conversations/{id}/regenerate` (SSE), `GET /api/conversations/{id}/export?format=txt|pdf`, `POST/DELETE /api/conversations/{id}/share`, `GET /api/shared/{token}`
- **Documents & Vision**: `POST /api/files/upload`, `GET /api/files`, `GET /api/files/{id}`, `GET /api/files/{id}/download`, `DELETE /api/files/{id}`, `POST /api/files/analyze`, `POST /api/image/analyze`
- **Voice & Search**: `POST /api/voice/transcribe`, `POST /api/search`
- **Memory & Projects**: `GET/POST /api/memories`, `PATCH/DELETE /api/memories/{id}`, `GET/POST /api/projects`, `PATCH/DELETE /api/projects/{id}`
- **User & Admin**: `GET/PATCH /api/user/preferences`, `PATCH /api/user/profile`, `GET /api/user/usage`, `GET /api/admin/overview`, `PATCH /api/admin/users/{id}/plan`

---

## Testing

### Backend API & Security Tests
```powershell
cd backend
python -m pytest tests/test_api.py -v
```
Tests verify authentication, email verification, password reset, strict unconfigured-model `503` behavior, PDF/DOCX/TXT extraction, invalid file rejection, SSE streaming, memory & project prompt injection, edit/regenerate, TXT/PDF export, share/revoke links, user isolation, admin RBAC, and rate limiting.

### Frontend TypeScript Check
```powershell
cd frontend
npm run typecheck
```

---

## Production Deployment

### 1. Backend on Render
1. Push repository to GitHub.
2. Create a new **Web Service** on Render pointing to `backend/` (or use `backend/render.yaml`).
3. Set environment variables (`ENVIRONMENT=production`, `SECRET_KEY`, `DATABASE_URL`, `SUPABASE_*`, `GEMINI_API_KEY`, `CORS_ORIGINS`).

### 2. Web Frontend on Vercel
1. Import the repository in Vercel with Root Directory set to `frontend`.
2. Vercel uses `frontend/vercel.json` (`npx expo export --platform web` -> `dist/`).
3. Add `EXPO_PUBLIC_API_URL=https://your-backend.onrender.com` in Vercel Environment Variables.

### 3. Android APK & Google Play AAB via Expo EAS
```powershell
cd frontend
npm install -g eas-cli
eas login
eas build:configure
# Build installable Android APK:
eas build -p android --profile preview
# Build Play Store App Bundle (AAB):
eas build -p android --profile production
```

