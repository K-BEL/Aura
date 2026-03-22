"""Tests for Pydantic models and SiteConfig loading."""

import tempfile
from pathlib import Path

import pytest

from omniscraper.models import (
    FieldSelector,
    ListingItem,
    PaginationConfig,
    ScrapeResult,
    SiteConfig,
)


# ---------------------------------------------------------------------------
# FieldSelector
# ---------------------------------------------------------------------------

class TestFieldSelector:
    def test_minimal(self):
        fs = FieldSelector(selector=".title::text")
        assert fs.selector == ".title::text"
        assert fs.attribute is None
        assert fs.multiple is False
        assert fs.transform is None

    def test_full(self):
        fs = FieldSelector(
            selector="img",
            attribute="src",
            multiple=True,
            transform="strip",
        )
        assert fs.attribute == "src"
        assert fs.multiple is True


# ---------------------------------------------------------------------------
# SiteConfig
# ---------------------------------------------------------------------------

SAMPLE_YAML = """\
name: "test_site"
base_url: "https://example.com"
fetcher: "basic"
listing_container: ".item"
fields:
  title: ".title::text"
  price:
    selector: ".price::text"
    transform: "clean_price"
  link:
    selector: "a::attr(href)"
    attribute: "href"
pagination:
  max_pages: 2
  next_page: ".next a::attr(href)"
delay: 1.0
"""


class TestSiteConfig:
    def _write_yaml(self, content: str) -> Path:
        f = tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False)
        f.write(content)
        f.close()
        return Path(f.name)

    def test_load_from_yaml(self):
        path = self._write_yaml(SAMPLE_YAML)
        cfg = SiteConfig.from_yaml(path)

        assert cfg.name == "test_site"
        assert cfg.base_url == "https://example.com"
        assert cfg.fetcher == "basic"
        assert cfg.listing_container == ".item"
        assert "title" in cfg.fields
        assert cfg.fields["title"].selector == ".title::text"
        assert cfg.fields["price"].transform == "clean_price"
        assert cfg.pagination.max_pages == 2
        assert cfg.delay == 1.0

    def test_invalid_fetcher(self):
        yaml = SAMPLE_YAML.replace('fetcher: "basic"', 'fetcher: "invalid"')
        path = self._write_yaml(yaml)
        with pytest.raises(Exception):
            SiteConfig.from_yaml(path)

    def test_missing_file(self):
        with pytest.raises(FileNotFoundError):
            SiteConfig.from_yaml("/nonexistent.yaml")

    def test_shorthand_string_selectors(self):
        """String selectors like 'title: \".title::text\"' should be auto-converted."""
        path = self._write_yaml(SAMPLE_YAML)
        cfg = SiteConfig.from_yaml(path)
        assert isinstance(cfg.fields["title"], FieldSelector)
        assert cfg.fields["title"].selector == ".title::text"


# ---------------------------------------------------------------------------
# ListingItem & ScrapeResult
# ---------------------------------------------------------------------------

class TestListingItem:
    def test_flat_dict(self):
        item = ListingItem(
            source_url="https://example.com/1",
            data={"title": "Apt", "price": 100000},
        )
        flat = item.flat_dict()
        assert flat["title"] == "Apt"
        assert flat["price"] == 100000
        assert "scraped_at" in flat
        assert flat["source_url"] == "https://example.com/1"


class TestScrapeResult:
    def test_count(self):
        result = ScrapeResult(
            site_name="test",
            items=[
                ListingItem(data={"a": 1}),
                ListingItem(data={"a": 2}),
            ],
        )
        assert result.count == 2

    def test_to_flat_dicts(self):
        result = ScrapeResult(
            site_name="test",
            items=[ListingItem(data={"x": "y"})],
        )
        dicts = result.to_flat_dicts()
        assert len(dicts) == 1
        assert dicts[0]["x"] == "y"
