"""Elasticsearch Hybrid Search — Dense Vector + BM25 keyword search.

Provides:
  - Index management with dense_vector mapping
  - Bulk indexing of EnrichedItems
  - Hybrid search combining kNN semantic similarity with BM25 text match
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

from .models import EnrichedItem

logger = logging.getLogger("omniscraper.database")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

ES_URL = os.getenv("AURA_ES_URL", "http://localhost:9200")
ES_INDEX = os.getenv("AURA_ES_INDEX", "aura-market-data")
VECTOR_DIMS = 384  # multilingual-MiniLM-L12-v2 output dimension


def _get_es_client():
    """Create and return an Elasticsearch client."""
    from elasticsearch import Elasticsearch

    return Elasticsearch(ES_URL)


# ---------------------------------------------------------------------------
# Index Management
# ---------------------------------------------------------------------------

INDEX_MAPPING = {
    "settings": {
        "number_of_shards": 1,
        "number_of_replicas": 0,
        "analysis": {
            "analyzer": {
                "multilingual": {
                    "type": "standard",
                    "stopwords": "_none_",
                }
            }
        },
    },
    "mappings": {
        "properties": {
            # Dense vector for semantic search
            "embedding": {
                "type": "dense_vector",
                "dims": VECTOR_DIMS,
                "index": True,
                "similarity": "cosine",
            },
            # Structured fields
            "sentiment": {"type": "keyword"},
            "entities": {"type": "keyword"},
            "source_url": {"type": "keyword"},
            "site_name": {"type": "keyword"},
            # Text fields for BM25
            "summary": {
                "type": "text",
                "analyzer": "multilingual",
            },
            "title": {
                "type": "text",
                "analyzer": "multilingual",
                "fields": {"keyword": {"type": "keyword"}},
            },
            "description": {
                "type": "text",
                "analyzer": "multilingual",
            },
            # Catch-all for dynamic listing fields
            "raw_text": {
                "type": "text",
                "analyzer": "multilingual",
            },
            # Timestamps
            "scraped_at": {"type": "date"},
            "enriched_at": {"type": "date"},
        }
    },
}


def create_index(index_name: str | None = None) -> None:
    """Create the Elasticsearch index with the hybrid search mapping.

    Skips creation if the index already exists.
    """
    index_name = index_name or ES_INDEX
    es = _get_es_client()

    if es.indices.exists(index=index_name):
        logger.info("Index '%s' already exists — skipping creation", index_name)
        return

    es.indices.create(
        index=index_name,
        settings=INDEX_MAPPING["settings"],
        mappings=INDEX_MAPPING["mappings"],
    )
    logger.info("Created index '%s' with hybrid search mapping", index_name)


def delete_index(index_name: str | None = None) -> None:
    """Delete an Elasticsearch index."""
    index_name = index_name or ES_INDEX
    es = _get_es_client()

    if es.indices.exists(index=index_name):
        es.indices.delete(index=index_name)
        logger.info("Deleted index '%s'", index_name)
    else:
        logger.info("Index '%s' does not exist — nothing to delete", index_name)


# ---------------------------------------------------------------------------
# Indexing
# ---------------------------------------------------------------------------

def _enriched_to_doc(item: EnrichedItem, site_name: str = "") -> dict[str, Any]:
    """Convert an EnrichedItem to an Elasticsearch document."""
    doc = item.to_es_doc()
    doc["site_name"] = site_name

    # Build a raw_text field from all string data for full-text search
    text_parts = []
    for key, value in item.original.data.items():
        if isinstance(value, str) and value.strip():
            text_parts.append(value.strip())
    doc["raw_text"] = " ".join(text_parts)

    return doc


def bulk_index(
    items: list[EnrichedItem],
    index_name: str | None = None,
    site_name: str = "",
) -> int:
    """Bulk index enriched items into Elasticsearch.

    Returns the number of successfully indexed documents.
    """
    from elasticsearch.helpers import bulk

    index_name = index_name or ES_INDEX
    es = _get_es_client()

    # Ensure index exists
    create_index(index_name)

    actions = []
    for item in items:
        doc = _enriched_to_doc(item, site_name)
        actions.append({
            "_index": index_name,
            "_source": doc,
        })

    if not actions:
        logger.warning("No documents to index")
        return 0

    success, errors = bulk(es, actions, raise_on_error=False)
    if errors:
        logger.warning("Bulk index had %d error(s)", len(errors))
        for err in errors[:5]:  # Log first 5 errors
            logger.warning("  → %s", err)

    logger.info("Indexed %d/%d documents into '%s'", success, len(actions), index_name)
    return success


# ---------------------------------------------------------------------------
# Hybrid Search
# ---------------------------------------------------------------------------

def hybrid_search(
    query: str,
    index_name: str | None = None,
    k: int = 10,
    *,
    sentiment_filter: str | None = None,
    entity_filter: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    embedding: list[float] | None = None,
) -> list[dict[str, Any]]:
    """Perform hybrid search combining kNN vector similarity with BM25 text match.

    Args:
        query: Search query text.
        index_name: Elasticsearch index name.
        k: Number of results to return.
        sentiment_filter: Filter by sentiment (positive/neutral/negative).
        entity_filter: Filter by entity keyword.
        date_from: Filter by min scraped_at date (ISO format).
        date_to: Filter by max scraped_at date (ISO format).
        embedding: Pre-computed query embedding. If None, generates one.

    Returns:
        List of matching documents with scores.
    """
    index_name = index_name or ES_INDEX
    es = _get_es_client()

    # Generate query embedding if not provided
    if embedding is None:
        from .ai_processor import generate_embedding
        embedding = generate_embedding(query)

    # Build filter clauses
    filters: list[dict[str, Any]] = []
    if sentiment_filter:
        filters.append({"term": {"sentiment": sentiment_filter}})
    if entity_filter:
        filters.append({"term": {"entities": entity_filter}})
    if date_from or date_to:
        date_range: dict[str, str] = {}
        if date_from:
            date_range["gte"] = date_from
        if date_to:
            date_range["lte"] = date_to
        filters.append({"range": {"scraped_at": date_range}})

    filter_clause = {"bool": {"must": filters}} if filters else {"match_all": {}}

    # Hybrid query: kNN + BM25
    body = {
        "size": k,
        "query": {
            "bool": {
                "should": [
                    # BM25 text match (boosted)
                    {
                        "multi_match": {
                            "query": query,
                            "fields": ["raw_text^2", "summary", "title^3"],
                            "type": "best_fields",
                            "boost": 0.3,
                        }
                    },
                ],
                "filter": filters if filters else [],
            }
        },
        "knn": {
            "field": "embedding",
            "query_vector": embedding,
            "k": k,
            "num_candidates": k * 10,
            "filter": filter_clause,
            "boost": 0.7,
        },
    }

    try:
        response = es.search(index=index_name, body=body)
    except Exception as e:
        logger.error("Hybrid search failed: %s", e)
        return []

    results = []
    for hit in response["hits"]["hits"]:
        doc = hit["_source"]
        doc["_score"] = hit["_score"]
        doc["_id"] = hit["_id"]
        results.append(doc)

    logger.info("Hybrid search returned %d result(s) for query: '%s'", len(results), query[:50])
    return results


def get_index_stats(index_name: str | None = None) -> dict[str, Any]:
    """Get basic statistics for the index."""
    index_name = index_name or ES_INDEX
    es = _get_es_client()

    try:
        stats = es.indices.stats(index=index_name)
        count = es.count(index=index_name)
        return {
            "index": index_name,
            "doc_count": count["count"],
            "size_bytes": stats["_all"]["primaries"]["store"]["size_in_bytes"],
        }
    except Exception as e:
        logger.error("Failed to get index stats: %s", e)
        return {"index": index_name, "doc_count": 0, "error": str(e)}
