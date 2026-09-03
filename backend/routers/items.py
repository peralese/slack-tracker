"""
routers/items.py — REST API routes for the dashboard.

Endpoints:
    GET  /items                     — list items with optional filters
    PATCH /items/{id}/status        — update item status
    PATCH /items/{id}/notes         — update item notes
    POST /items/{id}/rescore        — re-run LLM scoring on a stored item
    POST /poll/trigger              — manually trigger a poll cycle
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from backend.database import (
    get_item_by_id,
    get_items,
    rescore_item,
    update_item_notes,
    update_item_status,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class StatusUpdate(BaseModel):
    status: str


class NotesUpdate(BaseModel):
    notes: str


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/items")
def list_items(
    status: Optional[str] = None,
    min_score: Optional[float] = None,
    sort_by: str = "score",
):
    """Return all stored items, with optional filtering and sorting.

    Query params:
        status    — filter by status: new | reviewed | follow_up | dismissed
        min_score — filter to items with relevance_score >= this value
        sort_by   — sort field: score (default) | date
    """
    return get_items(status=status, min_score=min_score, sort_by=sort_by)


@router.patch("/items/{item_id}/status")
def set_status(item_id: int, body: StatusUpdate):
    """Update the status of an item."""
    try:
        updated = update_item_status(item_id, body.status)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    if updated is None:
        raise HTTPException(status_code=404, detail="Item not found.")
    return updated


@router.patch("/items/{item_id}/notes")
def set_notes(item_id: int, body: NotesUpdate):
    """Update the user notes on an item."""
    updated = update_item_notes(item_id, body.notes)
    if updated is None:
        raise HTTPException(status_code=404, detail="Item not found.")
    return updated


@router.post("/items/{item_id}/rescore")
def rescore(item_id: int, background_tasks: BackgroundTasks):
    """Re-run LLM relevance scoring on a stored item (runs in background)."""
    item = get_item_by_id(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found.")
    background_tasks.add_task(_safe_rescore, item_id, item["raw_text"])
    return {"message": "Re-scoring started."}


def _safe_rescore(item_id: int, raw_text: str) -> None:
    """Re-score a single item, catching all exceptions."""
    import yaml
    from backend.ranker import keyword_score
    from backend.llm_client import score_relevance
    from backend.ingestion import clean_slack_text
    try:
        with open("config.yaml") as f:
            cfg = yaml.safe_load(f)
        text = clean_slack_text(raw_text)
        keywords = cfg.get("ranking", {}).get("keywords", [])
        kw_hits = keyword_score(text, keywords)
        min_kw = int(cfg.get("ranking", {}).get("min_keyword_score", 1))
        if kw_hits < min_kw:
            score, explanation = 0.0, "Below keyword threshold — not sent to LLM."
        else:
            score, explanation = score_relevance(text, cfg)
        rescore_item(item_id, score, explanation, kw_hits)
        logger.info("Re-scored item id=%d → score=%.1f", item_id, score)
    except Exception as exc:
        logger.error("Re-score failed for item id=%d: %s", item_id, exc)


@router.post("/poll/trigger")
def trigger_poll(background_tasks: BackgroundTasks):
    """Manually trigger one poll cycle (runs in the background)."""
    from backend.slack_poller import run_poll
    background_tasks.add_task(_safe_poll)
    return {"message": "Poll triggered."}


def _safe_poll() -> None:
    """Run a poll cycle, catching all exceptions so background task never crashes the server."""
    from backend.slack_poller import run_poll
    try:
        run_poll()
    except Exception as exc:
        logger.error("Background poll failed: %s", exc)
