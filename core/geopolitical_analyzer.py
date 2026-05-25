"""
GoldX Bot — Geopolitical Analyzer (Pillar 3)

Gold is a classic safe-haven asset. Geopolitical risk directly impacts price.
This module:
  - Scans news for geopolitical keywords
  - Uses LLM (Claude) to interpret context if API key is available
  - Returns a score 0–100 and a directional bias
    Score > 65 → bullish gold (high geopolitical risk = more fear = gold up)
    Score < 35 → bearish gold (de-escalation, stability)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional

from utils.logger import logger
from config import (
    ANTHROPIC_API_KEY,
    GEO_BULLISH_KEYWORDS,
    GEO_BEARISH_KEYWORDS,
)
from data.news_feed import Article

Direction = Literal["BUY", "SELL", "NEUTRAL"]

# Hotspot regions that carry premium geopolitical risk for gold
HIGH_RISK_REGIONS = [
    "middle east", "israel", "iran", "gaza", "ukraine", "russia",
    "taiwan", "china", "north korea", "syria", "iraq", "venezuela",
    "pakistan", "india", "south china sea",
]

CRISIS_AMPLIFIERS = [
    "nuclear", "chemical weapon", "war declared", "troops deployed",
    "martial law", "economic collapse", "bank run", "default",
    "emergency", "nato", "un resolution",
]


@dataclass
class GeoEvent:
    headline: str
    risk_level: str          # HIGH / MEDIUM / LOW
    region: str
    source: str
    is_bullish_gold: bool    # True = escalation; False = de-escalation


@dataclass
class GeopoliticalResult:
    score: float             # 0–100
    direction: Direction
    risk_level: str          # HIGH / MEDIUM / LOW
    events: list[GeoEvent] = field(default_factory=list)
    llm_summary: str = ""
    details: dict = field(default_factory=dict)


class GeopoliticalAnalyzer:
    """Analyzes geopolitical risk from news articles."""

    def __init__(self) -> None:
        self._llm_client = None
        if ANTHROPIC_API_KEY:
            try:
                import anthropic
                self._llm_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
                logger.info("Anthropic LLM client initialized for geopolitical analysis.")
            except ImportError:
                logger.warning("anthropic package not installed.")

    # ── Public Interface ───────────────────────────────────────────────────

    def analyze(self, articles: list[Article]) -> GeopoliticalResult:
        if not articles:
            return GeopoliticalResult(score=50.0, direction="NEUTRAL", risk_level="LOW")

        events = self._extract_geo_events(articles)
        score, direction, risk_level = self._compute_score(events)

        # Use LLM for deeper interpretation if available
        llm_summary = ""
        if self._llm_client and events:
            llm_summary = self._llm_interpret(events[:5])

        result = GeopoliticalResult(
            score=score,
            direction=direction,
            risk_level=risk_level,
            events=events,
            llm_summary=llm_summary,
            details={"event_count": len(events), "high_risk_count": sum(1 for e in events if e.risk_level == "HIGH")},
        )
        logger.info(
            "Geopolitical: score={:.1f} dir={} risk={} events={}",
            score, direction, risk_level, len(events),
        )
        return result

    # ── Event Extraction ───────────────────────────────────────────────────

    def _extract_geo_events(self, articles: list[Article]) -> list[GeoEvent]:
        events: list[GeoEvent] = []
        for article in articles:
            text = (article.title + " " + article.description).lower()

            # Check for geopolitical relevance
            region = self._detect_region(text)
            if region is None:
                continue

            bullish_hits = sum(1 for kw in GEO_BULLISH_KEYWORDS if kw in text)
            bearish_hits = sum(1 for kw in GEO_BEARISH_KEYWORDS if kw in text)
            amplifier_hits = sum(1 for kw in CRISIS_AMPLIFIERS if kw in text)

            if bullish_hits == 0 and bearish_hits == 0:
                continue

            # Determine risk level
            total_risk = bullish_hits + amplifier_hits * 2
            if total_risk >= 4 or amplifier_hits >= 1:
                risk_level = "HIGH"
            elif total_risk >= 2:
                risk_level = "MEDIUM"
            else:
                risk_level = "LOW"

            is_bullish = bullish_hits > bearish_hits

            events.append(GeoEvent(
                headline=article.title[:120],
                risk_level=risk_level,
                region=region,
                source=article.source,
                is_bullish_gold=is_bullish,
            ))

        return events

    def _detect_region(self, text: str) -> Optional[str]:
        for region in HIGH_RISK_REGIONS:
            if region in text:
                return region.title()
        return None

    # ── LLM Interpretation ─────────────────────────────────────────────────

    def _llm_interpret(self, events: list[GeoEvent]) -> str:
        """Use Claude to summarize geopolitical risk for gold."""
        headlines = "\n".join(f"- [{e.risk_level}] {e.headline}" for e in events)
        prompt = f"""You are a macro trading analyst specializing in gold (XAU/USD).
Analyze these geopolitical headlines and assess their net impact on gold prices.

Headlines:
{headlines}

Answer in 2-3 sentences:
1. What is the dominant geopolitical theme?
2. Is this bullish or bearish for gold, and why?
3. Risk level: HIGH / MEDIUM / LOW?

Be concise and direct."""

        try:
            response = self._llm_client.messages.create(  # type: ignore[union-attr]
                model="claude-haiku-4-5-20251001",
                max_tokens=200,
                messages=[{"role": "user", "content": prompt}],
            )
            return response.content[0].text.strip()
        except Exception as exc:
            logger.warning("LLM geopolitical interpretation failed: {}", exc)
            return ""

    # ── Scoring ────────────────────────────────────────────────────────────

    def _compute_score(self, events: list[GeoEvent]) -> tuple[float, Direction, str]:
        if not events:
            return 50.0, "NEUTRAL", "LOW"

        bullish_weight = 0.0
        bearish_weight = 0.0
        risk_points = 0

        risk_multiplier = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}

        for e in events:
            w = risk_multiplier[e.risk_level]
            if e.is_bullish_gold:
                bullish_weight += w
                risk_points += w
            else:
                bearish_weight += w

        total = bullish_weight + bearish_weight
        if total == 0:
            return 50.0, "NEUTRAL", "LOW"

        # Score = how bullish geopolitical environment is for gold
        geo_score = (bullish_weight / total) * 100

        # Risk level
        if risk_points >= 6:
            risk_level = "HIGH"
        elif risk_points >= 3:
            risk_level = "MEDIUM"
        else:
            risk_level = "LOW"

        if geo_score >= 60:
            direction: Direction = "BUY"
        elif geo_score <= 40:
            direction = "SELL"
        else:
            direction = "NEUTRAL"

        return round(geo_score, 1), direction, risk_level
