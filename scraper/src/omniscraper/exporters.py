"""Export scraped data to various formats."""

from __future__ import annotations

import csv
import json
import logging
from pathlib import Path
from typing import Any

from .models import ScrapeResult

logger = logging.getLogger("omniscraper")


def to_csv(result: ScrapeResult, path: str | Path) -> Path:
    """Export scrape results to a CSV file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    rows = result.to_flat_dicts()
    if not rows:
        logger.warning("No data to export")
        path.write_text("")
        return path

    # Collect all unique keys across all rows
    fieldnames: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row:
            if key not in seen:
                fieldnames.append(key)
                seen.add(key)

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    logger.info("Exported %d rows to %s", len(rows), path)
    return path


def to_json(result: ScrapeResult, path: str | Path) -> Path:
    """Export scrape results to a JSON file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    rows = result.to_flat_dicts()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2, ensure_ascii=False, default=str)

    logger.info("Exported %d items to %s", len(rows), path)
    return path


def to_jsonl(result: ScrapeResult, path: str | Path) -> Path:
    """Export scrape results to a JSON Lines file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    rows = result.to_flat_dicts()
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")

    logger.info("Exported %d items to %s", len(rows), path)
    return path


# ---------------------------------------------------------------------------
# Format dispatcher
# ---------------------------------------------------------------------------

EXPORTERS: dict[str, Any] = {
    "csv": to_csv,
    "json": to_json,
    "jsonl": to_jsonl,
}


def export(result: ScrapeResult, path: str | Path, fmt: str | None = None) -> Path:
    """
    Export results, auto-detecting format from file extension if fmt is None.

    Args:
        result: The scrape result to export.
        path: Output file path.
        fmt: Format override ('csv', 'json', 'jsonl'). Auto-detected if None.

    Returns:
        The path the data was written to.
    """
    path = Path(path)

    if fmt is None:
        ext = path.suffix.lstrip(".")
        fmt = ext if ext in EXPORTERS else "json"

    exporter = EXPORTERS.get(fmt)
    if exporter is None:
        raise ValueError(f"Unknown format '{fmt}'. Supported: {list(EXPORTERS.keys())}")

    return exporter(result, path)
