"""Core scraping engine powered by Scrapling."""

from __future__ import annotations

import logging
import re
import time
from typing import Any

from .models import FieldSelector, ListingItem, ScrapeResult, SiteConfig
from .url_builder import build_url, resolve_next_page

logger = logging.getLogger("omniscraper")


# ---------------------------------------------------------------------------
# Field value transforms
# ---------------------------------------------------------------------------

def _apply_transform(value: Any, transform: str | None) -> Any:
    """Apply an optional transform to an extracted value."""
    if value is None or transform is None:
        return value

    if isinstance(value, list):
        return [_apply_transform(v, transform) for v in value]

    text = str(value).strip()

    if transform == "strip":
        return text
    elif transform == "int":
        cleaned = re.sub(r"[^\d]", "", text)
        return int(cleaned) if cleaned else None
    elif transform == "float":
        cleaned = re.sub(r"[^\d.]", "", text)
        return float(cleaned) if cleaned else None
    elif transform == "clean_price":
        # Remove currency symbols, non-breaking spaces, commas
        cleaned = re.sub(r"[^\d.]", "", text.replace("\u202f", "").replace(",", ""))
        return float(cleaned) if cleaned else None
    return text


# ---------------------------------------------------------------------------
# Fetcher factory
# ---------------------------------------------------------------------------

def _get_fetcher(config: SiteConfig):
    """Return the appropriate Scrapling fetcher based on config."""
    if config.fetcher == "basic":
        from scrapling.fetchers import Fetcher
        return Fetcher
    elif config.fetcher == "stealthy":
        from scrapling.fetchers import StealthyFetcher
        return StealthyFetcher
    elif config.fetcher == "dynamic":
        from scrapling.fetchers import DynamicFetcher
        return DynamicFetcher
    else:
        raise ValueError(f"Unknown fetcher type: {config.fetcher}")


def _fetch_page(config: SiteConfig, url: str):
    """Fetch a single page using the configured fetcher."""
    fetcher = _get_fetcher(config)

    if config.fetcher == "basic":
        return fetcher.get(url, stealthy_headers=True)
    else:
        return fetcher.fetch(url, headless=config.headless)


# ---------------------------------------------------------------------------
# Extraction logic
# ---------------------------------------------------------------------------

def _extract_field(element, field: FieldSelector) -> Any:
    """Extract a single field value from an element using a FieldSelector."""
    selector = field.selector

    # Detect if XPath
    is_xpath = selector.startswith("xpath:") or selector.startswith("/") or selector.startswith("(")
    if selector.startswith("xpath:"):
        selector = selector[len("xpath:"):]

    try:
        if is_xpath:
            if field.multiple:
                results = element.xpath(selector).getall()
            else:
                results = element.xpath(selector).get()
        else:
            if field.multiple:
                results = element.css(selector).getall()
            else:
                results = element.css(selector).get()
    except Exception:
        results = None

    # Handle attribute extraction for non-pseudo-element selectors
    if field.attribute and results is not None:
        if isinstance(results, list):
            results = [
                r.attrib.get(field.attribute) if hasattr(r, "attrib") else r
                for r in results
            ]
        elif hasattr(results, "attrib"):
            results = results.attrib.get(field.attribute)

    return _apply_transform(results, field.transform)


def _scrape_page(config: SiteConfig, page, url: str) -> list[ListingItem]:
    """Extract all listings from a single page response."""
    items: list[ListingItem] = []

    try:
        if config.listing_container.startswith("xpath:"):
            containers = page.xpath(config.listing_container[len("xpath:"):])
        elif config.listing_container.startswith("/") or config.listing_container.startswith("("):
            containers = page.xpath(config.listing_container)
        else:
            containers = page.css(config.listing_container)
    except Exception as e:
        logger.warning("Could not find listing container '%s': %s", config.listing_container, e)
        return items

    if not containers:
        logger.warning("No listings found with selector '%s'", config.listing_container)
        return items

    logger.info("Found %d listing(s) on page", len(containers))

    for i, container in enumerate(containers, 1):
        data: dict[str, Any] = {}
        try:
            for field_name, field_config in config.fields.items():
                data[field_name] = _extract_field(container, field_config)

            items.append(ListingItem(source_url=url, data=data))
        except Exception as e:
            logger.warning("Listing %d: extraction error — %s", i, e)
            continue

    return items


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def scrape(
    config: SiteConfig,
    *,
    url: str | None = None,
    replacements: dict[str, str] | None = None,
    extra_params: dict[str, str] | None = None,
) -> ScrapeResult:
    """
    Run a full scrape job using the given SiteConfig.

    Args:
        config: Loaded site configuration.
        url: Optional direct URL to scrape (overrides url_template).
        replacements: Placeholder values for the url_template pattern.
        extra_params: Additional query parameters.

    Returns:
        A ScrapeResult with all scraped items.
    """
    result = ScrapeResult(site_name=config.name)
    max_pages = config.pagination.max_pages
    next_page_url: str | None = None

    for page_num in range(1, max_pages + 1):
        # Determine target URL
        if url and page_num == 1:
            target_url = url
        elif url and config.pagination.page_param:
            from urllib.parse import urlencode, urlparse, parse_qs, urlunparse

            parsed = urlparse(url)
            params = parse_qs(parsed.query)
            params[config.pagination.page_param] = [str(page_num)]
            new_query = urlencode(params, doseq=True)
            target_url = urlunparse(parsed._replace(query=new_query))
        elif url:
            # Direct URL with no page_param — rely on next-page link navigation
            # (handled at the bottom of the loop)
            if page_num > 1 and next_page_url:
                target_url = next_page_url
            elif page_num > 1:
                logger.info("No page_param or next-page link — stopping at page 1")
                break
            else:
                target_url = url
        else:
            target_url = build_url(
                config,
                page=page_num,
                replacements=replacements,
                extra_params=extra_params,
            )

        logger.info("[Page %d/%d] Fetching: %s", page_num, max_pages, target_url)

        try:
            page_response = _fetch_page(config, target_url)
        except Exception as e:
            logger.error("Failed to fetch page %d: %s", page_num, e)
            break

        page_items = _scrape_page(config, page_response, target_url)
        result.items.extend(page_items)
        result.total_pages += 1

        logger.info("[Page %d] Scraped %d item(s)", page_num, len(page_items))

        if not page_items:
            logger.info("No items found — stopping pagination")
            break

        # Check for next page via link
        if config.pagination.next_page and page_num < max_pages:
            try:
                next_link = page_response.css(config.pagination.next_page).get()
                if not next_link:
                    logger.info("No next-page link found — stopping")
                    break
                next_page_url = resolve_next_page(config, target_url, next_link)
            except Exception:
                next_page_url = None
                break

        # Polite delay between pages
        if page_num < max_pages:
            logger.debug("Waiting %.1fs before next page...", config.delay)
            time.sleep(config.delay)

    logger.info("Scrape complete: %d item(s) from %d page(s)", result.count, result.total_pages)
    return result
