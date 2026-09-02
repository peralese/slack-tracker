# Slack Tracker — Project Plan

## How to Use This Plan (Read First)

This plan file is the **single source of truth** for building the `slack-tracker` app. It was created in a planning session and should be used in an **Agent mode chat** to drive implementation.

**Implementation instructions for the Agent:**
- Work through sub-tasks **one at a time**, in order
- Read this file at the start of each sub-task for full context
- After completing each sub-task, update its `Status` from `[ ] pending` to `[x] done`
- The project must be created at `/home/peralese/Development/slack-tracker/` — this is a **new standalone project**, not part of `project-kb`
- Use `execute_command` or terminal tools to create the folder and scaffold files outside the current workspace

---

## Conversation Context & Requirements

Everything captured from the planning conversation that is NOT in the sub-tasks:

### User Profile (used in LLM ranking prompt)
> IBM technical consultant/architect focused on AI, data, and cloud solutions for enterprise clients

This profile is embedded in the LLM system prompt inside `llm_client.py` to drive relevance scoring. It should not be hard-coded — put it in `config.yaml` under `ranking.user_profile` so it can be updated without touching code.

### Slack Setup Context
- IBM has an established process for Slack bots via the **CIO Chatops Field Guide**: https://pages.github.ibm.com/CIO-Chatops/cio-chatops-field-guide/
- Use a **bot token** (not user token) — IBM preference per the Field Guide
- Required bot token scopes: `channels:history`, `channels:read`
- The bot monitors **one specific channel** — configured via `config.yaml`
- The channel ID (format: `C0123ABCDEF`) must be obtained from Slack by the user and placed in `config.yaml`

### Polling Behaviour
- **First run / test mode**: scan back `slack.lookback_days` days (configurable, default 7) — this supports testing because relevant content is not posted every day
- **Subsequent runs**: only fetch messages newer than the last seen `slack_message_ts` stored in SQLite — this is the incremental/go-forward mode
- Polling interval is configurable via `slack.poll_interval_minutes` (default 15)

### Ranking Decisions
- **Phase 1 — Keyword pre-filter**: fast, no LLM call, count case-insensitive keyword hits against `ranking.keywords` list in config
- **Phase 2 — LLM scoring**: only for messages that pass the keyword threshold; returns a score (0–10 float) AND a one-sentence explanation of WHY the content is relevant to the user profile
- Both the score and the explanation are displayed on the dashboard

### LLM Provider
- Must be **configurable** — switching providers requires only changing `config.yaml`, not code
- Three providers to support: `openai` (OpenAI-compatible REST), `watsonx` (IBM watsonx.ai), `ollama` (local, no API key)
- Non-secret settings (provider, model, base_url) go in `config.yaml`
- Secret API key goes in `.env` as `LLM_API_KEY` — leave empty for Ollama

### Storage
- SQLite, local file, runs on the user's laptop — no server infrastructure
- Database file path should be configurable (default: `./slack-tracker.db`)

### Dashboard Requirements
- Web UI opened in a browser (React + Vite, served at `localhost:3000`)
- Each item card shows: relevance score (color-coded badge), relevance explanation, original message text, clickable URLs, attachment filenames, posted date, status, notes
- User actions per item: change status (`new` → `reviewed` / `follow_up` / `dismissed`), add/edit free-text notes
- Filter bar: filter by status, filter by minimum relevance score
- "Trigger Poll" button for manual testing without waiting for the scheduled interval

### Security Constraints (IBM policy — non-negotiable)
- FastAPI backend binds to `127.0.0.1` only — never `0.0.0.0`
- CORS restricted to `http://localhost:3000` only — no wildcards
- All secrets (`SLACK_BOT_TOKEN`, `LLM_API_KEY`) in `.env` only — never in `config.yaml` or code
- `.env` must be in `.gitignore`
- Generic error messages to API clients; detailed errors logged server-side only
- No sensitive data in logs

### Tech Stack Confirmed
| Layer | Choice |
|---|---|
| Backend language | Python 3.11+ |
| Backend framework | FastAPI |
| ASGI server | Uvicorn |
| Scheduler | APScheduler |
| Slack SDK | slack-sdk (official Python SDK) |
| ORM | SQLAlchemy |
| HTTP client | httpx |
| Config | pyyaml + pydantic-settings |
| Frontend | React + Vite |
| Frontend HTTP | axios |
| Database | SQLite |

---

## Overview

Build a local application that monitors a specific Slack channel, extracts and ranks content against the user's professional profile (IBM technical consultant — AI, data, and cloud solutions for enterprise clients), and presents a web dashboard where the user can review, score, annotate, and flag items for follow-up.

**Approach:**
- Python/FastAPI backend + React frontend
- Slack Web API polling (periodic, configurable interval)
- Two-phase ranking: keyword pre-filter → LLM relevance scoring
- LLM provider configurable via `config.yaml`; secrets in `.env`
- SQLite for local persistence
- Configurable lookback window for initial/test runs; incremental (new-only) on subsequent runs

**Project location:** `/home/peralese/Development/slack-tracker/`

**Non-goals:**
- Real-time Slack event streaming
- Multi-channel monitoring
- Multi-user support
- Cloud deployment

---

## Project Structure

```
slack-tracker/
├── .env                    # Secrets: Slack bot token, LLM API key
├── .env.example            # Template — no real values
├── .gitignore
├── config.yaml             # Non-secret config: channel, poll interval, LLM provider, keywords, lookback
├── requirements.txt
├── README.md
├── backend/
│   ├── main.py             # FastAPI app entrypoint + APScheduler
│   ├── database.py         # SQLite setup and SQLAlchemy models
│   ├── slack_poller.py     # Slack Web API polling logic
│   ├── ingestion.py        # Content extraction: text, URLs, attachments
│   ├── ranker.py           # Keyword pre-filter + LLM scoring pipeline
│   ├── llm_client.py       # Configurable LLM provider abstraction
│   └── routers/
│       └── items.py        # REST API routes for dashboard
└── frontend/
    ├── package.json
    └── src/
        ├── App.jsx
        ├── components/
        │   ├── ItemList.jsx
        │   ├── ItemCard.jsx
        │   └── FilterBar.jsx
        └── api.js          # Axios calls to FastAPI backend
```

---

## Sub-Tasks

---

### Sub-Task 1 — Project Scaffolding and Configuration

**Intent:**
Establish the project folder structure, dependency files, configuration schema, and secrets template. This is the foundation every other sub-task builds on.

**Expected Outcomes:**
- `/home/peralese/Development/slack-tracker/` exists with the full folder skeleton
- `requirements.txt` lists all Python dependencies
- `config.yaml` has all configurable knobs documented with sensible defaults
- `.env.example` documents required secrets (no real values)
- `.gitignore` excludes `.env`, `*.db`, `__pycache__`, `node_modules`

**Todo List:**
1. Create the full directory structure as shown in the Project Structure section above
2. Write `requirements.txt` — include: `fastapi`, `uvicorn`, `slack-sdk`, `sqlalchemy`, `pydantic`, `pydantic-settings`, `httpx`, `python-dotenv`, `pyyaml`, `apscheduler`
3. Write `config.yaml` with sections:
   - `slack.channel_id` — the channel to monitor
   - `slack.poll_interval_minutes` — how often to poll (default: 15)
   - `slack.lookback_days` — how far back to scan on first run (default: 7)
   - `llm.provider` — one of: `openai`, `watsonx`, `ollama`
   - `llm.model` — model name string
   - `llm.base_url` — optional, for Ollama or custom endpoints
   - `ranking.keywords` — list of relevance keywords for pre-filter
   - `ranking.min_keyword_score` — minimum keyword hits to pass pre-filter (default: 1)
4. Write `.env.example` with placeholders for `SLACK_BOT_TOKEN` and `LLM_API_KEY`
5. Write `.gitignore`

**Relevant Context:**
- Secrets must NEVER appear in `config.yaml` — only in `.env`
- IBM security policy requires secrets via environment variables only

**Status:** `[x] done`

---

### Sub-Task 2 — Database Layer

**Intent:**
Define the SQLite schema and ORM models. All ingested items, their scores, statuses, and user notes are stored here.

**Expected Outcomes:**
- `backend/database.py` defines SQLAlchemy models and creates the DB on startup
- Single `Item` table captures everything needed by the dashboard
- Database file path is configurable (defaults to `./slack-tracker.db`)

**Todo List:**
1. Set up SQLAlchemy with SQLite in `backend/database.py`
2. Define the `Item` model with these fields:
   - `id` — primary key
   - `slack_message_ts` — Slack message timestamp (unique, deduplication key)
   - `slack_channel_id` — channel the message came from
   - `slack_user_id` — sender
   - `posted_at` — datetime of original Slack post
   - `ingested_at` — datetime when the app first captured it
   - `raw_text` — original message text
   - `extracted_urls` — JSON list of URLs found in message
   - `attachment_names` — JSON list of attachment filenames
   - `keyword_score` — integer count of keyword hits
   - `relevance_score` — float 0.0–10.0 from LLM
   - `relevance_explanation` — short LLM-generated string explaining WHY it is relevant
   - `status` — enum: `new`, `reviewed`, `follow_up`, `dismissed`
   - `user_notes` — free text field for user annotations
3. Add a `create_tables()` function called on app startup
4. Add basic CRUD helper functions: `upsert_item`, `get_items`, `update_item_status`, `update_item_notes`

**Relevant Context:**
- `slack_message_ts` is Slack's native unique identifier — use it as the deduplication key to avoid re-processing messages on subsequent polls

**Status:** `[x] done`

---

### Sub-Task 3 — Slack Poller and Ingestion Pipeline

**Intent:**
Implement the Slack Web API polling loop and content extraction logic. This is the data entry point of the system.

**Expected Outcomes:**
- `backend/slack_poller.py` polls the configured channel using `slack-sdk`
- On first run (no prior state), it scans back `lookback_days` from config
- On subsequent runs, it only fetches messages newer than the last seen `ts`
- `backend/ingestion.py` extracts text, URLs, and attachment metadata from raw Slack message payloads
- New messages are passed to the ranker before being written to SQLite

**Todo List:**
1. In `backend/slack_poller.py`:
   - Load `SLACK_BOT_TOKEN` from environment
   - Use `slack_sdk.WebClient` to call `conversations.history` with `oldest` parameter
   - On first run: set `oldest` = now minus `lookback_days`
   - On subsequent runs: set `oldest` = last stored `slack_message_ts` from SQLite
   - Required Slack bot scopes: `channels:history`, `channels:read` (document in README)
2. In `backend/ingestion.py`:
   - Extract `text` from message payload
   - Extract all URLs from `text` using regex and from Slack's `blocks` / `attachments` fields
   - Extract attachment filenames from `files` field if present
   - Return a structured dict ready for the ranker
3. Wire the poller into APScheduler in `backend/main.py` to run on the configured interval
4. Document required Slack bot token scopes in `README.md`

**Relevant Context:**
- Slack `conversations.history` returns messages newest-first — track the highest `ts` seen per run
- Bot token (not user token) is the IBM-preferred approach per CIO Chatops Field Guide
- `SLACK_BOT_TOKEN` lives in `.env` — never log or expose it

**Status:** `[x] done`

---

### Sub-Task 4 — Ranking Engine

**Intent:**
Implement the two-phase ranking pipeline: keyword pre-filter for speed, then LLM scoring for shortlisted items. The LLM provider must be swappable via config.

**Expected Outcomes:**
- `backend/ranker.py` takes an ingested message dict and returns a relevance score (0–10) plus a short explanation
- Messages below `min_keyword_score` are stored with `relevance_score = 0` and skip LLM calls
- `backend/llm_client.py` abstracts provider differences behind a single `score_relevance(text) -> (float, str)` interface
- Supports at minimum: `openai` (OpenAI-compatible API), `watsonx` (IBM watsonx.ai), `ollama` (local)

**Todo List:**
1. In `backend/ranker.py`:
   - Implement `keyword_score(text, keywords) -> int` — case-insensitive keyword hit count
   - If score < `min_keyword_score`, return early with score 0 and explanation "below keyword threshold"
   - Otherwise call `llm_client.score_relevance(text)`
2. In `backend/llm_client.py`:
   - Read `llm.provider`, `llm.model`, `llm.base_url` from config
   - Read `LLM_API_KEY` from environment
   - Implement `score_relevance(text: str) -> tuple[float, str]`
   - System prompt embeds the user profile: IBM technical consultant specializing in AI, data, and cloud solutions for enterprise clients
   - User prompt asks LLM to score 0–10 and return a one-sentence relevance explanation
   - Parse LLM response to extract score and explanation
   - Support `openai` via `httpx` POST to OpenAI-compatible endpoint
   - Support `watsonx` via IBM watsonx.ai REST API
   - Support `ollama` via `httpx` POST to local Ollama endpoint
3. `LLM_API_KEY` must come from environment only — never from config file

**Relevant Context:**
- Keep the LLM prompt concise — the input is a Slack message, not a document
- The system prompt encodes the user profile and does not change at runtime
- Ollama support enables fully local/offline operation with no API key required

**Status:** `[x] done`

---

### Sub-Task 5 — FastAPI Backend (REST API)

**Intent:**
Expose the SQLite data to the React frontend via a clean REST API. The dashboard needs to list, filter, update status, and add notes to items.

**Expected Outcomes:**
- `backend/routers/items.py` provides all routes the frontend needs
- `backend/main.py` wires together FastAPI, APScheduler, CORS, and the router
- API is reachable at `http://127.0.0.1:8000`

**Todo List:**
1. In `backend/routers/items.py` implement:
   - `GET /items` — return all items, support query params: `status`, `min_score`, `sort_by` (score or date)
   - `PATCH /items/{id}/status` — update status to `reviewed`, `follow_up`, or `dismissed`
   - `PATCH /items/{id}/notes` — update user notes
   - `POST /poll/trigger` — manually trigger a poll cycle (for testing)
2. In `backend/main.py`:
   - Initialize FastAPI app
   - Add CORS middleware allowing `http://localhost:3000` only
   - Include the items router
   - On startup: call `create_tables()`, start APScheduler with configured interval
3. Bind to `127.0.0.1` only — never `0.0.0.0` (IBM security policy)

**Relevant Context:**
- CORS must be restricted to `localhost:3000` — no wildcard origins
- Service binds to `127.0.0.1` per IBM network security rules
- Generic error messages to clients; detailed errors logged server-side only

**Status:** `[x] done`

---

### Sub-Task 6 — React Dashboard (Frontend)

**Intent:**
Build a functional web dashboard that displays ranked Slack items and lets the user interact with them.

**Expected Outcomes:**
- React app scaffolded with Vite at `frontend/`
- Dashboard shows ranked items with score, relevance explanation, source text, extracted URLs, and status
- User can change status and add notes inline
- Filter bar for status and minimum relevance score
- Manual poll trigger button for testing

**Todo List:**
1. Scaffold the React app using Vite: `npm create vite@latest frontend -- --template react`
2. Install `axios` for API calls
3. Implement `frontend/src/api.js` — wrapper functions for all FastAPI routes
4. Implement `ItemCard.jsx` — displays a single item with:
   - Relevance score badge (color-coded: green ≥7, yellow 4–6, red <4)
   - Relevance explanation text
   - Original Slack message text
   - Clickable extracted URLs
   - Attachment filenames
   - Status dropdown (new / reviewed / follow up / dismissed)
   - Notes text area with save button
   - Posted date
5. Implement `FilterBar.jsx` — dropdowns/inputs for status filter and minimum score filter
6. Implement `ItemList.jsx` — fetches items from API, renders `FilterBar` + sorted `ItemCard` list
7. Implement `App.jsx` — top-level layout with header, "Trigger Poll" button, and `ItemList`
8. Add basic CSS for readability — no heavy UI framework required

**Relevant Context:**
- All API calls target `http://127.0.0.1:8000` — set this as the base URL in `api.js`
- Dashboard is local-only; no authentication needed

**Status:** `[x] done`

---

### Sub-Task 7 — README and Local Run Instructions

**Intent:**
Document how to set up and run the application locally, including Slack app creation, token scopes, and config setup.

**Expected Outcomes:**
- `README.md` covers everything needed to go from zero to a running app

**Todo List:**
1. Write `README.md` covering:
   - Project overview
   - Prerequisites: Python 3.11+, Node 18+, Slack workspace with bot creation rights
   - Slack app setup: create app, add bot scopes (`channels:history`, `channels:read`), install to workspace, copy bot token to `.env`
   - Copy `.env.example` to `.env` and fill in values
   - Edit `config.yaml` — channel ID, LLM provider, keywords, lookback window
   - Backend: `pip install -r requirements.txt` then `uvicorn backend.main:app --reload`
   - Frontend: `cd frontend && npm install && npm run dev`
   - How to find your Slack channel ID
   - LLM provider configuration examples for OpenAI, watsonx, and Ollama

**Status:** `[x] done`

---

## Configuration Reference

| Key | Location | Purpose |
|---|---|---|
| `SLACK_BOT_TOKEN` | `.env` | Slack bot OAuth token |
| `LLM_API_KEY` | `.env` | API key for LLM provider (empty for Ollama) |
| `slack.channel_id` | `config.yaml` | Slack channel to monitor |
| `slack.poll_interval_minutes` | `config.yaml` | How often to poll (default: 15) |
| `slack.lookback_days` | `config.yaml` | Lookback window for first/test run (default: 7) |
| `llm.provider` | `config.yaml` | `openai`, `watsonx`, or `ollama` |
| `llm.model` | `config.yaml` | Model name string |
| `llm.base_url` | `config.yaml` | Optional custom endpoint URL |
| `ranking.keywords` | `config.yaml` | Pre-filter keyword list |
| `ranking.min_keyword_score` | `config.yaml` | Min keyword hits to pass to LLM (default: 1) |
