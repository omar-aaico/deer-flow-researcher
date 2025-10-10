# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

from langchain_core.tools import tool
from typing import List, Dict, Any
import os
import httpx
import logging

logger = logging.getLogger(__name__)


@tool
def firecrawl_search(query: str, max_results: int = 3) -> List[Dict[str, Any]]:
    """
    Search using Firecrawl API for deep content extraction.

    Args:
        query: Search query string
        max_results: Maximum number of results to return

    Returns:
        List of search results with extracted content
    """
    api_key = os.getenv("FIRECRAWL_API_KEY")
    if not api_key:
        logger.error("FIRECRAWL_API_KEY not set in environment")
        raise ValueError("FIRECRAWL_API_KEY not set")

    try:
        logger.info(f"Firecrawl search: {query[:100]} (max_results={max_results})")

        response = httpx.post(
            "https://api.firecrawl.dev/v1/search",
            json={
                "query": query,
                "limit": max_results,
                "scrapeOptions": {
                    "formats": ["markdown", "html"],
                    "onlyMainContent": True
                }
            },
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30.0
        )
        response.raise_for_status()

        data = response.json()
        results = data.get("data", [])

        logger.info(f"Firecrawl search completed: {len(results)} results returned")

        # Transform to consistent format similar to other search tools
        formatted_results = []
        for result in results:
            formatted_results.append({
                "title": result.get("title", ""),
                "url": result.get("url", ""),
                "content": result.get("markdown", result.get("content", "")),
                "snippet": result.get("description", "")[:500],  # First 500 chars
            })

        return formatted_results

    except httpx.HTTPStatusError as e:
        logger.error(f"Firecrawl API error: {e.response.status_code} - {e.response.text}")
        return []
    except httpx.TimeoutException:
        logger.error("Firecrawl API timeout")
        return []
    except Exception as e:
        logger.error(f"Firecrawl search failed: {e}")
        return []
