"""
main.py — FastAPI application entrypoint.

Wires together:
    - FastAPI app with CORS restricted to localhost:3000
    - APScheduler for periodic Slack polling
    - Database table creation on startup
    - Items router
"""

from __future__ import annotations

import logging
import os

import yaml
from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.database import create_tables
from backend.routers.items import router as items_router

# Load .env before anything reads os.environ
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def _load_config() -> dict:
    try:
        with open("config.yaml", "r") as f:
            return yaml.safe_load(f)
    except Exception as exc:
        logger.warning("Could not load config.yaml: %s — using defaults.", exc)
        return {}


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(title="Slack Tracker", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3001", "http://127.0.0.1:3001"],  # restricted — no wildcard
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["Content-Type"],
)

app.include_router(items_router)


# ---------------------------------------------------------------------------
# Startup / shutdown
# ---------------------------------------------------------------------------

scheduler = BackgroundScheduler()


@app.on_event("startup")
def on_startup() -> None:
    create_tables()

    cfg = _load_config()
    interval_minutes: int = int(cfg.get("slack", {}).get("poll_interval_minutes", 15))

    from backend.slack_poller import run_poll

    scheduler.add_job(
        run_poll,
        trigger="interval",
        minutes=interval_minutes,
        id="slack_poll",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("Scheduler started — polling every %d minute(s).", interval_minutes)


@app.on_event("shutdown")
def on_shutdown() -> None:
    scheduler.shutdown(wait=False)
    logger.info("Scheduler stopped.")
