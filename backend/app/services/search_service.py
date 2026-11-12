"""Web search service supporting Tavily, Serper, and DuckDuckGo fallback."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List
from urllib.parse import quote_plus

import httpx
from bs4 import BeautifulSoup

from app.config import get_settings


@dataclass
class SearchResultItem:
    title: str
    url: str
    snippet: str
    source: str


class WebSearchUnavailableError(Exception):
    """Raised when no web search provider succeeds or is configured."""


async def search_web_results(query: str, max_results: int = 5) -> List[SearchResultItem]:
    """Query configured search provider (Tavily -> Serper -> DuckDuckGo HTML fallback)."""
    cleaned = query.strip()
    if not cleaned:
        return []

    settings = get_settings()

    if settings.tavily_api_key:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": settings.tavily_api_key,
                    "query": cleaned,
                    "max_results": max_results,
                    "include_answer": False,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return [
                SearchResultItem(
                    title=item.get("title", "Source"),
                    url=item.get("url", ""),
                    snippet=item.get("content", ""),
                    source="tavily",
                )
                for item in data.get("results", [])[:max_results]
            ]

    if settings.serper_api_key:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                "https://google.serper.dev/search",
                headers={"X-API-KEY": settings.serper_api_key, "Content-Type": "application/json"},
                json={"q": cleaned, "num": max_results},
            )
            resp.raise_for_status()
            data = resp.json()
            return [
                SearchResultItem(
                    title=item.get("title", "Source"),
                    url=item.get("link", ""),
                    snippet=item.get("snippet", ""),
                    source="serper",
                )
                for item in data.get("organic", [])[:max_results]
            ]

    if not settings.enable_public_web_search_fallback:
        raise WebSearchUnavailableError(
            "Web search is not configured. Set TAVILY_API_KEY or SERPER_API_KEY in backend/.env."
        )

    # Lightweight public DuckDuckGo HTML fallback
    try:
        async with httpx.AsyncClient(
            timeout=12.0,
            headers={"User-Agent": "Mozilla/5.0 (compatible; MeridianAI/1.0)"},
            follow_redirects=True,
        ) as client:
            resp = await client.get(f"https://html.duckduckgo.com/html/?q={quote_plus(cleaned)}")
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            results: List[SearchResultItem] = []
            for block in soup.select(".result")[:max_results]:
                link_el = block.select_one(".result__a")
                snippet_el = block.select_one(".result__snippet")
                if not link_el:
                    continue
                href = link_el.get("href", "")
                if href.startswith("//"):
                    href = "https:" + href
                results.append(
                    SearchResultItem(
                        title=link_el.get_text(" ", strip=True),
                        url=href,
                        snippet=snippet_el.get_text(" ", strip=True) if snippet_el else "",
                        source="duckduckgo",
                    )
                )
            return results
    except Exception as exc:
        raise WebSearchUnavailableError(
            f"Web search request failed ({exc}). Configure TAVILY_API_KEY or SERPER_API_KEY for reliable search."
        ) from exc


def format_search_context(results: List[SearchResultItem]) -> str:
    if not results:
        return ""
    lines = [
        "Live web search results (explicitly distinguish these searched facts from general knowledge using [1], [2], ... citations):"
    ]
    for idx, item in enumerate(results, start=1):
        lines.append(f"[{idx}] {item.title}\nURL: {item.url}\nSnippet: {item.snippet}")
    return "\n\n".join(lines)

