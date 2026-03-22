"""Aura API Bridge — FastAPI server connecting the chat frontend to OmniScraper.

Exposes endpoints for:
  - Scrape job management
  - Hybrid search (kNN + BM25)
  - Health checks
"""

from __future__ import annotations

import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Add scraper package to path
SCRAPER_SRC = Path(__file__).resolve().parent.parent / "scraper" / "src"
if str(SCRAPER_SRC) not in sys.path:
    sys.path.insert(0, str(SCRAPER_SRC))

from api.routes.scrape import router as scrape_router
from api.routes.scrape_answer import router as scrape_answer_router
from api.routes.search import router as search_router

logger = logging.getLogger("aura.api")

# ---------------------------------------------------------------------------
# App lifecycle
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    """App startup/shutdown lifecycle."""
    logger.info("Aura API starting up...")
    yield
    logger.info("Aura API shutting down...")


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Aura API",
    description="AI-Enriched Market Intelligence API — bridge between the chat frontend and OmniScraper",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS for Vite dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",   # Vite dev
        "http://localhost:3000",   # Alternative
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount routers
app.include_router(scrape_router, prefix="/api")
app.include_router(scrape_answer_router, prefix="/api")
app.include_router(search_router, prefix="/api")


@app.get("/api/health")
async def health():
    """Health check endpoint."""
    health_status = {
        "status": "ok",
        "scraper": "available",
    }

    # Check Elasticsearch
    try:
        from omniscraper.database import get_index_stats
        stats = get_index_stats()
        health_status["elasticsearch"] = {
            "status": "connected",
            "doc_count": stats.get("doc_count", 0),
        }
    except Exception as e:
        health_status["elasticsearch"] = {
            "status": "unavailable",
            "error": str(e),
        }

    return health_status
