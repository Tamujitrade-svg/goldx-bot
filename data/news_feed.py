"""
GoldX Bot — News Feed
Fetches gold/macro-relevant articles from NewsAPI and GNews.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import requests

from utils.logger import logger
from config import NEWS_API_KEY, GNEWS_API_KEY

GOLD_QUERIES = [
    "gold XAU inflation",
    "Federal Reserve interest rates",
    "DXY dollar index",
    "Trump trade tariffs",
    "geopolitical gold safe haven",
    "CPI inflation US",
    "NFP jobs report",
]


class Article:
    __slots__ = ("title", "description", "source", "url", "published_at", "content")

    def __init__(self, title: str, description: str, source: str,
                 url: str, published_at: str, content: str = "") -> None:
        self.title = title
        self.description = description
        self.source = source
        self.url = url
        self.published_at = published_at
        self.content = content

    def full_text(self) -> str:
        return f"{self.title}. {self.description}. {self.content}".strip()

    def __repr__(self) -> str:
        return f"Article(source={self.source!r}, title={self.title[:60]!r})"


class NewsFeed:
    """Aggregates articles from multiple news sources."""

    # ── NewsAPI ────────────────────────────────────────────────────────────

    def fetch_newsapi(self, query: str = "gold XAU OR inflation OR Federal Reserve",
                      hours_back: int = 6) -> list[Article]:
        if not NEWS_API_KEY:
            logger.warning("NEWS_API_KEY not set — skipping NewsAPI.")
            return []
        from_dt = (datetime.utcnow() - timedelta(hours=hours_back)).strftime("%Y-%m-%dT%H:%M:%SZ")
        params = {
            "q": query,
            "from": from_dt,
            "sortBy": "publishedAt",
            "language": "en",
            "apiKey": NEWS_API_KEY,
        }
        try:
            resp = requests.get("https://newsapi.org/v2/everything", params=params, timeout=10)
            resp.raise_for_status()
            articles = resp.json().get("articles", [])
            result = []
            for a in articles:
                result.append(Article(
                    title=a.get("title", ""),
                    description=a.get("description", "") or "",
                    source=a.get("source", {}).get("name", ""),
                    url=a.get("url", ""),
                    published_at=a.get("publishedAt", ""),
                    content=a.get("content", "") or "",
                ))
            logger.info("NewsAPI returned {} articles for query={!r}", len(result), query[:40])
            return result
        except Exception as exc:
            logger.error("NewsAPI error: {}", exc)
            return []

    # ── GNews ──────────────────────────────────────────────────────────────

    def fetch_gnews(self, query: str = "gold inflation Federal Reserve",
                    max_results: int = 10) -> list[Article]:
        if not GNEWS_API_KEY:
            logger.warning("GNEWS_API_KEY not set — skipping GNews.")
            return []
        params = {
            "q": query,
            "lang": "en",
            "max": max_results,
            "token": GNEWS_API_KEY,
        }
        try:
            resp = requests.get("https://gnews.io/api/v4/search", params=params, timeout=10)
            resp.raise_for_status()
            articles = resp.json().get("articles", [])
            result = []
            for a in articles:
                result.append(Article(
                    title=a.get("title", ""),
                    description=a.get("description", "") or "",
                    source=a.get("source", {}).get("name", ""),
                    url=a.get("url", ""),
                    published_at=a.get("publishedAt", ""),
                    content=a.get("content", "") or "",
                ))
            logger.info("GNews returned {} articles.", len(result))
            return result
        except Exception as exc:
            logger.error("GNews error: {}", exc)
            return []

    # ── Aggregate ──────────────────────────────────────────────────────────

    def fetch_all(self, hours_back: int = 6) -> list[Article]:
        """Fetch from all configured sources, deduplicate by title."""
        articles: list[Article] = []
        combined_query = " OR ".join(GOLD_QUERIES[:3])
        articles += self.fetch_newsapi(query=combined_query, hours_back=hours_back)
        articles += self.fetch_gnews(query="gold XAU inflation Federal Reserve")

        # Deduplicate by title prefix
        seen: set[str] = set()
        unique: list[Article] = []
        for a in articles:
            key = a.title[:60].lower()
            if key not in seen:
                seen.add(key)
                unique.append(a)

        logger.info("Total unique articles fetched: {}", len(unique))
        return unique

    # ── Mock (fallback for testing) ────────────────────────────────────────

    def mock_articles(self) -> list[Article]:
        return [
            Article(
                title="Trump announces new tariffs on Chinese imports",
                description="President Trump announced sweeping new tariffs, sending gold prices surging as investors seek safe-haven assets.",
                source="Reuters",
                url="",
                published_at=datetime.utcnow().isoformat(),
            ),
            Article(
                title="Fed signals potential rate cut amid cooling inflation",
                description="Federal Reserve officials hinted at possible rate cuts as CPI data came in below expectations, weakening the dollar.",
                source="Bloomberg",
                url="",
                published_at=datetime.utcnow().isoformat(),
            ),
            Article(
                title="Middle East tensions escalate — gold hits $2,400",
                description="Geopolitical tensions in the Middle East pushed gold to a multi-month high as investors fled risk assets.",
                source="Financial Times",
                url="",
                published_at=datetime.utcnow().isoformat(),
            ),
        ]
