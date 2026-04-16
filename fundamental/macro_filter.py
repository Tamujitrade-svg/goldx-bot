"""
GoldX Bot — Macro Filter
=========================
Determines the global macro context for gold trading.

Evaluates:
  - Risk regime: RISK-ON vs RISK-OFF
  - FED stance: DOVISH / NEUTRAL / HAWKISH
  - Inflation trend: RISING / STABLE / FALLING
  - USD direction: UP / SIDEWAYS / DOWN

RISK-OFF → Gold is bullish (fear, uncertainty → safe haven demand)
RISK-ON  → Gold can be bearish (investors prefer equities)

This filter gates trade entries:
  - RISK-OFF + DOVISH FED + WEAK USD → allow BUY
  - RISK-ON  + HAWKISH FED + STRONG USD → block or allow SELL

Usage:
    mf = MacroFilter()
    context = mf.evaluate()
    if context.allows_buy:
        print("Macro supports BUY")
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

import requests

from utils.logger import logger
from config import NEWS_API_KEY

# ── Types ─────────────────────────────────────────────────────────────────────
RiskRegime = Literal["RISK-OFF", "NEUTRAL", "RISK-ON"]
FedStance  = Literal["DOVISH", "NEUTRAL", "HAWKISH"]
Trend      = Literal["UP", "SIDEWAYS", "DOWN"]
TradeFilter = Literal["ALLOW_BUY", "ALLOW_SELL", "BLOCK", "NEUTRAL"]


@dataclass
class MacroContext:
    """
    Snapshot of current macro conditions.
    Used to filter/gate trade decisions.
    """
    risk_regime: RiskRegime = "NEUTRAL"
    fed_stance: FedStance = "NEUTRAL"
    fed_rate: Optional[float] = None
    inflation_trend: Trend = "SIDEWAYS"
    cpi_yoy: Optional[float] = None
    usd_trend: Trend = "SIDEWAYS"
    dxy_value: Optional[float] = None

    # ── Derived ────────────────────────────────────────────────────────
    trade_filter: TradeFilter = "NEUTRAL"
    gold_bias: str = "NEUTRAL"        # BULLISH / BEARISH / NEUTRAL
    macro_score: float = 50.0         # 0–100 (bullish for gold)
    notes: list[str] = ""            # type: ignore[assignment]

    def __post_init__(self) -> None:
        if isinstance(self.notes, str):
            self.notes = []

    @property
    def allows_buy(self) -> bool:
        return self.trade_filter in ("ALLOW_BUY", "NEUTRAL")

    @property
    def allows_sell(self) -> bool:
        return self.trade_filter in ("ALLOW_SELL", "NEUTRAL")

    def summary(self) -> str:
        return (
            f"Macro Context:\n"
            f"  Risk Regime  : {self.risk_regime}\n"
            f"  FED Stance   : {self.fed_stance} ({self.fed_rate}%)\n"
            f"  Inflation    : {self.inflation_trend} (CPI {self.cpi_yoy}%)\n"
            f"  USD Trend    : {self.usd_trend} (DXY {self.dxy_value})\n"
            f"  Gold Bias    : {self.gold_bias}\n"
            f"  Macro Score  : {self.macro_score:.0f}/100\n"
            f"  Trade Filter : {self.trade_filter}"
        )


class MacroFilter:
    """
    Evaluates the global macro environment and returns a MacroContext
    that gates trade execution.

    Logic:
      Gold is BULLISH when:
        - FED is DOVISH (rates falling / pausing)        → +25 pts
        - Inflation is RISING (real rates falling)       → +20 pts
        - USD is WEAKENING (DXY falling)                 → +25 pts
        - Environment is RISK-OFF (fear/uncertainty)     → +30 pts

      Gold is BEARISH when the opposite conditions hold.
    """

    def evaluate(self) -> MacroContext:
        """Run full macro evaluation. Returns a MacroContext."""
        ctx = MacroContext()

        # Fetch data
        ctx.fed_rate = self._fetch_fed_rate()
        ctx.cpi_yoy, ctx.inflation_trend = self._fetch_cpi()
        ctx.dxy_value, ctx.usd_trend = self._fetch_dxy()

        # Classify
        ctx.fed_stance = self._classify_fed(ctx.fed_rate)
        ctx.risk_regime = self._classify_risk(ctx)

        # Score
        ctx.macro_score, ctx.gold_bias = self._compute_score(ctx)

        # Trade filter
        ctx.trade_filter = self._determine_filter(ctx)

        # Notes
        ctx.notes = self._build_notes(ctx)

        logger.info(
            "MacroFilter: score={:.1f} bias={} filter={} risk={}",
            ctx.macro_score, ctx.gold_bias, ctx.trade_filter, ctx.risk_regime,
        )
        return ctx

    # ── Data Fetching ──────────────────────────────────────────────────────

    def _fetch_fed_rate(self) -> Optional[float]:
        """Fetch US Fed Funds Rate from FRED (St. Louis Fed)."""
        try:
            resp = requests.get(
                "https://fred.stlouisfed.org/graph/fredgraph.csv?id=FEDFUNDS",
                timeout=8,
            )
            last_line = resp.text.strip().split("\n")[-1]
            return float(last_line.split(",")[1])
        except Exception as exc:
            logger.debug("FRED fetch failed: {}", exc)
            return 5.25  # Fallback: approximate current rate

    def _fetch_cpi(self) -> tuple[Optional[float], Trend]:
        """Fetch US CPI YoY from BLS (Bureau of Labor Statistics)."""
        try:
            resp = requests.post(
                "https://api.bls.gov/publicAPI/v2/timeseries/data/",
                json={"seriesid": ["CUUR0000SA0"], "startyear": "2024", "endyear": "2026"},
                timeout=8,
            )
            series = resp.json().get("Results", {}).get("series", [{}])[0]
            values = [float(p["value"]) for p in series.get("data", [])[:3]]
            if len(values) >= 2:
                trend: Trend = "UP" if values[0] > values[1] else ("DOWN" if values[0] < values[1] else "SIDEWAYS")
                return values[0], trend
        except Exception as exc:
            logger.debug("BLS CPI fetch failed: {}", exc)
        return 3.2, "SIDEWAYS"

    def _fetch_dxy(self) -> tuple[Optional[float], Trend]:
        """Approximate DXY from EUR/USD (primary DXY component)."""
        try:
            resp = requests.get(
                "https://api.frankfurter.app/latest?from=USD&to=EUR",
                timeout=6,
            )
            eur_usd = resp.json().get("rates", {}).get("EUR", 1.05)
            # EUR/USD inversely correlates with DXY
            if eur_usd > 1.08:
                return 100.5, "DOWN"   # USD weak
            elif eur_usd < 1.02:
                return 106.5, "UP"     # USD strong
            else:
                return 103.0, "SIDEWAYS"
        except Exception as exc:
            logger.debug("DXY fetch failed: {}", exc)
            return 103.0, "SIDEWAYS"

    # ── Classification ─────────────────────────────────────────────────────

    def _classify_fed(self, rate: Optional[float]) -> FedStance:
        """
        Classify FED stance based on rate level + news headlines.
        High rate + cuts expected → DOVISH.
        High rate + no cuts → HAWKISH.
        """
        if rate is None:
            return "NEUTRAL"
        if rate >= 5.0:
            if self._news_signals_cuts():
                return "DOVISH"
            return "HAWKISH"
        if rate <= 3.0:
            return "DOVISH"
        return "NEUTRAL"

    def _news_signals_cuts(self) -> bool:
        """Quick news check for FED dovish/hawkish signals."""
        if not NEWS_API_KEY:
            return False
        try:
            resp = requests.get(
                "https://newsapi.org/v2/everything",
                params={
                    "q": "Federal Reserve rate cut pause pivot 2025",
                    "language": "en",
                    "pageSize": 5,
                    "sortBy": "publishedAt",
                    "apiKey": NEWS_API_KEY,
                },
                timeout=6,
            )
            headlines = " ".join(
                (a.get("title", "") + " " + a.get("description", "")).lower()
                for a in resp.json().get("articles", [])
            )
            dovish_score = sum(1 for w in ["cut", "pause", "pivot", "lower", "easing"] if w in headlines)
            hawkish_score = sum(1 for w in ["hike", "raise", "tighten", "higher for longer"] if w in headlines)
            return dovish_score > hawkish_score
        except Exception:
            return False

    def _classify_risk(self, ctx: MacroContext) -> RiskRegime:
        """
        RISK-OFF indicators (bullish for gold):
          - Hawkish FED + slowing economy
          - Geopolitical stress (from news — qualitative)
          - Rising inflation
          - Weak USD
        """
        risk_off = 0
        if ctx.fed_stance == "HAWKISH":
            risk_off += 1
        if ctx.inflation_trend == "UP":
            risk_off += 1
        if ctx.usd_trend == "DOWN":
            risk_off += 1  # Weak USD often accompanies risk-off in gold context
        if ctx.cpi_yoy and ctx.cpi_yoy > 4.0:
            risk_off += 1

        if risk_off >= 3:
            return "RISK-OFF"
        if risk_off == 0:
            return "RISK-ON"
        return "NEUTRAL"

    # ── Scoring ────────────────────────────────────────────────────────────

    def _compute_score(self, ctx: MacroContext) -> tuple[float, str]:
        """
        Score 0–100: how bullish the macro environment is for gold.
        50 = neutral; >60 = bullish; <40 = bearish.
        """
        score = 50.0

        # FED stance
        if ctx.fed_stance == "DOVISH":
            score += 25
        elif ctx.fed_stance == "HAWKISH":
            score -= 20

        # Inflation
        if ctx.inflation_trend == "UP":
            score += 20
        elif ctx.inflation_trend == "DOWN":
            score -= 15

        # USD
        if ctx.usd_trend == "DOWN":
            score += 25
        elif ctx.usd_trend == "UP":
            score -= 20

        # Risk regime
        if ctx.risk_regime == "RISK-OFF":
            score += 15
        elif ctx.risk_regime == "RISK-ON":
            score -= 10

        score = max(0.0, min(100.0, round(score, 1)))

        bias = "BULLISH" if score >= 60 else ("BEARISH" if score <= 40 else "NEUTRAL")
        return score, bias

    def _determine_filter(self, ctx: MacroContext) -> TradeFilter:
        """
        Gate trade execution based on macro context.
          - Strong bullish macro → ALLOW_BUY
          - Strong bearish macro → ALLOW_SELL
          - Mixed/neutral → NEUTRAL (allow both with caution)
          - Extreme conditions → BLOCK (wait for clarity)
        """
        if ctx.macro_score >= 70:
            return "ALLOW_BUY"
        if ctx.macro_score <= 30:
            return "ALLOW_SELL"
        if 45 <= ctx.macro_score <= 55 and ctx.risk_regime == "NEUTRAL":
            return "NEUTRAL"
        if ctx.macro_score > 55:
            return "ALLOW_BUY"
        if ctx.macro_score < 45:
            return "ALLOW_SELL"
        return "NEUTRAL"

    def _build_notes(self, ctx: MacroContext) -> list[str]:
        notes = []
        if ctx.fed_stance == "DOVISH":
            notes.append("FED dovish → pression baissière sur USD → haussier or")
        elif ctx.fed_stance == "HAWKISH":
            notes.append("FED hawkish → USD potentiellement fort → attention")
        if ctx.inflation_trend == "UP":
            notes.append(f"Inflation en hausse (CPI {ctx.cpi_yoy}%) → haussier or")
        if ctx.usd_trend == "DOWN":
            notes.append("DXY en baisse → favorable or")
        if ctx.risk_regime == "RISK-OFF":
            notes.append("Environnement RISK-OFF → demande safe-haven or ↑")
        elif ctx.risk_regime == "RISK-ON":
            notes.append("Environnement RISK-ON → or sous pression potentielle")
        return notes
