"""Shared constants and helpers for web-search skill."""

from __future__ import annotations

from urllib.parse import urlparse

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/123.0 Safari/537.36"
)

# Domains that block non-browser requests entirely (require JS, cookies,
# or a full browser environment).
_UNFETCHABLE_DOMAINS = {
    "facebook.com",
    "www.facebook.com",
    "m.facebook.com",
    "mbasic.facebook.com",
    "instagram.com",
    "www.instagram.com",
    "x.com",
    "twitter.com",
    "www.twitter.com",
    "linkedin.com",
    "www.linkedin.com",
}


def is_unfetchable(url: str) -> bool:
    """Check if a URL belongs to a domain known to block non-browser requests."""
    domain = (urlparse(url).hostname or "").lower()
    return domain in _UNFETCHABLE_DOMAINS or any(
        domain.endswith("." + d) for d in _UNFETCHABLE_DOMAINS
    )


def truncate(text: str, max_chars: int) -> str:
    """Truncate text to max_chars, appending [truncated] if needed.

    If max_chars is 0 or falsy, returns text unchanged.
    """
    if not max_chars or len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "\n\n[truncated]"
