"""LLM Enrichment Pipeline — Sentiment, Entities, Summary, and Embeddings.

Supports multiple LLM backends:
  - ollama  (local, default)
  - gemini  (Google AI API)
  - openai  (OpenAI API)

Embeddings are generated via sentence-transformers (multilingual MiniLM).
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime
from typing import Any

import httpx

from .models import EnrichedItem, ListingItem

logger = logging.getLogger("omniscraper.ai")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

LLM_PROVIDER = os.getenv("AURA_LLM_PROVIDER", "ollama")
OLLAMA_URL = os.getenv("AURA_OLLAMA_URL", "http://localhost:11434")
LLM_MODEL = os.getenv("AURA_LLM_MODEL", "llama3")
GEMINI_API_KEY = os.getenv("AURA_GEMINI_API_KEY", "")
OPENAI_API_KEY = os.getenv("AURA_OPENAI_API_KEY", "")
EMBEDDING_MODEL = os.getenv(
    "AURA_EMBEDDING_MODEL",
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
)

# Shared HTTP client (re-used across calls)
_http_client: httpx.Client | None = None


def _get_http_client() -> httpx.Client:
    global _http_client
    if _http_client is None:
        _http_client = httpx.Client(timeout=120.0)
    return _http_client


# ---------------------------------------------------------------------------
# Embedding model (lazy-loaded singleton)
# ---------------------------------------------------------------------------

_embedding_model = None


def _get_embedding_model():
    """Lazy-load the sentence-transformers model."""
    global _embedding_model
    if _embedding_model is None:
        from sentence_transformers import SentenceTransformer

        logger.info("Loading embedding model: %s", EMBEDDING_MODEL)
        _embedding_model = SentenceTransformer(EMBEDDING_MODEL)
        logger.info("Embedding model loaded (dim=%d)", _embedding_model.get_sentence_embedding_dimension())
    return _embedding_model


def generate_embedding(text: str) -> list[float]:
    """Generate a dense vector embedding for the given text.

    Returns a list of floats (384-dim for multilingual-MiniLM).
    """
    model = _get_embedding_model()
    embedding = model.encode(text, convert_to_numpy=True)
    return embedding.tolist()


def generate_embeddings_batch(texts: list[str]) -> list[list[float]]:
    """Generate embeddings for a batch of texts (more efficient)."""
    model = _get_embedding_model()
    embeddings = model.encode(texts, convert_to_numpy=True, batch_size=32)
    return [e.tolist() for e in embeddings]


# ---------------------------------------------------------------------------
# LLM Enrichment Prompt
# ---------------------------------------------------------------------------

_ENRICHMENT_PROMPT = """Analyze the following listing text and extract structured information.
Respond ONLY with a valid JSON object, no other text.

Listing text:
{text}

Required JSON format:
{{
  "sentiment": "positive" | "neutral" | "negative",
  "entities": ["entity1", "entity2"],
  "summary": "A concise 1-2 sentence summary of this listing."
}}

Rules:
- sentiment: Classify the overall tone. Consider pricing language, condition descriptions, and emotional cues.
- entities: Extract brand names, product names, locations, and other notable entities. Empty list if none found.
- summary: Summarize what the listing is about in 1-2 short sentences.
- If the text is in Arabic or French, still respond in English."""


def _build_enrichment_text(item: ListingItem) -> str:
    """Concatenate all text fields from a listing into a single string."""
    parts: list[str] = []
    for key, value in item.data.items():
        if value is not None and isinstance(value, str) and value.strip():
            parts.append(f"{key}: {value.strip()}")
    if item.source_url:
        parts.append(f"source: {item.source_url}")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# LLM backends
# ---------------------------------------------------------------------------

def _call_ollama(prompt: str) -> str:
    """Call a local Ollama instance."""
    client = _get_http_client()
    response = client.post(
        f"{OLLAMA_URL}/api/generate",
        json={
            "model": LLM_MODEL,
            "prompt": prompt,
            "stream": False,
            "format": "json",
        },
    )
    response.raise_for_status()
    return response.json().get("response", "")


def _call_gemini(prompt: str) -> str:
    """Call the Google Gemini API."""
    client = _get_http_client()
    response = client.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}",
        json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json"},
        },
    )
    response.raise_for_status()
    data = response.json()
    return data["candidates"][0]["content"]["parts"][0]["text"]


def _call_openai(prompt: str) -> str:
    """Call the OpenAI API."""
    client = _get_http_client()
    response = client.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
        json={
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {"type": "json_object"},
            "temperature": 0.3,
        },
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


_LLM_BACKENDS = {
    "ollama": _call_ollama,
    "gemini": _call_gemini,
    "openai": _call_openai,
}


def _call_llm(prompt: str) -> str:
    """Route the prompt to the configured LLM backend."""
    backend = _LLM_BACKENDS.get(LLM_PROVIDER)
    if backend is None:
        raise ValueError(
            f"Unknown LLM provider '{LLM_PROVIDER}'. "
            f"Supported: {list(_LLM_BACKENDS.keys())}"
        )
    return backend(prompt)


def _parse_llm_response(raw: str) -> dict[str, Any]:
    """Parse the LLM's JSON response, handling common formatting issues."""
    # Try direct JSON parse
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Try to extract JSON from markdown code blocks
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # Try to find a JSON object anywhere in the text
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    logger.warning("Could not parse LLM response as JSON: %s", raw[:200])
    return {"sentiment": "neutral", "entities": [], "summary": ""}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def enrich_item(item: ListingItem) -> EnrichedItem:
    """Enrich a single listing with LLM-extracted metadata and embeddings.

    Pipeline: text → LLM (sentiment + entities + summary) → embeddings → EnrichedItem
    """
    text = _build_enrichment_text(item)

    if not text.strip():
        logger.warning("Empty text for item %s — skipping LLM", item.source_url)
        return EnrichedItem(
            original=item,
            sentiment="neutral",
            entities=[],
            summary="",
            embedding=[],
        )

    # Step 1: LLM enrichment
    prompt = _ENRICHMENT_PROMPT.format(text=text)
    try:
        raw_response = _call_llm(prompt)
        parsed = _parse_llm_response(raw_response)
    except Exception as e:
        logger.error("LLM enrichment failed for %s: %s", item.source_url, e)
        parsed = {"sentiment": "neutral", "entities": [], "summary": ""}

    sentiment = parsed.get("sentiment", "neutral")
    if sentiment not in ("positive", "neutral", "negative"):
        sentiment = "neutral"

    entities = parsed.get("entities", [])
    if not isinstance(entities, list):
        entities = []
    entities = [str(e) for e in entities]

    summary = str(parsed.get("summary", ""))

    # Step 2: Generate embedding
    try:
        embedding = generate_embedding(text)
    except Exception as e:
        logger.error("Embedding generation failed: %s", e)
        embedding = []

    return EnrichedItem(
        original=item,
        sentiment=sentiment,
        entities=entities,
        summary=summary,
        embedding=embedding,
    )


def enrich_batch(items: list[ListingItem]) -> list[EnrichedItem]:
    """Enrich a batch of listings.

    Processes LLM calls sequentially (rate-limited) but batches embeddings.
    """
    if not items:
        return []

    logger.info("Enriching %d items with LLM (%s)...", len(items), LLM_PROVIDER)

    # Step 1: LLM enrichment (sequential)
    parsed_results: list[dict[str, Any]] = []
    texts: list[str] = []

    for item in items:
        text = _build_enrichment_text(item)
        texts.append(text)

        if not text.strip():
            parsed_results.append({"sentiment": "neutral", "entities": [], "summary": ""})
            continue

        prompt = _ENRICHMENT_PROMPT.format(text=text)
        try:
            raw = _call_llm(prompt)
            parsed_results.append(_parse_llm_response(raw))
        except Exception as e:
            logger.error("LLM failed for item: %s", e)
            parsed_results.append({"sentiment": "neutral", "entities": [], "summary": ""})

    # Step 2: Batch embeddings
    non_empty_texts = [t for t in texts if t.strip()]
    try:
        if non_empty_texts:
            embeddings_map = {}
            all_embeddings = generate_embeddings_batch(non_empty_texts)
            idx = 0
            for i, text in enumerate(texts):
                if text.strip():
                    embeddings_map[i] = all_embeddings[idx]
                    idx += 1
                else:
                    embeddings_map[i] = []
        else:
            embeddings_map = {i: [] for i in range(len(items))}
    except Exception as e:
        logger.error("Batch embedding failed: %s", e)
        embeddings_map = {i: [] for i in range(len(items))}

    # Step 3: Assemble EnrichedItems
    enriched: list[EnrichedItem] = []
    for i, item in enumerate(items):
        parsed = parsed_results[i]
        sentiment = parsed.get("sentiment", "neutral")
        if sentiment not in ("positive", "neutral", "negative"):
            sentiment = "neutral"

        entities = parsed.get("entities", [])
        if not isinstance(entities, list):
            entities = []

        enriched.append(
            EnrichedItem(
                original=item,
                sentiment=sentiment,
                entities=[str(e) for e in entities],
                summary=str(parsed.get("summary", "")),
                embedding=embeddings_map.get(i, []),
            )
        )

    logger.info("Enrichment complete: %d items processed", len(enriched))
    return enriched
