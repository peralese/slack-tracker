"""
ingestion.py — Extract structured content from a raw Slack message payload.

Produces a dict ready to be passed to the ranker and then stored in SQLite.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# Matches http(s):// URLs
_URL_RE = re.compile(r"https?://[^\s\>\]\"']+")

# Slack formatting patterns to strip before sending text to the LLM
_SLACK_URL_RE = re.compile(r"<https?://[^|>]*\|([^>]+)>")   # <url|label> → label
_SLACK_URL_BARE_RE = re.compile(r"<https?://[^>]+>")          # <url> → remove
_SLACK_BOLD_RE = re.compile(r"\*([^*]+)\*")                   # *bold* → text
_SLACK_ITALIC_RE = re.compile(r"_([^_]+)_")                   # _italic_ → text
_SLACK_STRIKE_RE = re.compile(r"~([^~]+)~")                   # ~strike~ → text
_SLACK_CODE_RE = re.compile(r"`([^`]+)`")                     # `code` → text
_SLACK_EMOJI_RE = re.compile(r":[a-z0-9_\-+]+:")              # :emoji: → remove
_SLACK_USER_RE = re.compile(r"<@[A-Z0-9]+>")                  # <@USER> → remove
_SLACK_CHANNEL_RE = re.compile(r"<#[A-Z0-9]+\|([^>]+)>")     # <#ID|name> → name
_SLACK_MULTISPACE_RE = re.compile(r" {2,}")                   # collapse extra spaces


def clean_slack_text(text: str) -> str:
    """Strip Slack formatting markup from message text for clean display and LLM input."""
    text = _SLACK_URL_RE.sub(r"\1", text)          # <url|label> → label
    text = _SLACK_URL_BARE_RE.sub("", text)        # bare <url> → remove
    text = _SLACK_CHANNEL_RE.sub(r"#\1", text)     # <#ID|name> → #name
    text = _SLACK_USER_RE.sub("", text)            # <@USER> → remove
    text = _SLACK_BOLD_RE.sub(r"\1", text)         # *bold* → text
    text = _SLACK_ITALIC_RE.sub(r"\1", text)       # _italic_ → text
    text = _SLACK_STRIKE_RE.sub(r"\1", text)       # ~strike~ → text
    text = _SLACK_CODE_RE.sub(r"\1", text)         # `code` → text
    text = _SLACK_EMOJI_RE.sub("", text)           # :emoji: → remove
    text = _SLACK_MULTISPACE_RE.sub(" ", text)     # collapse extra spaces
    return text.strip()


# Only match explicit date patterns — requires a recognisable month name or number
# with a day and optional year.  Rejects pure relative expressions ("in 15 minutes").
_DATE_RE = re.compile(
    r"""
    (?:
        # Month-name first: "Sep 2", "September 22 2026", "Sep. 22, 2026"
        (?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|
           Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)
        \.?\s+\d{1,2}(?:st|nd|rd|th)?(?:\s*,?\s*\d{4})?
    |
        # Numeric: MM/DD/YYYY or MM-DD-YYYY (4-digit year required to avoid false positives)
        \d{1,2}[\/\-]\d{1,2}[\/\-]\d{4}
    )
    """,
    re.VERBOSE | re.IGNORECASE,
)


def extract_dates(text: str) -> list[str]:
    """Parse explicit date references from free text.

    Only matches dates with a recognisable month name or full numeric date
    (MM/DD/YYYY).  Relative expressions like "in 15 minutes" are ignored.

    Returns a deduplicated list of ISO date strings (YYYY-MM-DD).
    Returns [] on any failure.
    """
    try:
        import dateparser  # lazy import — dateparser is slow to load
        from datetime import date

        today = date.today()
        matches = _DATE_RE.findall(text)
        if not matches:
            return []

        seen: set[str] = set()
        dates: list[str] = []
        for match in matches:
            dt = dateparser.parse(
                match,
                languages=["en"],
                settings={
                    "PREFER_DATES_FROM": "future",
                    "DATE_ORDER": "MDY",
                },
            )
            if dt is None:
                continue
            d = dt.date()
            # Skip dates more than 7 days in the past — keeps "today" and recent events
            from datetime import timedelta
            if d < today - timedelta(days=7):
                continue
            iso = d.isoformat()
            if iso not in seen:
                seen.add(iso)
                dates.append(iso)
        return dates
    except Exception:
        return []


def extract(message: dict[str, Any], channel_id: str) -> dict:
    """Return a structured dict from a raw Slack message payload.

    Fields returned:
        slack_message_ts, slack_channel_id, slack_user_id,
        posted_at, raw_text, extracted_urls, attachment_names, event_dates
    """
    ts = message.get("ts", "")
    user = message.get("user") or message.get("bot_id")
    slack_raw = message.get("text") or ""  # original Slack text with formatting markers

    # Convert Slack ts (Unix float string) to UTC datetime
    try:
        posted_at = datetime.fromtimestamp(float(ts), tz=timezone.utc)
    except (ValueError, TypeError):
        posted_at = datetime.now(timezone.utc)

    urls: list[str] = []
    attachment_names: list[str] = []

    # --- URLs from plain text (use original — URLs are in <url|label> format) ---
    urls.extend(_URL_RE.findall(slack_raw))

    # --- URLs and text from blocks (rich text / section) ---
    for block in message.get("blocks", []) or []:
        _extract_from_block(block, urls)

    # --- Legacy attachments ---
    for att in message.get("attachments", []) or []:
        att_text = att.get("text") or att.get("fallback") or ""
        urls.extend(_URL_RE.findall(att_text))  # noqa: use raw att text for URL extraction
        if att.get("title_link"):
            urls.append(att["title_link"])

    # --- File attachments ---
    for f in message.get("files", []) or []:
        name = f.get("name") or f.get("title")
        if name:
            attachment_names.append(name)
        # Slack sometimes includes a permalink for files
        permalink = f.get("permalink")
        if permalink:
            urls.append(permalink)

    # Deduplicate while preserving order
    seen: set[str] = set()
    unique_urls: list[str] = []
    for u in urls:
        # Strip trailing Slack pipe-label syntax: <url|label>
        u = u.rstrip(">").split("|")[0]
        if u not in seen:
            seen.add(u)
            unique_urls.append(u)

    # Clean formatting for display and date extraction
    display_text = clean_slack_text(slack_raw)
    event_dates = extract_dates(display_text)

    return {
        "slack_message_ts": ts,
        "slack_channel_id": channel_id,
        "slack_user_id": user,
        "posted_at": posted_at,
        "raw_text": display_text,   # store clean text — no Slack markup
        "extracted_urls": unique_urls,
        "attachment_names": attachment_names,
        "event_dates": event_dates,
    }


def _extract_from_block(block: dict, urls: list[str]) -> None:
    """Recursively walk a Slack block element collecting URLs."""
    block_type = block.get("type")

    if block_type == "rich_text":
        for element in block.get("elements", []) or []:
            _extract_from_block(element, urls)

    elif block_type in ("rich_text_section", "rich_text_list", "rich_text_quote"):
        for element in block.get("elements", []) or []:
            _extract_from_block(element, urls)

    elif block_type == "link":
        url = block.get("url")
        if url:
            urls.append(url)

    elif block_type == "section":
        # Section blocks may have a text object and/or accessory with a URL
        text_obj = block.get("text") or {}
        text_val = text_obj.get("text") or ""
        urls.extend(_URL_RE.findall(text_val))

    # elements array present on other composite block types
    for element in block.get("elements", []) or []:
        if isinstance(element, dict):
            _extract_from_block(element, urls)
