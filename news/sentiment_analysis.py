"""
GoldX Bot — Sentiment Analysis
================================
Analyzes text sentiment and translates it into a gold price impact signal.

Two-stage pipeline:
  1. Raw sentiment  → TextBlob polarity (-1.0 to +1.0)
  2. Gold-adjusted  → Apply domain-specific keyword overrides

Returns:
  SentimentResult with:
    - sentiment: BULLISH / BEARISH / NEUTRAL
    - score: 0–100 (higher = more bullish for gold)
    - impact: BUY / SELL / NEUTRAL

Usage:
    analyzer = SentimentAnalyzer()
    result = analyzer.analyze_articles(articles)
    print(result.sentiment, result.score)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal
from news.news_fetcher import NewsArticle
from utils.logger import logger

Sentiment = Literal["BULLISH", "BEARISH", "NEUTRAL"]
Impact = Literal["BUY", "SELL", "NEUTRAL"]

TEXTBLOB_AVAILABLE = False
try:
    from textblob import TextBlob  # type: ignore[import]
    TEXTBLOB_AVAILABLE = True
except ImportError:
    pass

# Gold-specific keyword weights (+positive = gold price goes UP)
GOLD_KEYWORD_WEIGHTS: dict[str, float] = {
    # Strong bullish for gold
    "rate cut": +0.9,
    "dovish": +0.85,
    "quantitative easing": +0.9,
    "safe haven": +0.85,
    "recession": +0.7,
    "crisis": +0.75,
    "inflation rises": +0.8,
    "inflation surge": +0.8,
    "tariff": +0.65,
    "trump tariff": +0.75,
    "sanctions": +0.7,
    "war": +0.8,
    "conflict": +0.7,
    "weak dollar": +0.85,
    "dollar falls": +0.9,
    "dxy falls": +0.85,
    "gold rally": +1.0,
    "gold surges": +1.0,
    "gold hits record": +1.0,
    "uncertainty": +0.55,
    "fear": +0.6,
    "debt ceiling": +0.65,
    "stimulus": +0.6,
    "budget deficit": +0.5,
    # Strong bearish for gold
    "rate hike": -0.9,
    "hawkish": -0.85,
    "strong dollar": -0.85,
    "dollar surges": -0.9,
    "risk on": -0.7,
    "gold drops": -1.0,
    "gold falls": -1.0,
    "inflation cools": -0.75,
    "inflation eases": -0.75,
    "ceasefire": -0.55,
    "peace deal": -0.65,
    "stability": -0.45,
    "equity rally": -0.6,
    "stock market soars": -0.65,
    "economic recovery": -0.5,
}

# High-impact sources get extra weight
SOURCE_WEIGHTS: dict[str, float] = {
    "Reuters": 1.3,
    "Bloomberg": 1.3,
    "Financial Times": 1.2,
    "Wall Street Journal": 1.2,
    "CNBC": 1.1,
    "MarketWatch": 1.0,
    "FXStreet": 1.0,
}


@dataclass
class ArticleSentiment:
    title: str
    source: str
    raw_polarity: float          # TextBlob: -1.0 to +1.0
    gold_polarity: float         # Domain-adjusted: -1.0 to +1.0
    keywords_matched: list[str]
    weight: float                # Source weight multiplier


@dataclass
class SentimentResult:
    sentiment: Sentiment         # BULLISH / BEARISH / NEUTRAL
    score: float                 # 0–100 (50 = neutral)
    impact: Impact               # BUY / SELL / NEUTRAL
    article_sentiments: list[ArticleSentiment] = field(default_factory=list)
    dominant_theme: str = ""
    trump_signal: bool = False   # True if Trump statement detected
    fed_signal: bool = False     # True if FED/Powell statement detected
    high_impact_count: int = 0

    def summary(self) -> str:
        return (
            f"Sentiment: {self.sentiment} | Score: {self.score:.0f}/100 | "
            f"Impact: {self.impact} | Articles: {len(self.article_sentiments)}"
        )


class SentimentAnalyzer:
    """Analyzes news article sentiment for gold price impact."""

    def analyze_articles(self, articles: list[NewsArticle]) -> SentimentResult:
        """
        Analyze a list of news articles and return aggregate sentiment.

        Pipeline:
          1. Score each article (raw + gold-adjusted)
          2. Compute weighted average
          3. Map to 0-100 score and direction
        """
        if not articles:
            return SentimentResult(sentiment="NEUTRAL", score=50.0, impact="NEUTRAL")

        scored: list[ArticleSentiment] = [self._score_article(a) for a in articles]

        # Weighted aggregate
        total_weight = 0.0
        weighted_sum = 0.0
        for s in scored:
            w = s.weight * (1.5 if abs(s.gold_polarity) > 0.6 else 1.0)  # boost strong signals
            weighted_sum += s.gold_polarity * w
            total_weight += w

        avg_polarity = weighted_sum / total_weight if total_weight > 0 else 0.0

        # Normalize -1..+1 → 0..100
        score = (avg_polarity + 1.0) / 2.0 * 100.0
        score = max(0.0, min(100.0, round(score, 1)))

        if score >= 62:
            sentiment: Sentiment = "BULLISH"
            impact: Impact = "BUY"
        elif score <= 38:
            sentiment = "BEARISH"
            impact = "SELL"
        else:
            sentiment = "NEUTRAL"
            impact = "NEUTRAL"

        # Special signals
        all_text = " ".join(f"{a.title} {a.description}" for a in articles).lower()
        trump_signal = any(kw in all_text for kw in ["trump", "tariff", "trade war", "white house"])
        fed_signal = any(kw in all_text for kw in ["federal reserve", "powell", "fomc", "fed rate"])

        # Dominant theme (most common keyword matched)
        from collections import Counter
        keyword_counts = Counter(kw for s in scored for kw in s.keywords_matched)
        dominant_theme = keyword_counts.most_common(1)[0][0] if keyword_counts else ""

        result = SentimentResult(
            sentiment=sentiment,
            score=score,
            impact=impact,
            article_sentiments=scored,
            dominant_theme=dominant_theme,
            trump_signal=trump_signal,
            fed_signal=fed_signal,
            high_impact_count=sum(1 for s in scored if abs(s.gold_polarity) > 0.6),
        )
        logger.info(
            "Sentiment: {} score={:.1f} impact={} trump={} fed={}",
            sentiment, score, impact, trump_signal, fed_signal,
        )
        return result

    def analyze_text(self, text: str) -> float:
        """
        Analyze a single text string.
        Returns gold-adjusted polarity: -1.0 (bearish) to +1.0 (bullish).
        """
        raw = self._raw_polarity(text)
        return self._gold_adjust(text, raw)

    # ── Private ────────────────────────────────────────────────────────────

    def _score_article(self, article: NewsArticle) -> ArticleSentiment:
        text = (article.title + " " + article.description).lower()
        raw = self._raw_polarity(text)
        gold, keywords = self._gold_adjust_with_keywords(text, raw)
        source_weight = SOURCE_WEIGHTS.get(article.source, 0.9)
        return ArticleSentiment(
            title=article.title[:80],
            source=article.source,
            raw_polarity=raw,
            gold_polarity=gold,
            keywords_matched=keywords,
            weight=source_weight,
        )

    def _raw_polarity(self, text: str) -> float:
        if TEXTBLOB_AVAILABLE:
            try:
                return TextBlob(text).sentiment.polarity  # type: ignore[attr-defined]
            except Exception:
                pass
        return self._keyword_polarity(text)

    def _keyword_polarity(self, text: str) -> float:
        """Simple fallback when TextBlob is unavailable."""
        pos_words = ["rise", "up", "gain", "rally", "strong", "surge", "high", "grow"]
        neg_words = ["fall", "down", "drop", "decline", "weak", "crash", "low", "shrink"]
        text_lower = text.lower()
        pos = sum(1 for w in pos_words if w in text_lower)
        neg = sum(1 for w in neg_words if w in text_lower)
        total = pos + neg
        return (pos - neg) / total if total > 0 else 0.0

    def _gold_adjust(self, text: str, raw: float) -> float:
        polarity, _ = self._gold_adjust_with_keywords(text, raw)
        return polarity

    def _gold_adjust_with_keywords(self, text: str, raw: float) -> tuple[float, list[str]]:
        """Override raw sentiment with gold-domain keywords."""
        adjustment = 0.0
        matched = []
        for kw, weight in GOLD_KEYWORD_WEIGHTS.items():
            if kw in text:
                adjustment += weight
                matched.append(kw)
        if matched:
            avg_adjustment = adjustment / len(matched)
            # Blend: 70% domain-specific, 30% raw sentiment
            polarity = 0.7 * avg_adjustment + 0.3 * raw
            return max(-1.0, min(1.0, polarity)), matched
        return raw, []
