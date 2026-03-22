"""OmniScraper CLI — powered by Typer & Rich."""

from __future__ import annotations

import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    from dotenv import load_dotenv
    # Walk up to project root to find .env (handles running from scraper/ or project root)
    _here = Path.cwd()
    for _candidate in [_here / ".env", _here.parent / ".env"]:
        if _candidate.exists():
            load_dotenv(_candidate)
            break
except ImportError:
    pass

import typer
from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel
from rich.table import Table

from . import __version__
from .models import SiteConfig, ScrapeResult

app = typer.Typer(
    name="omniscraper",
    help="🏠 OmniScraper — A generic, config-driven scraping framework.",
    add_completion=False,
    rich_markup_mode="rich",
)
console = Console()

# Default directories (relative to where CLI is run)
CONFIGS_DIR = Path("configs")
OUTPUT_DIR = Path("output")


def _build_output_path(site_name: str, fmt: str = "json") -> Path:
    """Generate a structured output path: output/<site_name>/<site_name>.<fmt>"""
    safe_name = site_name.replace(" ", "_").lower()
    out_dir = OUTPUT_DIR / safe_name
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir / f"{safe_name}.{fmt}"


def _setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True, show_path=False)],
    )


def _find_config(name: str) -> Path:
    """Resolve a config name or path to an actual YAML file."""
    path = Path(name)
    if path.exists():
        return path

    # Try in configs directory
    for ext in ("", ".yaml", ".yml"):
        candidate = CONFIGS_DIR / f"{name}{ext}"
        if candidate.exists():
            return candidate

    raise typer.BadParameter(
        f"Config '{name}' not found. Run 'omniscraper list-sites' to see available configs."
    )


def _display_results(result: ScrapeResult) -> None:
    """Print a rich table of scraped results."""
    if not result.items:
        console.print("[yellow]⚠ No items were scraped.[/yellow]")
        return

    # Build table from first item's fields
    table = Table(
        title=f"🏠 {result.site_name} — {result.count} listing(s)",
        show_lines=True,
        expand=True,
    )

    # Determine columns from first item
    sample = result.items[0].data
    table.add_column("#", style="dim", width=4)
    for key in sample:
        table.add_column(key.replace("_", " ").title(), overflow="fold")

    for i, item in enumerate(result.items, 1):
        row = [str(i)]
        for key in sample:
            val = item.data.get(key, "—")
            if isinstance(val, list):
                val = ", ".join(str(v) for v in val[:3])
                if len(item.data.get(key, [])) > 3:
                    val += "…"
            row.append(str(val) if val is not None else "—")
        table.add_row(*row)

    console.print(table)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

@app.command()
def scrape(
    config: str = typer.Argument(
        ...,
        help="Site config name or path to YAML file",
    ),
    url: Optional[str] = typer.Option(
        None,
        "--url", "-u",
        help="Direct URL to scrape (overrides url_template)",
    ),
    pages: Optional[int] = typer.Option(
        None,
        "--pages", "-p",
        help="Max pages to scrape (overrides config)",
    ),
    output: Optional[str] = typer.Option(
        None,
        "--output", "-o",
        help="Output path (e.g. results.csv). Default: output/<site>/timestamp.json",
    ),
    fmt: Optional[str] = typer.Option(
        "json",
        "--format", "-f",
        help="Output format: csv, json, jsonl (default: json)",
    ),
    ai_enrich: bool = typer.Option(
        False,
        "--ai-enrich",
        help="Enrich scraped data with LLM (sentiment, entities, summary, embeddings)",
    ),
    index: bool = typer.Option(
        False,
        "--index",
        help="Index enriched data to Elasticsearch (requires --ai-enrich)",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose", "-v",
        help="Enable debug logging",
    ),
) -> None:
    """🕷️ Run a scrape job using a site config."""
    _setup_logging(verbose)

    config_path = _find_config(config)
    console.print(
        Panel(
            f"[bold cyan]OmniScraper v{__version__}[/bold cyan]\n"
            f"Config: [green]{config_path}[/green]",
            title="🏠 OmniScraper",
            border_style="cyan",
        )
    )

    site_config = SiteConfig.from_yaml(config_path)

    if pages is not None:
        site_config.pagination.max_pages = pages

    console.print(f"[dim]Fetcher:[/dim] {site_config.fetcher}")
    console.print(f"[dim]Max pages:[/dim] {site_config.pagination.max_pages}")
    console.print(f"[dim]Headless:[/dim] {site_config.headless}")
    if ai_enrich:
        console.print("[dim]AI Enrich:[/dim] [green]enabled[/green]")
    if index:
        console.print("[dim]ES Index:[/dim] [green]enabled[/green]")
    console.print()

    from .scraper import scrape as run_scrape

    with console.status("[bold green]Scraping in progress…[/bold green]", spinner="dots"):
        result = run_scrape(site_config, url=url)

    _display_results(result)

    # --- AI Enrichment Pipeline ---
    if ai_enrich and result.count > 0:
        console.print()
        console.print(
            Panel(
                "[bold magenta]🧠 AI Enrichment Pipeline[/bold magenta]",
                border_style="magenta",
                expand=False,
            )
        )
        from .processor import process_results

        process_results(result, ai_enrich=True, index=index)
    elif index and not ai_enrich:
        console.print("[yellow]⚠ --index requires --ai-enrich (embeddings needed). Skipping.[/yellow]")

    # Export results
    if result.count > 0:
        from .exporters import export

        if output:
            out_path = export(result, output, fmt)
        else:
            auto_path = _build_output_path(site_config.name, fmt or "json")
            out_path = export(result, auto_path, fmt)

        console.print()
        console.print(
            Panel(
                f"[green]{result.count}[/green] items → [bold]{out_path}[/bold]",
                title="✅ Saved",
                border_style="green",
                expand=False,
            )
        )


@app.command(name="list-sites")
def list_sites() -> None:
    """📋 List available site configurations."""
    if not CONFIGS_DIR.exists():
        console.print("[yellow]No configs/ directory found.[/yellow]")
        raise typer.Exit()

    configs = list(CONFIGS_DIR.glob("*.yaml")) + list(CONFIGS_DIR.glob("*.yml"))
    # Filter out templates
    configs = [c for c in configs if not c.stem.startswith("_")]

    if not configs:
        console.print("[yellow]No site configs found in configs/.[/yellow]")
        raise typer.Exit()

    table = Table(title="📋 Available Site Configs", show_lines=False)
    table.add_column("Name", style="bold cyan")
    table.add_column("File", style="dim")
    table.add_column("Base URL", style="green")
    table.add_column("Fetcher")

    for config_path in sorted(configs):
        try:
            cfg = SiteConfig.from_yaml(config_path)
            table.add_row(cfg.name, config_path.name, cfg.base_url, cfg.fetcher)
        except Exception as e:
            table.add_row("⚠ ERROR", config_path.name, str(e), "—")

    console.print(table)


@app.command(name="init-config")
def init_config(
    output: str = typer.Option(
        "configs/my_site.yaml",
        "--output", "-o",
        help="Where to create the config file",
    ),
) -> None:
    """🔧 Generate a starter site config template."""
    template = CONFIGS_DIR / "_template.yaml"
    output_path = Path(output)

    if output_path.exists():
        overwrite = typer.confirm(f"'{output_path}' already exists. Overwrite?")
        if not overwrite:
            raise typer.Abort()

    output_path.parent.mkdir(parents=True, exist_ok=True)

    if template.exists():
        shutil.copy(template, output_path)
    else:
        # Generate inline template
        output_path.write_text(
            """# OmniScraper Site Configuration
# Docs: https://github.com/K-BEL/omniscraper

name: "my_site"
base_url: "https://example.com"
fetcher: "stealthy"        # basic | stealthy | dynamic
headless: true

# listing_container: CSS selector for each listing card on the page
listing_container: ".listing-card"

# fields: map of field_name → selector config
fields:
  title:
    selector: ".title::text"
  price:
    selector: ".price::text"
    transform: "clean_price"
  location:
    selector: ".location::text"
  image:
    selector: "img::attr(src)"
    attribute: "src"
  link:
    selector: "a::attr(href)"
    attribute: "href"

# pagination
pagination:
  next_page: ".next-page a::attr(href)"
  max_pages: 3

# Politeness delay between pages (seconds)
delay: 2.0
""",
            encoding="utf-8",
        )

    console.print(f"[bold green]✅ Created config:[/bold green] {output_path}")
    console.print("[dim]Edit the file to match your target site's selectors.[/dim]")


@app.command()
def version() -> None:
    """📦 Show version."""
    console.print(f"[bold cyan]OmniScraper[/bold cyan] v{__version__}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app()
