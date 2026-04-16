"""
GoldX Bot — News Fetcher
========================
Fetches and filters economic news relevant to gold, USD, inflation, and FED.

Sources:
  - NewsAPI (newsapi.org) — requires NEWS_API_KEY
  - GNews  (gnews.io)    — requires GNEWS_API_KEY
  - RSS fallback         — no key required

Usage:
    fetcher = NewsFetcher()
    articles = fetcher.fetch(hours_back=6)
    for a in articles:
        print(a.title, a.score)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional
import requests
import feedparser

from utils.logger import logger
from config import NEWS_API_KEY, GNEWS_API_KEY

# ── Gold-relevant filter topics ───────────────────────────────────────────────
FILTER_TOPICS = [
    "gold", "XAU", "XAUUSD",
    "inflation", "CPI",
    "Federal Reserve", "Fed", "FOMC", "Jerome Powell",
    "USD", "dollar", "DXY",
    "interest rate", "rate hike", "rate cut",
    "Trump", "tariff", "sanction",
    "NFP", "non-farm payroll", "GDP",
]

# Free RSS feeds (no API key required)
RSS_FEEDS = [
    "https://feeds.finance.yahoo.com/rss/2.0/headline?s=GC=F&region=US&lang=en-US",
    "https://www.forexlive.com/feed/news",
    "https://www.investing.com/rss/news_301.rss",  # Gold news
]


@dataclass
class NewsArticle:
    title: str
    description: str
    source: str
    url: str
    published_at: str
    content: str = ""
    relevance_score: float = 0.0    # 0.0–1.0 how relevant to gold/macro
    topics_matched: list[str] = field(default_factory=list)

    def full_text(self) -> str:
        return f"{self.title}. {self.description}. {self.content}".strip()

    def __repr__(self) -> str:
        return f"NewsArticle(source={self.source!r}, relevance={self.relevance_score:.2f}, title={self.title[:50]!r})"


class NewsFetcher:
    """
    Fetches news from multiple APIs and RSS feeds.
    Filters articles relevant to gold/macro/USD context.
    """

    # ── Public API ─────────────────────────────────────────────────────────

    def fetch(self, hours_back: int = 6, min_relevance: float = 0.1) -> list[NewsArticle]:
        """
        Fetch gold/macro-relevant articles from all available sources.

        Args:
            hours_back: How many hours back to look for news.
            min_relevance: Minimum relevance score to include (0.0–1.0).

        Returns:
            List of NewsArticle sorted by relevance (most relevant first).
        """
        articles: list[NewsArticle] = []
        articles += self._fetch_newsapi(hours_back)
        articles += self._fetch_gnews()
        articles += self._fetch_rss()

        # Deduplicate by title
        seen: set[str] = set()
        unique: list[NewsArticle] = []
        for a in articles:
            key = a.title[:50].lower()
            if key not in seen:
                seen.add(key)
                self._score_relevance(a)
                if a.relevance_score >= min_relevance:
                    unique.append(a)

        unique.sort(key=lambda x: x.relevance_score, reverse=True)
        logger.info("NewsFetcher: {} relevant articles (from {} total)", len(unique), len(articles))
        return unique

    # ── Data Sources ───────────────────────────────────────────────────────

    def _fetch_newsapi(self, hours_back: int) -> list[NewsArticle]:
        if not NEWS_API_KEY:
            return []
        from_dt = (datetime.utcnow() - timedelta(hours=hours_back)).strftime("%Y-%m-%dT%H:%M:%SZ")
        query = " OR ".join([
            "gold price", "XAU USD", "Federal Reserve",
            "inflation CPI", "dollar index", "Trump tariffs",
        ])
        try:
            resp = requests.get(
                "https://newsapi.org/v2/everything",
                params={
                    "q": query,
                    "from": from_dt,
                    "sortBy": "publishedAt",
                    "language": "en",
                    "pageSize": 20,
                    "apiKey": NEWS_API_KEY,
                },
                timeout=10,
            )
            resp.raise_for_status()
            return [
                NewsArticle(
                    title=a.get("title") or "",
                    description=a.get("description") or "",
                    source=a.get("source", {}).get("name", "NewsAPI"),
                    url=a.get("url") or "",
                    published_at=a.get("publishedAt") or "",
                    content=a.get("content") or "",
                )
                for a in resp.json().get("articles", [])
            ]
        except Exception as exc:
            logger.warning("NewsAPI fetch error: {}", exc)
            return []

    def _fetch_gnews(self) -> list[NewsArticle]:
        if not GNEWS_API_KEY:
            return []
        try:
            resp = requests.get(
                "https://gnews.io/api/v4/search",
                params={
                    "q": "gold inflation Federal Reserve dollar",
                    "lang": "en",
                    "max": 10,
                    "token": GNEWS_API_KEY,
                },
                timeout=10,
            )
            resp.raise_for_status()
            return [
                NewsArticle(
                    title=a.get("title") or "",
                    description=a.get("description") or "",
                    source=a.get("source", {}).get("name", "GNews"),
                    url=a.get("url") or "",
                    published_at=a.get("publishedAt") or "",
                    content=a.get("content") or "",
                )
                for a in resp.json().get("articles", [])
            ]
        except Exception as exc:
            logger.warning("GNews fetch error: {}", exc)
            return []

    def _fetch_rss(self) -> list[NewsArticle]:
        articles = []
        for feed_url in RSS_FEEDS:
            try:
                feed = feedparser.parse(feed_url)
                for entry in feed.entries[:5]:
                    articles.append(NewsArticle(
                        title=entry.get("title", ""),
                        description=entry.get("summary", ""),
                        source=feed.feed.get("title", "RSS"),
                        url=entry.get("link", ""),
                        published_at=str(entry.get("published", "")),
                    ))
            except Exception as exc:
                logger.debug("RSS fetch error for {}: {}", feed_url[:40], exc)
        return articles

    # ── Relevance Scoring ──────────────────────────────────────────────────

    def _score_relevance(self, article: NewsArticle) -> None:
        """
        Compute a 0.0–1.0 relevance score based on matched topics.
        High-impact topics (gold price, FED, CPI) score higher.
        """
        text = (article.title + " " + article.description).lower()
        matched = []
        score = 0.0

        # High-weight keywords (direct impact on gold)
        high_weight = {
            "gold": 0.4, "xau": 0.4, "federal reserve": 0.3, "fed": 0.2,
            "inflation": 0.25, "cpi": 0.3, "rate cut": 0.3, "rate hike": 0.3,
            "fomc": 0.35, "trump": 0.2, "tariff": 0.2, "dollar": 0.15,
            "nfp": 0.3, "non-farm": 0.3, "gdp": 0.2,
        }
        for kw, weight in high_weight.items():
            if kw in text:
                score += weight
                matched.append(kw)

        article.relevance_score = min(1.0, score)
        article.topics_matched = matched

    # ── Mock Data ──────────────────────────────────────────────────────────

    def mock_articles(self) -> list[NewsArticle]:
        """Return mock articles for testing without API keys."""
        now = datetime.utcnow().isoformat()
        return [
            NewsArticle(
                title="Trump announces 25% tariffs on Chinese imports",
                description="New tariffs send gold surging as investors seek safe-haven assets.",
                source="Reuters", url="", published_at=now,
                relevance_score=0.9, topics_matched=["gold", "trump", "tariff"],
            ),
            NewsArticle(
                title="Fed signals potential rate cut — CPI cools",
                description="Federal Reserve officials hinted at possible rate cuts as CPI came in below expectations.",
                source="Bloomberg", url="", published_at=now,
                relevance_score=0.95, topics_matched=["federal reserve", "rate cut", "cpi", "inflation"],
            ),
            NewsArticle(
                title="DXY Dollar Index falls to 3-month low",
                description="USD weakens sharply against major currencies, boosting gold and commodities.",
                source="FXStreet", url="", published_at=now,
                relevance_score=0.85, topics_matched=["dollar", "gold"],
            ),
        ]
