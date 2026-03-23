"""Scrape a configured site, then answer a natural-language question from fresh data."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger("aura.api.scrape_answer")

router = APIRouter(tags=["scrape"])


class ScrapeAndAnswerRequest(BaseModel):
    config_name: str = Field(..., description="Site YAML stem (e.g. 'example_site')")
    question: str = Field(..., description="Question to answer using scraped listings only")
    url: Optional[str] = Field(None, description="Optional URL override")
    max_pages: int = Field(3, ge=1, le=50)
    ai_enrich: bool = Field(True, description="Run LLM enrichment on each listing")
    index: bool = Field(
        False,
        description="If true, also index enriched items to Elasticsearch",
    )


class ScrapeAndAnswerResponse(BaseModel):
    answer: str
    site_name: str
    items_scraped: int
    listings_used_for_answer: int
    items_enriched: int
    items_indexed: int
    message: str


@router.post("/scrape-and-answer", response_model=ScrapeAndAnswerResponse)
def scrape_and_answer(request: ScrapeAndAnswerRequest):
    """Scrape the site defined by config, then answer ``question`` from that data."""
    try:
        from omniscraper.models import SiteConfig
        from omniscraper.processor import process_results
        from omniscraper.scraper import scrape as run_scrape
    except ImportError as e:
        raise HTTPException(status_code=500, detail=f"Scraper not available: {e}")

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

        result = run_scrape(site_config, url=request.url)
        items_scraped = result.count

        items_enriched = 0
        items_indexed = 0
        enriched_list: list = []

        if items_scraped == 0:
            return ScrapeAndAnswerResponse(
                answer="Nothing was scraped (0 items). Check selectors, URL, or network.",
                site_name=site_config.name,
                items_scraped=0,
                listings_used_for_answer=0,
                items_enriched=0,
                items_indexed=0,
                message="Scrape returned no items.",
            )

        if request.ai_enrich:
            enriched_list = process_results(
                result,
                ai_enrich=True,
                index=request.index,
            )
            items_enriched = len(enriched_list)
            if request.index:
                items_indexed = items_enriched
            from omniscraper.ai_processor import answer_question_from_scraped_data

            answer, used = answer_question_from_scraped_data(
                request.question,
                enriched_list,
            )
        else:
            from omniscraper.ai_processor import answer_question_from_listings

            answer, used = answer_question_from_listings(request.question, result.items)
            if request.index:
                raise HTTPException(
                    status_code=400,
                    detail="index=true requires ai_enrich=true",
                )

        return ScrapeAndAnswerResponse(
            answer=answer,
            site_name=site_config.name,
            items_scraped=items_scraped,
            listings_used_for_answer=used,
            items_enriched=items_enriched,
            items_indexed=items_indexed,
            message=f"Answered from {used} listing(s) scraped from {site_config.name}",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("scrape-and-answer failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
