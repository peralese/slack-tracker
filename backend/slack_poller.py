"""
slack_poller.py — Poll a Slack channel for new messages and feed them into
                  the ingestion + ranking pipeline.

Polling strategy:
  - First run (no prior ts in DB): fetch messages from now minus lookback_days.
  - Subsequent runs: fetch only messages newer than the last stored ts.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
import yaml
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from backend.database import get_latest_message_ts, upsert_item
from backend.document_extractor import extract_text
from backend.ingestion import extract

logger = logging.getLogger(__name__)


def _load_config() -> dict:
    with open("config.yaml", "r") as f:
        return yaml.safe_load(f)


def run_poll() -> None:
    """Execute one full poll cycle: fetch new Slack messages, rank, and store."""
    cfg = _load_config()
    slack_cfg = cfg.get("slack", {})

    token = os.environ.get("SLACK_BOT_TOKEN", "")
    if not token:
        logger.error("SLACK_BOT_TOKEN is not set — skipping poll.")
        return

    channel_id: str = slack_cfg.get("channel_id", "")
    if not channel_id or channel_id == "REPLACE_WITH_YOUR_CHANNEL_ID":
        logger.error("slack.channel_id is not configured in config.yaml — skipping poll.")
        return

    lookback_days: int = int(slack_cfg.get("lookback_days", 7))

    # Determine the oldest timestamp to fetch from
    last_ts = get_latest_message_ts()
    if last_ts:
        oldest = last_ts  # incremental: only fetch newer messages
        logger.info("Incremental poll: fetching messages newer than ts=%s", last_ts)
    else:
        cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
        oldest = str(cutoff.timestamp())
        logger.info("First run: fetching messages from the last %d days.", lookback_days)

    client = WebClient(token=token)
    messages = _fetch_all_messages(client, channel_id, oldest)

    if not messages:
        logger.info("No new messages found.")
        return

    logger.info("Fetched %d new message(s) from channel %s.", len(messages), channel_id)

    # Import here to avoid a circular dependency at module load time
    from backend.ranker import rank

    for msg in messages:
        # Only process actual user/bot messages (skip join/leave subtypes)
        subtype = msg.get("subtype")
        if subtype and subtype not in ("bot_message",):
            continue

        ingested = extract(msg, channel_id)

        # Attempt document summarization if the message has file attachments
        doc_summary: str | None = None
        if msg.get("files"):
            doc_summary = _download_and_summarize(msg["files"], token, cfg)
        ingested["doc_summary"] = doc_summary

        ranked = rank(ingested, cfg)

        upsert_item({**ingested, **ranked})


def _download_and_summarize(files: list, token: str, cfg: dict) -> str | None:
    """Download the first supported file attachment and return an LLM summary.

    Returns None if no supported files are present or all downloads fail.
    Returns the fallback string if extraction/summarization fails.
    """
    from backend.llm_client import summarize_document

    for f in files:
        filename = f.get("name") or f.get("title") or ""
        url = f.get("url_private_download") or f.get("url_private")
        if not url or not filename:
            continue

        # Check extension before downloading to avoid fetching unsupported files
        import os as _os
        ext = _os.path.splitext(filename.lower())[1]
        if ext not in {".docx", ".pptx", ".pdf"}:
            continue

        try:
            with httpx.Client(timeout=60) as client:
                resp = client.get(
                    url,
                    headers={"Authorization": f"Bearer {token}"},
                    follow_redirects=True,
                )
                resp.raise_for_status()
            file_bytes = resp.content
        except Exception as exc:
            logger.error("Failed to download file %s: %s", filename, exc)
            return "Summary unavailable — document attached but could not be processed."

        text = extract_text(file_bytes, filename)
        if not text or not text.strip():
            return "Summary unavailable — document attached but could not be processed."

        logger.info("Summarizing document: %s (%d chars extracted)", filename, len(text))
        return summarize_document(text, cfg)

    return None  # no supported files found


def _fetch_all_messages(
    client: WebClient,
    channel_id: str,
    oldest: str,
) -> list[dict[str, Any]]:
    """Fetch all messages newer than `oldest`, handling Slack pagination."""
    messages: list[dict] = []
    cursor: str | None = None

    while True:
        kwargs: dict[str, Any] = {
            "channel": channel_id,
            "oldest": oldest,
            "limit": 200,
        }
        if cursor:
            kwargs["cursor"] = cursor

        try:
            response = client.conversations_history(**kwargs)
        except SlackApiError as exc:
            logger.error(
                "Slack API error during conversations.history: %s",
                exc.response.get("error", str(exc)),
            )
            break

        batch = response.get("messages", [])
        messages.extend(batch)

        if response.get("has_more") and response.get("response_metadata", {}).get("next_cursor"):
            cursor = response["response_metadata"]["next_cursor"]
        else:
            break

    # conversations.history returns newest-first; reverse so we process oldest first
    messages.reverse()
    return messages
