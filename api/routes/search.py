"""Search routes — hybrid search over enriched market data."""

from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger("aura.api.search")

router = APIRouter(tags=["search"])


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class SearchRequest(BaseModel):
    """Request body for hybrid search."""
    query: str = Field(..., description="Search query text")
    k: int = Field(10, description="Number of results to return")
    sentiment: Optional[str] = Field(None, description="Filter by sentiment")
    entity: Optional[str] = Field(None, description="Filter by entity")
    date_from: Optional[str] = Field(None, description="Filter: min date (ISO)")
    date_to: Optional[str] = Field(None, description="Filter: max date (ISO)")


class SearchResult(BaseModel):
    """A single search result."""
    score: float
    title: Optional[str] = None
    summary: Optional[str] = None
    sentiment: Optional[str] = None
    entities: list[str] = []
    source_url: Optional[str] = None
    scraped_at: Optional[str] = None
    raw_data: dict[str, Any] = {}


class SearchResponse(BaseModel):
    """Response from hybrid search."""
    query: str
    total: int
    results: list[SearchResult]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/search", response_model=SearchResponse)
async def search(request: SearchRequest):
    """Perform hybrid search (kNN + BM25) over enriched market data."""
    try:
        from omniscraper.database import hybrid_search
    except ImportError as e:
        raise HTTPException(status_code=500, detail=f"Search backend not available: {e}")

    try:
        results = hybrid_search(
            query=request.query,
            k=request.k,
            sentiment_filter=request.sentiment,
            entity_filter=request.entity,
            date_from=request.date_from,
            date_to=request.date_to,
        )

        search_results = []
        for doc in results:
            search_results.append(
                SearchResult(
                    score=doc.get("_score", 0.0),
                    title=doc.get("title"),
                    summary=doc.get("summary"),
                    sentiment=doc.get("sentiment"),
                    entities=doc.get("entities", []),
                    source_url=doc.get("source_url"),
                    scraped_at=doc.get("scraped_at"),
                    raw_data={
                        k: v for k, v in doc.items()
                        if k not in ("_score", "_id", "embedding", "title", "summary",
                                     "sentiment", "entities", "source_url", "scraped_at")
                    },
                )
            )

        return SearchResponse(
            query=request.query,
            total=len(search_results),
            results=search_results,
        )

    except Exception as e:
        logger.error("Search failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/index-stats")
async def index_stats():
    """Get Elasticsearch index statistics."""
    try:
        from omniscraper.database import get_index_stats
        return get_index_stats()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
