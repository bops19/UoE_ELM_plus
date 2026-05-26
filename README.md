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
| Backend | Python 3.14, Flask, SQLite |
| Frontend | Pre-built Angular 21 (served from `static/ng/`) |
| AI | OpenAI API (Chat, Responses, Realtime, Images, Embeddings) |
| Automation | Playwright (Chromium) |
| Infra | GitHub Actions |

---

## Prerequisites

- Python 3.14
- An [OpenAI API key](https://platform.openai.com/account/api-keys)

> Node.js is **not required** — the frontend is pre-built and included in `static/ng/`.
> This project is pinned for **Python 3.14**.

### PDF Conversion

The app supports a Marker-based PDF to Markdown workflow:

- `ArXiv` mode:
  - standard Marker conversion
  - best for born-digital academic PDFs
- `OCR` mode:
  - Marker conversion with forced OCR
  - best for scanned or image-heavy PDFs

The `Create Markdown` tool in the webapp exposes these two modes directly from
the dropdown in the Tools section.

### Optional Enhanced PDF Converters

`Marker` is used by the webapp for PDF conversion, but it is **not**
included in the main app environment because its current package metadata
conflicts with this project's pinned dependencies.

Current conflict:

- `marker-pdf==1.10.2` requires `openai<2.0.0`
- this app pins `openai==2.33.0`

If you want PDF-to-Markdown support in the webapp, install `Marker`
separately and make
`marker_single` available on your system `PATH`:

#### macOS / Linux

```bash
python3 -m venv .venv-marker
source .venv-marker/bin/activate
pip install -r requirements-pdf-marker.txt
```

#### Windows

```powershell
py -3.14 -m venv .venv-marker
.venv-marker\Scripts\activate
pip install -r requirements-pdf-marker.txt
```

The webapp will use `Marker` automatically when `marker_single` is available.

---

## Quick Start

### macOS / Linux

```bash
# 1. Clone and enter the repo
git clone <repo-url>
cd <repo-folder>

# 2. Create a Python 3.14 virtual environment
python3 -m venv venv
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set your OpenAI API key
export OPENAI_API_KEY="your_api_key"

# 5. Configure environment
cp .env.example .env
# Edit .env if you want to persist additional settings

# 6. Start the server
python3 run.py
```

### Windows

```bat
:: 1. Clone and enter the repo
git clone <repo-url>
cd <repo-folder>

:: 2. Create a Python 3.14 virtual environment
py -3.14 -m venv venv
venv\Scripts\activate

:: 3. Install dependencies
pip install -r requirements.txt

:: 4. Set your OpenAI API key in PowerShell
powershell -Command "$env:OPENAI_API_KEY='your_api_key'"

:: 5. Configure environment
copy .env.example .env
:: Edit .env if you want to persist additional settings

:: 6. Start the server
python run.py
```

If you are already in PowerShell, you can set the key directly with:

```powershell
$env:OPENAI_API_KEY="your_api_key"
```

Open **http://localhost:9595** in your browser.

---

## Computer Use (optional)

The computer use tab requires Playwright browsers. Run once after installing dependencies:

```bash
playwright install chromium
```

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
├── run.py                  # Entry point
├── handlers/               # Request handlers (chat, voice, image, …)
├── routes/                 # Flask blueprints
├── static/ng/              # Pre-built Angular frontend (served by Flask)
└── tests/                  # Backend test suite
```

---

## Running Tests

```bash
python -m pytest tests/ -v
```

---

## License

University of Edinburgh. Internal use.
