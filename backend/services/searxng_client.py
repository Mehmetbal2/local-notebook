"""SearXNG metasearch client and web page text extraction.

SearXNG runs locally in Docker (services/searxng) and is queried through its
JSON API: GET {base_url}/search?q=...&format=json.
"""
from __future__ import annotations

import asyncio
import ipaddress
import logging
import os
import re
import socket
import time
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urljoin, urlparse

import httpx

logger = logging.getLogger("searxng")

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36 LocalNotebook/1.0"
)

# Wikimedia sites refuse browser-like user agents from scripts; they ask clients to
# name themselves (https://meta.wikimedia.org/wiki/User-Agent_policy).
HONEST_USER_AGENT = "LocalNotebook/1.0 (self-hosted personal research assistant) httpx/0.28"
HONEST_UA_HOSTS = ("wikipedia.org", "wikimedia.org", "wiktionary.org", "wikisource.org", "wikidata.org")


def _user_agent_for(url: str) -> str:
    try:
        host = urlparse(url).netloc.lower()
    except ValueError:
        return USER_AGENT
    return HONEST_USER_AGENT if host.endswith(HONEST_UA_HOSTS) else USER_AGENT


TIME_RANGES = {"day", "week", "month", "year"}

# freshness values of the web_search tool -> SearXNG time_range
FRESHNESS_TO_TIME_RANGE = {
    "oneDay": "day",
    "oneWeek": "week",
    "oneMonth": "month",
    "oneYear": "year",
}


class SearxngError(Exception):
    """A SearXNG request failed. `code` is one of: unreachable, json_disabled,
    rate_limited, timeout, http, blocked (a page address that is not public)."""

    def __init__(self, code: str, message: str = "", status: int | None = None):
        super().__init__(message or code)
        self.code = code
        self.status = status


@dataclass
class SearchResult:
    title: str
    url: str
    content: str = ""
    engines: list[str] = field(default_factory=list)
    score: float = 0.0
    published_date: str = ""
    category: str = ""
    # Scholarly results (SearXNG "paper" template)
    doi: str = ""
    pdf_url: str = ""
    authors: list[str] = field(default_factory=list)
    journal: str = ""

    @property
    def domain(self) -> str:
        try:
            host = urlparse(self.url).netloc.lower()
        except ValueError:
            return ""
        return host[4:] if host.startswith("www.") else host

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "url": self.url,
            "content": self.content,
            "engines": self.engines,
            "score": self.score,
            "published_date": self.published_date,
            "domain": self.domain,
            "doi": self.doi,
            "pdf_url": self.pdf_url,
            "authors": self.authors,
            "journal": self.journal,
        }


def _normalize_url(url: str) -> str:
    """Key used to drop duplicate results (scheme, www., trailing slash ignored)."""
    try:
        p = urlparse(url.strip())
    except ValueError:
        return url.strip()
    host = p.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    path = p.path.rstrip("/")
    return f"{host}{path}?{p.query}" if p.query else f"{host}{path}"


async def search(
    base_url: str,
    query: str,
    *,
    categories: Optional[str] = None,
    language: Optional[str] = None,
    time_range: Optional[str] = None,
    pageno: int = 1,
    engines: Optional[str] = None,
    timeout: float = 20.0,
) -> list[SearchResult]:
    params: dict[str, str | int] = {"q": query, "format": "json", "pageno": pageno}
    if categories:
        params["categories"] = categories
    if engines:
        params["engines"] = engines
    if language and language != "auto":
        params["language"] = language
    if time_range in TIME_RANGES:
        params["time_range"] = time_range

    url = f"{base_url.rstrip('/')}/search"
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url, params=params, headers={"Accept": "application/json"})
    except httpx.ConnectError as exc:
        raise SearxngError("unreachable", str(exc)) from exc
    except httpx.TimeoutException as exc:
        raise SearxngError("timeout", str(exc)) from exc
    except httpx.HTTPError as exc:
        raise SearxngError("unreachable", str(exc)) from exc

    if resp.status_code == 403:
        raise SearxngError("json_disabled", "SearXNG JSON format is disabled", status=403)
    if resp.status_code == 429:
        raise SearxngError("rate_limited", "SearXNG rate limit", status=429)
    if resp.status_code != 200:
        raise SearxngError("http", resp.text[:200], status=resp.status_code)

    try:
        data = resp.json()
    except ValueError as exc:
        raise SearxngError("http", "invalid JSON from SearXNG", status=resp.status_code) from exc

    _mark_reachable(base_url, True)
    results: list[SearchResult] = []
    seen: set[str] = set()
    for item in data.get("results") or []:
        link = (item.get("url") or "").strip()
        if not link.startswith(("http://", "https://")):
            continue
        key = _normalize_url(link)
        if key in seen:
            continue
        seen.add(key)
        engines_list = item.get("engines") or ([item["engine"]] if item.get("engine") else [])
        results.append(
            SearchResult(
                title=(item.get("title") or "").strip() or link,
                url=link,
                content=re.sub(r"\s+", " ", (item.get("content") or "")).strip(),
                engines=[str(e) for e in engines_list],
                score=float(item.get("score") or 0.0),
                published_date=str(item.get("publishedDate") or item.get("pubdate") or "")[:25],
                category=str(item.get("category") or ""),
                doi=str(item.get("doi") or "").strip(),
                pdf_url=str(item.get("pdf_url") or "").strip(),
                authors=[str(a).strip() for a in (item.get("authors") or []) if str(a).strip()][:20],
                journal=str(item.get("journal") or "").strip()[:300],
            )
        )
    return results


# ── Reachability (cached so preflight checks stay cheap) ────────────────────

_REACHABLE_TTL = 20.0
_reachable_cache: dict[str, tuple[float, bool]] = {}


def _mark_reachable(base_url: str, ok: bool) -> None:
    _reachable_cache[base_url.rstrip("/")] = (time.monotonic(), ok)


async def is_reachable(base_url: str) -> bool:
    key = base_url.rstrip("/")
    cached = _reachable_cache.get(key)
    if cached and time.monotonic() - cached[0] < _REACHABLE_TTL:
        return cached[1]
    ok = False
    try:
        async with httpx.AsyncClient(timeout=2.5) as client:
            resp = await client.get(f"{key}/healthz")
            ok = resp.status_code == 200
            if not ok:
                # Older images have no /healthz; any answer from the root means it is up.
                resp = await client.get(f"{key}/")
                ok = resp.status_code < 500
    except httpx.HTTPError:
        ok = False
    _mark_reachable(key, ok)
    return ok


# ── Page fetching and main-text extraction ──────────────────────────────────

MAX_PAGE_BYTES = 8 * 1024 * 1024
MAX_PDF_BYTES = 60 * 1024 * 1024

_DROP_TAGS = (
    "script", "style", "noscript", "svg", "canvas", "iframe", "form", "button",
    "nav", "footer", "header", "aside", "template", "select", "input",
)
_NOISE_RE = re.compile(
    r"(^|[\s_-])(nav|menu|footer|header|sidebar|breadcrumb|cookie|consent|banner|share|social|"
    r"related|comment|advert|ads?|promo|newsletter|subscribe|popup|modal|signup|login)([\s_-]|$)",
    re.I,
)


@dataclass
class FetchedPage:
    url: str
    final_url: str
    content_type: str
    title: str = ""
    text: str = ""          # markdown-ish main text (HTML pages)
    description: str = ""
    authors: list[str] = field(default_factory=list)
    published: str = ""
    site_name: str = ""
    pdf_url: str = ""       # citation_pdf_url etc. found on a landing page
    pdf_bytes: bytes | None = None

    @property
    def is_pdf(self) -> bool:
        return self.pdf_bytes is not None


def _meta(soup, *names: str) -> str:
    for name in names:
        tag = soup.find("meta", attrs={"name": name}) or soup.find("meta", attrs={"property": name})
        if tag and tag.get("content"):
            return str(tag["content"]).strip()
    return ""


def _meta_all(soup, name: str) -> list[str]:
    out = []
    for tag in soup.find_all("meta", attrs={"name": name}):
        value = str(tag.get("content") or "").strip()
        if value and value not in out:
            out.append(value)
    return out


def _clean_inline(text: str) -> str:
    return re.sub(r"[ \t ]+", " ", text).strip()


def _element_to_markdown(root) -> str:
    """Flatten the main content into simple markdown (headings, paragraphs, lists)."""
    from bs4 import NavigableString, Tag

    lines: list[str] = []
    block_tags = {"p", "li", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "pre", "td", "th", "dd", "dt", "figcaption"}

    def walk(node) -> None:
        for child in node.children:
            if isinstance(child, NavigableString):
                continue
            if not isinstance(child, Tag):
                continue
            name = child.name.lower()
            if name in block_tags:
                text = _clean_inline(child.get_text(" ", strip=True))
                if not text:
                    continue
                if name.startswith("h") and len(name) == 2:
                    level = min(int(name[1]) + 1, 6)
                    lines.append(f"{'#' * level} {text}")
                elif name == "li":
                    lines.append(f"- {text}")
                elif name == "blockquote":
                    lines.append(f"> {text}")
                else:
                    lines.append(text)
            elif name in ("br", "hr", "img"):
                continue
            else:
                # Text directly inside a div (no <p>) still counts as a paragraph.
                direct = "".join(str(c) for c in child.children if isinstance(c, NavigableString)).strip()
                if direct and len(direct) > 40 and not child.find(block_tags):
                    lines.append(_clean_inline(child.get_text(" ", strip=True)))
                else:
                    walk(child)

    walk(root)
    out: list[str] = []
    for line in lines:
        if out and out[-1] == line:
            continue
        out.append(line)
    return "\n\n".join(out)


def _pick_main(soup):
    for selector in ("article", "main", "[role=main]", "#content", ".content", "#main"):
        node = soup.select_one(selector)
        if node and len(node.get_text(" ", strip=True)) > 400:
            return node
    # Fallback: the container holding the most paragraph text.
    best, best_len = None, 0
    for node in soup.find_all(["div", "section"]):
        length = sum(len(p.get_text(" ", strip=True)) for p in node.find_all("p", recursive=False))
        if length > best_len:
            best, best_len = node, length
    if best is not None and best_len > 300:
        return best
    return soup.body or soup


def extract_html(html: str, base_url: str) -> dict:
    from bs4 import BeautifulSoup

    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        soup = BeautifulSoup(html, "html.parser")

    title = (
        _meta(soup, "citation_title", "og:title", "twitter:title")
        or (soup.title.get_text(" ", strip=True) if soup.title else "")
    )
    authors = _meta_all(soup, "citation_author") or _meta_all(soup, "dc.creator")
    if not authors:
        single = _meta(soup, "author", "article:author")
        if single and not single.startswith("http"):
            authors = [single]
    published = _meta(
        soup, "citation_publication_date", "citation_date", "article:published_time",
        "dc.date", "date", "pubdate",
    )
    pdf_url = _meta(soup, "citation_pdf_url")
    if pdf_url:
        pdf_url = urljoin(base_url, pdf_url)

    for tag in soup.find_all(_DROP_TAGS):
        tag.decompose()
    for tag in soup.find_all(True):
        if tag.attrs is None:
            continue
        attrs = " ".join(tag.get("class") or []) + " " + str(tag.get("id") or "")
        if attrs.strip() and _NOISE_RE.search(attrs) and tag.name not in ("body", "html", "article", "main"):
            # Large wrappers (e.g. "content has-sidebar") hold the article itself.
            if tag.find(["article", "main"]) or len(tag.find_all("p")) >= 3:
                continue
            if len(tag.get_text(" ", strip=True)) < 2500:
                tag.decompose()

    main = _pick_main(soup)
    text = _element_to_markdown(main)
    if len(text) < 200:
        text = _clean_inline((soup.body or soup).get_text("\n", strip=True))

    return {
        "title": _clean_inline(title),
        "text": text.strip(),
        "description": _meta(soup, "description", "og:description", "citation_abstract"),
        "authors": authors[:20],
        "published": published[:25],
        "site_name": _meta(soup, "og:site_name", "citation_journal_title", "citation_publisher"),
        "pdf_url": pdf_url,
    }


async def _download(client: httpx.AsyncClient, url: str, limit: int) -> tuple[httpx.Response, bytes]:
    async with client.stream("GET", url) as resp:
        if resp.status_code >= 400:
            raise SearxngError("http", f"HTTP {resp.status_code}", status=resp.status_code)
        chunks: list[bytes] = []
        size = 0
        async for chunk in resp.aiter_bytes():
            size += len(chunk)
            if size > limit:
                raise SearxngError("http", "file too large")
            chunks.append(chunk)
        return resp, b"".join(chunks)


# Pages are fetched on behalf of users (web source import, web search, deep research),
# so a URL must not reach services that only the server can see: loopback,
# private networks, link-local addresses such as the cloud metadata endpoint
# 169.254.169.254, and other non-public ranges. Every hop of a redirect is checked.
# Set WEB_FETCH_ALLOW_PRIVATE=1 to allow intranet pages on a trusted single-user install.
WEB_FETCH_ALLOW_PRIVATE = (os.getenv("WEB_FETCH_ALLOW_PRIVATE") or "").strip().lower() in ("1", "true", "yes", "on")


def _is_public_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    mapped = getattr(ip, "ipv4_mapped", None)
    if mapped is not None:
        ip = mapped
    return ip.is_global and not ip.is_multicast


async def check_public_destination(url: str) -> None:
    """Raise SearxngError("blocked") unless the URL is http(s) and resolves only to public addresses."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise SearxngError("blocked", "only http and https addresses can be fetched")
    if WEB_FETCH_ALLOW_PRIVATE:
        return
    host = parsed.hostname
    try:
        addresses = {ipaddress.ip_address(host)}
    except ValueError:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        try:
            infos = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
        except socket.gaierror as exc:
            raise SearxngError("http", f"could not resolve {host}") from exc
        addresses = {ipaddress.ip_address(info[4][0].split("%", 1)[0]) for info in infos}
    if not addresses or not all(_is_public_ip(ip) for ip in addresses):
        raise SearxngError("blocked", f"{host} is not a public internet address")


async def _check_request_destination(request: httpx.Request) -> None:
    await check_public_destination(str(request.url))


def _looks_like_pdf(content_type: str, body: bytes) -> bool:
    return "application/pdf" in content_type or body[:5] == b"%PDF-"


async def fetch_page(url: str, *, timeout: float = 15.0, follow_pdf: bool = False) -> FetchedPage:
    """Download a URL. PDFs are returned as bytes; HTML pages as extracted text.

    With follow_pdf=True a landing page that advertises a PDF (citation_pdf_url)
    is followed, so academic pages import as the full-text PDF.
    """
    headers = {
        "User-Agent": _user_agent_for(url),
        "Accept": "text/html,application/xhtml+xml,application/pdf;q=0.9,*/*;q=0.8",
        "Accept-Language": "tr,en;q=0.8,*;q=0.5",
    }
    async with httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=True,
        headers=headers,
        event_hooks={"request": [_check_request_destination]},
    ) as client:
        resp, body = await _download(client, url, MAX_PDF_BYTES)
        content_type = (resp.headers.get("content-type") or "").lower()
        final_url = str(resp.url)
        page = FetchedPage(url=url, final_url=final_url, content_type=content_type)

        if _looks_like_pdf(content_type, body):
            page.pdf_bytes = body
            return page
        if len(body) > MAX_PAGE_BYTES:
            raise SearxngError("http", "page too large")
        if "html" not in content_type and "xml" not in content_type and not body.lstrip()[:1] == b"<":
            if content_type.startswith("text/"):
                page.text = body.decode(resp.encoding or "utf-8", errors="replace")
                return page
            raise SearxngError("http", f"unsupported content type: {content_type or 'unknown'}")

        html = body.decode(resp.encoding or "utf-8", errors="replace")
        info = await asyncio.to_thread(extract_html, html, final_url)
        page.title = info["title"]
        page.text = info["text"]
        page.description = info["description"]
        page.authors = info["authors"]
        page.published = info["published"]
        page.site_name = info["site_name"]
        page.pdf_url = info["pdf_url"]

        if follow_pdf and page.pdf_url and page.pdf_url != final_url:
            try:
                pdf_resp, pdf_body = await _download(client, page.pdf_url, MAX_PDF_BYTES)
                if _looks_like_pdf((pdf_resp.headers.get("content-type") or "").lower(), pdf_body):
                    page.pdf_bytes = pdf_body
            except (httpx.HTTPError, SearxngError) as exc:
                logger.info(f"PDF link not downloadable ({page.pdf_url}): {exc}")
        return page


def relevant_excerpt(text: str, query: str, max_chars: int = 1500) -> str:
    """Paragraphs of `text` that best match the query words, in document order."""
    paragraphs = [p.strip() for p in re.split(r"\n{2,}", text) if len(p.strip()) > 40]
    if not paragraphs:
        return text[:max_chars]
    words = {w for w in re.findall(r"\w{3,}", query.lower())}
    scored = []
    for idx, para in enumerate(paragraphs):
        low = para.lower()
        hits = sum(1 for w in words if w in low)
        scored.append((hits, -idx, idx, para))
    chosen: list[tuple[int, str]] = []
    total = 0
    for hits, _neg, idx, para in sorted(scored, reverse=True):
        if total >= max_chars:
            break
        if hits == 0 and chosen:
            break
        chosen.append((idx, para))
        total += len(para)
    chosen.sort()
    out = "\n\n".join(p for _, p in chosen)
    return out[:max_chars].rstrip()
