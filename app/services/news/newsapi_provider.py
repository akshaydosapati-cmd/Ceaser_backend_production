from __future__ import annotations

from typing import Any

import httpx

from app.core.cache import ttl_cache
from app.core.config.settings import settings
from app.services.news.schemas import NewsArticle, NewsBrief


class NewsApiProvider:
    provider_name = "newsapi"
    default_base_url = "https://newsapi.org/v2"

    CATEGORY_ALIASES = {
        "ai": "technology",
        "artificial intelligence": "technology",
        "startup": "business",
        "startups": "business",
        "funding": "business",
        "healthtech": "health",
        "healthcare": "health",
        "medical": "health",
        "tech": "technology",
        "technology": "technology",
        "business": "business",
        "world": "general",
        "latest": "general",
        "general": "general",
        "health": "health",
        "science": "science",
        "sport": "sports",
        "sports": "sports",
        "entertainment": "entertainment",
    }

    def configured(self) -> bool:
        return bool(settings.news_api_key)

    def latest(self) -> NewsBrief:
        return self.category("general")

    def category(self, category: str) -> NewsBrief:
        normalized = self._category(category)
        return self._request(
            path="/top-headlines",
            query=normalized,
            mode=f"category:{normalized}",
            params={
                "country": settings.news_default_region.lower(),
                "category": normalized,
                "pageSize": str(settings.news_max_items),
            },
        )

    def search(self, query: str) -> NewsBrief:
        cleaned = query.strip() or "latest news"
        return self._request(
            path="/everything",
            query=cleaned,
            mode="search",
            params={
                "q": cleaned,
                "language": settings.news_default_language,
                "sortBy": "publishedAt",
                "pageSize": str(settings.news_max_items),
            },
        )

    def _request(self, *, path: str, query: str, mode: str, params: dict[str, str]) -> NewsBrief:
        if not self.configured():
            return NewsBrief(query=query, mode=mode, provider=self.provider_name, articles=[], error="NewsAPI.org is not configured.")

        cache_key = f"newsapi:{path}:{mode}:{query}:{sorted(params.items())}"
        cached = ttl_cache.get(cache_key)
        if cached is not None:
            return cached

        url = f"{(settings.news_api_base_url or self.default_base_url).rstrip('/')}/{path.lstrip('/')}"
        try:
            with httpx.Client(timeout=20, trust_env=False) as client:
                response = client.get(url, params={**params, "apiKey": settings.news_api_key})
                response.raise_for_status()
                payload = response.json()
        except httpx.HTTPStatusError as exc:
            return NewsBrief(query=query, mode=mode, provider=self.provider_name, articles=[], error=self._http_error(exc))
        except Exception as exc:
            return NewsBrief(query=query, mode=mode, provider=self.provider_name, articles=[], error=str(exc))

        if payload.get("status") == "error":
            return NewsBrief(query=query, mode=mode, provider=self.provider_name, articles=[], error=str(payload.get("message") or "NewsAPI returned an error."))
        articles = self._extract_articles(payload)
        brief = NewsBrief(query=query, mode=mode, provider=self.provider_name, articles=articles[: settings.news_max_items])
        ttl_cache.set(cache_key, brief, ttl_seconds=300)
        return brief

    def _extract_articles(self, payload: Any) -> list[NewsArticle]:
        items = payload.get("articles") if isinstance(payload, dict) else []
        articles: list[NewsArticle] = []
        seen: set[str] = set()
        for item in items or []:
            if not isinstance(item, dict):
                continue
            title = self._clean(item.get("title"))
            if not title or title == "[Removed]":
                continue
            url = self._clean(item.get("url"))
            key = (url or title).lower()
            if key in seen:
                continue
            seen.add(key)
            source = item.get("source") if isinstance(item.get("source"), dict) else {}
            articles.append(
                NewsArticle(
                    title=title,
                    source=self._clean(source.get("name")) or "NewsAPI",
                    url=url,
                    published_at=self._clean(item.get("publishedAt")),
                    summary=self._clean(item.get("description")) or self._clean(item.get("content")),
                    image_url=self._clean(item.get("urlToImage")),
                )
            )
        return articles

    def _http_error(self, exc: httpx.HTTPStatusError) -> str:
        try:
            payload = exc.response.json()
            message = payload.get("message") or payload.get("code")
        except ValueError:
            message = None
        if exc.response.status_code in {401, 403}:
            return f"NewsAPI access denied. Check NEWS_API_KEY. {message or ''}".strip()
        if exc.response.status_code == 429:
            return "NewsAPI rate limit reached. Try again after the quota resets."
        return f"NewsAPI request failed with HTTP {exc.response.status_code}. {message or ''}".strip()

    def _category(self, value: str) -> str:
        normalized = value.lower().strip()
        return self.CATEGORY_ALIASES.get(normalized, normalized.replace(" ", "-"))

    def _clean(self, value: Any) -> str | None:
        if isinstance(value, str) and value.strip():
            return value.strip()
        return None
