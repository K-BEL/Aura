import { useState, useCallback } from 'react';

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

/**
 * React hook for Aura market intelligence features.
 * Connects the chat frontend to the OmniScraper + Elasticsearch backend.
 */
export function useMarketSearch() {
  const [searchResults, setSearchResults] = useState([]);
  const [isSearching, setIsSearching] = useState(false);
  const [searchError, setSearchError] = useState(null);

  const [scrapeStatus, setScrapeStatus] = useState(null);
  const [isScraping, setIsScraping] = useState(false);
  const [scrapeError, setScrapeError] = useState(null);

  /**
   * Perform hybrid search over enriched market data.
   */
  const search = useCallback(async (query, options = {}) => {
    setIsSearching(true);
    setSearchError(null);

    try {
      const response = await fetch(`${API_URL}/api/search`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query,
          k: options.k || 10,
          sentiment: options.sentiment || null,
          entity: options.entity || null,
          date_from: options.dateFrom || null,
          date_to: options.dateTo || null,
        }),
      });

      if (!response.ok) {
        const err = await response.json();
        throw new Error(err.detail || `Search failed: ${response.status}`);
      }

      const data = await response.json();
      setSearchResults(data.results || []);
      return data;
    } catch (err) {
      setSearchError(err.message);
      setSearchResults([]);
      return null;
    } finally {
      setIsSearching(false);
    }
  }, []);

  /**
   * Trigger a scrape job with optional AI enrichment.
   */
  const triggerScrape = useCallback(async (configName, options = {}) => {
    setIsScraping(true);
    setScrapeError(null);
    setScrapeStatus(null);

    try {
      const response = await fetch(`${API_URL}/api/scrape`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          config_name: configName,
          url: options.url || null,
          max_pages: options.maxPages || 3,
          ai_enrich: options.aiEnrich !== false,
          index: options.index !== false,
        }),
      });

      if (!response.ok) {
        const err = await response.json();
        throw new Error(err.detail || `Scrape failed: ${response.status}`);
      }

      const data = await response.json();
      setScrapeStatus(data);
      return data;
    } catch (err) {
      setScrapeError(err.message);
      return null;
    } finally {
      setIsScraping(false);
    }
  }, []);

  /**
   * Get available site configurations.
   */
  const getConfigs = useCallback(async () => {
    try {
      const response = await fetch(`${API_URL}/api/configs`);
      if (!response.ok) throw new Error('Failed to fetch configs');
      return await response.json();
    } catch (err) {
      console.error('Failed to fetch configs:', err);
      return { configs: [] };
    }
  }, []);

  /**
   * Check API health status.
   */
  const checkHealth = useCallback(async () => {
    try {
      const response = await fetch(`${API_URL}/api/health`);
      if (!response.ok) throw new Error('API unavailable');
      return await response.json();
    } catch (err) {
      return { status: 'error', error: err.message };
    }
  }, []);

  return {
    // Search
    search,
    searchResults,
    isSearching,
    searchError,

    // Scrape
    triggerScrape,
    scrapeStatus,
    isScraping,
    scrapeError,

    // Utilities
    getConfigs,
    checkHealth,
  };
}
