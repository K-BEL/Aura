"""Pydantic data models for site configs and scraped data."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import yaml
from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Site configuration (loaded from YAML)
# ---------------------------------------------------------------------------

class PaginationConfig(BaseModel):
    """How to navigate between pages."""

    next_page: Optional[str] = Field(
        None,
        description="CSS selector for the next-page link (e.g. '.next a::attr(href)')",
    )
    page_param: Optional[str] = Field(
        None,
        description="Query-param name for page number (e.g. 'page' or 'o')",
    )
    max_pages: int = Field(
        1,
        description="Maximum number of pages to scrape",
    )


class UrlTemplate(BaseModel):
    """Template for building search URLs."""

    pattern: str = Field(
        ...,
        description="URL pattern with {placeholders}, e.g. '{base_url}/{city}/{category}'",
    )
    params: dict[str, str] = Field(
        default_factory=dict,
        description="Default query parameters to include",
    )


class FieldSelector(BaseModel):
    """Maps a field name to a CSS/XPath selector."""

    selector: str = Field(..., description="CSS or XPath selector")
    attribute: Optional[str] = Field(
        None,
        description="HTML attribute to extract (e.g. 'href', 'src'). Default: text content.",
    )
    multiple: bool = Field(
        False,
        description="If True, extract all matching elements as a list",
    )
    transform: Optional[str] = Field(
        None,
        description="Optional transform: 'int', 'float', 'strip', 'clean_price'",
    )


class SiteConfig(BaseModel):
    """Full site adapter configuration, loaded from a YAML file."""

    name: str = Field(..., description="Human-readable site name")
    base_url: str = Field(..., description="Base URL of the target site")
    fetcher: str = Field(
        "stealthy",
        description="Fetcher type: 'basic', 'stealthy', or 'dynamic'",
    )
    headless: bool = Field(True, description="Run browser in headless mode")

    url_template: Optional[UrlTemplate] = None
    listing_container: str = Field(
        ...,
        description="CSS selector for the container holding all listings",
    )
    fields: dict[str, FieldSelector] = Field(
        ...,
        description="Map of field_name → FieldSelector for each listing",
    )
    pagination: PaginationConfig = Field(default_factory=PaginationConfig)

    # Delays & politeness
    delay: float = Field(2.0, description="Seconds to wait between page fetches")

    @field_validator("fetcher")
    @classmethod
    def validate_fetcher(cls, v: str) -> str:
        allowed = {"basic", "stealthy", "dynamic"}
        if v not in allowed:
            raise ValueError(f"fetcher must be one of {allowed}, got '{v}'")
        return v

    @classmethod
    def from_yaml(cls, path: str | Path) -> "SiteConfig":
        """Load a SiteConfig from a YAML file."""
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        # Convert the flat 'fields' dict with string selectors to FieldSelector objects
        if "fields" in data:
            parsed_fields = {}
            for name, value in data["fields"].items():
                if isinstance(value, str):
                    parsed_fields[name] = {"selector": value}
                else:
                    parsed_fields[name] = value
            data["fields"] = parsed_fields
        return cls(**data)


# ---------------------------------------------------------------------------
# Scraped data models
# ---------------------------------------------------------------------------

class ListingItem(BaseModel):
    """A single scraped listing."""

    scraped_at: datetime = Field(default_factory=datetime.now)
    source_url: str = ""
    data: dict[str, Any] = Field(default_factory=dict)

    def flat_dict(self) -> dict[str, Any]:
        """Flatten to a simple dict for export."""
        return {
            "scraped_at": self.scraped_at.isoformat(),
            "source_url": self.source_url,
            **self.data,
        }


class ScrapeResult(BaseModel):
    """Result of a complete scrape job."""

    site_name: str
    total_pages: int = 0
    items: list[ListingItem] = Field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.items)

    def to_flat_dicts(self) -> list[dict[str, Any]]:
        """Convert all items to flat dicts for export."""
        return [item.flat_dict() for item in self.items]


# ---------------------------------------------------------------------------
# Enriched data models (NLP pipeline output)
# ---------------------------------------------------------------------------

class EnrichedItem(BaseModel):
    """A listing enriched with NLP metadata."""

    original: ListingItem
    sentiment: str = Field(
        ...,
        description="Detected sentiment: 'positive', 'neutral', or 'negative'",
    )
    entities: list[str] = Field(
        default_factory=list,
        description="Extracted named entities (brands, products, locations)",
    )
    summary: str = Field(
        "",
        description="LLM-generated 1-2 sentence summary",
    )
    embedding: list[float] = Field(
        default_factory=list,
        description="Dense vector embedding (384-dim for multilingual-MiniLM)",
    )
    enriched_at: datetime = Field(default_factory=datetime.now)

    def to_es_doc(self) -> dict[str, Any]:
        """Flatten to an Elasticsearch-ready document."""
        return {
            "scraped_at": self.original.scraped_at.isoformat(),
            "source_url": self.original.source_url,
            "sentiment": self.sentiment,
            "entities": self.entities,
            "summary": self.summary,
            "embedding": self.embedding,
            "enriched_at": self.enriched_at.isoformat(),
            **self.original.data,
        }
