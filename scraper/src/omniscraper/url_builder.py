"""Generic URL builder from site config templates."""

from __future__ import annotations

from urllib.parse import urlencode, urljoin

from .models import SiteConfig


def build_url(
    config: SiteConfig,
    *,
    page: int = 1,
    extra_params: dict[str, str] | None = None,
    replacements: dict[str, str] | None = None,
) -> str:
    """
    Build a target URL from the site config's URL template.

    Args:
        config: The loaded SiteConfig.
        page: Page number (used if url_template or pagination.page_param is set).
        extra_params: Additional query parameters to append.
        replacements: Placeholder replacements for the URL template pattern.

    Returns:
        The fully constructed URL string.
    """
    if config.url_template:
        # Start with template pattern and fill placeholders
        subs = {"base_url": config.base_url, "page": page}
        if replacements:
            subs.update(replacements)
        try:
            url = config.url_template.pattern.format(**subs)
        except KeyError as e:
            raise ValueError(
                f"URL template has unknown placeholder {e}. "
                f"Available: {list(subs.keys())}. Pass extras via replacements."
            ) from e

        # Merge query params
        params: dict[str, str] = dict(config.url_template.params)
        if config.pagination.page_param and page > 1:
            params[config.pagination.page_param] = str(page)
        if extra_params:
            params.update(extra_params)

        if params:
            url = f"{url}?{urlencode(params)}"
        return url

    # Fallback: just use base_url with optional page param
    url = config.base_url
    params = {}
    if config.pagination.page_param and page > 1:
        params[config.pagination.page_param] = str(page)
    if extra_params:
        params.update(extra_params)
    if params:
        url = f"{url}?{urlencode(params)}"
    return url


def resolve_next_page(config: SiteConfig, current_url: str, next_href: str) -> str:
    """Resolve a relative next-page href against the current URL."""
    return urljoin(current_url, next_href)
