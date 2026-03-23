# Aura — AI-Enriched Market Intelligence Platform

Aura is a complete, end-to-end framework for scraping, enriching, indexing, and querying market data using a conversational AI interface.

It combines a robust Python scraping engine (**OmniScraper**) with a sleek React AI chat application, connected via a FastAPI bridge and powered by Elasticsearch hybrid search and multilingual Large Language Models (LLMs).

---

## 🏗️ Architecture Overview

The Aura monorepo consists of four main components:

1. `**scraper/` (OmniScraper Core)**
  A configuration-driven web scraping framework built on `scrapling`. It features an advanced AI backend (`ai_processor.py`) that uses LLMs to extract sentiment, entities, and summaries from raw scraped text, while generating 384-dimensional multilingual embeddings.
2. `**api/` (Aura API Bridge)**
  A lightweight FastAPI server (`main.py`) that sits between the frontend and the scraper. It exposes endpoints to trigger scrape jobs, run **scrape-then-answer** (fresh data + LLM reply), and execute hybrid searches. It loads `.env` from the project root automatically via `python-dotenv`.
3. `**frontend/` (AI Chat Application)**
  A React/Vite application that provides a ChatGPT-like interface. Users can search the market intelligence database in natural language or trigger new scrapes via Quick Start cards (`ChatBox.jsx`).
4. **Elasticsearch & Kibana**
  A local cluster (managed via Docker Compose) that provides the `aura-market-data` index. It supports **Hybrid Search**, combining semantic vector similarity (kNN) with keyword matching (BM25).

---

## 🚀 Quick Start Guide

### 1. Prerequisites

- Python 3.10+
- Node.js 18+
- Docker & Docker Compose
- Ollama (running locally with a model that fits in your RAM — e.g. `qwen2.5:1.5b` for 8 GB machines, `llama3` for 16+ GB)

### 2. Environment Setup

Copy the example environment files and fill in your API keys (optional if using local models):

```bash
# Project-root .env (backend: LLM, Elasticsearch, API settings)
cp .env.example .env

# Frontend .env (chat provider API keys)
cp frontend/.env.example frontend/.env
```

Both the API bridge and the CLI auto-load `.env` from the project root via `python-dotenv`. The frontend uses Vite's built-in `.env` loading (`VITE_*` variables only).

### 3. Start Elasticsearch (Database)

Start the local Elasticsearch 8.x and Kibana cluster. This is required for indexing and searching enriched data.

```bash
docker compose up -d
```

*Kibana will be available at [http://localhost:5601](http://localhost:5601).*

### 4. Setup the Backend (Scraper & API)

**Use a virtual environment.** On macOS with Homebrew Python, `pip install` on the system interpreter fails with `externally-managed-environment` (PEP 668). Always `source` a venv before `pip` or `uvicorn`.

Create the scraper venv once, then install OmniScraper + API deps:

```bash
cd scraper
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev,ai]"
cd ..
```

**Next time** (new terminal), from the project root:

```bash
source scraper/.venv/bin/activate
pip install -r api/requirements.txt
uvicorn api.main:app --reload --port 8000
```

*The API Bridge will be available at [http://localhost:8000](http://localhost:8000).*

### 5. Setup the Frontend (Chat UI)

Open a new terminal window, install the Node dependencies, and start the Vite dev server:

```bash
cd frontend
npm install
npm run dev
```

*The Chat interface will be available at [http://localhost:5173](http://localhost:5173).*

---

## 🛠️ Usage Guide

### Using the Chat Interface

1. Open the frontend in your browser.
2. Under "How can I help you?", click **Market Search** to query existing data (e.g., "Find positive reviews for MacBook Pro in Casablanca").
3. Click **Scrape Site** to trigger a new extraction job using one of the existing YAML configurations.
4. The backend will scrape the data, pass it through the local LLM for sentiment/entity extraction, generate vector embeddings, and index it into Elasticsearch automatically.
5. Click **Ask a site** or type a command (see below) to scrape a configured site **once** and get an answer grounded in that fresh data—without relying on data already in Elasticsearch.

### Ask a site (scrape, then answer)

Use this when you want a natural-language answer **only from what was just scraped** from a target you define in YAML (under `scraper/configs/`).

**In the chat box**, use this pattern (config name = YAML filename without `.yaml`):

```text
Ask site: example_site | Which authors appear in these quotes?
```

- **Left of `|`:** the site config name (e.g. `example_site` for `example_site.yaml`).
- **Right of `|`:** your question.

The UI shows a short loading state, then appends the assistant reply.

**Important:** The answer step uses the **LLM configured for the API / scraper** (`AURA_LLM_PROVIDER`, `AURA_LLM_MODEL` in `.env`—typically Ollama on the machine running `uvicorn`). It does **not** use the chat provider/model selected in the frontend settings (e.g. Groq).

By default this flow does **not** index into Elasticsearch (faster interactive use). To index as well, call the API with `"index": true` (see below).

**API (optional):** `POST /api/scrape-and-answer` with JSON body:

```json
{
  "config_name": "example_site",
  "question": "Summarize the main themes.",
  "url": null,
  "max_pages": 3,
  "ai_enrich": true,
  "index": false
}
```

Response includes `answer`, `items_scraped`, `listings_used_for_answer`, and counts for enrichment/indexing.

### Using the CLI Directly

You can bypass the API and use the OmniScraper CLI directly from the `scraper/` directory:

```bash
source .venv/bin/activate

# List available site configs
omniscraper list-sites

# Scrape a site, run it through the AI pipeline, and index it to Elasticsearch
omniscraper scrape my_target_site --ai-enrich --index
```

---

## 🧠 The AI Enrichment Pipeline

The pipeline (`ai_processor.py`) intercepts raw scraped `ListingItem` objects and generates `EnrichedItem` objects by:

1. Contacting an LLM (Ollama, Gemini, or OpenAI) to perform a zero-shot extraction of sentiment, entities, and summaries.
2. Generating a 384-dimension text embedding using `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`. This model is multilingual, natively supporting English, French, and Arabic.
3. Pushing the `EnrichedItem` to Elasticsearch (`database.py`) if the `--index` flag is active.

### LLM Configuration

Edit your `.env` file to change the provider:

```env
# Supported: ollama, gemini, openai
AURA_LLM_PROVIDER=ollama
AURA_LLM_MODEL=qwen2.5:1.5b
```

Make sure the model is pulled locally: `ollama pull qwen2.5:1.5b`

---

## 🧪 Testing

The AI processor and database integration features are fully covered by a mocked `pytest` suite.

```bash
cd scraper
source .venv/bin/activate
pytest tests/test_ai_processor.py tests/test_database.py -v
```

