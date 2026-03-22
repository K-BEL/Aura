"""Tests for the Elasticsearch database module (database.py).

All Elasticsearch calls are mocked — no real ES cluster is needed.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch, call

import pytest

from omniscraper.models import ListingItem, EnrichedItem
from omniscraper.database import (
    INDEX_MAPPING,
    _enriched_to_doc,
    create_index,
    bulk_index,
    hybrid_search,
    get_index_stats,
    VECTOR_DIMS,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def enriched_item():
    item = ListingItem(
        source_url="https://example.com/listing/1",
        data={
            "title": "iPhone 15 Pro Max",
            "price": "12000",
            "location": "Casablanca",
        },
    )
    return EnrichedItem(
        original=item,
        sentiment="positive",
        entities=["iPhone", "Apple"],
        summary="Brand new iPhone listing in Casablanca",
        embedding=[0.1] * VECTOR_DIMS,
    )


@pytest.fixture
def mock_es():
    """Create a mock Elasticsearch client."""
    with patch("omniscraper.database._get_es_client") as mock_factory:
        mock_client = MagicMock()
        mock_factory.return_value = mock_client
        yield mock_client


# ---------------------------------------------------------------------------
# Unit tests: index mapping
# ---------------------------------------------------------------------------

class TestIndexMapping:
    def test_mapping_has_dense_vector(self):
        props = INDEX_MAPPING["mappings"]["properties"]
        assert "embedding" in props
        assert props["embedding"]["type"] == "dense_vector"
        assert props["embedding"]["dims"] == VECTOR_DIMS

    def test_mapping_has_keyword_fields(self):
        props = INDEX_MAPPING["mappings"]["properties"]
        assert props["sentiment"]["type"] == "keyword"
        assert props["entities"]["type"] == "keyword"

    def test_mapping_has_text_fields(self):
        props = INDEX_MAPPING["mappings"]["properties"]
        assert props["summary"]["type"] == "text"
        assert props["raw_text"]["type"] == "text"


# ---------------------------------------------------------------------------
# Unit tests: document conversion
# ---------------------------------------------------------------------------

class TestEnrichedToDoc:
    def test_converts_to_doc(self, enriched_item):
        doc = _enriched_to_doc(enriched_item, site_name="test_site")

        assert doc["sentiment"] == "positive"
        assert doc["entities"] == ["iPhone", "Apple"]
        assert doc["summary"] == "Brand new iPhone listing in Casablanca"
        assert len(doc["embedding"]) == VECTOR_DIMS
        assert doc["site_name"] == "test_site"
        assert "raw_text" in doc
        assert "iPhone 15 Pro Max" in doc["raw_text"]


# ---------------------------------------------------------------------------
# Unit tests: create_index
# ---------------------------------------------------------------------------

class TestCreateIndex:
    def test_creates_index_when_not_exists(self, mock_es):
        mock_es.indices.exists.return_value = False

        create_index("test-index")

        mock_es.indices.create.assert_called_once()
        args = mock_es.indices.create.call_args
        assert args[1]["index"] == "test-index"

    def test_skips_when_exists(self, mock_es):
        mock_es.indices.exists.return_value = True

        create_index("test-index")

        mock_es.indices.create.assert_not_called()


# ---------------------------------------------------------------------------
# Unit tests: bulk_index
# ---------------------------------------------------------------------------

class TestBulkIndex:
    @patch("elasticsearch.helpers.bulk")
    def test_bulk_indexes_items(self, mock_bulk, mock_es, enriched_item):
        mock_es.indices.exists.return_value = True
        mock_bulk.return_value = (1, [])

        count = bulk_index([enriched_item], index_name="test-index", site_name="my_site")

        assert count == 1
        mock_bulk.assert_called_once()
        # Check that the action has the right index
        actions = mock_bulk.call_args[0][1]
        assert actions[0]["_index"] == "test-index"

    @patch("elasticsearch.helpers.bulk")
    def test_bulk_empty_list(self, mock_bulk, mock_es):
        count = bulk_index([], index_name="test-index")
        assert count == 0
        mock_bulk.assert_not_called()


# ---------------------------------------------------------------------------
# Unit tests: hybrid_search
# ---------------------------------------------------------------------------

class TestHybridSearch:
    @patch("omniscraper.ai_processor.generate_embedding")
    def test_search_returns_results(self, mock_embed, mock_es):
        mock_embed.return_value = [0.1] * VECTOR_DIMS
        mock_es.search.return_value = {
            "hits": {
                "hits": [
                    {
                        "_id": "doc1",
                        "_score": 0.95,
                        "_source": {
                            "title": "iPhone 15",
                            "sentiment": "positive",
                            "entities": ["iPhone"],
                            "summary": "A phone",
                        },
                    }
                ]
            }
        }

        results = hybrid_search("iPhone", index_name="test-index")

        assert len(results) == 1
        assert results[0]["_score"] == 0.95
        assert results[0]["title"] == "iPhone 15"

    @patch("omniscraper.ai_processor.generate_embedding")
    def test_search_with_filters(self, mock_embed, mock_es):
        mock_embed.return_value = [0.1] * VECTOR_DIMS
        mock_es.search.return_value = {"hits": {"hits": []}}

        results = hybrid_search(
            "test",
            index_name="test-index",
            sentiment_filter="positive",
            entity_filter="Apple",
        )

        assert results == []
        # Verify search was called with filters
        search_body = mock_es.search.call_args[1]["body"]
        query_filters = search_body["query"]["bool"]["filter"]
        assert any(f.get("term", {}).get("sentiment") == "positive" for f in query_filters)

    @patch("omniscraper.ai_processor.generate_embedding")
    def test_search_error_returns_empty(self, mock_embed, mock_es):
        mock_embed.return_value = [0.1] * VECTOR_DIMS
        mock_es.search.side_effect = Exception("Connection refused")

        results = hybrid_search("test", index_name="test-index")
        assert results == []


# ---------------------------------------------------------------------------
# Unit tests: get_index_stats
# ---------------------------------------------------------------------------

class TestGetIndexStats:
    def test_returns_stats(self, mock_es):
        mock_es.count.return_value = {"count": 42}
        mock_es.indices.stats.return_value = {
            "_all": {"primaries": {"store": {"size_in_bytes": 1024}}}
        }

        stats = get_index_stats("test-index")

        assert stats["doc_count"] == 42
        assert stats["size_bytes"] == 1024

    def test_returns_error_on_failure(self, mock_es):
        mock_es.count.side_effect = Exception("Not found")

        stats = get_index_stats("nonexistent")
        assert "error" in stats
