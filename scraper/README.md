<p align="center">
  <h1 align="center">🏠 OmniScraper</h1>
  <p align="center">A generic, config-driven scraping framework powered by <a href="https://github.com/K-BEL/Scrapling">Scrapling</a></p>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.10%2B-blue?style=flat-square" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/license-MIT-green?style=flat-square" alt="MIT License">
  <img src="https://img.shields.io/badge/powered%20by-Scrapling-orange?style=flat-square" alt="Scrapling">
</p>

---

**OmniScraper** is a professional, site-agnostic web scraping toolkit. Instead of hardcoding selectors for a single website, you define **YAML config files** that map CSS/XPath selectors to data fields. One framework, any site.

## ✨ Features

- 🔌 **Plugin-style site configs** — Each target site is a simple YAML file
- 🕷️ **Powered by Scrapling** — HTTP, stealth browser, and dynamic rendering fetchers
- 🧠 **AI Enrichment Pipeline** — Extract sentiment, entities, and summaries with local (Ollama) or cloud (Gemini/OpenAI) LLMs
- 🔍 **Hybrid Search ready** — Index to Elasticsearch with 384-dimensional text embeddings automatically
- 🖥️ **Beautiful CLI** — Typer + Rich with tables, progress spinners, and colored output
- 📊 **Multiple export formats** — CSV, JSON, ES indexing
- 🧩 **Pydantic data models** — Typed, validated scraped data
- 📄 **Pagination support** — Follow next-page links or increment page params
- 🎯 **Smart extraction** — CSS, XPath, attribute extraction, value transforms
- 🐢 **Polite scraping** — Configurable delays between page fetches

## 🚀 Quick Start

### Installation

```bash
# Clone the repo
git clone https://github.com/K-BEL/omniscraper.git
cd omniscraper

# Install in editable mode
pip install -e .

# Install Scrapling browser dependencies (for stealth/dynamic fetchers)
scrapling install
```

### Usage

```bash
# List available site configs
omniscraper list-sites

# Run a basic scrape without AI
omniscraper scrape example_site --output results.json

# Run a scrape with AI enrichment (Sentiment, Entities, Embedding)
omniscraper scrape example_site --ai-enrich -o enriched_results.json

# Run a scrape with AI enrichment and push to Elasticsearch
omniscraper scrape example_site --ai-enrich --index

# Generate a new site config template
omniscraper init-config --output configs/my_site.yaml
```

## 📁 Project Structure

```
omniscraper/
├── src/omniscraper/        # Core package
│   ├── cli.py             # Typer CLI (scrape, list-sites)
│   ├── models.py          # Pydantic models (EnrichedItem)
│   ├── scraper.py         # Scrapling-based engine
│   ├── ai_processor.py    # LLM & Embedding pipeline
│   ├── database.py        # Elasticsearch Hybrid Search client
│   └── processor.py       # Scrape -> Enrich -> Index orchestrator
├── configs/               # Site adapter configs (YAML)
├── tests/                 # Pytest test suite, including mocked LLM/ES
├── pyproject.toml         # Modern Python packaging
└── README.md
```

## 🔧 Writing a Site Config

Each site is defined by a YAML config. Here's an example:

```yaml
name: "my_site"
base_url: "https://example.com"
fetcher: "stealthy"          # basic | stealthy | dynamic
headless: true

listing_container: ".item-card"

fields:
  title:
    selector: ".card-title::text"
  price:
    selector: ".price::text"
    transform: "clean_price"
  location:
    selector: ".location::text"
  link:
    selector: "a::attr(href)"

pagination:
  next_page: ".pagination .next a::attr(href)"
  max_pages: 10

delay: 2.0
```

### Fetcher Types

| Fetcher | Use Case |
|---------|----------|
| `basic` | Fast HTTP requests — for static sites with no JS |
| `stealthy` | Headless browser with anti-bot bypass — for protected sites |
| `dynamic` | Full Playwright browser automation — for heavy JS-rendered sites |

### Field Transforms

| Transform | Effect |
|-----------|--------|
| `strip` | Remove leading/trailing whitespace |
| `int` | Extract digits and convert to integer |
| `float` | Extract number and convert to float |
| `clean_price` | Remove currency symbols, spaces, and parse as number |

## 🤖 AI Enrichment & Elasticsearch

Install the `ai` dependency group to enable these features:

```bash
pip install -e ".[ai]"
```

Configure your `.env` file at the project root for LLM and ES settings:

```env
# LLM Provider options: ollama (default), gemini, openai
AURA_LLM_PROVIDER=ollama
AURA_OLLAMA_URL=http://localhost:11434

AURA_ES_URL=http://localhost:9200
```

## 🧪 Running Tests

```bash
pip install -e ".[dev,ai]"
python -m pytest tests/ -v
```

## 🐳 Docker (Optional)

Use Scrapling's official Docker image for a batteries-included environment:

```bash
docker pull pyd4vinci/scrapling
```

## ⚠️ Disclaimer

> This tool is provided for **educational and research purposes only**. By using this software, you agree to comply with local and international laws regarding web scraping and data privacy. The authors are **not responsible** for any misuse. Always:
>
> - Respect websites' **Terms of Service**
> - Check and obey **robots.txt** files
> - Use reasonable **rate limiting** (the `delay` config field)
> - Never scrape personal or sensitive data without consent

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.
