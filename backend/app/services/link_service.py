"""Open Graph link previews.

The server fetches a URL that a *user* supplied, which is a textbook SSRF sink:
without care, "https://internal-admin/" or a link that redirects to
169.254.169.254 turns this endpoint into a proxy into the private network and
the cloud metadata service.

Defences, in order:

1. scheme allowlist (http/https only - no file://, gopher://, data:)
2. every resolved IP checked against private, loopback, link-local, reserved and
   multicast ranges, before connecting
3. redirects followed manually so *each* hop is re-validated (a public host is
   free to redirect to 127.0.0.1)
4. hard caps on redirects, response size and total time
5. HTML parsed with the stdlib parser, capped at the first 128 KB

Results are cached in-process with a TTL, so a busy conversation fetches each
link once rather than once per viewer.
"""

from __future__ import annotations

import asyncio
import html
import ipaddress
import logging
import socket
import time
from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import httpx

from app.core.errors import Unprocessable, ValidationError

logger = logging.getLogger(__name__)

ALLOWED_SCHEMES = {"http", "https"}
MAX_REDIRECTS = 3
MAX_BYTES = 128 * 1024
TIMEOUT_SECONDS = 5.0
CACHE_TTL_SECONDS = 60 * 30
CACHE_MAX_ENTRIES = 512


@dataclass(slots=True)
class LinkPreview:
    url: str
    title: str | None = None
    description: str | None = None
    image: str | None = None
    site_name: str | None = None
    fetched_at: float = field(default_factory=time.time)


_cache: dict[str, LinkPreview] = {}


def _is_public_address(host: str) -> bool:
    """Resolve a hostname and require every answer to be a public address."""
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False
    if not infos:
        return False

    for info in infos:
        address = info[4][0]
        try:
            ip = ipaddress.ip_address(address)
        except ValueError:
            return False
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            return False
    return True


def validate_url(raw: str) -> str:
    parsed = urlparse(raw)
    if parsed.scheme not in ALLOWED_SCHEMES:
        raise ValidationError("Only http and https links can be previewed",
                              code="UNSUPPORTED_SCHEME")
    if not parsed.hostname:
        raise ValidationError("That does not look like a link")
    if not _is_public_address(parsed.hostname):
        # Deliberately vague: a precise error would turn this into a port
        # scanner for the internal network.
        raise Unprocessable("That link cannot be previewed", code="LINK_NOT_ALLOWED")
    return raw


class _OpenGraphParser(HTMLParser):
    """Pulls og:* / twitter:* tags and the <title>, then stops caring."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.meta: dict[str, str] = {}
        self.title: str | None = None
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "title":
            self._in_title = True
            return
        if tag != "meta":
            return
        attributes = {key.lower(): (value or "") for key, value in attrs}
        key = attributes.get("property") or attributes.get("name")
        content = attributes.get("content")
        if key and content:
            self.meta.setdefault(key.lower(), content.strip())

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_title and self.title is None:
            stripped = data.strip()
            if stripped:
                self.title = stripped


def _clean(value: str | None, limit: int) -> str | None:
    if not value:
        return None
    return html.unescape(value).strip()[:limit] or None


async def _fetch(url: str) -> LinkPreview:
    current = validate_url(url)

    async with httpx.AsyncClient(
        timeout=TIMEOUT_SECONDS,
        follow_redirects=False,  # each hop is validated by hand, see module docs
        headers={
            # Identify honestly, and ask for HTML only.
            "User-Agent": "SignalClone-LinkPreview/1.0 (+link unfurl)",
            "Accept": "text/html,application/xhtml+xml",
        },
    ) as client:
        for _ in range(MAX_REDIRECTS + 1):
            response = await client.get(current)

            if response.is_redirect:
                location = response.headers.get("location")
                if not location:
                    break
                # Re-validate: a public host may redirect straight to localhost.
                current = validate_url(urljoin(current, location))
                continue

            content_type = response.headers.get("content-type", "")
            if "html" not in content_type.lower():
                # Not a page - still useful to echo the URL back.
                return LinkPreview(url=current)

            body = response.content[:MAX_BYTES].decode(
                response.encoding or "utf-8", errors="replace"
            )
            parser = _OpenGraphParser()
            parser.feed(body)
            meta = parser.meta

            image = meta.get("og:image") or meta.get("twitter:image")
            if image:
                image = urljoin(current, image)
                # The image is rendered by the browser, so it gets the same
                # scheme check rather than being trusted because the page said so.
                if urlparse(image).scheme not in ALLOWED_SCHEMES:
                    image = None

            return LinkPreview(
                url=current,
                title=_clean(meta.get("og:title") or meta.get("twitter:title") or parser.title, 200),
                description=_clean(
                    meta.get("og:description") or meta.get("twitter:description")
                    or meta.get("description"),
                    300,
                ),
                image=image,
                site_name=_clean(meta.get("og:site_name") or urlparse(current).hostname, 80),
            )

    raise Unprocessable("Too many redirects", code="TOO_MANY_REDIRECTS")


async def get_preview(url: str) -> LinkPreview:
    now = time.time()
    cached = _cache.get(url)
    if cached and now - cached.fetched_at < CACHE_TTL_SECONDS:
        return cached

    try:
        preview = await asyncio.wait_for(_fetch(url), timeout=TIMEOUT_SECONDS * 2)
    except (ValidationError, Unprocessable):
        raise
    except Exception as exc:
        logger.debug("link preview failed for %s: %s", url, exc)
        raise Unprocessable("That link could not be loaded", code="LINK_FETCH_FAILED") from exc

    if len(_cache) >= CACHE_MAX_ENTRIES:
        # Crude eviction is fine for a bounded, purely-derived cache.
        oldest = min(_cache, key=lambda key: _cache[key].fetched_at)
        _cache.pop(oldest, None)
    _cache[url] = preview
    return preview


def clear_cache() -> None:
    _cache.clear()
