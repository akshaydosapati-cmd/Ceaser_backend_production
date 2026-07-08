from __future__ import annotations

from pydantic import BaseModel


class NewsArticle(BaseModel):
    title: str
    source: str | None = None
    url: str | None = None
    published_at: str | None = None
    summary: str | None = None
    image_url: str | None = None


class NewsBrief(BaseModel):
    query: str
    mode: str
    provider: str
    articles: list[NewsArticle]
    error: str | None = None

