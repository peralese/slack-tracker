# Slack Tracker — Project Status & Current Blocker

> Handoff document · Generated for AI-assisted troubleshooting

---

## 1. What Was Built

A fully local application that monitors a specific IBM Slack channel, ranks messages by relevance to a user profile using a two-phase pipeline (keyword pre-filter → LLM scoring), and presents a web dashboard for review and annotation.

| Sub-Task | Description | Status |
|---|---|---|
| 1. Scaffolding | Directory structure, `requirements.txt`, `config.yaml`, `.env.example`, `.gitignore` | ✅ Done |
| 2. Database Layer | SQLAlchemy + SQLite, `Item` model, CRUD helpers in `backend/database.py` | ✅ Done |
| 3. Slack Poller | `backend/slack_poller.py` + `backend/ingestion.py` — polls via `conversations.history`, extracts text/URLs/attachments | ✅ Done |
| 4. Ranking Engine | `backend/ranker.py` + `backend/llm_client.py` — keyword pre-filter then LLM scoring; supports OpenAI, IBM watsonx.ai, Ollama | ✅ Done |
| 5. FastAPI Backend | `backend/main.py` + `backend/routers/items.py` — REST API, APScheduler, CORS locked to `localhost:3000`, bound to `127.0.0.1` | ✅ Done |
| 6. React Dashboard | Vite + React frontend — item cards with score badges, status/notes editing, filter bar, manual poll trigger | ✅ Done |
| 7. README | Full setup docs, Slack app instructions, LLM provider examples | ✅ Done |

---

## 2. Tech Stack

| Layer | Technology |
|---|---|
| Backend language | Python 3.14 (3.11+ required) |
| Backend framework | FastAPI + Uvicorn |
| Scheduler | APScheduler |
| Slack SDK | slack-sdk (official Python SDK) |
| ORM / Database | SQLAlchemy + SQLite (local file) |
| HTTP client | httpx |
| Config | pyyaml + pydantic-settings + python-dotenv |
| Frontend | React + Vite |
| Frontend HTTP | axios |

---

## 3. Key Files

```
slack-tracker/
├── .env                    # Secrets: SLACK_BOT_TOKEN, LLM_API_KEY (not committed)
├── .env.example            # Template — no real values
├── config.yaml             # Non-secret config (channel, poll interval, LLM, keywords)
├── requirements.txt
├── README.md
├── backend/
│   ├── main.py             # FastAPI app + APScheduler startup
│   ├── database.py         # SQLAlchemy Item model + CRUD helpers
│   ├── slack_poller.py     # Slack conversations.history polling
│   ├── ingestion.py        # Text / URL / attachment extraction
│   ├── ranker.py           # Keyword pre-filter + LLM scoring pipeline
│   ├── llm_client.py       # Pluggable LLM abstraction (OpenAI / watsonx / Ollama)
│   └── routers/items.py    # REST routes: GET /items, PATCH /items/{id}/status|notes, POST /poll/trigger
└── frontend/src/
    ├── App.jsx             # Layout + Trigger Poll button
    ├── api.js              # Axios wrappers (base URL: http://127.0.0.1:8000)
    └── components/
        ├── ItemCard.jsx    # Score badge, explanation, URLs, status/notes editing
        ├── ItemList.jsx    # Fetches + renders items with filters
        └── FilterBar.jsx   # Status, min score, sort filters
```

---

## 4. Current Status — One Remaining Blocker

### The Problem

The application code is **fully complete**. The only missing piece is a valid `SLACK_BOT_TOKEN` (format: `xoxb-...`) in the `.env` file.

When attempting to create a Slack app at `api.slack.com/apps` and selecting the **IBM Consulting Americas** workspace, Slack shows:

> *"You don't have permission to install apps in IBM Consulting Americas. You can still create your app and request to install when you're ready."*

This means the workspace has an **admin-enforced app install policy**. Individual users cannot self-install Slack apps — an administrator must approve the installation, or an alternative authentication method must be used.

---

## 5. Options to Resolve the Blocker

### Option A — Use a Slack User Token instead of a Bot Token *(fastest)*

A **user OAuth token** (`xoxp-...`) authenticates as you personally and does not require app installation approval. The required scopes are the same: `channels:history` and `channels:read`. This is faster but uses your personal credentials rather than a service account.

**Steps:**
1. Go to `api.slack.com/apps` and create a new app (From scratch)
2. Go to **OAuth & Permissions** in the left sidebar
3. Under **User Token Scopes** (not Bot Token Scopes) add:
   - `channels:history`
   - `channels:read`
4. Click **Install to Workspace** — this uses your own user authorization and typically bypasses the admin approval requirement for user tokens
5. Copy the `xoxp-...` token into `.env` as `SLACK_BOT_TOKEN`

> Note: IBM's CIO Chatops Field Guide prefers bot tokens for production integrations, but user tokens are acceptable for personal/local tooling.

---

### Option B — Request Admin Approval via IBM CIO Chatops Process

IBM has a formal process for getting Slack apps approved in managed workspaces. The [CIO Chatops Field Guide](https://pages.github.ibm.com/CIO-Chatops/cio-chatops-field-guide/) describes the app approval and registration process. You create the app, submit it for admin review, and once approved the bot token becomes usable.

**Timeline:** Can take days to weeks depending on the approval queue. Best path if this tool is intended to be persistent or shared with others.

---

### Option C — Test on a Personal Workspace First

If you have access to a personal or free Slack workspace (e.g. a personal `yourname.slack.com`), you can install the bot there with no restrictions, validate the full pipeline end-to-end, and then migrate to the IBM workspace token once approval comes through.

---

## 6. What Happens Once You Have a Token

1. Paste the token into `.env`:
   ```
   SLACK_BOT_TOKEN=xoxb-...   (or xoxp-... for a user token)
   ```
2. Set your channel ID in `config.yaml` under `slack.channel_id` (format: `C0123ABCDEF` — found in the channel URL in your browser)
3. If using a bot token, invite the bot to the channel in Slack: `/invite @slack-tracker`
4. Start the backend:
   ```bash
   source .venv/bin/activate
   uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
   ```
5. Start the frontend:
   ```bash
   cd frontend && npm run dev
   ```
6. Open `http://localhost:3000` and click **Trigger Poll** to fetch the first batch of messages

---

## 7. Security Notes (IBM Policy)

| Constraint | Implementation |
|---|---|
| Secrets never in code or config | `SLACK_BOT_TOKEN` and `LLM_API_KEY` are in `.env` only; `.env` is in `.gitignore` |
| Backend binds to localhost only | Uvicorn launched with `--host 127.0.0.1`; never `0.0.0.0` |
| CORS restricted | Only `http://localhost:3000` is whitelisted; no wildcard |
| No sensitive data in logs | Token values are never logged; only generic error messages returned to clients |
