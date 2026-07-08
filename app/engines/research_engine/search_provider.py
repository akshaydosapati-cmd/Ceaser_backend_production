from __future__ import annotations

import html
import re
from abc import ABC, abstractmethod
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

import httpx


class SearchProvider(ABC):
    @abstractmethod
    def search(self, query: str, limit: int = 6) -> list[dict]:
        raise NotImplementedError


class DuckDuckGoSearchProvider(SearchProvider):
    def search(self, query: str, limit: int = 6) -> list[dict]:
        url = f"https://api.duckduckgo.com/?q={quote_plus(query)}&format=json&no_html=1&skip_disambig=1"
        try:
            with httpx.Client(timeout=12, follow_redirects=True) as client:
                response = client.get(url)
                response.raise_for_status()
                data = response.json()
        except Exception:  # noqa: BLE001
            return []

        sources = []
        if data.get("AbstractURL"):
            sources.append(
                {
                    "title": data.get("Heading") or query,
                    "url": data.get("AbstractURL"),
                    "source": "DuckDuckGo",
                    "snippet": data.get("AbstractText") or data.get("Abstract") or "",
                }
            )
        for item in self._flatten_related(data.get("RelatedTopics", [])):
            if item.get("FirstURL") and item.get("Text"):
                sources.append(
                    {
                        "title": item.get("Text", "").split(" - ")[0][:120],
                        "url": item["FirstURL"],
                        "source": "DuckDuckGo",
                        "snippet": item.get("Text", ""),
                    }
                )
            if len(sources) >= limit:
                break
        if not sources:
            sources = self._search_html(query=query, limit=limit)
        return sources[:limit]

    def _flatten_related(self, items: list[dict]) -> list[dict]:
        flattened = []
        for item in items:
            if "Topics" in item:
                flattened.extend(self._flatten_related(item["Topics"]))
            else:
                flattened.append(item)
        return flattened

    def _search_html(self, query: str, limit: int) -> list[dict]:
        url = f"https://duckduckgo.com/html/?q={quote_plus(query)}"
        try:
            with httpx.Client(timeout=12, follow_redirects=True, headers={"User-Agent": "CEASER Research"}) as client:
                response = client.get(url)
                response.raise_for_status()
                body = response.text
        except Exception:  # noqa: BLE001
            return []

        title_matches = re.findall(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', body, flags=re.IGNORECASE | re.DOTALL)
        snippet_matches = re.findall(r'<a[^>]+class="result__snippet"[^>]*>(.*?)</a>', body, flags=re.IGNORECASE | re.DOTALL)
        sources = []
        for index, (raw_url, raw_title) in enumerate(title_matches[:limit]):
            clean_url = self._clean_result_url(html.unescape(raw_url))
            sources.append(
                {
                    "title": self._strip_tags(raw_title),
                    "url": clean_url,
                    "source": urlparse(clean_url).netloc.replace("www.", "") or "DuckDuckGo",
                    "snippet": self._strip_tags(snippet_matches[index]) if index < len(snippet_matches) else "",
                }
            )
        return sources

    def _strip_tags(self, value: str) -> str:
        return re.sub(r"<[^>]+>", "", html.unescape(value)).strip()

    def _clean_result_url(self, value: str) -> str:
        parsed = urlparse(value)
        query = parse_qs(parsed.query)
        if "uddg" in query:
            return unquote(query["uddg"][0])
        return value
