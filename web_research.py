"""
Web Research Engine & Pluggable Search Providers
=================================================

Performs live internet search to identify which real football club uses a stadium.
Supports pluggable search providers (Google Custom Search, Bing Web Search, DuckDuckGo, Wikipedia API),
multi-query two-pass search strategies, source tiering, and confidence scoring.
"""

from __future__ import annotations

import html
import json
import logging
import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional
from urllib.parse import quote_plus, urlencode

import requests


@dataclass
class SearchResultItem:
    """A single web search result."""
    title: str
    snippet: str
    url: str
    provider: str


@dataclass
class EvidenceItem:
    """Evidence snippet linking a stadium to a football club."""
    source_name: str
    url: str
    statement: str
    tier: int  # Level 1 = Official club, Level 2 = League/Federation, Level 3 = Database/News


@dataclass
class StadiumResearchResult:
    """Auditable research result for a stadium."""
    stadium_name: str
    club_name: str | None = None
    alternative_clubs: list[str] = field(default_factory=list)
    confidence: float = 0.0
    evidence: list[EvidenceItem] = field(default_factory=list)
    reasoning: str = ""
    is_shared: bool = False
    is_historical: bool = False
    error: str | None = None
    search_queries_used: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert research result to serializable dict for JSON cache."""
        return {
            "stadium_name": self.stadium_name,
            "club_name": self.club_name,
            "alternative_clubs": self.alternative_clubs,
            "confidence": round(self.confidence, 3),
            "reasoning": self.reasoning,
            "is_shared": self.is_shared,
            "is_historical": self.is_historical,
            "error": self.error,
            "queries": self.search_queries_used,
            "evidence": [
                {
                    "source": e.source_name,
                    "url": e.url,
                    "statement": e.statement,
                    "tier": e.tier,
                }
                for e in self.evidence
            ],
        }


# ---------------------------------------------------------------------------
# Pluggable Search Providers
# ---------------------------------------------------------------------------

class WebSearchProvider(ABC):
    """Abstract base class for search engine providers."""

    @abstractmethod
    def search(self, query: str, num_results: int = 5) -> list[SearchResultItem]:
        """Execute a web search query and return result items."""
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Name of the search provider."""
        pass


class GoogleSearchProvider(WebSearchProvider):
    """Google Custom Search JSON API provider."""

    API_URL = "https://customsearch.googleapis.com/customsearch/v1"

    def __init__(self, api_key: str, search_engine_id: str, logger: logging.Logger | None = None):
        self.api_key = api_key
        self.cx = search_engine_id
        self.logger = logger or logging.getLogger("stadium_mapper.search.google")

    @property
    def name(self) -> str:
        return "Google Custom Search"

    def search(self, query: str, num_results: int = 5) -> list[SearchResultItem]:
        if not self.api_key or not self.cx:
            self.logger.warning("Google Search API key or Search Engine ID missing.")
            return []

        results: list[SearchResultItem] = []
        try:
            params = {
                "key": self.api_key,
                "cx": self.cx,
                "q": query,
                "num": min(num_results, 10),
            }
            resp = requests.get(self.API_URL, params=params, timeout=12)
            resp.raise_for_status()
            data = resp.json()

            for item in data.get("items", []):
                results.append(SearchResultItem(
                    title=item.get("title", ""),
                    snippet=item.get("snippet", ""),
                    url=item.get("link", ""),
                    provider=self.name,
                ))
        except Exception as e:
            self.logger.warning(f"Google Search API error: {e}")

        return results


class BingSearchProvider(WebSearchProvider):
    """Bing Web Search API v7 provider."""

    API_URL = "https://api.bing.microsoft.com/v7.0/search"

    def __init__(self, api_key: str, logger: logging.Logger | None = None):
        self.api_key = api_key
        self.logger = logger or logging.getLogger("stadium_mapper.search.bing")

    @property
    def name(self) -> str:
        return "Bing Web Search"

    def search(self, query: str, num_results: int = 5) -> list[SearchResultItem]:
        if not self.api_key:
            self.logger.warning("Bing API key missing.")
            return []

        results: list[SearchResultItem] = []
        headers = {"Ocp-Apim-Subscription-Key": self.api_key}
        params = {"q": query, "count": num_results}
        try:
            resp = requests.get(self.API_URL, headers=headers, params=params, timeout=12)
            resp.raise_for_status()
            data = resp.json()

            for item in data.get("webPages", {}).get("value", []):
                results.append(SearchResultItem(
                    title=item.get("name", ""),
                    snippet=item.get("snippet", ""),
                    url=item.get("url", ""),
                    provider=self.name,
                ))
        except Exception as e:
            self.logger.warning(f"Bing Search API error: {e}")

        return results


class WikipediaSearchProvider(WebSearchProvider):
    """Wikipedia MediaWiki API search provider."""

    API_URL = "https://en.wikipedia.org/w/api.php"

    def __init__(self, logger: logging.Logger | None = None):
        self.logger = logger or logging.getLogger("stadium_mapper.search.wiki")
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "PES2021StadiumMapper/2.0 (https://github.com/pes-stadium-mapper)"
        })

    @property
    def name(self) -> str:
        return "Wikipedia API"

    def search(self, query: str, num_results: int = 5) -> list[SearchResultItem]:
        results: list[SearchResultItem] = []
        try:
            # 1. Search titles
            search_params = {
                "action": "query",
                "list": "search",
                "srsearch": query,
                "format": "json",
                "utf8": 1,
                "srlimit": num_results,
            }
            resp = self.session.get(self.API_URL, params=search_params, timeout=10)
            if resp.status_code == 429:
                time.sleep(2.0)
                resp = self.session.get(self.API_URL, params=search_params, timeout=10)
            resp.raise_for_status()
            data = resp.json()

            search_hits = data.get("query", {}).get("search", [])
            if not search_hits:
                return []

            # 2. Get lead extract for top result
            top_title = search_hits[0]["title"]
            extract_params = {
                "action": "query",
                "titles": top_title,
                "prop": "extracts",
                "exintro": True,
                "explaintext": True,
                "format": "json",
                "utf8": 1,
            }
            resp = self.session.get(self.API_URL, params=extract_params, timeout=10)
            resp.raise_for_status()
            ext_data = resp.json()

            pages = ext_data.get("query", {}).get("pages", {})
            for pid, page in pages.items():
                if pid == "-1":
                    continue
                extract = page.get("extract", "")
                wiki_url = f"https://en.wikipedia.org/wiki/{quote_plus(top_title.replace(' ', '_'))}"
                results.append(SearchResultItem(
                    title=top_title,
                    snippet=extract[:500] if extract else search_hits[0].get("snippet", ""),
                    url=wiki_url,
                    provider=self.name,
                ))
        except Exception as e:
            self.logger.warning(f"Wikipedia search error: {e}")

        return results


class DuckDuckGoSearchProvider(WebSearchProvider):
    """DuckDuckGo HTML & Instant Answer Provider (Keyless Fallback)."""

    DDG_HTML = "https://html.duckduckgo.com/html/"
    DDG_API = "https://api.duckduckgo.com/"

    def __init__(self, logger: logging.Logger | None = None):
        self.logger = logger or logging.getLogger("stadium_mapper.search.ddg")
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            )
        })

    @property
    def name(self) -> str:
        return "DuckDuckGo"

    def search(self, query: str, num_results: int = 5) -> list[SearchResultItem]:
        results: list[SearchResultItem] = []

        # 1. Instant Answer API
        try:
            params = {"q": query, "format": "json", "no_html": 1}
            resp = self.session.get(self.DDG_API, params=params, timeout=8)
            if resp.status_code == 200:
                data = resp.json()
                abstract = data.get("Abstract", "")
                url = data.get("AbstractURL", "")
                if abstract:
                    results.append(SearchResultItem(
                        title=data.get("Heading", query),
                        snippet=abstract,
                        url=url,
                        provider=self.name,
                    ))
        except Exception:
            pass

        # 2. HTML search fallback
        try:
            time.sleep(1.2)  # Rate limiting
            resp = self.session.post(self.DDG_HTML, data={"q": query}, timeout=10)
            if resp.status_code == 200:
                snippets = re.findall(r'<a class="result__snippet"[^>]*>(.*?)</a>', resp.text, re.DOTALL)
                urls = re.findall(r'<a class="result__url"[^>]*href="([^"]+)"', resp.text)

                for i, snip in enumerate(snippets[:num_results]):
                    clean_snip = html.unescape(re.sub(r"<[^>]+>", "", snip)).strip()
                    item_url = urls[i] if i < len(urls) else ""
                    results.append(SearchResultItem(
                        title=query,
                        snippet=clean_snip,
                        url=item_url,
                        provider=self.name,
                    ))
        except Exception as e:
            self.logger.warning(f"DuckDuckGo HTML search error: {e}")

        return results


# ---------------------------------------------------------------------------
# Two-Pass Multi-Query Research Engine
# ---------------------------------------------------------------------------

class WebStadiumResearcher:
    """
    Intelligent two-pass research engine.

    Determines which football club owns/uses a stadium based on evidence extracted from web searches.
    """

    # Patterns indicating team-stadium relationship
    RELATIONSHIP_PATTERNS = [
        re.compile(r"home\s+(?:ground|stadium|venue)\s+(?:of|for)\s+(.+?)(?:\.|\,|$)", re.I),
        re.compile(r"(?:is|was)\s+the\s+home\s+(?:ground|stadium|venue)?\s*(?:of|for)\s+(.+?)(?:\.|\,|$)", re.I),
        re.compile(r"home\s+(?:to|of)\s+(.+?)(?:\.|\,|$)", re.I),
        re.compile(r"(.+?)\s+play\s+(?:their|at)\s+home\s+(?:matches|games)\s+at", re.I),
        re.compile(r"(.+?)(?:'s|'s)\s+home\s+(?:ground|stadium|venue)", re.I),
        re.compile(r"stadium\s+(?:of|for|used\s+by)\s+(.+?)(?:\.|\,|$)", re.I),
        re.compile(r"used\s+(?:by|as\s+home)\s+(.+?)(?:\.|\,|$)", re.I),
    ]

    # Descriptor prefixes to strip from extracted club names
    DESCRIPTORS = [
        "Premier League football club", "EFL Championship football club", "Championship football club",
        "Premier League club", "EFL Championship club", "Championship club",
        "English football club", "football club", "rugby league club",
        "association football club", "professional football club", "club",
        "English club", "Spanish club", "German club", "Italian club", "French club",
    ]

    # Level 1 and 2 domain keywords for tiering
    OFFICIAL_LEAGUE_DOMAINS = [
        "premierleague.com", "uefa.com", "laliga.com", "bundesliga.com",
        "legaseriea.it", "lFP.fr", "efl.com", "fifa.com"
    ]

    def __init__(
        self,
        providers: list[WebSearchProvider] | None = None,
        logger: logging.Logger | None = None,
    ):
        self.logger = logger or logging.getLogger("stadium_mapper.researcher")
        # Default providers: Wikipedia + DuckDuckGo if none specified
        self.providers = providers or [
            WikipediaSearchProvider(logger=self.logger),
            DuckDuckGoSearchProvider(logger=self.logger),
        ]

    def identify_stadium_club(self, stadium_name: str) -> StadiumResearchResult:
        """
        Executes two-pass multi-query web research for a stadium.
        """
        self.logger.info(f"Starting web research for stadium: '{stadium_name}'")
        result = StadiumResearchResult(stadium_name=stadium_name)

        # PASS 1: Fast queries
        pass1_queries = [
            f'"{stadium_name}" football stadium home club',
            f'"{stadium_name}" home ground team',
        ]

        candidate_counts: dict[str, float] = {}
        found_evidence: list[EvidenceItem] = []

        for query in pass1_queries:
            result.search_queries_used.append(query)
            items = self._execute_query_across_providers(query)

            for item in items:
                club = self._extract_club_from_snippet(item.snippet, stadium_name)
                if club:
                    tier = self._determine_source_tier(item.url)
                    weight = 1.5 if tier == 1 else (1.2 if tier == 2 else 1.0)
                    candidate_counts[club] = candidate_counts.get(club, 0.0) + weight
                    found_evidence.append(EvidenceItem(
                        source_name=item.provider,
                        url=item.url,
                        statement=item.snippet[:300],
                        tier=tier,
                    ))

        # Evaluate Pass 1
        if candidate_counts:
            sorted_candidates = sorted(candidate_counts.items(), key=lambda x: x[1], reverse=True)
            top_club, top_score = sorted_candidates[0]

            # High confidence threshold in Pass 1
            if top_score >= 2.0 or len(sorted_candidates) == 1:
                result.club_name = top_club
                result.confidence = min(0.60 + (top_score * 0.15), 0.98)
                result.evidence = found_evidence
                result.reasoning = f"Pass 1 search identified {top_club} with high agreement across sources."

                if len(sorted_candidates) > 1:
                    result.alternative_clubs = [c for c, _ in sorted_candidates[1:]]
                    if sorted_candidates[1][1] >= 1.5:
                        result.is_shared = True
                        result.reasoning += f" SHARED stadium candidate: {result.alternative_clubs[0]}"

                self.logger.info(f"Pass 1 SUCCESS for '{stadium_name}' -> '{top_club}' (conf={result.confidence:.2f})")
                return result

        # PASS 2: Deep queries (for uncertain stadiums)
        self.logger.info(f"Pass 1 inconclusive for '{stadium_name}'. Initiating Pass 2 deep research...")
        pass2_queries = [
            f'"{stadium_name}" home of',
            f'"{stadium_name}" football team',
        ]

        for query in pass2_queries:
            result.search_queries_used.append(query)
            items = self._execute_query_across_providers(query)

            for item in items:
                club = self._extract_club_from_snippet(item.snippet, stadium_name)
                if club:
                    tier = self._determine_source_tier(item.url)
                    weight = 1.0
                    candidate_counts[club] = candidate_counts.get(club, 0.0) + weight
                    found_evidence.append(EvidenceItem(
                        source_name=item.provider,
                        url=item.url,
                        statement=item.snippet[:300],
                        tier=tier,
                    ))

        result.evidence = found_evidence

        if candidate_counts:
            sorted_candidates = sorted(candidate_counts.items(), key=lambda x: x[1], reverse=True)
            top_club, top_score = sorted_candidates[0]
            result.club_name = top_club
            result.confidence = min(0.40 + (top_score * 0.10), 0.85)
            result.reasoning = f"Pass 2 deep research resolved {top_club}."

            if len(sorted_candidates) > 1:
                result.alternative_clubs = [c for c, _ in sorted_candidates[1:] if c != top_club]
                if sorted_candidates[1][1] >= 2.0:
                    result.is_shared = True
                    result.reasoning += f" Shared venue candidate: {result.alternative_clubs[0]}"
        else:
            result.confidence = 0.0
            result.reasoning = "No clear football club evidence found in search results."
            result.error = "Unresolved stadium owner"

        self.logger.info(f"Research finished for '{stadium_name}': Club='{result.club_name}', Conf={result.confidence:.2f}")
        return result

    def _execute_query_across_providers(self, query: str) -> list[SearchResultItem]:
        """Run query across registered search providers."""
        all_items: list[SearchResultItem] = []
        for provider in self.providers:
            try:
                items = provider.search(query, num_results=4)
                all_items.extend(items)
                if items:
                    break  # Got results from primary provider
            except Exception as e:
                self.logger.warning(f"Provider {provider.name} failed for query '{query}': {e}")
        return all_items

    def _extract_club_from_snippet(self, text: str, stadium_name: str) -> str | None:
        """Extract club name from snippet text using regex patterns."""
        if not text:
            return None

        for pattern in self.RELATIONSHIP_PATTERNS:
            m = pattern.search(text)
            if m:
                raw_club = m.group(1).strip()
                cleaned = self._clean_club_name(raw_club)
                if cleaned and stadium_name.lower() not in cleaned.lower():
                    return cleaned

        return None

    def _clean_club_name(self, name: str) -> str:
        """Clean descriptor prefixes and trailing punctuation from club name."""
        name = name.strip()
        name = re.sub(r"[,\.\;\:\!\?]+$", "", name)

        for desc in self.DESCRIPTORS:
            if name.lower().startswith(desc.lower() + " "):
                name = name[len(desc):].strip()

        for suffix in [" in ", " since ", " from ", " and ", " which ", " who "]:
            idx = name.lower().find(suffix)
            if idx > 0:
                name = name[:idx]

        name = re.sub(r"^(?:the|a|an)\s+", "", name, flags=re.I)
        return name.strip()

    def _determine_source_tier(self, url: str) -> int:
        """Determine source authority level from URL."""
        if not url:
            return 3
        url_lower = url.lower()
        for dom in self.OFFICIAL_LEAGUE_DOMAINS:
            if dom in url_lower:
                return 2
        if any(w in url_lower for w in ["official", "club", "fc.com"]):
            return 1
        return 3
