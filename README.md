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

## Prerequisites

- **Python 3.10+**
- An [OpenAI API key](https://platform.openai.com/account/api-keys)

> No Node.js required — the frontend is pre-built and included in `static/ng/`.

---

## Quick Start

### macOS / Linux

```bash
# 1. Clone the repo
git clone https://github.com/bops19/UoE_ELM_plus.git
cd UoE_ELM_plus

# 2. Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env

# Open .env in a text editor and fill in your keys:
#   OPENAI_API_KEY=sk-...
#   API_KEY=any-secret-string-you-choose
# Or set them directly from the terminal:
export OPENAI_API_KEY="sk-your-key-here"
export API_KEY="your-secret-here"

# 5. Start the server
python run.py
```

### Windows

```cmd
:: 1. Clone the repo
git clone https://github.com/bops19/UoE_ELM_plus.git
cd UoE_ELM_plus

:: 2. Create and activate a virtual environment
python -m venv venv
venv\Scripts\activate

:: 3. Install dependencies
pip install -r requirements.txt

:: 4. Configure environment
copy .env.example .env

:: Open .env in Notepad and fill in your keys:
::   OPENAI_API_KEY=sk-...
::   API_KEY=any-secret-string-you-choose
:: Or set them directly in the terminal:
set OPENAI_API_KEY=sk-your-key-here
set API_KEY=your-secret-here

:: 5. Start the server
python run.py
```

Open **http://localhost:9595** in your browser.

---

## Docker

No Python or pip install needed — just Docker Desktop.

```bash
git clone https://github.com/bops19/UoE_ELM_plus.git
cd UoE_ELM_plus
cp .env.example .env   # add your OPENAI_API_KEY and API_KEY
docker compose up
```

Open **http://localhost:9595** in your browser.

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

Runtime files (database, uploads, logs) are stored in a user profile directory — **not** inside the repo folder. The location depends on your OS:

| OS | Default path |
|---|---|
| **macOS** | `~/Library/Application Support/elmplus/runtime/` |
| **Windows** | `%APPDATA%\elmplus\runtime\` |
| **Linux** | `~/.local/share/elmplus/runtime/` |

```
runtime/
├── chat_store.db          # SQLite database
├── chat_files/            # Uploaded attachments
├── prompt_presets.json    # Saved prompt presets
└── token_usage_log.jsonl  # Token usage audit log
```

To override the location, set `ELMPLUS_RUNTIME_DIR` in your `.env`:

```
ELMPLUS_RUNTIME_DIR=/path/to/your/runtime
```

---

## Project Structure

```
.
├── app.py                  # Flask app factory + route wiring
├── run.py                  # Dev server entry point
├── handlers/               # Request handlers (chat, voice, image, …)
├── routes/                 # Flask blueprints
├── static/ng/              # Pre-built Angular frontend (no build step needed)
├── tests/                  # Backend test suite
├── Dockerfile
└── docker-compose.yml
```

---

## Running Tests

```bash
python -m pytest tests/ -v
```

---

## License

University of Edinburgh. Internal use.
