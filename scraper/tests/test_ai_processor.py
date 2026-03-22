"""Tests for the AI enrichment pipeline (ai_processor.py).

All LLM calls are mocked — no real API requests are made.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from omniscraper.models import ListingItem, EnrichedItem
from omniscraper.ai_processor import (
    _build_enrichment_text,
    _parse_llm_response,
    enrich_item,
    enrich_batch,
    generate_embedding,
    generate_embeddings_batch,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_item_en():
    return ListingItem(
        source_url="https://example.com/listing/1",
        data={
            "title": "Brand new iPhone 15 Pro Max — Great condition!",
            "price": "12000",
            "location": "Casablanca",
        },
    )


@pytest.fixture
def sample_item_fr():
    return ListingItem(
        source_url="https://example.com/listing/2",
        data={
            "title": "Appartement 3 chambres à Rabat, très bon état",
            "price": "850000",
            "location": "Rabat",
        },
    )


@pytest.fixture
def sample_item_ar():
    return ListingItem(
        source_url="https://example.com/listing/3",
        data={
            "title": "شقة للبيع في الدار البيضاء، 3 غرف",
            "price": "750000",
            "location": "الدار البيضاء",
        },
    )


# ---------------------------------------------------------------------------
# Unit tests: text building
# ---------------------------------------------------------------------------

class TestBuildEnrichmentText:
    def test_concatenates_fields(self, sample_item_en):
        text = _build_enrichment_text(sample_item_en)
        assert "iPhone 15 Pro Max" in text
        assert "12000" in text
        assert "Casablanca" in text
        assert "source:" in text

    def test_empty_item(self):
        item = ListingItem(source_url="", data={})
        text = _build_enrichment_text(item)
        assert text == ""

    def test_skips_none_values(self):
        item = ListingItem(
            source_url="https://example.com",
            data={"title": "Test", "image": None, "desc": ""},
        )
        text = _build_enrichment_text(item)
        assert "title: Test" in text
        assert "image" not in text
        assert "desc" not in text


# ---------------------------------------------------------------------------
# Unit tests: JSON parsing
# ---------------------------------------------------------------------------

class TestParseLLMResponse:
    def test_valid_json(self):
        raw = '{"sentiment": "positive", "entities": ["iPhone"], "summary": "A phone listing"}'
        result = _parse_llm_response(raw)
        assert result["sentiment"] == "positive"
        assert "iPhone" in result["entities"]

    def test_json_in_code_block(self):
        raw = '```json\n{"sentiment": "negative", "entities": [], "summary": "Bad"}\n```'
        result = _parse_llm_response(raw)
        assert result["sentiment"] == "negative"

    def test_json_embedded_in_text(self):
        raw = 'Here is the result: {"sentiment": "neutral", "entities": ["Samsung"], "summary": "A listing"} end.'
        result = _parse_llm_response(raw)
        assert result["entities"] == ["Samsung"]

    def test_unparseable_returns_defaults(self):
        raw = "I cannot process this request."
        result = _parse_llm_response(raw)
        assert result["sentiment"] == "neutral"
        assert result["entities"] == []


# ---------------------------------------------------------------------------
# Unit tests: enrichment with mocked LLM
# ---------------------------------------------------------------------------

class TestEnrichItem:
    @patch("omniscraper.ai_processor._call_llm")
    @patch("omniscraper.ai_processor.generate_embedding")
    def test_enrich_basic(self, mock_embed, mock_llm, sample_item_en):
        mock_llm.return_value = '{"sentiment": "positive", "entities": ["iPhone", "Apple"], "summary": "iPhone listing"}'
        mock_embed.return_value = [0.1] * 384

        result = enrich_item(sample_item_en)

        assert isinstance(result, EnrichedItem)
        assert result.sentiment == "positive"
        assert "iPhone" in result.entities
        assert len(result.embedding) == 384
        assert result.original == sample_item_en

    @patch("omniscraper.ai_processor._call_llm")
    @patch("omniscraper.ai_processor.generate_embedding")
    def test_enrich_llm_failure_graceful(self, mock_embed, mock_llm, sample_item_en):
        mock_llm.side_effect = Exception("API error")
        mock_embed.return_value = [0.0] * 384

        result = enrich_item(sample_item_en)

        assert result.sentiment == "neutral"
        assert result.entities == []
        assert result.summary == ""

    @patch("omniscraper.ai_processor._call_llm")
    @patch("omniscraper.ai_processor.generate_embedding")
    def test_enrich_invalid_sentiment_normalized(self, mock_embed, mock_llm, sample_item_en):
        mock_llm.return_value = '{"sentiment": "very happy", "entities": [], "summary": ""}'
        mock_embed.return_value = [0.5] * 384

        result = enrich_item(sample_item_en)
        assert result.sentiment == "neutral"  # Invalid → neutral

    def test_enrich_empty_item(self):
        item = ListingItem(source_url="", data={})
        result = enrich_item(item)
        assert result.sentiment == "neutral"
        assert result.embedding == []


class TestEnrichBatch:
    @patch("omniscraper.ai_processor._call_llm")
    @patch("omniscraper.ai_processor.generate_embeddings_batch")
    def test_batch_enrichment(self, mock_batch_embed, mock_llm, sample_item_en, sample_item_fr):
        mock_llm.return_value = '{"sentiment": "positive", "entities": [], "summary": "test"}'
        mock_batch_embed.return_value = [[0.1] * 384, [0.2] * 384]

        results = enrich_batch([sample_item_en, sample_item_fr])

        assert len(results) == 2
        assert all(isinstance(r, EnrichedItem) for r in results)
        assert mock_llm.call_count == 2

    def test_empty_batch(self):
        results = enrich_batch([])
        assert results == []


# ---------------------------------------------------------------------------
# Unit tests: to_es_doc
# ---------------------------------------------------------------------------

class TestEnrichedItemEsDoc:
    def test_es_doc_structure(self, sample_item_en):
        enriched = EnrichedItem(
            original=sample_item_en,
            sentiment="positive",
            entities=["iPhone"],
            summary="Phone listing",
            embedding=[0.1] * 384,
        )
        doc = enriched.to_es_doc()

        assert doc["sentiment"] == "positive"
        assert doc["entities"] == ["iPhone"]
        assert doc["summary"] == "Phone listing"
        assert len(doc["embedding"]) == 384
        assert doc["source_url"] == "https://example.com/listing/1"
        assert "title" in doc  # From original.data
