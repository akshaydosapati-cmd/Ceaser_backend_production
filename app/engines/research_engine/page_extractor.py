from __future__ import annotations

import html
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urlparse

import httpx


@dataclass
class ExtractedPage:
    url: str
    title: str | None
    publisher: str | None
    excerpt: str
    retrieved_at: str


class PageExtractor:
    def __init__(self, timeout_seconds: float = 8.0, max_bytes: int = 1_000_000):
        self.timeout_seconds = timeout_seconds
        self.max_bytes = max_bytes

    def extract(self, url: str, query: str) -> ExtractedPage | None:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            return None

        try:
            with httpx.Client(
                follow_redirects=True,
                timeout=self.timeout_seconds,
                trust_env=False,
                headers={"User-Agent": "CEASER Research/1.0"},
            ) as client:
                response = client.get(url)
                response.raise_for_status()
                content_type = response.headers.get("content-type", "").lower()
                if "text/html" not in content_type and "text/plain" not in content_type:
                    return None
                raw = response.content[: self.max_bytes]
        except Exception:
            return None

        text = raw.decode("utf-8", errors="ignore")
        title = self._title(text)
        clean_text = self._clean(text)
        excerpt = self._excerpt(clean_text, query)
        if not excerpt:
            return None
        return ExtractedPage(
            url=url,
            title=title,
            publisher=parsed.netloc.replace("www.", ""),
            excerpt=excerpt,
            retrieved_at=datetime.now(timezone.utc).isoformat(),
        )

    def _title(self, text: str) -> str | None:
        match = re.search(r"<title[^>]*>(.*?)</title>", text, flags=re.IGNORECASE | re.DOTALL)
        if not match:
            return None
        return html.unescape(re.sub(r"\s+", " ", match.group(1))).strip()[:180] or None

    def _clean(self, text: str) -> str:
        text = re.sub(r"(?is)<(script|style|nav|header|footer|noscript|svg|canvas).*?</\1>", " ", text)
        text = re.sub(r"(?is)<br\s*/?>", "\n", text)
        text = re.sub(r"(?is)</p>|</li>|</h[1-6]>", "\n", text)
        text = re.sub(r"(?is)<[^>]+>", " ", text)
        text = html.unescape(text)
        return re.sub(r"\s+", " ", text).strip()

    def _excerpt(self, text: str, query: str) -> str:
        if not text:
            return ""
        terms = {term.lower() for term in re.findall(r"[A-Za-z0-9]{4,}", query)}
        sentences = re.split(r"(?<=[.!?])\s+", text)
        ranked = sorted(
            ((sum(1 for term in terms if term in sentence.lower()), sentence) for sentence in sentences if len(sentence) > 60),
            key=lambda item: item[0],
            reverse=True,
        )
        selected = [sentence for score, sentence in ranked[:4] if score > 0] or sentences[:4]
        return " ".join(selected).strip()[:1400]
