"""
GoldX Bot — Fundamental / Macro Analyzer (Pillar 2)

Analyzes:
  - CPI inflation trends
  - FED interest rate stance (hawkish / dovish)
  - DXY Dollar Index direction
  - Risk-on vs Risk-off regime

Returns a score 0–100 and a directional bias for gold.
  Score > 65 → bullish gold (weak USD, dovish FED, high inflation)
  Score < 35 → bearish gold (strong USD, hawkish FED, falling inflation)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional

import requests

from utils.logger import logger
from config import NEWS_API_KEY

Direction = Literal["BUY", "SELL", "NEUTRAL"]
FedStance = Literal["DOVISH", "HAWKISH", "NEUTRAL"]
RiskRegime = Literal["RISK-OFF", "RISK-ON", "NEUTRAL"]


@dataclass
class MacroData:
    cpi_yoy: Optional[float] = None          # e.g. 3.2 = 3.2% YoY
    cpi_trend: str = "UNKNOWN"               # RISING / FALLING / STABLE
    fed_rate: Optional[float] = None         # e.g. 5.25
    fed_stance: FedStance = "NEUTRAL"
    dxy_value: Optional[float] = None
    dxy_trend: str = "UNKNOWN"               # UP / DOWN / SIDEWAYS
    risk_regime: RiskRegime = "NEUTRAL"


@dataclass
class FundamentalResult:
    score: float                             # 0–100
    direction: Direction
    macro_data: MacroData = field(default_factory=MacroData)
    details: dict = field(default_factory=dict)


class FundamentalAnalyzer:
    """
    Evaluates macro conditions for gold.

    Gold is bullish when:
      - Inflation HIGH and RISING → real rates falling
      - FED DOVISH (cutting rates / pausing)
      - USD WEAK (DXY falling)
      - Risk-OFF environment (fear in markets)
    """

    # ── Public Interface ───────────────────────────────────────────────────

    def analyze(self, macro_data: Optional[MacroData] = None) -> FundamentalResult:
        if macro_data is None:
            macro_data = self._fetch_macro_data()

        score, direction = self._compute_score(macro_data)
        result = FundamentalResult(
            score=score,
            direction=direction,
            macro_data=macro_data,
            details=self._build_details(macro_data),
        )
        logger.info(
            "Fundamental: score={:.1f} dir={} CPI={} FED={} DXY={}",
            score, direction,
            macro_data.cpi_yoy, macro_data.fed_stance, macro_data.dxy_trend,
        )
        return result

    # ── Data Fetching ──────────────────────────────────────────────────────

    def _fetch_macro_data(self) -> MacroData:
        """
        Attempt to fetch real macro data from free APIs.
        Falls back to mock data when unavailable.
        """
        data = MacroData()

        # FED rate from FRED (no key needed for public series)
        data.fed_rate = self._fetch_fed_rate()
        data.fed_stance = self._infer_fed_stance(data.fed_rate)

        # CPI approximate from cached last report (mock)
        data.cpi_yoy, data.cpi_trend = self._fetch_cpi_estimate()

        # DXY from free source
        data.dxy_value, data.dxy_trend = self._fetch_dxy()

        # Risk regime derived
        data.risk_regime = self._infer_risk_regime(data)

        return data

    def _fetch_fed_rate(self) -> Optional[float]:
        """Fetch latest Fed Funds Rate from FRED free API."""
        url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=FEDFUNDS"
        try:
            resp = requests.get(url, timeout=8)
            lines = resp.text.strip().split("\n")
            # Last line is most recent
            last = lines[-1].split(",")
            rate = float(last[1])
            logger.debug("FRED FEDFUNDS: {}%", rate)
            return rate
        except Exception as exc:
            logger.warning("FRED fetch failed: {} — using mock.", exc)
            return 5.25  # Mock: current approximate rate

    def _infer_fed_stance(self, rate: Optional[float]) -> FedStance:
        """
        Very simplified heuristic:
        - Rate > 5.0 and recent headlines say 'pause' → NEUTRAL
        - Rate cut underway → DOVISH
        - Rate hike cycle → HAWKISH
        We also check news headlines for context.
        """
        if rate is None:
            return "NEUTRAL"
        if rate >= 5.0:
            # Check if FED is signaling cuts
            if self._news_suggests_cuts():
                return "DOVISH"
            return "HAWKISH"
        if rate <= 3.0:
            return "DOVISH"
        return "NEUTRAL"

    def _news_suggests_cuts(self) -> bool:
        """Quick headline scan for dovish signals."""
        if not NEWS_API_KEY:
            return False
        try:
            resp = requests.get(
                "https://newsapi.org/v2/everything",
                params={
                    "q": "Federal Reserve rate cut pause pivot",
                    "language": "en",
                    "pageSize": 5,
                    "apiKey": NEWS_API_KEY,
                },
                timeout=6,
            )
            articles = resp.json().get("articles", [])
            dovish_terms = ["cut", "pause", "pivot", "lower", "reduce", "easing"]
            hawkish_terms = ["hike", "raise", "higher for longer", "tighten"]
            dovish = sum(1 for a in articles if any(t in (a.get("title", "") + a.get("description", "")).lower() for t in dovish_terms))
            hawkish = sum(1 for a in articles if any(t in (a.get("title", "") + a.get("description", "")).lower() for t in hawkish_terms))
            return dovish > hawkish
        except Exception:
            return False

    def _fetch_cpi_estimate(self) -> tuple[Optional[float], str]:
        """
        Fetch latest US CPI YoY from BLS public data.
        Returns (cpi_yoy, trend).
        """
        try:
            # BLS public API (no key needed for some series)
            resp = requests.post(
                "https://api.bls.gov/publicAPI/v2/timeseries/data/",
                json={"seriesid": ["CUUR0000SA0"], "startyear": "2024", "endyear": "2026"},
                timeout=8,
            )
            data = resp.json()
            series = data.get("Results", {}).get("series", [{}])[0]
            values = [float(p["value"]) for p in series.get("data", [])[:3]]
            if len(values) >= 2:
                current = values[0]
                prev = values[1]
                trend = "RISING" if current > prev else ("FALLING" if current < prev else "STABLE")
                return current, trend
        except Exception as exc:
            logger.warning("BLS CPI fetch failed: {} — using mock.", exc)
        return 3.2, "STABLE"  # Mock fallback

    def _fetch_dxy(self) -> tuple[Optional[float], str]:
        """
        Fetch DXY trend from a public JSON API or derive from news.
        Returns (dxy_value, trend).
        """
        try:
            # Use a financial data proxy — currencyapi free tier
            resp = requests.get(
                "https://api.frankfurter.app/latest?from=USD&to=EUR,GBP,JPY,CHF,SEK,CAD",
                timeout=6,
            )
            rates = resp.json().get("rates", {})
            # DXY approximation: USD is strong when EUR/USD is low
            eur_usd = rates.get("EUR", 1.0)
            if eur_usd > 1.08:
                trend = "DOWN"
                dxy = 100.5
            elif eur_usd < 1.02:
                trend = "UP"
                dxy = 106.0
            else:
                trend = "SIDEWAYS"
                dxy = 103.5
            return dxy, trend
        except Exception as exc:
            logger.warning("DXY fetch failed: {} — using mock.", exc)
            return 103.0, "SIDEWAYS"

    def _infer_risk_regime(self, data: MacroData) -> RiskRegime:
        """Determine if we are in risk-on or risk-off based on macro signals."""
        risk_off_points = 0
        if data.cpi_trend == "RISING":
            risk_off_points += 1
        if data.fed_stance == "HAWKISH":
            risk_off_points += 1
        if data.dxy_trend == "UP":
            risk_off_points += 1

        if risk_off_points >= 2:
            return "RISK-OFF"
        if risk_off_points == 0:
            return "RISK-ON"
        return "NEUTRAL"

    # ── Scoring ────────────────────────────────────────────────────────────

    def _compute_score(self, data: MacroData) -> tuple[float, Direction]:
        """
        Gold is BULLISH (BUY) when:
          - Inflation rising (+20)
          - FED dovish (+25)
          - USD weakening (+25)
          - Risk-off environment (+30)
        """
        score = 50.0  # Neutral baseline

        # CPI / Inflation
        if data.cpi_trend == "RISING":
            score += 20
        elif data.cpi_trend == "FALLING":
            score -= 15

        # FED stance
        if data.fed_stance == "DOVISH":
            score += 25
        elif data.fed_stance == "HAWKISH":
            score -= 20

        # DXY
        if data.dxy_trend == "DOWN":
            score += 25
        elif data.dxy_trend == "UP":
            score -= 20

        # Risk regime (most powerful for gold)
        if data.risk_regime == "RISK-OFF":
            score += 15
        elif data.risk_regime == "RISK-ON":
            score -= 10

        score = max(0.0, min(100.0, score))

        if score >= 60:
            direction: Direction = "BUY"
        elif score <= 40:
            direction = "SELL"
        else:
            direction = "NEUTRAL"

        return round(score, 1), direction

    def _build_details(self, data: MacroData) -> dict:
        return {
            "cpi_yoy": data.cpi_yoy,
            "cpi_trend": data.cpi_trend,
            "fed_rate": data.fed_rate,
            "fed_stance": data.fed_stance,
            "dxy_value": data.dxy_value,
            "dxy_trend": data.dxy_trend,
            "risk_regime": data.risk_regime,
        }
