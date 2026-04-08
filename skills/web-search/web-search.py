#!/usr/bin/env python3
"""CLI entry point for web search and content fetching."""

import argparse
import os
import sys

from requests import exceptions as req_exceptions
from search import SearchResult, extract_domain, relative_age, query_search
from content import PageContent, fetch_page_content

MAX_RESULTS = 20
DEFAULT_N = 5


def _render_result(
    item: SearchResult,
    index: int,
    include_content: bool,
    is_spa: bool = False,
    data_urls: list[str] | None = None,
) -> str:
    """Render a single search result as text."""
    parts = [
        f"--- Result {index} ---",
        f"Title: {item.title}",
        f"Link: {item.url}",
        f"Domain: {item.domain or 'unknown'}",
        f"Age: {relative_age(item.published_date)}",
    ]

    if item.engines:
        parts.append(f"Engines: {', '.join(item.engines)}")
    if item.snippet:
        parts.append(f"Snippet: {item.snippet}")
    if is_spa:
        parts.append("SPA Detected: yes (content is rendered by JavaScript)")
        if data_urls:
            parts.append("Data URLs found:")
            for du in data_urls:
                parts.append(f"  - {du}")
            parts.append(
                "Hint: Page content is dynamically rendered. "
                "Use 'fetch' on a data URL above to retrieve the actual data."
            )
        else:
            parts.append("No data URLs found in the HTML source.")
    elif include_content and item.content:
        parts.append("Content:")
        for line in item.content.splitlines():
            parts.append(f"  {line}")
    parts.append("")
    return "\n".join(parts)


def _render_results(results: list[SearchResult], include_content: bool) -> str:
    """Render all results as text."""
    parts = [
        _render_result(item, i, include_content) for i, item in enumerate(results, 1)
    ]
    return "\n".join(parts).rstrip() + "\n"


def _fetch_content(url: str, max_chars: int, timeout: int) -> PageContent:
    try:
        return fetch_page_content(url, max_chars=max_chars, timeout=timeout)
    except (TypeError, req_exceptions.ReadTimeout) as exc:
        return PageContent(
            url=url,
            title="(content fetch failed)",
            content_markdown=f"[failed to fetch content: {exc}]",
        )
    except req_exceptions.RequestException as exc:
        return PageContent(
            url=url,
            title="(content fetch failed)",
            content_markdown=f"[failed with unknown error: {exc}]",
        )


def _cmd_fetch(args: argparse.Namespace) -> int:
    """Fetch a single URL and print its content."""
    page = _fetch_content(args.url, max_chars=args.max_chars, timeout=args.timeout)
    result = SearchResult(
        title=page.title,
        url=page.url,
        snippet="",
        domain=extract_domain(page.url),
        content=page.content_markdown,
    )
    print(
        _render_result(
            result,
            1,
            include_content=True,
            is_spa=page.is_spa,
            data_urls=page.data_urls,
        )
    )
    return 0


def _cmd_search(args: argparse.Namespace) -> int:
    """Search and optionally fetch content for results."""
    query = " ".join(args.query).strip()
    search_engine = (
        args.search_engine
        or os.environ.get("ENGINE_BASE_URL")
        or "http://localhost:8888"
    )

    results = query_search(
        query=query,
        base_url=search_engine,
        max_results=args.n,
        response_format=args.format,
        timeout=args.timeout,
    )

    if not results:
        print("No results found.", file=sys.stderr)
        return 0

    if args.content:
        for item in results:
            page = _fetch_content(
                item.url, max_chars=args.max_chars, timeout=args.timeout
            )
            item.content = page.content_markdown
            if page.title and item.title in ("(untitled)", item.url):
                item.title = page.title

    print(_render_results(results, args.content))
    return 0


def _validate_range(min_value: int, max_value: int):
    def check(value):
        n = int(value)
        if n < min_value or n > max_value:
            raise argparse.ArgumentTypeError(
                f"must be between {min_value} and {max_value}"
            )
        return n

    return check


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="web-search",
        description="Search the web or fetch pages converting to markdown when\
                it makes sense to do so.",
    )
    sub = parser.add_subparsers(dest="command")

    # --- search ---
    search = sub.add_parser("search", help="Search the Web")
    search.add_argument("query", nargs="+", help="Search query")
    search.add_argument(
        "-n",
        type=_validate_range(1, MAX_RESULTS),
        default=DEFAULT_N,
        help=f"number of results (default: {DEFAULT_N}, max: {MAX_RESULTS})",
    )
    search.add_argument(
        "--content",
        action="store_true",
        help="fetch and include page content as markdown",
    )
    search.add_argument(
        "--search-engine",
        default=None,
        help="SearXNG base URL (default: http://localhost:8888, or ENGINE_BASE_URL env var)",
    )
    search.add_argument(
        "--max-chars",
        type=int,
        default=0,
        help="maximum content characters per page (0 = unlimited, default: unlimited)",
    )
    search.add_argument(
        "--format",
        choices=["json", "html"],
        default="json",
        help="response format: json (default) or html (parse HTML results page)",
    )
    search.add_argument(
        "--timeout",
        type=int,
        default=15,
        help="HTTP timeout in seconds (default: 15)",
    )

    # --- fetch ---
    fetch = sub.add_parser("fetch", help="Fetch a single URL as markdown")
    fetch.add_argument("url", help="URL to fetch")
    fetch.add_argument(
        "--max-chars",
        type=int,
        default=0,
        help="maximum content characters (0 = unlimited, default: unlimited)",
    )
    fetch.add_argument(
        "--timeout",
        type=int,
        default=15,
        help="HTTP timeout in seconds (default: 15)",
    )

    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 2

    try:
        if args.command == "fetch":
            return _cmd_fetch(args)

        return _cmd_search(args)
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
