"""Bounded, SSRF-aware facility website text retrieval."""

import ipaddress
import socket
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import urldefrag, urljoin, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from sevah.affinity_models import WebsiteDocument

MAX_WEBSITE_BYTES = 1_000_000


class WebsiteFetchError(RuntimeError):
    """Raised when website evidence cannot be retrieved safely."""


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._ignored_depth = 0
        self.fragments: list[str] = []
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in {"script", "style", "noscript", "svg"}:
            self._ignored_depth += 1
        if tag == "a" and not self._ignored_depth:
            href = dict(attrs).get("href")
            if href:
                self.links.append(href)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg"} and self._ignored_depth:
            self._ignored_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self._ignored_depth and data.strip():
            self.fragments.append(data.strip())


class _SafeRedirectHandler(HTTPRedirectHandler):
    def __init__(self, allowed_origin_url: str | None = None) -> None:
        super().__init__()
        self._allowed_origin = (
            _url_origin(allowed_origin_url) if allowed_origin_url else None
        )

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _validate_public_http_url(newurl)
        if (
            self._allowed_origin is not None
            and _url_origin(newurl) != self._allowed_origin
        ):
            raise WebsiteFetchError("Cross-origin website redirects are blocked.")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch_website_document(
    url: str,
    *,
    timeout_seconds: float = 8,
    max_bytes: int = MAX_WEBSITE_BYTES,
    allowed_origin_url: str | None = None,
) -> WebsiteDocument:
    """Fetch one public HTML page and return visible text only."""

    try:
        _validate_public_http_url(url)
        request = Request(
            url,
            headers={
                "Accept": "text/html,application/xhtml+xml",
                "User-Agent": "Sevah/0.1 facility research",
            },
        )
        opener = build_opener(_SafeRedirectHandler(allowed_origin_url))
        with opener.open(request, timeout=timeout_seconds) as response:
            content_type = response.headers.get_content_type()
            if content_type not in {"text/html", "application/xhtml+xml"}:
                raise WebsiteFetchError("Facility website did not return HTML.")
            payload = response.read(max_bytes + 1)
            if len(payload) > max_bytes:
                raise WebsiteFetchError("Facility website exceeded the size limit.")
            charset = response.headers.get_content_charset() or "utf-8"
            resolved_url = response.geturl()

        parser = _TextExtractor()
        parser.feed(payload.decode(charset, errors="replace"))
        text = " ".join(" ".join(parser.fragments).split())
        links = tuple(
            dict.fromkeys(
                normalized
                for href in parser.links
                if (
                    normalized := _normalize_link(resolved_url, href)
                ) is not None
            )
        )
        return WebsiteDocument(
            url=resolved_url,
            text=text,
            content_characters=len(text),
            links=links,
        )
    except WebsiteFetchError:
        raise
    except (HTTPError, URLError, TimeoutError, UnicodeError, ValueError) as exc:
        raise WebsiteFetchError("Facility website request failed.") from exc


def _validate_public_http_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise WebsiteFetchError("Only public HTTP or HTTPS websites are allowed.")
    if parsed.username or parsed.password:
        raise WebsiteFetchError("Website URLs with credentials are not allowed.")

    try:
        addresses = {
            address[4][0]
            for address in socket.getaddrinfo(
                parsed.hostname,
                parsed.port or (443 if parsed.scheme == "https" else 80),
                type=socket.SOCK_STREAM,
            )
        }
    except socket.gaierror as exc:
        raise WebsiteFetchError("Facility website host could not be resolved.") from exc

    if not addresses:
        raise WebsiteFetchError("Facility website host could not be resolved.")
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if not ip.is_global:
            raise WebsiteFetchError("Private or non-routable website hosts are blocked.")


def _normalize_link(base_url: str, href: str) -> str | None:
    resolved, _ = urldefrag(urljoin(base_url, href.strip()))
    parsed = urlparse(resolved)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return None
    return resolved


def _url_origin(url: str) -> tuple[str, str, int]:
    parsed = urlparse(url)
    return (
        parsed.scheme.lower(),
        (parsed.hostname or "").lower(),
        parsed.port or (443 if parsed.scheme == "https" else 80),
    )
