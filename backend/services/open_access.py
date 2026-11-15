"""Find the legally free full text of scholarly works.

Academic search results often point to a publisher page that shows only the
abstract. OpenAlex (and Semantic Scholar as a fallback) know where an open
access copy lives: the publisher's own free PDF, a repository copy (author
manuscript) or a preprint server. Both are free public APIs.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from urllib.parse import quote

import httpx

logger = logging.getLogger("open_access")

OPENALEX_WORKS = "https://api.openalex.org/works"
S2_PAPER = "https://api.semanticscholar.org/graph/v1/paper"
USER_AGENT = "LocalNotebook/1.0 (open-access lookup)"
OPENALEX_BATCH = 50

DOI_RE = re.compile(r"\b(10\.\d{4,9}/[^\s\"<>#?]+)", re.IGNORECASE)
ARXIV_RE = re.compile(r"arxiv\.org/(?:abs|pdf)/([0-9]{4}\.[0-9]{4,5}(?:v\d+)?|[a-z\-]+(?:\.[A-Z]{2})?/\d{7}(?:v\d+)?)", re.IGNORECASE)
# Crossref also registers peer-review reports and decision letters ("/v2/review1", "/v1/decision1").
REVIEW_DOI_RE = re.compile(r"/v\d+/(?:review|decision|response|reply|author-response)\d*$", re.IGNORECASE)


@dataclass
class OpenAccessInfo:
    doi: str = ""
    is_oa: bool = False
    pdf_urls: list[str] = field(default_factory=list)  # direct PDF links, best first
    landing_url: str = ""   # free landing page (repository record etc.)
    title: str = ""
    authors: list[str] = field(default_factory=list)
    year: str = ""
    venue: str = ""


def normalize_doi(value: str | None) -> str:
    """Bare lower-case DOI ("10.1177/abc") from a DOI, doi.org/oadoi.org URL or text."""
    if not value:
        return ""
    match = DOI_RE.search(value)
    if not match:
        return ""
    doi = match.group(1).rstrip(".,;:)]}'\"")
    return doi.lower()


def is_review_record(doi: str, title: str = "") -> bool:
    if doi and REVIEW_DOI_RE.search(doi):
        return True
    low = (title or "").strip().lower()
    return low.startswith(("decision letter for", "review for", "author response for", "reviewer report"))


def arxiv_pdf_url(url: str) -> str:
    match = ARXIV_RE.search(url or "")
    return f"https://arxiv.org/pdf/{match.group(1)}" if match else ""


def _from_openalex(work: dict) -> OpenAccessInfo:
    oa = work.get("open_access") or {}
    pdfs: list[str] = []
    best = work.get("best_oa_location") or {}
    if best.get("pdf_url"):
        pdfs.append(best["pdf_url"])
    for loc in work.get("locations") or []:
        url = (loc or {}).get("pdf_url")
        if url and url not in pdfs and (loc.get("is_oa") is not False):
            pdfs.append(url)
    oa_url = oa.get("oa_url") or ""
    if oa_url.lower().endswith(".pdf") and oa_url not in pdfs:
        pdfs.append(oa_url)
    source = ((work.get("primary_location") or {}).get("source") or {})
    year = work.get("publication_year")
    return OpenAccessInfo(
        doi=normalize_doi(work.get("doi")),
        is_oa=bool(oa.get("is_oa")),
        pdf_urls=pdfs,
        landing_url=(best.get("landing_page_url") or oa_url or "") if oa.get("is_oa") else "",
        title=(work.get("display_name") or "").strip(),
        authors=[
            ((a or {}).get("author") or {}).get("display_name", "")
            for a in (work.get("authorships") or [])
            if ((a or {}).get("author") or {}).get("display_name")
        ][:20],
        year=str(year) if year else "",
        venue=(source.get("display_name") or "").strip(),
    )


async def openalex_lookup(dois: list[str], timeout: float = 12.0) -> dict[str, OpenAccessInfo]:
    """Open-access data for many DOIs (one request per 50). Missing DOIs are left out."""
    wanted = sorted({normalize_doi(d) for d in dois if normalize_doi(d)})
    found: dict[str, OpenAccessInfo] = {}
    if not wanted:
        return found
    select = "doi,display_name,publication_year,authorships,open_access,best_oa_location,locations,primary_location"
    async with httpx.AsyncClient(timeout=timeout, headers={"User-Agent": USER_AGENT}) as client:
        for start in range(0, len(wanted), OPENALEX_BATCH):
            batch = wanted[start:start + OPENALEX_BATCH]
            try:
                resp = await client.get(
                    OPENALEX_WORKS,
                    params={"filter": "doi:" + "|".join(batch), "select": select, "per-page": OPENALEX_BATCH},
                )
                if resp.status_code != 200:
                    logger.info(f"OpenAlex lookup failed: HTTP {resp.status_code}")
                    continue
                for work in resp.json().get("results") or []:
                    info = _from_openalex(work)
                    if info.doi:
                        found[info.doi] = info
            except (httpx.HTTPError, ValueError) as exc:
                logger.info(f"OpenAlex lookup failed: {exc}")
    return found


async def semantic_scholar_lookup(doi: str, timeout: float = 10.0) -> OpenAccessInfo | None:
    doi = normalize_doi(doi)
    if not doi:
        return None
    try:
        async with httpx.AsyncClient(timeout=timeout, headers={"User-Agent": USER_AGENT}) as client:
            resp = await client.get(
                f"{S2_PAPER}/DOI:{quote(doi, safe='/')}",
                params={"fields": "title,year,authors,venue,openAccessPdf,isOpenAccess"},
            )
        if resp.status_code != 200:
            return None
        data = resp.json()
    except (httpx.HTTPError, ValueError):
        return None
    pdf = ((data.get("openAccessPdf") or {}).get("url") or "").strip()
    return OpenAccessInfo(
        doi=doi,
        is_oa=bool(data.get("isOpenAccess") or pdf),
        pdf_urls=[pdf] if pdf else [],
        title=(data.get("title") or "").strip(),
        authors=[a.get("name", "") for a in (data.get("authors") or []) if a.get("name")][:20],
        year=str(data.get("year") or ""),
        venue=(data.get("venue") or "").strip(),
    )


async def resolve_open_access(doi: str) -> OpenAccessInfo | None:
    """Best known open-access data for one DOI: OpenAlex, then Semantic Scholar for a PDF."""
    doi = normalize_doi(doi)
    if not doi:
        return None
    info = (await openalex_lookup([doi])).get(doi)
    if info is None or not info.pdf_urls:
        s2 = await semantic_scholar_lookup(doi)
        if s2 is not None:
            if info is None:
                return s2
            info.pdf_urls.extend(u for u in s2.pdf_urls if u not in info.pdf_urls)
            info.is_oa = info.is_oa or s2.is_oa
    return info
