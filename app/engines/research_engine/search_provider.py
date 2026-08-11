from __future__ import annotations

import html
import re
from abc import ABC, abstractmethod
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

import httpx

from app.core.cache import ttl_cache
from app.core.config import settings
from app.services.news import NewsService


class SearchProvider(ABC):
    @abstractmethod
    def search(self, query: str, limit: int = 6) -> list[dict]:
        raise NotImplementedError

    def search_images(self, query: str, limit: int = 3) -> list[dict]:
        _ = query, limit
        return []


class SerperSearchProvider(SearchProvider):
    """Google-ranked web and image search through Serper's API."""

    def __init__(self, api_key: str | None = None, base_url: str | None = None):
        self.api_key = api_key if api_key is not None else settings.search_api_key
        self.base_url = (base_url or settings.search_api_base_url or "https://google.serper.dev/search").rstrip("/")

    def search(self, query: str, limit: int = 6) -> list[dict]:
        if not self.api_key:
            return []
        result_limit = max(1, min(limit, 10))
        cache_key = f"research:serper:{query.strip().lower()}:{result_limit}"
        cached = ttl_cache.get(cache_key)
        if cached is not None:
            return cached
        try:
            with httpx.Client(timeout=10, follow_redirects=True, trust_env=False) as client:
                response = client.post(
                    self.base_url,
                    headers={"X-API-KEY": self.api_key, "Content-Type": "application/json"},
                    json={"q": query, "num": result_limit, "autocorrect": False},
                )
                response.raise_for_status()
                items = response.json().get("organic", [])
        except Exception:  # noqa: BLE001
            return []

        sources = []
        for item in items:
            url = str(item.get("link") or "").strip()
            if not url.startswith(("https://", "http://")):
                continue
            sources.append(
                {
                    "title": str(item.get("title") or url),
                    "url": url,
                    "source": str(item.get("domain") or urlparse(url).netloc.replace("www.", "")),
                    "snippet": str(item.get("snippet") or ""),
                }
            )
        ttl_cache.set(cache_key, sources, ttl_seconds=300)
        return sources

    def search_images(self, query: str, limit: int = 3) -> list[dict]:
        if not self.api_key:
            return []
        result_limit = max(1, min(limit, 10))
        cache_key = f"research:serper-images:{query.strip().lower()}:{result_limit}"
        cached = ttl_cache.get(cache_key)
        if cached is not None:
            return cached
        image_url = f"{self.base_url.rsplit('/', 1)[0]}/images"
        try:
            with httpx.Client(timeout=10, follow_redirects=True, trust_env=False) as client:
                response = client.post(
                    image_url,
                    headers={"X-API-KEY": self.api_key, "Content-Type": "application/json"},
                    json={"q": query, "num": result_limit, "autocorrect": False},
                )
                response.raise_for_status()
                items = response.json().get("images", [])
        except Exception:  # noqa: BLE001
            return []

        images = []
        for item in items:
            page_url = str(item.get("link") or "").strip()
            preview_url = str(item.get("imageUrl") or item.get("thumbnailUrl") or "").strip()
            if not page_url.startswith(("https://", "http://")) or not preview_url.startswith("https://"):
                continue
            images.append({"title": str(item.get("title") or "Live web image"), "url": page_url, "image_url": preview_url, "source": str(item.get("source") or item.get("domain") or urlparse(page_url).netloc.replace("www.", ""))})
        ttl_cache.set(cache_key, images, ttl_seconds=300)
        return images


class DuckDuckGoSearchProvider(SearchProvider):
    def search(self, query: str, limit: int = 6) -> list[dict]:
        cache_key = f"research:ddg:{query.strip().lower()}:{limit}"
        cached = ttl_cache.get(cache_key)
        if cached is not None:
            return cached
        url = f"https://api.duckduckgo.com/?q={quote_plus(query)}&format=json&no_html=1&skip_disambig=1"
        try:
            with httpx.Client(timeout=12, follow_redirects=True, trust_env=False) as client:
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
        result = sources[:limit]
        if not result:
            result = self._search_html(query, limit)
        if not result:
            result = self._search_news(query, limit)
        ttl_cache.set(cache_key, result, ttl_seconds=300)
        return result

    @staticmethod
    def _search_news(query: str, limit: int) -> list[dict]:
        """Use the configured news provider when general web search is unavailable."""
        try:
            brief = NewsService().for_automation(name=query, prompt=query)
        except Exception:  # noqa: BLE001
            return []
        return [
            {
                "title": article.title,
                "url": article.url or "",
                "source": article.source or brief.provider,
                "snippet": article.summary or "",
            }
            for article in brief.articles[:limit]
            if article.title and article.url
        ]

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
            with httpx.Client(timeout=12, follow_redirects=True, trust_env=False, headers={"User-Agent": "CEASER Research"}) as client:
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
