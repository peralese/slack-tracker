"""
database.py — SQLite setup, SQLAlchemy models, and CRUD helpers.
"""

from __future__ import annotations

import enum
import json
import logging
from datetime import datetime, timezone
from typing import Optional

import yaml
from sqlalchemy import (
    Column,
    DateTime,
    Enum,
    Float,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config — read DB path from config.yaml
# ---------------------------------------------------------------------------

def _db_url() -> str:
    try:
        with open("config.yaml", "r") as f:
            cfg = yaml.safe_load(f)
        path = cfg.get("database", {}).get("path", "./slack-tracker.db")
    except Exception:
        path = "./slack-tracker.db"
    return f"sqlite:///{path}"


engine = create_engine(
    _db_url(),
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


# ---------------------------------------------------------------------------
# ORM Base
# ---------------------------------------------------------------------------

class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ItemStatus(str, enum.Enum):
    new = "new"
    reviewed = "reviewed"
    follow_up = "follow_up"
    dismissed = "dismissed"


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------

class Item(Base):
    __tablename__ = "items"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Slack identifiers
    slack_message_ts = Column(String, unique=True, nullable=False, index=True)
    slack_channel_id = Column(String, nullable=False)
    slack_user_id = Column(String, nullable=True)

    # Timestamps
    posted_at = Column(DateTime(timezone=True), nullable=False)
    ingested_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # Content
    raw_text = Column(Text, nullable=True)
    extracted_urls = Column(Text, nullable=True)    # JSON-encoded list[str]
    attachment_names = Column(Text, nullable=True)  # JSON-encoded list[str]
    event_dates = Column(Text, nullable=True)       # JSON-encoded list[str]
    doc_summary = Column(Text, nullable=True)

    # Ranking
    keyword_score = Column(Integer, nullable=False, default=0)
    relevance_score = Column(Float, nullable=False, default=0.0)
    relevance_explanation = Column(Text, nullable=True)

    # User interaction
    status = Column(Enum(ItemStatus), nullable=False, default=ItemStatus.new)
    user_notes = Column(Text, nullable=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "slack_message_ts": self.slack_message_ts,
            "slack_channel_id": self.slack_channel_id,
            "slack_user_id": self.slack_user_id,
            "posted_at": self.posted_at.isoformat() if self.posted_at else None,
            "ingested_at": self.ingested_at.isoformat() if self.ingested_at else None,
            "raw_text": self.raw_text,
            "extracted_urls": json.loads(self.extracted_urls) if self.extracted_urls else [],
            "attachment_names": json.loads(self.attachment_names) if self.attachment_names else [],
            "keyword_score": self.keyword_score,
            "relevance_score": self.relevance_score,
            "relevance_explanation": self.relevance_explanation,
            "status": self.status.value if self.status else ItemStatus.new.value,
            "user_notes": self.user_notes,
            "event_dates": json.loads(self.event_dates) if self.event_dates else [],
            "doc_summary": self.doc_summary,
        }


# ---------------------------------------------------------------------------
# Table creation
# ---------------------------------------------------------------------------

def create_tables() -> None:
    """Create all tables. Safe to call on every startup (no-op if already exist)."""
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables verified/created.")


# ---------------------------------------------------------------------------
# CRUD helpers
# ---------------------------------------------------------------------------

def upsert_item(data: dict) -> Item:
    """Insert a new item or skip if slack_message_ts already exists.

    Returns the Item (existing or newly created).
    """
    with SessionLocal() as session:
        existing = (
            session.query(Item)
            .filter(Item.slack_message_ts == data["slack_message_ts"])
            .first()
        )
        if existing:
            return existing

        item = Item(
            slack_message_ts=data["slack_message_ts"],
            slack_channel_id=data["slack_channel_id"],
            slack_user_id=data.get("slack_user_id"),
            posted_at=data["posted_at"],
            raw_text=data.get("raw_text"),
            extracted_urls=json.dumps(data.get("extracted_urls", [])),
            attachment_names=json.dumps(data.get("attachment_names", [])),
            keyword_score=data.get("keyword_score", 0),
            relevance_score=data.get("relevance_score", 0.0),
            relevance_explanation=data.get("relevance_explanation"),
            event_dates=json.dumps(data["event_dates"]) if data.get("event_dates") is not None else None,
            doc_summary=data.get("doc_summary"),
            status=ItemStatus.new,
        )
        session.add(item)
        session.commit()
        session.refresh(item)
        logger.info("Stored new item ts=%s", data["slack_message_ts"])
        return item


def get_items(
    status: Optional[str] = None,
    min_score: Optional[float] = None,
    sort_by: str = "score",
) -> list[dict]:
    """Return items as dicts, optionally filtered and sorted."""
    with SessionLocal() as session:
        q = session.query(Item)
        if status:
            try:
                q = q.filter(Item.status == ItemStatus(status))
            except ValueError:
                pass  # unknown status — ignore filter
        if min_score is not None:
            q = q.filter(Item.relevance_score >= min_score)
        if sort_by == "date":
            q = q.order_by(Item.posted_at.desc())
        else:
            q = q.order_by(Item.relevance_score.desc())
        return [item.to_dict() for item in q.all()]


def update_item_status(item_id: int, status: str) -> Optional[dict]:
    """Update the status of an item. Returns the updated item dict, or None if not found."""
    with SessionLocal() as session:
        item = session.query(Item).filter(Item.id == item_id).first()
        if not item:
            return None
        try:
            item.status = ItemStatus(status)
        except ValueError:
            raise ValueError(f"Invalid status: {status!r}")
        session.commit()
        session.refresh(item)
        return item.to_dict()


def update_item_notes(item_id: int, notes: str) -> Optional[dict]:
    """Update the user notes of an item. Returns the updated item dict, or None if not found."""
    with SessionLocal() as session:
        item = session.query(Item).filter(Item.id == item_id).first()
        if not item:
            return None
        item.user_notes = notes
        session.commit()
        session.refresh(item)
        return item.to_dict()


def get_latest_message_ts() -> Optional[str]:
    """Return the highest (most recent) slack_message_ts stored, or None on first run."""
    with SessionLocal() as session:
        row = (
            session.query(Item.slack_message_ts)
            .order_by(Item.slack_message_ts.desc())
            .first()
        )
        return row[0] if row else None
