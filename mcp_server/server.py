#!/usr/bin/env python3
"""
MCP Server — expose scraped data as MCP tools.
Uses the hexagonal architecture's SearchUseCase for data access.

Run: python -m mcp_server.server
"""

import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from dataclasses import asdict

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.use_cases import SearchUseCase
from adapters.outbound.storage_adapter import StorageAdapter

logger = logging.getLogger(__name__)


# --- Build dependencies (composition root) ---

def _build_search() -> SearchUseCase:
    """Wire up SearchUseCase with storage adapter."""
    storage = StorageAdapter()
    return SearchUseCase(storage=storage)


# --- MCP Tool Handlers ---

def search_jobs(keyword: str = "", location: str = "", limit: int = 20) -> List[Dict]:
    """
    Search job listings scraped from Jobsdb, Indeed, Upwork.

    Args:
        keyword: Job title or skill (e.g., "Python developer", "AI engineer")
        location: Location filter (e.g., "Bangkok", "Remote")
        limit: Max results to return

    Returns:
        List of job listings with title, company, salary, URL
    """
    search = _build_search()
    items = search.search_jobs(keyword=keyword, location=location, limit=limit)
    return [asdict(item) if hasattr(item, "__dataclass_fields__") else dict(item) for item in items]


def search_businesses(category: str = "", area: str = "", limit: int = 20) -> List[Dict]:
    """
    Search business listings from Thai directories and Wongnai.

    Args:
        category: Business category (e.g., "ร้านอาหาร", "สปา", "คลินิก")
        area: Area filter (e.g., "กรุงเทพฯ", "เชียงใหม่")
        limit: Max results

    Returns:
        List of business listings with name, address, rating, phone
    """
    search = _build_search()
    items = search.search_businesses(category=category, area=area, limit=limit)
    return [asdict(item) if hasattr(item, "__dataclass_fields__") else dict(item) for item in items]


def get_product_prices(keyword: str = "", max_price: float = None, limit: int = 20) -> List[Dict]:
    """
    Search product prices from Shopee, Lazada.

    Args:
        keyword: Product name or category
        max_price: Maximum price filter (THB)
        limit: Max results

    Returns:
        List of products with name, price, seller, rating
    """
    search = _build_search()
    items = search.search_products(keyword=keyword, max_price=max_price, limit=limit)
    return [asdict(item) if hasattr(item, "__dataclass_fields__") else dict(item) for item in items]


def get_news(topic: str = "", limit: int = 20) -> List[Dict]:
    """
    Get latest news articles by topic.

    Args:
        topic: News topic or keyword
        limit: Max results

    Returns:
        List of articles with title, URL, summary, date
    """
    search = _build_search()
    items = search.search_jobs(keyword=topic, limit=limit)  # reuse search; extend later
    return [asdict(item) if hasattr(item, "__dataclass_fields__") else dict(item) for item in items]


# --- MCP Tool Registry ---

TOOLS = {
    "search_jobs": {
        "description": "Search job listings from Thai job boards (Jobsdb, Indeed, Upwork)",
        "parameters": {
            "keyword": {"type": "string", "description": "Job title or skill"},
            "location": {"type": "string", "description": "Location filter"},
            "limit": {"type": "integer", "description": "Max results", "default": 20},
        },
        "handler": search_jobs,
    },
    "search_businesses": {
        "description": "Search Thai business listings (Wongnai, Yellow Pages)",
        "parameters": {
            "category": {"type": "string", "description": "Business category"},
            "area": {"type": "string", "description": "Area filter"},
            "limit": {"type": "integer", "description": "Max results", "default": 20},
        },
        "handler": search_businesses,
    },
    "get_product_prices": {
        "description": "Compare product prices from Shopee, Lazada",
        "parameters": {
            "keyword": {"type": "string", "description": "Product name"},
            "max_price": {"type": "number", "description": "Max price (THB)"},
            "limit": {"type": "integer", "description": "Max results", "default": 20},
        },
        "handler": get_product_prices,
    },
    "get_news": {
        "description": "Get latest news articles by topic",
        "parameters": {
            "topic": {"type": "string", "description": "News topic"},
            "limit": {"type": "integer", "description": "Max results", "default": 20},
        },
        "handler": get_news,
    },
}


def handle_tool_call(tool_name: str, arguments: Dict) -> Any:
    """Route MCP tool call to handler."""
    if tool_name not in TOOLS:
        return {"error": f"Unknown tool: {tool_name}"}
    handler = TOOLS[tool_name]["handler"]
    return handler(**arguments)


def list_tools() -> List[Dict]:
    """List all available MCP tools."""
    return [
        {"name": name, "description": info["description"], "parameters": info["parameters"]}
        for name, info in TOOLS.items()
    ]


# --- Server Entry Point ---

def main():
    """
    Run as standalone MCP server.
    For production, integrate with MCP SDK:
        pip install mcp
        from mcp.server import Server
    """
    print("Book Scraping MCP Server")
    print("=" * 40)
    print("\nAvailable tools:")
    for tool in list_tools():
        print(f"  - {tool['name']}: {tool['description']}")
    print("\nRun scrapers first to populate data/")
    print("Then call tools via MCP protocol.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
