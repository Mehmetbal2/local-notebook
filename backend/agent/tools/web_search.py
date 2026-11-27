import asyncio
import json
import logging
from typing import Optional

from pydantic import BaseModel, Field

from kosong.tooling import CallableTool2, ToolOk, ToolError, ToolReturnValue

from agent.tools.query_knowledge_base import CitationState

logger = logging.getLogger("tool.web_search")

# How many of the top SearXNG hits are opened to read their text.
SEARXNG_PAGES_TO_READ = 3
SEARXNG_PAGE_TIMEOUT = 8.0
EXCERPT_CHARS = 1500
# Text read from a PDF search hit before the relevant excerpt is chosen.
PDF_MAX_TEXT_CHARS = 400_000


class WebSearchParams(BaseModel):
    query: str = Field(description="Search query.")
    max_results: int = Field(default=5, description="Number of results to return. Default is 5.")
    freshness: str = Field(
        default="noLimit",
        description=(
            "Time range: noLimit, oneDay, oneWeek, oneMonth, or oneYear."
        ),
    )


class WebSearchTool(CallableTool2[WebSearchParams]):
    name: str = "web_search"
    description: str = (
        "Search the internet for current information. Use it for news, industry "
        "updates, people or organization information, public reviews, related "
        "materials, or content not covered by the documents. Search results include "
        "citation markers in `[citation_X]` format; use them in the answer."
    )
    params: type[WebSearchParams] = WebSearchParams

    def __init__(
        self,
        citation_state: Optional[CitationState] = None,
        base_url: str = "",
    ):
        super().__init__()
        self.state = citation_state or CitationState()
        self.base_url = base_url

    @classmethod
    async def create(cls, citation_state: Optional[CitationState] = None) -> "WebSearchTool":
        """Build the tool for the SearXNG address configured in Settings."""
        import config

        return cls(citation_state=citation_state, base_url=await config.resolve_searxng_url())

    async def __call__(self, params: WebSearchParams) -> ToolReturnValue:
        query = params.query.strip()
        if not query:
            return ToolError(message="Search query must not be empty", brief="empty query")
        max_results = max(1, min(int(params.max_results or 5), 10))
        return await self._searxng(query, max_results, params.freshness)

    # ── citations ──────────────────────────────────────────────────────────

    def _add_result(self, results: list, *, title: str, url: str, snippet: str, source: str,
                    published_date: str, content: str = "") -> None:
        state = self.state
        citation_id = f"citation_{state.citation_counter}"
        entry = {
            "citation_id": f"[{citation_id}]",
            "title": title,
            "url": url,
            "snippet": snippet[:300] if snippet else "",
            "source": source,
            "published_date": published_date,
        }
        if content:
            entry["page_text"] = content
        results.append(entry)
        state.citations_map[citation_id] = {
            "type": "web",
            "title": title,
            "url": url,
            "snippet": (content or snippet or "")[:500],
            "source": source,
            "published_date": published_date,
            "favicon": "",
        }
        state.citation_counter += 1

    # ── SearXNG (local metasearch) ─────────────────────────────────────────

    async def _searxng(self, query: str, max_results: int, freshness: str) -> ToolReturnValue:
        from services import searxng_client as sx

        try:
            logger.info(f"web search (searxng): {query}")
            hits = await sx.search(
                self.base_url,
                query,
                time_range=sx.FRESHNESS_TO_TIME_RANGE.get(freshness),
            )
        except sx.SearxngError as exc:
            if exc.code == "unreachable":
                msg = (
                    f"Web search is unavailable: SearXNG does not answer at {self.base_url}. "
                    "Docker/OrbStack may be closed. Tell the user web search is offline."
                )
            elif exc.code == "json_disabled":
                msg = "SearXNG refused the JSON API (enable `json` under search.formats in settings.yml)."
            elif exc.code == "rate_limited":
                msg = "SearXNG rate limit reached. Try again shortly."
            elif exc.code == "timeout":
                msg = "Search request timed out. Try again later."
            else:
                msg = f"Search request failed: {exc}"
            return ToolError(message=msg, brief=exc.code)

        hits = hits[:max_results]
        if not hits:
            return ToolOk(output="No relevant search results found")

        # Read the text of the top pages so answers rest on more than a snippet.
        async def read(hit):
            try:
                # Scholarly hits often carry a free PDF: read that instead of the abstract page.
                target = hit.pdf_url or hit.url
                page = await asyncio.wait_for(sx.fetch_page(target, timeout=SEARXNG_PAGE_TIMEOUT), SEARXNG_PAGE_TIMEOUT + 2)
            except Exception as exc:  # unreachable pages just keep their snippet
                logger.debug(f"page not read ({hit.url}): {exc}")
                return ""
            if page.is_pdf:
                return await asyncio.to_thread(_pdf_text, page.pdf_bytes or b"", query)
            return sx.relevant_excerpt(page.text, query, EXCERPT_CHARS) if page.text else ""

        texts = await asyncio.gather(*(read(h) for h in hits[:SEARXNG_PAGES_TO_READ]))
        texts = list(texts) + [""] * (len(hits) - len(texts))

        results: list = []
        for hit, text in zip(hits, texts):
            self._add_result(
                results,
                title=hit.title,
                url=hit.url,
                snippet=hit.content,
                source=hit.domain,
                published_date=hit.published_date,
                content=text,
            )
        logger.info(f"Search succeeded, got {len(results)} results ({sum(1 for t in texts if t)} pages read)")
        return ToolOk(output=json.dumps(results, ensure_ascii=False))


def _pdf_text(data: bytes, query: str) -> str:
    """Relevant text from the first pages of a PDF search hit."""
    from services.searxng_client import relevant_excerpt
    from workers.parsers.pdf_limits import extract_plain_text

    text = extract_plain_text(data, max_pages=12, max_chars=PDF_MAX_TEXT_CHARS)
    return relevant_excerpt(text, query, EXCERPT_CHARS) if text else ""
