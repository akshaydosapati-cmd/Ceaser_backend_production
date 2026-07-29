from __future__ import annotations

from typing import Any
from urllib.parse import quote_plus

import httpx

from app.core.config.settings import settings
from app.services.news.schemas import NewsArticle, NewsBrief


class RapidApiGoogleNewsProvider:
    provider_name = "rapidapi_google_news"

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
        "world": "world",
        "health": "health",
        "science": "science",
        "sport": "sport",
        "sports": "sport",
        "entertainment": "entertainment",
    }

    SEARCH_PARAM_CANDIDATES = ("keyword", "q", "query", "search")

    def configured(self) -> bool:
        return bool(settings.rapidapi_key and settings.rapidapi_news_host and settings.rapidapi_news_base_url)

    def latest(self) -> NewsBrief:
        return self._first_success(paths=settings.rapidapi_news_latest_paths, query="latest news", mode="latest")

    def category(self, category: str) -> NewsBrief:
        normalized = self._category(category)
        paths = [path.format(category=normalized) for path in settings.rapidapi_news_category_paths]
        return self._first_success(paths=paths, query=normalized, mode=f"category:{normalized}")

    def search(self, query: str) -> NewsBrief:
        paths = [path.format(query=quote_plus(query)) for path in settings.rapidapi_news_search_paths]
        return self._first_success(paths=paths, query=query, mode="search", use_search_params=True)

    def _first_success(self, *, paths: list[str], query: str, mode: str, use_search_params: bool = False) -> NewsBrief:
        if not self.configured():
            return NewsBrief(query=query, mode=mode, provider=self.provider_name, articles=[], error="RapidAPI news is not configured.")

        errors: list[str] = []
        for path in paths:
            if use_search_params and "{" not in path and "{query}" not in path:
                for param_name in self.SEARCH_PARAM_CANDIDATES:
                    brief = self._request(path=path, query=query, mode=mode, params={param_name: query})
                    if brief.articles:
                        return brief
                    if brief.error:
                        errors.append(brief.error)
                continue

            brief = self._request(path=path, query=query, mode=mode)
            if brief.articles:
                return brief
            if brief.error:
                errors.append(brief.error)

        return NewsBrief(
            query=query,
            mode=mode,
            provider=self.provider_name,
            articles=[],
            error=errors[-1] if errors else "No news articles returned by provider.",
        )

    def _request(self, *, path: str, query: str, mode: str, params: dict[str, str] | None = None) -> NewsBrief:
        url = f"{settings.rapidapi_news_base_url.rstrip('/')}/{path.lstrip('/')}"
        request_params = dict(params or {})
        if settings.rapidapi_news_language:
            request_params.setdefault("lr", settings.rapidapi_news_language)

        try:
            with httpx.Client(timeout=20, trust_env=False) as client:
                response = client.get(
                    url,
                    headers={
                        "X-RapidAPI-Key": settings.rapidapi_key or "",
                        "X-RapidAPI-Host": settings.rapidapi_news_host,
                    },
                    params=request_params,
                )
                response.raise_for_status()
                payload = response.json()
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            if status_code in {401, 403}:
                error = "RapidAPI news access denied. Check the Google News13 subscription and X-RapidAPI-Key."
            elif status_code == 429:
                error = "RapidAPI news rate limit reached. Try again after the provider quota resets."
            else:
                error = f"RapidAPI news request failed with HTTP {status_code}."
            return NewsBrief(query=query, mode=mode, provider=self.provider_name, articles=[], error=error)
        except Exception as exc:
            return NewsBrief(query=query, mode=mode, provider=self.provider_name, articles=[], error=str(exc))

        articles = self._extract_articles(payload)
        return NewsBrief(query=query, mode=mode, provider=self.provider_name, articles=articles[: settings.rapidapi_news_max_items])

    def _extract_articles(self, payload: Any) -> list[NewsArticle]:
        candidates = self._candidate_lists(payload)
        articles: list[NewsArticle] = []
        seen: set[str] = set()
        for item in candidates:
            if not isinstance(item, dict):
                continue
            title = self._first_text(item, "title", "name", "headline")
            url = self._first_text(item, "url", "link", "newsUrl", "article_url", "source_url")
            if not title:
                continue
            key = (url or title).lower()
            if key in seen:
                continue
            seen.add(key)
            source = self._source(item)
            articles.append(
                NewsArticle(
                    title=title,
                    source=source,
                    url=url,
                    published_at=self._first_text(item, "published_at", "publishedAt", "published", "date", "datetime", "timestamp"),
                    summary=self._first_text(item, "snippet", "description", "summary", "content"),
                    image_url=self._image(item),
                )
            )
            for subitem in item.get("subnews") or []:
                if not isinstance(subitem, dict):
                    continue
                subtitle = self._first_text(subitem, "title", "name", "headline")
                suburl = self._first_text(subitem, "url", "link", "newsUrl", "article_url", "source_url")
                if not subtitle:
                    continue
                subkey = (suburl or subtitle).lower()
                if subkey in seen:
                    continue
                seen.add(subkey)
                articles.append(
                    NewsArticle(
                        title=subtitle,
                        source=self._source(subitem),
                        url=suburl,
                        published_at=self._first_text(subitem, "published_at", "publishedAt", "published", "date", "datetime", "timestamp"),
                        summary=self._first_text(subitem, "snippet", "description", "summary", "content"),
                        image_url=self._image(subitem),
                    )
                )
        return articles

    def _candidate_lists(self, payload: Any) -> list[Any]:
        if isinstance(payload, list):
            return payload
        if not isinstance(payload, dict):
            return []
        for key in ("articles", "items", "results", "news", "data", "entries"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
            if isinstance(value, dict):
                nested = self._candidate_lists(value)
                if nested:
                    return nested
        return []

    def _source(self, item: dict) -> str | None:
        source = item.get("source")
        if isinstance(source, dict):
            return self._first_text(source, "name", "title", "domain")
        if isinstance(source, str):
            return source
        publisher = item.get("publisher")
        if isinstance(publisher, dict):
            return self._first_text(publisher, "name", "title")
        if isinstance(publisher, str):
            return publisher
        return self._first_text(item, "source_name", "publisher_name", "domain")

    def _first_text(self, item: dict, *keys: str) -> str | None:
        for key in keys:
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    def _image(self, item: dict) -> str | None:
        direct = self._first_text(item, "image", "image_url", "thumbnail", "photo_url")
        if direct:
            return direct
        images = item.get("images")
        if isinstance(images, dict):
            return self._first_text(images, "thumbnail", "thumbnailProxied", "url")
        return None

    def _category(self, value: str) -> str:
        normalized = value.lower().strip()
        return self.CATEGORY_ALIASES.get(normalized, normalized.replace(" ", "-"))
