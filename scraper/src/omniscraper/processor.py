"""Pipeline Orchestrator — Scrape → Enrich → Embed → Index.

Coordinates the full data pipeline, tying together the scraper,
AI processor, and Elasticsearch indexer.
"""

from __future__ import annotations

import logging
from typing import Any

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

from .ai_processor import enrich_batch
from .database import bulk_index
from .models import EnrichedItem, ListingItem, ScrapeResult

logger = logging.getLogger("omniscraper.processor")
console = Console()


def process_results(
    result: ScrapeResult,
    *,
    ai_enrich: bool = True,
    index: bool = False,
    index_name: str | None = None,
    batch_size: int = 10,
) -> list[EnrichedItem]:
    """Process scrape results through the enrichment and indexing pipeline.

    Args:
        result: The raw scrape result.
        ai_enrich: If True, run LLM enrichment (sentiment, entities, summary, embeddings).
        index: If True, bulk-index enriched items to Elasticsearch.
        index_name: Elasticsearch index name override.
        batch_size: Number of items to process per batch.

    Returns:
        List of EnrichedItems (or empty list if ai_enrich is False).
    """
    if not result.items:
        console.print("[yellow]⚠ No items to process.[/yellow]")
        return []

    if not ai_enrich:
        console.print("[dim]AI enrichment disabled — skipping pipeline.[/dim]")
        return []

    items = result.items
    all_enriched: list[EnrichedItem] = []

    # Process in batches
    total_batches = (len(items) + batch_size - 1) // batch_size

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]Enriching..."),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Processing", total=len(items))

        for batch_idx in range(total_batches):
            start = batch_idx * batch_size
            end = min(start + batch_size, len(items))
            batch = items[start:end]

            enriched_batch = enrich_batch(batch)
            all_enriched.extend(enriched_batch)
            progress.update(task, advance=len(batch))

    # Summary
    sentiments = {"positive": 0, "neutral": 0, "negative": 0}
    all_entities: set[str] = set()
    for item in all_enriched:
        sentiments[item.sentiment] = sentiments.get(item.sentiment, 0) + 1
        all_entities.update(item.entities)

    console.print()
    console.print(f"[bold green]✅ Enriched {len(all_enriched)} item(s)[/bold green]")
    console.print(
        f"  Sentiment: "
        f"[green]{sentiments['positive']}↑[/green] "
        f"[dim]{sentiments['neutral']}→[/dim] "
        f"[red]{sentiments['negative']}↓[/red]"
    )
    if all_entities:
        top_entities = list(all_entities)[:10]
        console.print(f"  Entities: {', '.join(top_entities)}")

    # Index to Elasticsearch if requested
    if index:
        console.print()
        with console.status("[bold cyan]Indexing to Elasticsearch...[/bold cyan]"):
            indexed = bulk_index(all_enriched, index_name=index_name, site_name=result.site_name)
        console.print(f"[bold green]✅ Indexed {indexed} document(s) to Elasticsearch[/bold green]")

    return all_enriched


def enrich_and_export(
    result: ScrapeResult,
    output_path: str | None = None,
) -> list[dict[str, Any]]:
    """Enrich results and return them as flat dicts (for JSON/CSV export).

    This is a convenience function that enriches and flattens in one step.
    """
    enriched = process_results(result, ai_enrich=True, index=False)
    flat = []
    for item in enriched:
        doc = item.original.flat_dict()
        doc["sentiment"] = item.sentiment
        doc["entities"] = item.entities
        doc["summary"] = item.summary
        doc["enriched_at"] = item.enriched_at.isoformat()
        flat.append(doc)

    if output_path:
        import json
        from pathlib import Path

        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(flat, f, indent=2, ensure_ascii=False, default=str)
        console.print(f"[green]Saved enriched data to {path}[/green]")

    return flat
