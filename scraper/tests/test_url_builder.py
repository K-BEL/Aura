"""Tests for URL builder."""

import pytest

from omniscraper.models import PaginationConfig, SiteConfig, UrlTemplate
from omniscraper.url_builder import build_url, resolve_next_page


def _make_config(**overrides) -> SiteConfig:
    """Helper to create a minimal SiteConfig for testing."""
    defaults = {
        "name": "test",
        "base_url": "https://example.com",
        "fetcher": "basic",
        "listing_container": ".item",
        "fields": {"title": {"selector": ".t::text"}},
    }
    defaults.update(overrides)
    return SiteConfig(**defaults)


class TestBuildUrl:
    def test_simple_base_url(self):
        cfg = _make_config()
        url = build_url(cfg)
        assert url == "https://example.com"

    def test_with_page_param(self):
        cfg = _make_config(
            pagination=PaginationConfig(page_param="page", max_pages=5)
        )
        # Page 1 should not add param
        assert build_url(cfg, page=1) == "https://example.com"
        # Page 2 should
        url = build_url(cfg, page=2)
        assert "page=2" in url

    def test_with_url_template(self):
        cfg = _make_config(
            url_template=UrlTemplate(
                pattern="{base_url}/listings/{city}",
                params={"sort": "newest"},
            )
        )
        url = build_url(cfg, replacements={"city": "casablanca"})
        assert "example.com/listings/casablanca" in url
        assert "sort=newest" in url

    def test_extra_params(self):
        cfg = _make_config()
        url = build_url(cfg, extra_params={"q": "luxury"})
        assert "q=luxury" in url

    def test_template_with_pagination(self):
        cfg = _make_config(
            url_template=UrlTemplate(pattern="{base_url}/search"),
            pagination=PaginationConfig(page_param="p", max_pages=10),
        )
        url = build_url(cfg, page=3)
        assert "p=3" in url


class TestResolveNextPage:
    def test_relative(self):
        cfg = _make_config()
        result = resolve_next_page(cfg, "https://example.com/page/1", "/page/2")
        assert result == "https://example.com/page/2"

    def test_absolute(self):
        cfg = _make_config()
        result = resolve_next_page(
            cfg, "https://example.com/page/1", "https://example.com/page/2"
        )
        assert result == "https://example.com/page/2"
