"""Scrape routes — trigger and manage scrape jobs."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger("aura.api.scrape")

router = APIRouter(tags=["scrape"])


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class ScrapeRequest(BaseModel):
    """Request body for triggering a scrape job."""
    config_name: str = Field(..., description="Site config name (e.g. 'example_site')")
    url: Optional[str] = Field(None, description="Direct URL to scrape (overrides config)")
    max_pages: int = Field(3, description="Maximum pages to scrape")
    ai_enrich: bool = Field(True, description="Run LLM enrichment pipeline")
    index: bool = Field(True, description="Index to Elasticsearch after enrichment")


class ScrapeResponse(BaseModel):
    """Response from a scrape job."""
    status: str
    site_name: str
    items_scraped: int
    items_enriched: int
    items_indexed: int
    message: str


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/scrape", response_model=ScrapeResponse)
async def trigger_scrape(request: ScrapeRequest):
    """Trigger a scrape job with optional AI enrichment and indexing."""
    try:
        from omniscraper.models import SiteConfig
        from omniscraper.scraper import scrape as run_scrape
    except ImportError as e:
        raise HTTPException(status_code=500, detail=f"Scraper not available: {e}")

    # Find config
    configs_dir = Path(__file__).resolve().parent.parent.parent / "scraper" / "configs"
    config_path = configs_dir / f"{request.config_name}.yaml"
    if not config_path.exists():
        config_path = configs_dir / f"{request.config_name}.yml"
    if not config_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Config '{request.config_name}' not found in {configs_dir}",
        )

    try:
        site_config = SiteConfig.from_yaml(config_path)
        site_config.pagination.max_pages = request.max_pages

        # Run scrape
        result = run_scrape(site_config, url=request.url)
        items_enriched = 0
        items_indexed = 0

        # Enrichment pipeline
        if request.ai_enrich and result.count > 0:
            from omniscraper.processor import process_results

            enriched = process_results(
                result,
                ai_enrich=True,
                index=request.index,
            )
            items_enriched = len(enriched)
            if request.index:
                items_indexed = items_enriched

        return ScrapeResponse(
            status="completed",
            site_name=site_config.name,
            items_scraped=result.count,
            items_enriched=items_enriched,
            items_indexed=items_indexed,
            message=f"Successfully scraped {result.count} items from {site_config.name}",
        )

    except Exception as e:
        logger.error("Scrape failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/configs")
async def list_configs():
    """List available site configurations."""
    configs_dir = Path(__file__).resolve().parent.parent.parent / "scraper" / "configs"
    if not configs_dir.exists():
        return {"configs": []}

    configs = []
    for f in sorted(configs_dir.glob("*.yaml")):
        if f.stem.startswith("_"):
            continue
        try:
            from omniscraper.models import SiteConfig
            cfg = SiteConfig.from_yaml(f)
            configs.append({
                "name": cfg.name,
                "file": f.name,
                "base_url": cfg.base_url,
                "fetcher": cfg.fetcher,
            })
        except Exception:
            configs.append({"name": f.stem, "file": f.name, "error": "invalid config"})

    return {"configs": configs}
