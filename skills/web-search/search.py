"""Web Search Code."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import sys
from typing import Any, Optional

import requests
from bs4 import BeautifulSoup
from shared import DEFAULT_USER_AGENT, is_unfetchable


DEFAULT_SEARCH_ENGINE = "http://localhost:8888"


@dataclass
class SearchResult: # pylint: disable=too-many-instance-attributes
    """A single search result with metadata and optional fetched content."""

    title: str
    url: str
    snippet: str = ""
    published_date: Optional[str] = None
    engines: list[str] = field(default_factory=list)
    score: float = 0.0
    domain: str = ""
    content: Optional[str] = None


def extract_domain(url: str) -> str:
    """Extract the domain from a URL."""
    match = re.match(r"^https?://([^/]+)", url.strip(), re.IGNORECASE)
    return match.group(1).lower() if match else ""


def _parse_date(value: Optional[str]) -> Optional[datetime]:
    """Parse a date string into a timezone-aware datetime."""
    if not value:
        return None

    value = value.strip()
    for parser in (
        lambda s: datetime.fromisoformat(s.replace("Z", "+00:00")),
        parsedate_to_datetime,
    ):
        try:
            dt = parser(value)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except (ValueError, TypeError):
            pass
    return None


def _rank_result(raw: dict[str, Any]) -> SearchResult:
    title = raw.get("title") or raw.get("url") or "(untitled)"
    url = raw.get("url") or ""
    snippet = raw.get("content") or ""
    published_date = raw.get("publishedDate") or raw.get("pubdate")
    engines = raw.get("engines") or ([raw["engine"]] if raw.get("engine") else [])
    score = float(raw.get("score") or 0.0)

    return SearchResult(
        title=title.strip(),
        url=url.strip(),
        snippet=snippet.strip(),
        published_date=published_date,
        engines=engines,
        score=score,
        domain=extract_domain(url),
    )


def _query_relevance(query: str, item: SearchResult) -> float:
    """Score how well a result matches the query terms (0.0 to 1.0).

    Title matches count 2x, snippet matches count 1x.
    """
    query_terms = re.findall(r"[a-z0-9]+", query.lower())
    if not query_terms:
        return 1.0  # no meaningful terms to match against

    title_tokens = set(re.findall(r"[a-z0-9]+", item.title.lower()))
    snippet_tokens = set(re.findall(r"[a-z0-9]+", item.snippet.lower()))

    max_score = (
        len(query_terms) * 3
    )  # best case: every term in both title (2) + snippet (1)
    actual = 0.0
    for term in query_terms:
        if term in title_tokens:
            actual += 2.0
        if term in snippet_tokens:
            actual += 1.0

    return actual / max_score


def _sort_key(query: str, item: SearchResult) -> tuple[int, float, float]:
    return (
        1 if is_unfetchable(item.url) else 0,
        -_query_relevance(query, item),
        -item.score,
    )


def _parse_searxng_html_results(html_text: str) -> list[SearchResult]:
    """Parse search results from an HTML response.

    This is specific to SearXNG's 'simple' theme HTML structure.
    Other search engines (Whoogle, etc.) would need their own parser.
    """
    soup = BeautifulSoup(html_text, "html.parser")
    results: list[SearchResult] = []

    for article in soup.select("article.result"):
        # Title and URL from <h3><a href="...">title</a></h3>
        h3 = article.find("h3")
        if not h3:
            continue
        link = h3.find("a")
        if not link or not link.get("href"):
            continue

        url = link["href"].strip()
        title = link.get_text(strip=True) or url

        # Snippet from <p class="content">
        snippet_el = article.select_one("p.content")
        snippet = ""
        if snippet_el:
            text = snippet_el.get_text(strip=True)
            # Skip the "no description" placeholder
            if "did not provide any description" not in text:
                snippet = text

        # Published date from <time class="published_date">
        time_el = article.select_one("time.published_date")
        published_date = None
        if time_el and time_el.get("datetime"):
            published_date = time_el["datetime"]

        # Engines from <div class="engines"><span>name</span>...
        engines: list[str] = []
        engines_el = article.select_one("div.engines")
        if engines_el:
            engines = [
                span.get_text(strip=True)
                for span in engines_el.find_all("span")
                if span.get_text(strip=True)
            ]

        results.append(
            SearchResult(
                title=title,
                url=url,
                snippet=snippet,
                published_date=published_date,
                engines=engines,
                score=0.0,
                domain=extract_domain(url),
            )
        )

    return results


def relative_age(value: Optional[str]) -> str: # pylint: disable=too-many-return-statements
    """Convert a date string to a human-readable relative age."""
    dt = _parse_date(value)
    if not dt:
        return "unknown"

    now = datetime.now(timezone.utc)
    delta = now - dt
    days = delta.days

    if days < 0:
        return "unknown"
    if days < 1:
        hours = int(delta.total_seconds() // 3600)
        return f"{hours} hours ago"
    if days < 7:
        return f"{days} days ago"
    if days < 31:
        weeks = days // 7
        return f"{weeks} weeks ago"
    if days < 366:
        months = days // 30
        return f"{months} months ago"

    years = days // 365
    return f"{years} years ago"


def query_search(
    query: str,
    base_url: str = DEFAULT_SEARCH_ENGINE,
    max_results: int = 5,
    response_format: str = "json",
    timeout: int = 15,
) -> list[SearchResult]:
    """Search the internet and return ranked results.

    Args:
        query: Search query string.
        base_url: Instance URL.
        max_results: Maximum number of results to return.
        response_format: 'json' (structured API) or 'html' (parse HTML page).

    Returns:
        List of SearchResult, sorted by relevance.
    """
    params: dict[str, str] = {
        "q": query,
        "language": "en",
    }

    if response_format == "json":
        params["format"] = "json"

    headers = {
        "User-Agent": DEFAULT_USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
    }

    try:
        response = requests.get(
            f"{base_url.rstrip('/')}/search",
            params=params,
            timeout=(5, timeout),
            headers=headers,
        )
    except requests.exceptions.RequestException as exc:
        print(f"Search request failed: {exc}", file=sys.stderr)
        return []

    response.raise_for_status()

    if response_format == "html":
        results = _parse_searxng_html_results(response.text)
    else:
        data = response.json()
        results = [
            _rank_result(item) for item in data.get("results", []) if item.get("url")
        ]

    results.sort(key=lambda item: _sort_key(query, item))
    return results[:max_results]
