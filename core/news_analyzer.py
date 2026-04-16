"""
GoldX Bot — News & Sentiment Analyzer (Pillar 4)

Processes:
  - Financial news articles (NewsAPI, GNews)
  - Twitter/X statements (Trump, FED, etc.)
  - Performs sentiment analysis (TextBlob + optional LLM)
  - Detects high-impact event mentions
  - Returns a score 0–100 and a directional bias for gold
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional

from utils.logger import logger
from config import ANTHROPIC_API_KEY
from data.news_feed import Article
from data.twitter_feed import Tweet

Direction = Literal["BUY", "SELL", "NEUTRAL"]
Sentiment = Literal["BULLISH", "BEARISH", "NEUTRAL"]

TEXTBLOB_AVAILABLE = False
try:
    from textblob import TextBlob  # type: ignore[import]
    TEXTBLOB_AVAILABLE = True
except ImportError:
    pass

# Gold-specific keyword scoring overrides
GOLD_BULLISH_KEYWORDS = {
    "safe haven": 0.8, "inflation": 0.6, "rate cut": 0.9, "dove": 0.7,
    "dovish": 0.8, "weak dollar": 0.9, "dollar falls": 0.9,
    "gold rally": 1.0, "gold surges": 1.0, "xau rallies": 1.0,
    "recession": 0.7, "fear": 0.6, "uncertainty": 0.6, "crisis": 0.8,
    "tariffs": 0.7, "sanctions": 0.7, "war risk": 0.9,
    "trump tariff": 0.8, "trade war": 0.8, "stimulus": 0.6,
    "debt ceiling": 0.7, "budget deficit": 0.5,
}

GOLD_BEARISH_KEYWORDS = {
    "rate hike": -0.9, "hawkish": -0.8, "strong dollar": -0.9,
    "dollar surges": -0.9, "gold drops": -1.0, "gold falls": -1.0,
    "risk on": -0.7, "equity rally": -0.6, "recovery": -0.4,
    "inflation cools": -0.7, "inflation eases": -0.7, "ceasefire": -0.5,
    "peace deal": -0.6, "stability": -0.4,
}

# Key accounts that have outsized market impact
HIGH_IMPACT_AUTHORS = {
    "realDonaldTrump": 1.5,
    "JeromeHPowell": 1.5,
    "federalreserve": 1.3,
    "GoldmanSachs": 1.0,
    "BloombergMarkets": 0.8,
}


@dataclass
class ScoredItem:
    text: str
    source: str
    raw_sentiment: float      # -1.0 to +1.0
    gold_sentiment: float     # adjusted for gold context
    is_high_impact: bool


@dataclass
class NewsResult:
    score: float              # 0–100
    direction: Direction
    sentiment: Sentiment
    items: list[ScoredItem] = field(default_factory=list)
    trump_alert: bool = False
    fed_alert: bool = False
    llm_summary: str = ""
    details: dict = field(default_factory=dict)


class NewsAnalyzer:
    """Sentiment analysis of news and tweets for gold trading signals."""

    def __init__(self) -> None:
        self._llm_client = None
        if ANTHROPIC_API_KEY:
            try:
                import anthropic
                self._llm_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
            except ImportError:
                pass

    # ── Public Interface ───────────────────────────────────────────────────

    def analyze(
        self,
        articles: list[Article],
        tweets: Optional[list[Tweet]] = None,
    ) -> NewsResult:
        if tweets is None:
            tweets = []

        scored_items: list[ScoredItem] = []

        # Score articles
        for article in articles:
            item = self._score_article(article)
            if item is not None:
                scored_items.append(item)

        # Score tweets
        for tweet in tweets:
            item = self._score_tweet(tweet)
            scored_items.append(item)

        if not scored_items:
            return NewsResult(score=50.0, direction="NEUTRAL", sentiment="NEUTRAL")

        # Aggregate
        score, direction, sentiment = self._compute_score(scored_items)

        # Special alerts
        trump_alert = any(
            "trump" in s.text.lower() and abs(s.gold_sentiment) > 0.5
            for s in scored_items
        )
        fed_alert = any(
            ("federal reserve" in s.text.lower() or "powell" in s.text.lower() or "fomc" in s.text.lower())
            and abs(s.gold_sentiment) > 0.5
            for s in scored_items
        )

        # LLM summary for top items
        llm_summary = ""
        if self._llm_client and scored_items:
            llm_summary = self._llm_summarize(scored_items[:6])

        result = NewsResult(
            score=score,
            direction=direction,
            sentiment=sentiment,
            items=scored_items,
            trump_alert=trump_alert,
            fed_alert=fed_alert,
            llm_summary=llm_summary,
            details={
                "total_items": len(scored_items),
                "high_impact": sum(1 for s in scored_items if s.is_high_impact),
                "avg_gold_sentiment": sum(s.gold_sentiment for s in scored_items) / len(scored_items),
            },
        )
        logger.info(
            "News: score={:.1f} dir={} sentiment={} trump={} fed={}",
            score, direction, sentiment, trump_alert, fed_alert,
        )
        return result

    # ── Scoring ────────────────────────────────────────────────────────────

    def _score_article(self, article: Article) -> Optional[ScoredItem]:
        text = article.full_text()
        if len(text) < 20:
            return None
        raw = self._textblob_sentiment(text)
        gold = self._gold_adjusted_sentiment(text, raw)
        is_high = self._is_high_impact(text)
        return ScoredItem(
            text=text[:300],
            source=article.source,
            raw_sentiment=raw,
            gold_sentiment=gold,
            is_high_impact=is_high,
        )

    def _score_tweet(self, tweet: Tweet) -> ScoredItem:
        raw = self._textblob_sentiment(tweet.text)
        gold = self._gold_adjusted_sentiment(tweet.text, raw)
        # Apply author weight
        author_weight = HIGH_IMPACT_AUTHORS.get(tweet.author, 0.7)
        gold = max(-1.0, min(1.0, gold * author_weight))
        is_high = tweet.author in HIGH_IMPACT_AUTHORS
        return ScoredItem(
            text=tweet.text[:300],
            source=f"@{tweet.author}",
            raw_sentiment=raw,
            gold_sentiment=gold,
            is_high_impact=is_high,
        )

    def _textblob_sentiment(self, text: str) -> float:
        """Returns sentiment polarity -1.0 to +1.0."""
        if TEXTBLOB_AVAILABLE:
            try:
                return TextBlob(text).sentiment.polarity  # type: ignore[attr-defined]
            except Exception:
                pass
        return self._keyword_sentiment(text)

    def _keyword_sentiment(self, text: str) -> float:
        """Simple keyword-based fallback."""
        text_lower = text.lower()
        positive_words = ["good", "up", "rise", "gain", "high", "strong", "positive", "growth"]
        negative_words = ["bad", "down", "fall", "drop", "low", "weak", "negative", "decline"]
        pos = sum(1 for w in positive_words if w in text_lower)
        neg = sum(1 for w in negative_words if w in text_lower)
        total = pos + neg
        if total == 0:
            return 0.0
        return (pos - neg) / total

    def _gold_adjusted_sentiment(self, text: str, raw_sentiment: float) -> float:
        """
        Override raw sentiment with gold-specific keywords.
        Note: positive gold sentiment = gold price goes up = BUY.
        """
        text_lower = text.lower()
        adjustment = 0.0
        matches = 0

        for kw, weight in GOLD_BULLISH_KEYWORDS.items():
            if kw in text_lower:
                adjustment += weight
                matches += 1

        for kw, weight in GOLD_BEARISH_KEYWORDS.items():
            if kw in text_lower:
                adjustment += weight  # weight is already negative
                matches += 1

        if matches > 0:
            return max(-1.0, min(1.0, adjustment / matches))
        return raw_sentiment

    def _is_high_impact(self, text: str) -> bool:
        text_lower = text.lower()
        triggers = ["cpi", "fomc", "fed rate", "nfp", "payrolls", "trump",
                    "powell", "interest rate decision", "inflation report"]
        return any(t in text_lower for t in triggers)

    def _compute_score(self, items: list[ScoredItem]) -> tuple[float, Direction, Sentiment]:
        """
        Weighted average gold sentiment → score 0-100.
        High-impact items get 2x weight.
        """
        total_weight = 0.0
        weighted_sum = 0.0

        for item in items:
            w = 2.0 if item.is_high_impact else 1.0
            weighted_sum += item.gold_sentiment * w
            total_weight += w

        if total_weight == 0:
            return 50.0, "NEUTRAL", "NEUTRAL"

        avg = weighted_sum / total_weight  # -1.0 to +1.0
        # Normalize to 0-100: 0 = -1, 50 = 0, 100 = +1
        score = (avg + 1.0) / 2.0 * 100.0
        score = max(0.0, min(100.0, score))

        if score >= 62:
            direction: Direction = "BUY"
            sentiment: Sentiment = "BULLISH"
        elif score <= 38:
            direction = "SELL"
            sentiment = "BEARISH"
        else:
            direction = "NEUTRAL"
            sentiment = "NEUTRAL"

        return round(score, 1), direction, sentiment

    # ── LLM Summary ────────────────────────────────────────────────────────

    def _llm_summarize(self, items: list[ScoredItem]) -> str:
        texts = "\n".join(f"[{s.source}] {s.text[:150]}" for s in items)
        prompt = f"""You are a professional gold (XAU/USD) trader.
Below are the latest news headlines and tweets that affect gold prices.

{texts}

In 2-3 sentences, explain:
1. What is the dominant market narrative?
2. Net impact on gold: BULLISH, BEARISH, or NEUTRAL?
3. What is the key risk to watch?

Be brief and professional."""

        try:
            response = self._llm_client.messages.create(  # type: ignore[union-attr]
                model="claude-haiku-4-5-20251001",
                max_tokens=200,
                messages=[{"role": "user", "content": prompt}],
            )
            return response.content[0].text.strip()
        except Exception as exc:
            logger.warning("LLM news summary failed: {}", exc)
            return ""
