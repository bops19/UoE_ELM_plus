# ELM+ AI Chat

> University of Edinburgh — AI-powered chat interface built on the OpenAI API.

A self-hosted web application for AI-assisted conversations with support for voice, image generation, file attachments, semantic search, and computer use automation.

---

## Features

- **Streaming chat** — real-time token streaming with reasoning/progress updates
- **Session management** — create, rename, archive, and delete conversations
- **Voice chat** — WebRTC-based real-time voice sessions
- **Image generation** — generate, refine, and manage AI images within a session
- **File attachments** — upload documents and include them in model context
- **Embeddings & semantic search** — index and query content via vector embeddings
- **Computer use** — Playwright-powered browser automation via the model
- **Deep research** — configurable MCP server and vector store integrations
- **Prompt presets** — save and reuse system prompt configurations
- **Usage tracking** — per-session token usage and cost rollups
- **Export** — download conversations as Markdown or plain text
- **PWA** — installable as a Progressive Web App

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12, Flask, SQLite, Gunicorn |
| Frontend | Angular 21, TypeScript, RxJS |
| AI | OpenAI API (Chat, Responses, Realtime, Images, Embeddings) |
| Automation | Playwright (Chromium) |
| Infra | Docker, GitHub Actions |

---

## Prerequisites

- Python 3.12+
- Node.js 22 (LTS) — for frontend development
- An [OpenAI API key](https://platform.openai.com/account/api-keys)

---

## Quick Start (Local)

```bash
# 1. Clone and enter the repo
git clone <repo-url>
cd <repo-folder>

# 2. Create a virtual environment
python -m venv venv
source venv/bin/activate        # Mac/Linux
venv\Scripts\activate           # Windows

# 3. Install Python dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Edit .env and set OPENAI_API_KEY and API_KEY

# 5. Start the server
python run.py
```

Open **http://localhost:9595** in your browser.

### Frontend development (optional)

If you want to run the Angular dev server or rebuild the frontend:

```bash
cd frontend
npm install
npm run build        # production build → output to static/ng/
npm start            # dev server at http://localhost:4200
```

---

## Docker

```bash
# Build and run (builds frontend automatically)
docker compose up --build

# Or build the image directly
docker build -t elmplus .
docker run -p 5000:5000 --env-file .env elmplus
```

The container runs on port **5000**.

---

## Environment Variables

Copy `.env.example` to `.env` and configure:

| Variable | Required | Description |
|---|---|---|
| `OPENAI_API_KEY` | Yes | Your OpenAI API key |
| `API_KEY` | Yes (prod) | Secret key for the app's own API guard (`X-API-Key` header) |
| `APP_ENV` | No | `development` or `production` (default: `development`) |
| `ELMPLUS_RUNTIME_DIR` | No | Override for runtime data directory (DB, uploads, logs) |
| `SENTRY_DSN` | No | Sentry error tracking DSN |
| `DEEP_RESEARCH_VECTOR_STORE_IDS` | No | Comma-separated OpenAI vector store IDs |
| `DEEP_RESEARCH_MCP_SERVER_URL` | No | MCP server endpoint for deep research |
| `SESSION_ARCHIVE_AFTER_DAYS` | No | Days before sessions are auto-archived (default: 7) |
| `SESSION_DELETE_ARCHIVED_AFTER_DAYS` | No | Days before archived sessions are deleted (default: 60) |

See `.env.example` for the full list with defaults.

---

## Runtime Data

All runtime state is written to `runtime/` (gitignored):

```
runtime/
├── chat_store.db          # SQLite database
├── chat_files/            # Uploaded attachments
├── prompt_presets.json    # Saved prompt presets
└── token_usage_log.jsonl  # Token usage audit log
```

---

## Project Structure

```
.
├── app.py                  # Flask app factory + route wiring
├── handlers/               # Request handlers (chat, voice, image, …)
├── routes/                 # Flask blueprints
├── frontend/               # Angular 21 workspace
│   └── src/app/
│       ├── core/           # API client, interceptors
│       └── pages/          # Shell page and feature components
├── tests/                  # Backend test suite
├── Dockerfile
└── docker-compose.yml
```

---

## Running Tests

```bash
# Backend
python -m pytest tests/ -v

# Frontend
cd frontend
npm run test
npm run e2e        # Playwright end-to-end
```

---

## License

University of Edinburgh. Internal use.
