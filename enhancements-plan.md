# Slack Tracker — Enhancements Plan

## How to Use This Plan

Work through sub-tasks **one at a time**, in order. After completing each sub-task, update its `Status` from `[ ] pending` to `[x] done`. Read this file at the start of each sub-task for full context.

> **Before starting:** Delete the existing `slack-tracker.db` file so the database is recreated cleanly with the new schema.
> `rm slack-tracker.db`

---

## Overview

Two gaps are being addressed:

**Use Case 1 — Date / Deadline Extraction**
Messages about training opportunities or events often contain dates buried in the text (e.g. "Register by Sept 15", "Session on Oct 3 2026"). These dates are currently invisible to the user. The fix: parse dates out of `raw_text` during ingestion and surface them as a dedicated "Dates" section on the item card.

**Use Case 2 — Document Summarization**
When a manager posts a Word doc, PowerPoint, or PDF, the app currently only stores the filename. The fix: during the poll, download the file via the Slack API, extract its text content, send it to the LLM for a summary, and store the summary alongside the item so it's ready when the card loads.

**Approach:**
- Two new database columns: `event_dates` (JSON list of date strings) and `doc_summary` (text)
- Date extraction added to `ingestion.py` using `dateparser`
- Document download + text extraction added to `slack_poller.py`
- LLM summarization function added to `llm_client.py`
- `ItemCard.jsx` updated to show both new sections
- All changes are additive — no existing behaviour is broken

---

## Design Decisions (confirmed)

| Decision | Choice |
|---|---|
| Date display | Separate section below message text — no HTML injection into raw text |
| Failed summarization | Store `"Summary unavailable — document attached but could not be processed."` in `doc_summary` |
| File size cap | Truncate extracted document text to first 3,000 words before sending to LLM |
| File types | `.docx` (python-docx), `.pptx` (python-pptx), `.pdf` (pypdf) |
| Summarization trigger | Automatic during poll — not manual |

---

## Project Structure (relevant files)

```
slack-tracker/
├── requirements.txt                  ← Sub-Task 1: add new dependencies
├── backend/
│   ├── database.py                   ← Sub-Task 2: new columns + CRUD updates
│   ├── ingestion.py                  ← Sub-Task 3: date extraction
│   ├── llm_client.py                 ← Sub-Task 4: summarize_document()
│   ├── slack_poller.py               ← Sub-Task 5: file download + summarization wiring
│   └── routers/items.py              ← no changes needed
└── frontend/src/
    ├── components/ItemCard.jsx        ← Sub-Task 6: Dates + Summary sections
    └── App.css                        ← Sub-Task 6: new styles
```

---

## Sub-Tasks

---

### Sub-Task 1 — Add New Python Dependencies

**Intent:**
Add the four Python packages required by the new features. No code changes — just dependency declarations.

**Expected Outcomes:**
- `requirements.txt` includes `python-docx`, `python-pptx`, `pypdf`, and `dateparser`
- All packages are the latest stable versions

**Todo List:**
1. Add to `requirements.txt`:
   - `python-docx` — extract text from `.docx` files
   - `python-pptx` — extract text from `.pptx` files
   - `pypdf` — extract text from `.pdf` files
   - `dateparser` — parse natural-language date strings from message text

**Relevant Context:**
- Current `requirements.txt` has: `fastapi`, `uvicorn`, `slack-sdk`, `sqlalchemy`, `pydantic`, `pydantic-settings`, `httpx`, `python-dotenv`, `pyyaml`, `apscheduler`
- Use latest stable versions for all four packages

**Status:** `[x] done`

---

### Sub-Task 2 — Database: Add New Columns

**Intent:**
Add two new columns to the `Item` model to hold extracted dates and document summaries. The migration must be safe — existing rows get `NULL` for both columns, which is handled gracefully by the frontend.

**Expected Outcomes:**
- `Item` model has `event_dates` (Text, JSON-encoded list of date strings, nullable)
- `Item` model has `doc_summary` (Text, nullable)
- `to_dict()` includes both new fields: `event_dates` as a list, `doc_summary` as a string or `None`
- `upsert_item()` accepts and stores both new fields from the input dict
- `create_tables()` uses `Base.metadata.create_all()` which creates the full schema fresh — no migration needed since the DB is deleted before implementation

**Todo List:**
1. Add `event_dates = Column(Text, nullable=True)` to the `Item` model — stores a JSON-encoded list of date strings
2. Add `doc_summary = Column(Text, nullable=True)` to the `Item` model — stores LLM-generated document summary text
3. Update `to_dict()` to include:
   - `"event_dates": json.loads(self.event_dates) if self.event_dates else []`
   - `"doc_summary": self.doc_summary`
4. Update `upsert_item()` to write both fields from the input dict (default to `None` if not present)

**Relevant Context:**
- `backend/database.py` — `Item` model starts at line 72, `to_dict()` at line 104, `upsert_item()` at line 137, `create_tables()` at line 127
- Other JSON-encoded list fields for reference: `extracted_urls` (line 92), `attachment_names` (line 93)

**Status:** `[ ] pending`

---

### Sub-Task 3 — Date Extraction in Ingestion

**Intent:**
Parse natural-language date references out of the raw message text during ingestion and return them as a list of ISO date strings. This runs on every message — it is fast and requires no LLM call.

**Expected Outcomes:**
- `ingestion.py` has a new `extract_dates(text: str) -> list[str]` function
- `extract()` calls `extract_dates()` and adds `event_dates` to the returned dict
- Dates are returned as human-readable strings (e.g. `"2026-09-02"`) — ISO format preferred
- Dates in the past (older than today) are excluded — only future-relevant dates are surfaced
- Duplicate dates are deduplicated

**Todo List:**
1. Add `extract_dates(text: str) -> list[str]` to `ingestion.py`:
   - Use `dateparser.search.search_dates(text, settings={"RETURN_TIME_AS_PERIOD": False, "PREFER_DATES_FROM": "future"})` to find all date-like substrings
   - `search_dates()` returns a list of `(matched_string, datetime)` tuples or `None`
   - Convert each matched datetime to an ISO date string (`datetime.date().isoformat()`)
   - Deduplicate and return the list
   - Wrap in try/except — if dateparser fails for any reason, return `[]`
2. Call `extract_dates(raw_text)` inside `extract()` and add `"event_dates": <result>` to the returned dict

**Relevant Context:**
- `backend/ingestion.py` — `extract()` returns a dict at line 74; add `event_dates` to that dict
- `dateparser.search.search_dates` is the right function — it finds multiple dates in free text, unlike `dateparser.parse` which expects a single date string
- The `PREFER_DATES_FROM: future` setting helps with ambiguous dates like "Sept 2" resolving to the next occurrence

**Status:** `[ ] pending`

---

### Sub-Task 4 — LLM: Document Summarization Function

**Intent:**
Add a `summarize_document(text: str, cfg: dict) -> str` function to `llm_client.py` that sends extracted document text to the configured LLM provider and returns a concise summary paragraph. It follows the exact same provider-switching pattern as the existing `score_relevance()` function.

**Expected Outcomes:**
- `llm_client.py` exports `summarize_document(text: str, cfg: dict) -> str`
- Supports all three providers: `openai`, `watsonx`, `ollama`
- Input text is truncated to the first 3,000 words before sending to the LLM
- Returns a plain-text summary string (not JSON)
- On any error (API failure, timeout, parse error), returns `"Summary unavailable — document attached but could not be processed."`

**Todo List:**
1. Add a `_truncate_to_words(text: str, max_words: int = 3000) -> str` helper at the top of `llm_client.py`
2. Add `summarize_document(text: str, cfg: dict) -> str`:
   - Truncate input to 3,000 words using the helper
   - System prompt: instruct the LLM to act as a professional summarizer and produce a concise 3–5 sentence summary suitable for a busy IBM consultant
   - User prompt: `"Please summarize the following document:\n\n{truncated_text}"`
   - Use the same provider dispatch pattern as `score_relevance()` — read `cfg["llm"]["provider"]` and call the appropriate provider function
   - Each provider function returns the raw summary string (not parsed as JSON)
   - Wrap entire function in try/except — return the fallback string on any exception

**Relevant Context:**
- `backend/llm_client.py` — `score_relevance()` is the pattern to follow; read it fully before implementing
- The system prompt for `score_relevance()` uses the `ranking.user_profile` from config — do the same for `summarize_document()` to keep summaries relevant to the user's role
- Provider implementations use `httpx.Client()` with a timeout — use the same timeout pattern
- `LLM_API_KEY` and `WATSONX_PROJECT_ID` are read from `os.environ` — no change needed there

**Status:** `[ ] pending`

---

### Sub-Task 5 — Slack Poller: File Download and Summarization

**Intent:**
Extend the poll cycle so that when a message has file attachments, the files are downloaded from Slack, their text is extracted based on file type, and the result is summarized using the new `summarize_document()` function. The summary is added to the item dict before `upsert_item()` is called.

**Expected Outcomes:**
- For messages with `.docx`, `.pptx`, or `.pdf` attachments, `doc_summary` is populated in the stored item
- For messages with unsupported file types (e.g. `.png`, `.zip`), `doc_summary` is left `None`
- For messages with no attachments, behaviour is unchanged
- File download uses the Slack SDK's authenticated `files.getUploadURLExternal` or the file's `url_private_download` with a bearer token header — the file is never written to disk; content is processed in memory
- A new `backend/document_extractor.py` module handles the file type dispatch and text extraction

**Todo List:**
1. Create `backend/document_extractor.py` with a single public function:
   - `extract_text(file_bytes: bytes, filename: str) -> str | None`
   - Dispatches on file extension: `.docx` → python-docx, `.pptx` → python-pptx, `.pdf` → pypdf
   - For `.docx`: use `docx.Document(io.BytesIO(file_bytes))` and join all paragraph texts
   - For `.pptx`: use `pptx.Presentation(io.BytesIO(file_bytes))` and extract text from all slide shapes
   - For `.pdf`: use `pypdf.PdfReader(io.BytesIO(file_bytes))` and extract text from all pages
   - Returns `None` for unsupported extensions
   - Wraps each extractor in try/except — returns `None` on failure
2. In `backend/slack_poller.py`, add a `_download_and_summarize(files: list, token: str, cfg: dict) -> str | None` helper:
   - Iterates over the files list from the Slack message payload
   - For each file, checks the extension (from `f.get("name")` or `f.get("title")`)
   - Downloads the file using `httpx.get(url_private_download, headers={"Authorization": f"Bearer {token}"})` — in memory, no disk writes
   - Calls `document_extractor.extract_text(response.content, filename)`
   - If text is extracted, calls `summarize_document(text, cfg)` and returns the result
   - If multiple files are attached, summarize the first supported file only
   - Returns `None` if no supported files or all downloads fail
3. In `run_poll()`, after calling `extract(msg, channel_id)`, check if the message has files (`msg.get("files")`). If so, call `_download_and_summarize()` and add the result as `doc_summary` to the ingested dict before calling `rank()` and `upsert_item()`

**Relevant Context:**
- `backend/slack_poller.py` — `run_poll()` loop is at lines 71–80; the upsert call is at line 80
- Slack file `url_private_download` requires the bot token as a Bearer token in the Authorization header — this is the standard Slack file download pattern
- The `token` variable is already available in `run_poll()` at line 37
- `SLACK_BOT_TOKEN` must never be logged
- Files list is at `msg.get("files", [])` in the raw Slack message payload

**Status:** `[ ] pending`

---

### Sub-Task 6 — Frontend: Display Dates and Document Summary

**Intent:**
Update `ItemCard.jsx` to show two new sections when data is present: a "Dates Mentioned" section listing extracted dates, and a "Document Summary" section showing the LLM-generated summary. Add CSS for both. No existing sections are modified.

**Expected Outcomes:**
- Items with extracted dates show a "📅 Dates Mentioned" section below the message text listing each date
- Items with a doc summary show a "📄 Document Summary" section with the summary text
- Items where summarization failed show the fallback message `"Summary unavailable — document attached but could not be processed."` styled distinctly (muted/italic)
- Items with no dates and no summary look identical to today — no visual regression

**Todo List:**
1. In `ItemCard.jsx`, after the `<p className="raw-text">` block, add:
   - A "📅 Dates Mentioned" section: render only if `item.event_dates?.length > 0`; display as a simple list of date strings
   - A "📄 Document Summary" section: render only if `item.doc_summary`; display the summary text in a styled block; apply a muted style if the text matches the fallback failure message
2. In `App.css`, add styles for:
   - `.dates-section` — subtle highlighted background (light yellow/amber tint), small font, rounded
   - `.date-pill` — inline badge style for each individual date string
   - `.doc-summary` — slightly inset block with a left border accent, readable font size
   - `.doc-summary-failed` — muted gray italic style for the failure fallback message

**Relevant Context:**
- `frontend/src/components/ItemCard.jsx` — raw text rendered at line 71; attachment names section ends around line 95; new sections go after attachments, before the notes textarea
- `frontend/src/App.css` — existing badge and section styles can be used as reference for spacing and color conventions
- The fallback failure string is exactly: `"Summary unavailable — document attached but could not be processed."`
- `item.event_dates` will be an array (possibly empty); `item.doc_summary` will be a string or `null`

**Status:** `[ ] pending`

---

## Configuration Reference (no changes needed)

All new features use the existing `llm` section of `config.yaml` — no new config keys are required. The same provider, model, and base URL used for relevance scoring are also used for document summarization.
