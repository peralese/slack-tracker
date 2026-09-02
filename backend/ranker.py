"""
ranker.py — Two-phase relevance ranking pipeline.

Phase 1: Keyword pre-filter (fast, no LLM call).
Phase 2: LLM relevance scoring (only for messages that pass Phase 1).
"""

from __future__ import annotations

import logging

from backend.llm_client import score_relevance

logger = logging.getLogger(__name__)


def keyword_score(text: str, keywords: list[str]) -> int:
    """Return the number of keywords found in text (case-insensitive)."""
    if not text:
        return 0
    lower = text.lower()
    return sum(1 for kw in keywords if kw.lower() in lower)


def rank(ingested: dict, cfg: dict) -> dict:
    """Score an ingested message dict and return ranking fields.

    Returns a dict with:
        keyword_score       — int: number of keyword hits
        relevance_score     — float 0.0–10.0
        relevance_explanation — str: one-sentence LLM explanation
    """
    ranking_cfg = cfg.get("ranking", {})
    keywords: list[str] = ranking_cfg.get("keywords", [])
    min_keyword_score: int = int(ranking_cfg.get("min_keyword_score", 1))

    from backend.ingestion import clean_slack_text
    raw = ingested.get("raw_text") or ""
    text = clean_slack_text(raw)
    kw_hits = keyword_score(text, keywords)

    if kw_hits < min_keyword_score:
        logger.debug(
            "Message ts=%s below keyword threshold (%d/%d) — skipping LLM.",
            ingested.get("slack_message_ts"),
            kw_hits,
            min_keyword_score,
        )
        return {
            "keyword_score": kw_hits,
            "relevance_score": 0.0,
            "relevance_explanation": "Below keyword threshold — not sent to LLM.",
        }

    logger.debug(
        "Message ts=%s passed keyword filter (%d hits) — calling LLM.",
        ingested.get("slack_message_ts"),
        kw_hits,
    )
    score, explanation = score_relevance(text, cfg)  # text is already clean
    return {
        "keyword_score": kw_hits,
        "relevance_score": score,
        "relevance_explanation": explanation,
    }
