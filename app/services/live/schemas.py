from __future__ import annotations

from pydantic import BaseModel


class LiveProviderState(BaseModel):
    name: str
    configured: bool
    status: str
    message: str | None = None


class LiveStatus(BaseModel):
    news: LiveProviderState
    weather: LiveProviderState
    search: LiveProviderState
    market: LiveProviderState
    maps: LiveProviderState
    google_calendar: LiveProviderState
    gmail: LiveProviderState
    google_drive: LiveProviderState
    microsoft: LiveProviderState
    notion: LiveProviderState
    canvas: LiveProviderState
    moodle: LiveProviderState


class LiveArticle(BaseModel):
    title: str
    source: str | None = None
    url: str | None = None
    published_at: str | None = None
    summary: str | None = None
    image_url: str | None = None


class LiveNewsBrief(BaseModel):
    query: str
    mode: str
    provider: str
    configured: bool
    articles: list[LiveArticle]
    error: str | None = None


class LiveWeatherReport(BaseModel):
    location: str
    provider: str
    configured: bool
    temperature: float | None = None
    condition: str | None = None
    humidity: int | None = None
    wind_speed: float | None = None
    error: str | None = None
