from __future__ import annotations

from app.core.config.settings import settings
from app.services.live.schemas import LiveArticle, LiveNewsBrief, LiveProviderState, LiveStatus, LiveWeatherReport
from app.services.news.news_service import NewsService
from app.services.weather import OpenWeatherProvider


class LiveService:
    def status(self) -> LiveStatus:
        return LiveStatus(
            news=self._state(settings.news_provider or settings.rapidapi_news_provider, self._news_configured()),
            weather=self._state(settings.weather_provider or "openweather", bool(settings.weather_api_key)),
            search=self._state(settings.search_provider or "search", bool(settings.search_api_key and settings.search_api_base_url)),
            market=self._state(settings.market_provider or "market", bool(settings.market_api_key and settings.market_api_base_url)),
            maps=self._state(settings.maps_provider or "maps", bool(settings.maps_api_key and settings.maps_api_base_url)),
            google_calendar=self._state(settings.calendar_provider, bool(settings.google_client_id and settings.google_client_secret)),
            gmail=self._state(settings.gmail_provider, bool(settings.google_client_id and settings.google_client_secret)),
            google_drive=self._state(settings.drive_provider, bool(settings.google_client_id and settings.google_client_secret)),
            microsoft=self._state("microsoft", bool(settings.microsoft_client_id and settings.microsoft_client_secret)),
            notion=self._state("notion", bool(settings.notion_client_id and settings.notion_client_secret)),
            canvas=self._state("canvas", bool(settings.canvas_client_id and settings.canvas_client_secret)),
            moodle=self._state("moodle", bool(settings.moodle_client_id and settings.moodle_client_secret and settings.moodle_base_url)),
        )

    def latest_news(self) -> LiveNewsBrief:
        if not self._news_configured():
            return self._news_not_configured(query="latest news", mode="latest")
        brief = NewsService().for_automation(name="Daily News Reader", prompt="latest news")
        return self._from_news_brief(brief)

    def search_news(self, query: str) -> LiveNewsBrief:
        cleaned = query.strip()
        if not cleaned:
            return self._news_not_configured(query=query, mode="search", error="Search query is required.")
        if not self._news_configured():
            return self._news_not_configured(query=cleaned, mode="search")
        brief = NewsService().for_automation(name="News Search", prompt=cleaned)
        return self._from_news_brief(brief)

    def category_news(self, category: str) -> LiveNewsBrief:
        cleaned = category.strip() or "latest"
        if not self._news_configured():
            return self._news_not_configured(query=cleaned, mode=f"category:{cleaned}")
        brief = NewsService().for_automation(name=f"{cleaned} news", prompt=cleaned)
        return self._from_news_brief(brief)

    def current_weather(self, location: str | None = None) -> LiveWeatherReport:
        requested_location = (location or settings.weather_default_location).strip()
        if not settings.weather_api_key:
            return LiveWeatherReport(
                location=requested_location,
                provider=settings.weather_provider or "openweather",
                configured=False,
                error="Weather provider is not connected yet.",
            )
        return OpenWeatherProvider().current(requested_location)

    def _news_configured(self) -> bool:
        return bool(settings.news_api_key or settings.rapidapi_key)

    def _state(self, name: str | None, configured: bool) -> LiveProviderState:
        return LiveProviderState(
            name=name or "not_selected",
            configured=configured,
            status="ready" if configured else "not_connected",
            message=None if configured else "Add provider credentials in backend/.env.",
        )

    def _news_not_configured(self, *, query: str, mode: str, error: str | None = None) -> LiveNewsBrief:
        return LiveNewsBrief(
            query=query,
            mode=mode,
            provider=settings.news_provider or settings.rapidapi_news_provider,
            configured=False,
            articles=[],
            error=error or "News provider is not connected yet.",
        )

    def _from_news_brief(self, brief) -> LiveNewsBrief:
        return LiveNewsBrief(
            query=brief.query,
            mode=brief.mode,
            provider=brief.provider,
            configured=True,
            articles=[
                LiveArticle(
                    title=article.title,
                    source=article.source,
                    url=article.url,
                    published_at=article.published_at,
                    summary=article.summary,
                    image_url=article.image_url,
                )
                for article in brief.articles
            ],
            error=brief.error,
        )
