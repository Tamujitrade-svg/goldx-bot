"""
GoldX Bot — Global Scoring Engine

Combines the 4 pillar scores into a single composite score.
Each pillar has a configurable weight.

Score interpretation:
  0 – 100 (how bullish the signal is for gold)
  > 65 → Potential BUY
  < 35 → Potential SELL
  35–65 → NO TRADE
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from utils.logger import logger
from config import (
    SCORE_WEIGHT_TECHNICAL,
    SCORE_WEIGHT_FUNDAMENTAL,
    SCORE_WEIGHT_GEOPOLITICAL,
    SCORE_WEIGHT_NEWS,
    MIN_SCORE_TO_TRADE,
)
from core.technical_analyzer import TechnicalResult
from core.fundamental_analyzer import FundamentalResult
from core.geopolitical_analyzer import GeopoliticalResult
from core.news_analyzer import NewsResult

Direction = Literal["BUY", "SELL", "NEUTRAL"]


@dataclass
class GlobalScore:
    # ── Raw scores (0–100 each) ─────────────────────────────────────────
    technical: float
    fundamental: float
    geopolitical: float
    news: float

    # ── Composite ──────────────────────────────────────────────────────
    global_score: float
    direction: Direction
    confidence: str          # HIGH / MEDIUM / LOW
    trade_valid: bool

    # ── Individual directions ──────────────────────────────────────────
    technical_direction: Direction = "NEUTRAL"
    fundamental_direction: Direction = "NEUTRAL"
    geopolitical_direction: Direction = "NEUTRAL"
    news_direction: Direction = "NEUTRAL"

    # ── Supporting data ────────────────────────────────────────────────
    pillar_alignment: int = 0        # How many pillars agree with direction (0-4)
    notes: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        bars = "█" * int(self.global_score / 10) + "░" * (10 - int(self.global_score / 10))
        return (
            f"SCORE GLOBAL: {self.global_score:.0f}/100 [{bars}]\n"
            f"  Technique    : {self.technical:.0f}/100  ({self.technical_direction})\n"
            f"  Fondamental  : {self.fundamental:.0f}/100  ({self.fundamental_direction})\n"
            f"  Géopolitique : {self.geopolitical:.0f}/100  ({self.geopolitical_direction})\n"
            f"  News/Discours: {self.news:.0f}/100  ({self.news_direction})\n"
            f"  Direction    : {self.direction}  |  Confiance: {self.confidence}\n"
            f"  Trade validé : {'✅ OUI' if self.trade_valid else '❌ NON'}"
        )


class ScoringEngine:
    """Combines 4 pillar analyses into a global trading decision score."""

    def compute(
        self,
        technical: TechnicalResult,
        fundamental: FundamentalResult,
        geopolitical: GeopoliticalResult,
        news: NewsResult,
    ) -> GlobalScore:

        # ── Weighted average ───────────────────────────────────────────
        global_score = (
            technical.score * SCORE_WEIGHT_TECHNICAL
            + fundamental.score * SCORE_WEIGHT_FUNDAMENTAL
            + geopolitical.score * SCORE_WEIGHT_GEOPOLITICAL
            + news.score * SCORE_WEIGHT_NEWS
        )
        global_score = round(max(0.0, min(100.0, global_score)), 1)

        # ── Direction ──────────────────────────────────────────────────
        direction = self._determine_direction(
            global_score,
            technical.direction,
            fundamental.direction,
            geopolitical.direction,
            news.direction,
        )

        # ── Pillar alignment count ─────────────────────────────────────
        alignment = sum(1 for d in [
            technical.direction,
            fundamental.direction,
            geopolitical.direction,
            news.direction,
        ] if d == direction and direction != "NEUTRAL")

        # ── Confidence ─────────────────────────────────────────────────
        confidence = self._grade_confidence(global_score, alignment)

        # ── Trade validity ─────────────────────────────────────────────
        trade_valid = (
            direction != "NEUTRAL"
            and global_score >= MIN_SCORE_TO_TRADE
            and alignment >= 2
        )

        # ── Notes ──────────────────────────────────────────────────────
        notes = self._build_notes(
            technical, fundamental, geopolitical, news,
            global_score, direction, alignment,
        )

        result = GlobalScore(
            technical=technical.score,
            fundamental=fundamental.score,
            geopolitical=geopolitical.score,
            news=news.score,
            global_score=global_score,
            direction=direction,
            confidence=confidence,
            trade_valid=trade_valid,
            technical_direction=technical.direction,
            fundamental_direction=fundamental.direction,
            geopolitical_direction=geopolitical.direction,
            news_direction=news.direction,
            pillar_alignment=alignment,
            notes=notes,
        )

        logger.info(
            "Global score={:.1f} dir={} conf={} valid={} alignment={}/4",
            global_score, direction, confidence, trade_valid, alignment,
        )
        return result

    # ── Helpers ────────────────────────────────────────────────────────

    def _determine_direction(
        self,
        global_score: float,
        tech: Direction,
        fund: Direction,
        geo: Direction,
        news: Direction,
    ) -> Direction:
        """
        Use global score as primary signal, validated by pillar majority.
        """
        buy_votes = sum(1 for d in [tech, fund, geo, news] if d == "BUY")
        sell_votes = sum(1 for d in [tech, fund, geo, news] if d == "SELL")

        if global_score >= 60 and buy_votes >= 2:
            return "BUY"
        if global_score <= 40 and sell_votes >= 2:
            return "SELL"
        # If score is strong but pillars disagree, trust score
        if global_score >= 68:
            return "BUY"
        if global_score <= 32:
            return "SELL"
        return "NEUTRAL"

    def _grade_confidence(self, score: float, alignment: int) -> str:
        """Grade: HIGH / MEDIUM / LOW."""
        if alignment >= 3 and (score >= 72 or score <= 28):
            return "HIGH"
        if alignment >= 2 and (score >= 62 or score <= 38):
            return "MEDIUM"
        return "LOW"

    def _build_notes(
        self,
        tech: TechnicalResult,
        fund: FundamentalResult,
        geo: GeopoliticalResult,
        news: NewsResult,
        score: float,
        direction: Direction,
        alignment: int,
    ) -> list[str]:
        notes = []

        if tech.session not in ("OFF-HOURS",):
            notes.append(f"Session active: {tech.session}")

        if geo.risk_level == "HIGH":
            notes.append("⚠️ RISQUE GÉOPOLITIQUE ÉLEVÉ — or favorisé")

        if news.trump_alert:
            notes.append("🚨 Déclaration Trump détectée — impact USD/or potentiel")

        if news.fed_alert:
            notes.append("🏦 Communication FED détectée — surveiller volatilité")

        if fund.macro_data.fed_stance == "DOVISH":
            notes.append("FED dovish → pression baissière sur USD → haussier or")

        if fund.macro_data.dxy_trend == "DOWN":
            notes.append("DXY en baisse → haussier or")

        if alignment < 2 and direction != "NEUTRAL":
            notes.append(f"⚠️ Faible alignement ({alignment}/4) — signal peu fiable")

        if score >= 80:
            notes.append("💪 Signal très fort — tous feux verts")
        elif score >= 70:
            notes.append("✅ Signal solide")
        elif score >= MIN_SCORE_TO_TRADE:
            notes.append("Signal modéré — seuil minimum atteint")

        return notes
