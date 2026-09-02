# Slack Tracker

A local application that monitors a Slack channel, ranks messages by relevance to your professional profile using a two-phase pipeline (keyword pre-filter → LLM scoring), and presents a web dashboard where you can review, annotate, and flag items for follow-up.

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Slack App Setup](#slack-app-setup)
3. [How to Find Your Channel ID](#how-to-find-your-channel-id)
4. [Installation](#installation)
5. [Configuration](#configuration)
6. [Running the Application](#running-the-application)
7. [LLM Provider Configuration](#llm-provider-configuration)
8. [Dashboard Overview](#dashboard-overview)
9. [Project Structure](#project-structure)

---

## Prerequisites

| Requirement | Minimum Version | Notes |
|---|---|---|
| Python | 3.11+ | `python3 --version` |
| Node.js | 18+ | `node --version` |
| npm | 9+ | `npm --version` |
| Slack workspace | — | Bot creation rights required |
| LLM provider | — | OpenAI, IBM watsonx.ai, or local Ollama |

---

## Slack App Setup

You need a Slack **bot token** (`xoxb-…`) with the right scopes. Follow these steps:

1. Go to [https://api.slack.com/apps](https://api.slack.com/apps) and click **Create New App → From scratch**.
2. Give it a name (e.g. `slack-tracker`) and select your workspace.
3. In the left sidebar go to **OAuth & Permissions**.
4. Under **Bot Token Scopes** add:
   - `channels:history` — read messages from public channels
   - `channels:read` — list channels (needed to resolve channel names)
5. Click **Install to Workspace** at the top of the OAuth & Permissions page and approve.
6. Copy the **Bot OAuth Token** (starts with `xoxb-`) — you will put this in `.env`.
7. Invite the bot to your target channel in Slack: open the channel → **Add apps** → search for your bot name.

> **IBM CIO Chatops Field Guide:** IBM recommends using bot tokens (not user tokens) for workspace integrations. See the [CIO Chatops Field Guide](https://pages.github.ibm.com/CIO-Chatops/cio-chatops-field-guide/) for IBM-specific guidance on Slack app creation and approval processes.

---

## How to Find Your Channel ID

The channel ID is the alphanumeric string (e.g. `C0123ABCDEF`) that uniquely identifies a Slack channel.

**Method 1 — Slack desktop app:**
1. Right-click the channel name in the sidebar.
2. Select **View channel details**.
3. Scroll to the bottom — the channel ID is shown there. Copy it.

**Method 2 — Browser:**
1. Open Slack in your browser.
2. Navigate to the channel.
3. The URL will look like: `https://app.slack.com/client/T.../C0123ABCDEF`
4. The last path segment starting with `C` is your channel ID.

---

## Installation

### 1. Clone / download the project

```bash
cd /home/peralese/Development
# already present at slack-tracker/
```

### 2. Set up the Python virtual environment

```bash
cd slack-tracker
python3 -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Configure secrets

```bash
cp .env.example .env
```

Open `.env` and fill in your values:

```dotenv
SLACK_BOT_TOKEN=xoxb-your-real-token-here
LLM_API_KEY=sk-...              # leave empty for Ollama
```

> **Never commit `.env` to version control.** It is already listed in `.gitignore`.

### 4. Install frontend dependencies

```bash
cd frontend
npm install
cd ..
```

---

## Configuration

All non-secret settings live in [`config.yaml`](config.yaml). Open it and at minimum set:

```yaml
slack:
  channel_id: "C0123ABCDEF"    # ← replace with your real channel ID
```

### Full configuration reference

| Key | Default | Purpose |
|---|---|---|
| `slack.channel_id` | *(required)* | Slack channel to monitor |
| `slack.poll_interval_minutes` | `15` | How often to poll for new messages |
| `slack.lookback_days` | `7` | How far back to scan on the very first run |
| `llm.provider` | `ollama` | LLM provider: `openai` \| `watsonx` \| `ollama` |
| `llm.model` | `llama3.2` | Model name string (provider-specific) |
| `llm.base_url` | `http://localhost:11434` | Custom endpoint URL (optional for OpenAI) |
| `ranking.user_profile` | *(IBM consultant profile)* | Embedded in the LLM system prompt |
| `ranking.keywords` | *(AI/cloud list)* | Pre-filter keyword list |
| `ranking.min_keyword_score` | `1` | Min keyword hits before LLM scoring |
| `database.path` | `./slack-tracker.db` | SQLite file location |

---

## Running the Application

Open **two terminals** from the project root.

### Terminal 1 — Backend

```bash
cd /home/peralese/Development/slack-tracker
source .venv/bin/activate
uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

The API will be available at `http://127.0.0.1:8000`.  
Interactive API docs: `http://127.0.0.1:8000/docs`

> **Security note:** The `--host 127.0.0.1` flag is required. Never use `0.0.0.0` — the backend is local-only per IBM security policy.

### Terminal 2 — Frontend

```bash
cd /home/peralese/Development/slack-tracker/frontend
npm run dev
```

Open your browser at **[http://localhost:3000](http://localhost:3000)**.

### First run behaviour

On the very first run the scheduler will poll Slack and fetch messages from the past `slack.lookback_days` days (default: 7). This is intentional — relevant content may not have been posted today. On all subsequent runs only messages newer than the last stored timestamp are fetched.

You can also click the **Trigger Poll** button in the dashboard at any time to force an immediate fetch.

---

## LLM Provider Configuration

### Ollama (local, no API key)

Ideal for fully offline use. Install [Ollama](https://ollama.com), pull a model, then configure:

```bash
ollama pull llama3.2
```

```yaml
# config.yaml
llm:
  provider: "ollama"
  model: "llama3.2"
  base_url: "http://localhost:11434"
```

Leave `LLM_API_KEY` empty in `.env`.

---

### OpenAI

```yaml
# config.yaml
llm:
  provider: "openai"
  model: "gpt-4o-mini"
  base_url: ""          # leave empty to use https://api.openai.com/v1
```

```dotenv
# .env
LLM_API_KEY=sk-...your-openai-key...
```

Any OpenAI-compatible endpoint (e.g. Azure OpenAI, local vLLM) can be used by setting `base_url` to the appropriate endpoint.

---

### IBM watsonx.ai

```yaml
# config.yaml
llm:
  provider: "watsonx"
  model: "ibm/granite-3-3-8b-instruct"
  base_url: "https://us-south.ml.cloud.ibm.com"
```

```dotenv
# .env
LLM_API_KEY=your-ibm-cloud-iam-api-key
```

You also need to set your watsonx project ID in `.env`:

```dotenv
WATSONX_PROJECT_ID=your-project-id-here
```

Your IBM Cloud IAM API key is exchanged automatically for a bearer token on each scoring call.

---

## Dashboard Overview

| Element | Description |
|---|---|
| **Score badge** | Green ≥ 7.0 · Yellow 4–6.9 · Red < 4.0 |
| **Relevance explanation** | One-sentence LLM reason why the message is relevant |
| **Links** | All URLs extracted from the message, clickable |
| **Attachments** | Filenames of any Slack file attachments |
| **Status dropdown** | `New` → `Reviewed` / `Follow Up` / `Dismissed` |
| **Notes** | Free-text annotation; saved per item |
| **Filter bar** | Filter by status, minimum score; sort by score or date |
| **Trigger Poll** | Forces an immediate Slack poll without waiting for the scheduled interval |

---

## Project Structure

```
slack-tracker/
├── .env                      # Secrets (not committed)
├── .env.example              # Secrets template
├── .gitignore
├── config.yaml               # All non-secret configuration
├── requirements.txt
├── README.md
├── backend/
│   ├── main.py               # FastAPI app + APScheduler startup
│   ├── database.py           # SQLAlchemy models + CRUD helpers
│   ├── slack_poller.py       # Slack Web API polling logic
│   ├── ingestion.py          # Content extraction (text, URLs, attachments)
│   ├── ranker.py             # Keyword pre-filter + LLM scoring pipeline
│   ├── llm_client.py         # Configurable LLM provider abstraction
│   └── routers/
│       └── items.py          # REST API routes
└── frontend/
    ├── package.json
    └── src/
        ├── App.jsx            # Top-level layout + Trigger Poll button
        ├── App.css            # All styles
        ├── api.js             # Axios wrappers for all API calls
        └── components/
            ├── ItemList.jsx   # Fetches + renders item list with filters
            ├── ItemCard.jsx   # Single item display + status/notes editing
            └── FilterBar.jsx  # Status, score, and sort filters
```
