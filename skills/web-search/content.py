"""Fetch web pages and extract content as markdown."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse, urljoin

import requests
from bs4 import BeautifulSoup, Tag
from markdownify import markdownify
from shared import DEFAULT_USER_AGENT, is_unfetchable, truncate


# Tags to strip entirely — they never contain useful content
_STRIP_TAGS = [
    "script",
    "style",
    "noscript",
    "svg",
    "canvas",
    "iframe",
    "footer",
    "nav",
    "header",
    "aside",
]


@dataclass
class PageContent:
    """Fetched web page with its content converted to markdown."""

    url: str
    title: str
    content_markdown: str
    data_urls: list[str] | None = None
    is_spa: bool = False


def _clean_whitespace(text: str) -> str:
    text = text.replace("\r\n", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# Raw URL rewriting for known hosts
_RAW_URL_RULES: list[tuple[re.Pattern, str]] = [
    # GitHub: github.com/<user>/<repo>/blob/<ref>/<path>
    #      -> raw.githubusercontent.com/<user>/<repo>/<ref>/<path>
    (
        re.compile(r"^https?://github\.com/([^/]+/[^/]+)/blob/(.+)$"),
        r"https://raw.githubusercontent.com/\1/\2",
    ),
    # GitLab: gitlab.com/<user>/<repo>/-/blob/<ref>/<path>
    #      -> gitlab.com/<user>/<repo>/-/raw/<ref>/<path>
    (
        re.compile(r"^(https?://gitlab\.com/[^/]+/[^/]+)/-/blob/(.+)$"),
        r"\1/-/raw/\2",
    ),
    # Bitbucket: bitbucket.org/<user>/<repo>/src/<ref>/<path>
    #         -> bitbucket.org/<user>/<repo>/raw/<ref>/<path>
    (
        re.compile(r"^(https?://bitbucket\.org/[^/]+/[^/]+)/src/(.+)$"),
        r"\1/raw/\2",
    ),
]

# File extensions that are safe to return as raw text
_RAW_TEXT_EXTENSIONS = {
    ".md",
    ".txt",
    ".rst",
    ".adoc",
    ".yaml",
    ".yml",
    ".json",
    ".toml",
    ".xml",
    ".csv",
    ".ini",
    ".cfg",
    ".conf",
    ".sh",
    ".bash",
    ".py",
    ".js",
    ".ts",
    ".c",
    ".h",
    ".cpp",
    ".hpp",
    ".java",
    ".go",
    ".rs",
    ".rb",
    ".pl",
    ".lua",
    ".r",
    ".sql",
    ".dockerfile",
    ".makefile",
}


def _try_raw_url(url: str) -> Optional[str]:
    """If the URL points to a known code host blob view, return the raw URL."""
    for pattern, replacement in _RAW_URL_RULES:
        if pattern.match(url):
            return pattern.sub(replacement, url)
    return None


def _is_text_file(url: str) -> bool:
    """Check if the URL path looks like a text file we can display."""
    path = urlparse(url).path.lower()
    # Handle files without extensions (Makefile, Dockerfile, etc.)
    filename = path.rsplit("/", 1)[-1] if "/" in path else path
    if filename.lower() in {
        "makefile",
        "dockerfile",
        "rakefile",
        "gemfile",
        "cmakelists.txt",
    }:
        return True
    return any(path.endswith(ext) for ext in _RAW_TEXT_EXTENSIONS)


def _fetch_raw_text(
    url: str,
    timeout: int = 15,
    user_agent: str = DEFAULT_USER_AGENT,
) -> Optional[PageContent]:
    """Try to fetch raw text content from a rewritten URL."""
    raw_url = _try_raw_url(url)
    if raw_url is None:
        return None

    # Only attempt raw fetch for known text file types
    if not _is_text_file(raw_url):
        return None

    response = requests.get(
        raw_url,
        timeout=(5, timeout),
        headers={"User-Agent": user_agent},
    )
    response.raise_for_status()

    content_type = response.headers.get("Content-Type", "")
    if "text/" not in content_type and "application/json" not in content_type:
        return None

    # Derive a title from the file path
    path = urlparse(url).path
    filename = path.rsplit("/", 1)[-1] if "/" in path else path
    title = filename or url

    return PageContent(
        url=url,
        title=title,
        content_markdown=_clean_whitespace(response.text),
    )


# HTML -> Markdown extraction
def _extract_title(soup: BeautifulSoup) -> str:
    """Extract page title from og:title, <title>, or <h1>."""
    og = soup.find("meta", attrs={"property": "og:title"})
    if og and og.get("content"):
        return og["content"].strip()

    if soup.title:
        return soup.title.get_text(" ", strip=True)

    h1 = soup.find("h1")
    if h1:
        return h1.get_text(" ", strip=True)

    return ""


def _code_language(el: Tag) -> str:
    """Extract language hint from a code element's class attribute."""
    classes = el.get("class") or []
    if not classes:
        return ""
    for cls in classes:
        if cls.startswith("language-"):
            return cls[len("language-") :]
    return ""


def _strip_hidden_elements(soup: BeautifulSoup) -> None:
    """Remove elements that are invisible to the user.

    These are unambiguously junk — if the browser doesn't show it,
    the LLM shouldn't see it.  Zero false-positive risk.
    """
    for el in soup.find_all(
        style=lambda s: s and ("display:none" in s or "display: none" in s)
    ):
        el.decompose()
    for el in soup.find_all(attrs={"aria-hidden": "true"}):
        el.decompose()
    for el in soup.find_all(attrs={"hidden": True}):
        el.decompose()


def _html_to_markdown(raw_html: str) -> tuple[str, str]:
    """Convert HTML to markdown preserving all headings and structure."""
    soup = BeautifulSoup(raw_html, "html.parser")

    title = _extract_title(soup)

    for tag in soup(_STRIP_TAGS):
        tag.decompose()

    # Remove permalink/headerlink anchors (e.g. Sphinx docs' "¶" links)
    for tag in soup.select("a.headerlink"):
        tag.decompose()

    # Remove elements hidden from the user (modals, cookie banners, etc.)
    _strip_hidden_elements(soup)

    node = soup.body or soup

    markdown = markdownify(
        str(node),
        heading_style="ATX",
        code_language_callback=_code_language,
    )

    return title, _clean_whitespace(markdown)


# SPA detection and data URL discovery
_TEMPLATE_PATTERN = re.compile(r"\{\{[^}]+\}\}")

# Patterns for JSON/API endpoints in HTML source
_DATA_URL_PATTERNS = [
    # Quoted paths ending in .json
    re.compile(r'["\'](/[a-zA-Z0-9_./-]+\.json)["\']'),
    re.compile(r'["\']([a-zA-Z0-9_./-]+\.json)["\']'),
    # Common API URL patterns
    re.compile(r'["\'](/api/[a-zA-Z0-9_./-]+)["\']'),
    # fetch() or axios calls
    re.compile(r'(?:fetch|axios\.get)\s*\(\s*["\']([^"\'>]+)["\']'),
]


def _detect_spa(html_text: str) -> bool:
    """Detect if a page is a JavaScript SPA with no real content.

    Runs on *raw* HTML before any expensive markdown conversion so we
    can bail out early.  Two heuristics:

    1. Template markers (``{{...}}``) — Angular/Vue/Handlebars apps
       leave these in the source when content is rendered client-side.
    2. Content ratio — if the HTML is large but contains very little
       visible text, it's likely an empty shell that loads via JS.
    """
    # 1. Template markers in the raw HTML (including <script> blocks)
    template_matches = _TEMPLATE_PATTERN.findall(html_text)
    if len(template_matches) >= 3:
        return True

    # 2. Very little visible text relative to HTML size
    html_len = len(html_text)
    if html_len > 5000:
        soup = BeautifulSoup(html_text, "html.parser")
        # Remove elements that never carry user-visible content
        for tag in soup(["script", "style", "noscript", "svg"]):
            tag.decompose()
        text_len = len(soup.get_text(separator=" ", strip=True))
        if text_len < 200 or text_len / html_len < 0.01:
            return True

    return False


def _discover_data_urls(html_text: str, base_url: str) -> list[str]:
    """Extract potential JSON/API data URLs from HTML source."""
    found: set[str] = set()
    for pattern in _DATA_URL_PATTERNS:
        for match in pattern.findall(html_text):
            # Skip common non-data files
            if any(
                skip in match
                for skip in [
                    "package.json",
                    "manifest.json",
                    "tsconfig",
                    ".min.js",
                    "node_modules",
                    "webpack",
                ]
            ):
                continue
            absolute = urljoin(base_url, match)
            found.add(absolute)
    return sorted(found)


def _page_content(url: str, timeout: int, user_agent: str) -> requests.Response:
    # Fetch the URL
    #
    # Use a two-phase approach to detect bot/WAF-protected sites that accept
    # the TCP+TLS connection but never send HTTP response headers (e.g.
    # Akamai Bot Manager).  Phase 1 uses stream=True with a short timeout
    # to see if we get response headers at all.  Phase 2 reads the body
    # with the caller's full timeout.
    #
    # The initial header timeout is capped at 5s regardless of the
    # caller's --timeout, because a legitimate server always sends headers
    # within milliseconds even if the body is large.
    header_timeout = min(timeout, 5)
    try:
        response = requests.get(
            url,
            timeout=(5, header_timeout),
            headers={"User-Agent": user_agent},
            stream=True,
        )
        response.raise_for_status()
    except requests.exceptions.ReadTimeout:
        raise requests.exceptions.ReadTimeout(
            f"No response headers received from {url} within {header_timeout}s "
            f"\u2014 the server accepted the connection but never responded "
            f"(likely bot/WAF protection requiring JavaScript). "
            f"Try an alternative source."
        ) from None

    # Phase 2: read the full body with the caller's timeout.
    try:
        _ = response.content
    except requests.exceptions.ReadTimeout:
        raise requests.exceptions.ReadTimeout(
            f"Response headers received from {url} but body read timed out "
            f"after {timeout}s."
        ) from None

    # Fix encoding: when the server doesn't specify a charset, requests
    # defaults to ISO-8859-1 (per HTTP/1.1) which mangles UTF-8 content.
    # Use the auto-detected encoding instead.
    if response.encoding and response.apparent_encoding:
        # requests sets encoding from Content-Type header; if it fell back
        # to ISO-8859-1 but the content looks like UTF-8, override it.
        if response.encoding.lower().replace("-", "") == "iso88591":
            response.encoding = response.apparent_encoding

    return response


def fetch_page_content(
    url: str,
    timeout: int = 15,
    max_chars: int = 0,
    user_agent: str = DEFAULT_USER_AGENT,
) -> PageContent:
    """Fetch a URL and return its content as markdown.

    For known code hosts (GitHub, GitLab, Bitbucket), rewrites to the raw URL
    and returns the file content directly. For all other URLs, fetches HTML
    and converts to markdown.

    When an SPA (single-page app) is detected, the raw HTML is scanned for
    JSON/API data URLs which are returned in ``data_urls``.

    Args:
        url: The URL to fetch.
        timeout: HTTP request timeout in seconds.
        max_chars: Maximum characters to return (0 = unlimited).
        user_agent: User-Agent header for HTTP requests.

    Returns:
        PageContent with title, markdown content, and optional data_urls.
    """
    # Bail out immediately for domains known to block non-browser requests
    if is_unfetchable(url):
        domain = urlparse(url).hostname or url
        raise RuntimeError(
            f"{domain} blocks non-browser requests (requires login/JS). "
            f"Content is only available in a real browser."
        )

    # Try raw URL rewriting for known code hosts
    raw_result = _fetch_raw_text(url, timeout=timeout, user_agent=user_agent)
    if raw_result is not None:
        raw_result.content_markdown = truncate(raw_result.content_markdown, max_chars)
        return raw_result

    response = _page_content(url, timeout=timeout, user_agent=user_agent)

    # Reject binary content, then route HTML vs raw text.
    # Detect binary the same way git/file(1) do: null bytes in the first
    # 512 bytes mean it's binary (images, PDFs, zip, etc.).
    if b"\x00" in response.content[:512]:
        content_type = response.headers.get("Content-Type", "unknown")
        raise TypeError(
            f"Cannot extract text from binary content ({content_type}) at {url}"
        )

    content_type = response.headers.get("Content-Type", "")

    is_html = "text/html" in content_type or "application/xhtml+xml" in content_type
    if not is_html:
        raw_content = truncate(_clean_whitespace(response.text), max_chars)
        filename = urlparse(url).path.rsplit("/", 1)[-1] or url
        return PageContent(
            url=url,
            title=filename,
            content_markdown=raw_content,
        )

    # HTML — detect SPA *before* the expensive markdown conversion
    is_spa = _detect_spa(response.text)
    if is_spa:
        # Extract just the title (cheap) and data URLs — skip markdown
        soup = BeautifulSoup(response.text, "html.parser")
        return PageContent(
            url=url,
            title=html.unescape(_extract_title(soup) or url),
            content_markdown="",
            data_urls=_discover_data_urls(response.text, url),
            is_spa=True,
        )

    # Normal HTML — convert to markdown
    title, content = _html_to_markdown(response.text)
    if not title:
        title = url

    content = truncate(content, max_chars)

    return PageContent(
        url=url,
        title=html.unescape(title),
        content_markdown=content,
    )
