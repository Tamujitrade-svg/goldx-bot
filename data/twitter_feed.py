"""
GoldX Bot — Twitter / X Feed
Monitors key accounts (Trump, FED officials, market analysts) for
market-moving statements using Twitter API v2 via Tweepy.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

import pytz

from utils.logger import logger
from config import (
    TWITTER_BEARER_TOKEN,
    TWITTER_ACCOUNTS_TO_MONITOR,
)

UTC = pytz.UTC

TWEEPY_AVAILABLE = False
try:
    import tweepy
    TWEEPY_AVAILABLE = True
except ImportError:
    pass

# Keywords that signal market-moving content
GOLD_RELEVANT_KEYWORDS = [
    "gold", "xau", "dollar", "inflation", "cpi", "rate", "fed",
    "tariff", "tariffs", "sanction", "war", "conflict", "china",
    "iran", "ukraine", "crisis", "recession", "cut rates", "hike",
    "treasury", "bond", "sell", "buy", "crash", "rally",
]


@dataclass
class Tweet:
    id: str
    text: str
    author: str
    created_at: Optional[datetime]
    is_gold_relevant: bool = False

    def __post_init__(self) -> None:
        text_lower = self.text.lower()
        self.is_gold_relevant = any(kw in text_lower for kw in GOLD_RELEVANT_KEYWORDS)

    def __repr__(self) -> str:
        return f"Tweet(@{self.author}: {self.text[:80]!r})"


class TwitterFeed:
    """Fetches recent tweets from monitored accounts."""

    def __init__(self) -> None:
        self._client = None
        if TWEEPY_AVAILABLE and TWITTER_BEARER_TOKEN:
            try:
                self._client = tweepy.Client(bearer_token=TWITTER_BEARER_TOKEN, wait_on_rate_limit=False)  # type: ignore[attr-defined]
                logger.info("Twitter API v2 client initialized.")
            except Exception as exc:
                logger.warning("Twitter client init failed: {}", exc)

    def fetch_user_tweets(self, username: str, max_results: int = 10) -> list[Tweet]:
        """Fetch recent tweets from a specific user."""
        if not self._client:
            return []
        try:
            # Lookup user ID first
            user_resp = self._client.get_user(username=username)
            if not user_resp.data:
                return []
            user_id = user_resp.data.id

            # Fetch tweets
            start_time = datetime.now(tz=UTC) - timedelta(hours=6)
            tweets_resp = self._client.get_users_tweets(
                id=user_id,
                max_results=min(max_results, 100),
                start_time=start_time,
                tweet_fields=["created_at", "text"],
                exclude=["retweets", "replies"],
            )
            if not tweets_resp.data:
                return []
            tweets = []
            for t in tweets_resp.data:
                tweets.append(Tweet(
                    id=str(t.id),
                    text=t.text,
                    author=username,
                    created_at=t.created_at,
                ))
            logger.info("Fetched {} tweets from @{}", len(tweets), username)
            return tweets
        except Exception as exc:
            logger.warning("Twitter fetch error for @{}: {}", username, exc)
            return []

    def fetch_all_monitored(self) -> list[Tweet]:
        """Fetch tweets from all monitored accounts, filter gold-relevant."""
        all_tweets: list[Tweet] = []
        for account in TWITTER_ACCOUNTS_TO_MONITOR:
            all_tweets += self.fetch_user_tweets(account)

        relevant = [t for t in all_tweets if t.is_gold_relevant]
        logger.info(
            "Twitter: {} total tweets, {} gold-relevant",
            len(all_tweets), len(relevant)
        )
        return relevant

    def search_keywords(self, query: str = "gold XAU inflation tariff",
                        max_results: int = 20) -> list[Tweet]:
        """Search recent tweets by keyword (requires elevated API access)."""
        if not self._client:
            return self._mock_tweets()
        try:
            start_time = datetime.now(tz=UTC) - timedelta(hours=3)
            resp = self._client.search_recent_tweets(
                query=f"({query}) lang:en -is:retweet",
                max_results=min(max_results, 100),
                start_time=start_time,
                tweet_fields=["created_at", "text", "author_id"],
            )
            if not resp.data:
                return []
            return [
                Tweet(id=str(t.id), text=t.text, author="search", created_at=t.created_at)
                for t in resp.data
            ]
        except Exception as exc:
            logger.warning("Twitter search error: {}", exc)
            return self._mock_tweets()

    def _mock_tweets(self) -> list[Tweet]:
        now = datetime.now(tz=UTC)
        return [
            Tweet(
                id="1",
                text="Just announced: 25% tariffs on Chinese imports starting immediately. America First!",
                author="realDonaldTrump",
                created_at=now,
            ),
            Tweet(
                id="2",
                text="The Federal Reserve remains committed to returning inflation to 2%. Rates unchanged.",
                author="JeromeHPowell",
                created_at=now,
            ),
        ]
