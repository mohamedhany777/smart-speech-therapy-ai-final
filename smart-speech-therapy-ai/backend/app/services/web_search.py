"""
Web retrieval — Layer 2 of the hybrid knowledge system (spec sections 14-15).

Only activates when TAVILY_API_KEY is set (see app/core/config.py). Tavily
was chosen because it's a search API purpose-built for LLM/RAG use cases
(returns clean snippets rather than raw HTML) with a simple single-key
setup. The interface (`WebSearchProvider`) is generic — swapping to Google
Custom Search, Bing, or Serper only means writing another class here.

Makes a real HTTPS call via `httpx` — not testable live in the sandbox this
was built in (network allowlist blocks api.tavily.com), so verify end-to-end
once a real key is configured.

Trusted-source filtering (spec section 15: prefer professional/academic/
government sources, avoid random blogs/forums) is applied client-side after
retrieval, since Tavily doesn't accept an arbitrary domain-preference list —
`_score_domain_trust()` is pure logic and IS tested without needing network
access.
"""
from abc import ABC, abstractmethod
from urllib.parse import urlparse

from app.core.config import settings

TRUSTED_TLDS = (".gov", ".edu")
TRUSTED_DOMAIN_KEYWORDS = (
    "who.int",
    "nih.gov",
    "asha.org",  # American Speech-Language-Hearing Association
    "cdc.gov",
    "nhs.uk",
    "mayoclinic.org",
    "pubmed",
    "ncbi.nlm.nih.gov",
)
DISCOURAGED_DOMAIN_KEYWORDS = ("blogspot", "forum", "reddit.com", "quora.com", "pinterest")


def _score_domain_trust(url: str) -> float:
    """Pure, testable scoring logic — higher is more trustworthy per spec
    section 15's guidance (professional orgs, universities, government
    health bodies, peer-reviewed sources; avoid blogs/forums/social media)."""
    domain = urlparse(url).netloc.lower()

    if any(k in domain for k in DISCOURAGED_DOMAIN_KEYWORDS):
        return 0.1
    if domain.endswith(TRUSTED_TLDS):
        return 1.0
    if any(k in domain for k in TRUSTED_DOMAIN_KEYWORDS):
        return 1.0
    if domain.endswith(".org"):
        return 0.7
    return 0.4


class WebSearchProvider(ABC):
    name: str

    @abstractmethod
    def search(self, query: str, max_results: int = 5) -> list[dict]:
        """Return [{"title", "url", "snippet", "domain", "trust_score"}, ...],
        sorted by trust_score descending."""


class TavilySearchProvider(WebSearchProvider):
    name = "tavily"

    def search(self, query: str, max_results: int = 5) -> list[dict]:
        import httpx

        response = httpx.post(
            "https://api.tavily.com/search",
            json={
                "api_key": settings.TAVILY_API_KEY,
                "query": query,
                "max_results": max_results,
                "search_depth": "basic",
            },
            timeout=15.0,
        )
        response.raise_for_status()
        data = response.json()

        results = []
        for item in data.get("results", []):
            url = item.get("url", "")
            results.append(
                {
                    "title": item.get("title"),
                    "url": url,
                    "snippet": item.get("content"),
                    "domain": urlparse(url).netloc,
                    "trust_score": _score_domain_trust(url),
                }
            )
        results.sort(key=lambda r: r["trust_score"], reverse=True)
        return results


class UnavailableWebSearchProvider(WebSearchProvider):
    name = "unavailable"

    def search(self, query: str, max_results: int = 5) -> list[dict]:
        return []


def is_configured() -> bool:
    return bool(settings.TAVILY_API_KEY)


def get_web_search_provider() -> WebSearchProvider:
    if settings.TAVILY_API_KEY:
        return TavilySearchProvider()
    return UnavailableWebSearchProvider()
