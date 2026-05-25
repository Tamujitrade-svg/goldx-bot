"""
GoldX Assistant — Market Structure Analyzer

Identifies the full market structure on a given timeframe:
  - Trend: HH/HL (bullish) or LH/LL (bearish) or ranging
  - Swing highs/lows
  - Fair Value Gaps (FVG / imbalances)
  - Order Blocks (OB)
  - Break of Structure (BOS) / Change of Character (ChoCH)
  - Daily / Weekly levels
  - Supply & Demand zones

Returns a MarketStructureResult with context for smart money concepts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import numpy as np
import pandas as pd

from utils.logger import logger

Direction = Literal["BULLISH", "BEARISH", "RANGING"]


@dataclass
class SwingPoint:
    price: float
    index: int
    type: str  # "HIGH" or "LOW"


@dataclass
class FairValueGap:
    upper: float
    lower: float
    midpoint: float
    direction: str     # "BULLISH" or "BEARISH"
    candle_index: int
    filled: bool = False


@dataclass
class OrderBlock:
    upper: float
    lower: float
    midpoint: float
    direction: str     # "BULLISH" (demand) or "BEARISH" (supply)
    candle_index: int
    strength: str      # "STRONG" / "MEDIUM" / "WEAK"
    touched: bool = False


@dataclass
class MarketStructureResult:
    trend: Direction = "RANGING"
    trend_strength: str = "WEAK"       # STRONG / MODERATE / WEAK
    last_bos: str = "NONE"             # BOS_UP / BOS_DOWN / NONE
    last_choch: str = "NONE"           # CHOCH_UP / CHOCH_DOWN / NONE
    swing_highs: list[SwingPoint] = field(default_factory=list)
    swing_lows: list[SwingPoint] = field(default_factory=list)
    fvgs: list[FairValueGap] = field(default_factory=list)
    order_blocks: list[OrderBlock] = field(default_factory=list)
    current_price: float = 0.0
    nearest_support: float = 0.0
    nearest_resistance: float = 0.0
    premium_zone: float = 0.0     # 79% of last swing range
    discount_zone: float = 0.0    # 21% of last swing range
    equilibrium: float = 0.0      # 50% of last swing range
    narrative: str = ""

    def format_summary(self) -> str:
        trend_icon = {"BULLISH": "📈", "BEARISH": "📉", "RANGING": "↔️"}[self.trend]
        lines = [
            f"🏗 **STRUCTURE DE MARCHÉ**",
            "",
            f"{trend_icon} Tendance     : **{self.trend}** ({self.trend_strength})",
            f"💥 Dernier BOS  : {self.last_bos}",
            f"🔄 Dernier CHoCH: {self.last_choch}",
            "",
            f"🎯 **NIVEAUX CLÉS**",
            f"  Résistance    : `{self.nearest_resistance:.2f}`",
            f"  Prix actuel   : `{self.current_price:.2f}`",
            f"  Support       : `{self.nearest_support:.2f}`",
            "",
            f"⚖️ **ZONES DE PRIX**",
            f"  Premium (79%) : `{self.premium_zone:.2f}`",
            f"  Équilibre (50%): `{self.equilibrium:.2f}`",
            f"  Discount (21%): `{self.discount_zone:.2f}`",
        ]
        if self.order_blocks:
            lines += ["", "📦 **ORDER BLOCKS ACTIFS**"]
            for ob in self.order_blocks[:3]:
                icon = "🟢" if ob.direction == "BULLISH" else "🔴"
                lines.append(f"  {icon} {ob.direction} OB: `{ob.lower:.2f}` – `{ob.upper:.2f}` [{ob.strength}]")
        if self.fvgs:
            lines += ["", "🕳 **FAIR VALUE GAPS**"]
            for fvg in self.fvgs[:3]:
                icon = "📈" if fvg.direction == "BULLISH" else "📉"
                lines.append(f"  {icon} FVG: `{fvg.lower:.2f}` – `{fvg.upper:.2f}` (mid: `{fvg.midpoint:.2f}`)")
        if self.narrative:
            lines += ["", f"💡 _{self.narrative}_"]
        return "\n".join(lines)


class MarketStructureAnalyzer:
    """Identifies market structure using swing analysis and SMC concepts."""

    def analyze(self, df: pd.DataFrame, current_price: float = 0.0) -> MarketStructureResult:
        if len(df) < 30:
            return MarketStructureResult(narrative="Pas assez de données.")

        result = MarketStructureResult()
        result.current_price = current_price or float(df["close"].iloc[-1])

        # Swing points
        highs, lows = self._find_swings(df)
        result.swing_highs = highs
        result.swing_lows = lows

        # Trend
        result.trend, result.trend_strength = self._classify_trend(highs, lows)

        # BOS / CHoCH
        result.last_bos, result.last_choch = self._find_bos_choch(df, highs, lows)

        # Support / Resistance from recent swings
        result.nearest_support = self._nearest_support(lows, result.current_price)
        result.nearest_resistance = self._nearest_resistance(highs, result.current_price)

        # Premium / Discount zones
        if result.nearest_support > 0 and result.nearest_resistance > 0:
            swing_range = result.nearest_resistance - result.nearest_support
            result.equilibrium = result.nearest_support + swing_range * 0.5
            result.premium_zone = result.nearest_support + swing_range * 0.79
            result.discount_zone = result.nearest_support + swing_range * 0.21

        # FVGs
        result.fvgs = self._find_fvgs(df)

        # Order Blocks
        result.order_blocks = self._find_order_blocks(df)

        # Narrative
        result.narrative = self._build_narrative(result)

        logger.debug(
            "Market Structure: trend={} BOS={} support={:.2f} resistance={:.2f}",
            result.trend, result.last_bos,
            result.nearest_support, result.nearest_resistance,
        )
        return result

    # ── Swing Detection ────────────────────────────────────────────────

    def _find_swings(self, df: pd.DataFrame, left: int = 5, right: int = 5) -> tuple[list[SwingPoint], list[SwingPoint]]:
        highs = []
        lows = []
        for i in range(left, len(df) - right):
            window_h = df["high"].iloc[i - left:i + right + 1]
            window_l = df["low"].iloc[i - left:i + right + 1]
            if df["high"].iloc[i] == window_h.max():
                highs.append(SwingPoint(float(df["high"].iloc[i]), i, "HIGH"))
            if df["low"].iloc[i] == window_l.min():
                lows.append(SwingPoint(float(df["low"].iloc[i]), i, "LOW"))
        return highs[-10:], lows[-10:]

    def _classify_trend(self, highs: list[SwingPoint], lows: list[SwingPoint]) -> tuple[Direction, str]:
        if len(highs) < 2 or len(lows) < 2:
            return "RANGING", "WEAK"

        hh = highs[-1].price > highs[-2].price  # Higher High
        hl = lows[-1].price > lows[-2].price    # Higher Low
        lh = highs[-1].price < highs[-2].price  # Lower High
        ll = lows[-1].price < lows[-2].price    # Lower Low

        if hh and hl:
            # Check strength by consistency
            strength = "STRONG" if len(highs) >= 3 and highs[-2].price > highs[-3].price else "MODERATE"
            return "BULLISH", strength
        if lh and ll:
            strength = "STRONG" if len(lows) >= 3 and lows[-2].price < lows[-3].price else "MODERATE"
            return "BEARISH", strength
        return "RANGING", "WEAK"

    def _find_bos_choch(
        self, df: pd.DataFrame,
        highs: list[SwingPoint],
        lows: list[SwingPoint],
    ) -> tuple[str, str]:
        if not highs or not lows:
            return "NONE", "NONE"

        last_close = float(df["close"].iloc[-1])
        prev_close = float(df["close"].iloc[-2]) if len(df) > 1 else last_close

        bos = "NONE"
        choch = "NONE"

        if highs:
            last_high = highs[-1].price
            if prev_close < last_high <= last_close:
                bos = "BOS_UP"
            prev_prev_high = highs[-2].price if len(highs) >= 2 else last_high
            if prev_close < prev_prev_high <= last_close and last_close > last_high:
                choch = "CHOCH_UP"

        if lows:
            last_low = lows[-1].price
            if prev_close > last_low >= last_close:
                bos = "BOS_DOWN"
            prev_prev_low = lows[-2].price if len(lows) >= 2 else last_low
            if prev_close > prev_prev_low >= last_close and last_close < last_low:
                choch = "CHOCH_DOWN"

        return bos, choch

    def _nearest_support(self, lows: list[SwingPoint], price: float) -> float:
        below = [s.price for s in lows if s.price < price]
        return max(below) if below else (lows[-1].price if lows else 0.0)

    def _nearest_resistance(self, highs: list[SwingPoint], price: float) -> float:
        above = [s.price for s in highs if s.price > price]
        return min(above) if above else (highs[-1].price if highs else 0.0)

    # ── FVG Detection ──────────────────────────────────────────────────

    def _find_fvgs(self, df: pd.DataFrame) -> list[FairValueGap]:
        """A Fair Value Gap is a 3-candle imbalance."""
        fvgs = []
        for i in range(2, min(len(df), 50)):
            c1_high = float(df["high"].iloc[i - 2])
            c3_low  = float(df["low"].iloc[i])
            c1_low  = float(df["low"].iloc[i - 2])
            c3_high = float(df["high"].iloc[i])

            # Bullish FVG: C1 high < C3 low (gap up)
            if c3_low > c1_high:
                mid = (c3_low + c1_high) / 2
                fvgs.append(FairValueGap(upper=c3_low, lower=c1_high, midpoint=mid,
                                          direction="BULLISH", candle_index=i))
            # Bearish FVG: C3 high < C1 low (gap down)
            elif c3_high < c1_low:
                mid = (c3_high + c1_low) / 2
                fvgs.append(FairValueGap(upper=c1_low, lower=c3_high, midpoint=mid,
                                          direction="BEARISH", candle_index=i))
        return fvgs[-5:]  # Last 5 FVGs

    # ── Order Block Detection ──────────────────────────────────────────

    def _find_order_blocks(self, df: pd.DataFrame) -> list[OrderBlock]:
        """
        Order Block = last opposing candle before a strong move.
        Bullish OB: last bearish candle before impulsive bullish move.
        Bearish OB: last bullish candle before impulsive bearish move.
        """
        obs = []
        for i in range(5, min(len(df), 80)):
            # Impulse detection: next 3 candles move strongly
            move = float(df["close"].iloc[i + 3]) - float(df["close"].iloc[i]) if i + 3 < len(df) else 0
            atr_approx = float(df["high"].iloc[i] - df["low"].iloc[i]) * 3

            if abs(move) < atr_approx * 0.5:
                continue

            candle_is_bearish = float(df["close"].iloc[i]) < float(df["open"].iloc[i])
            candle_is_bullish = float(df["close"].iloc[i]) > float(df["open"].iloc[i])

            if move > 0 and candle_is_bearish:
                # Bullish OB
                upper = max(float(df["open"].iloc[i]), float(df["close"].iloc[i]))
                lower = min(float(df["open"].iloc[i]), float(df["close"].iloc[i]))
                strength = "STRONG" if abs(move) > atr_approx else "MEDIUM"
                obs.append(OrderBlock(upper=upper, lower=lower, midpoint=(upper + lower) / 2,
                                       direction="BULLISH", candle_index=i, strength=strength))
            elif move < 0 and candle_is_bullish:
                # Bearish OB
                upper = max(float(df["open"].iloc[i]), float(df["close"].iloc[i]))
                lower = min(float(df["open"].iloc[i]), float(df["close"].iloc[i]))
                strength = "STRONG" if abs(move) > atr_approx else "MEDIUM"
                obs.append(OrderBlock(upper=upper, lower=lower, midpoint=(upper + lower) / 2,
                                       direction="BEARISH", candle_index=i, strength=strength))
        return obs[-5:]

    def _build_narrative(self, r: MarketStructureResult) -> str:
        price = r.current_price
        if r.trend == "BULLISH":
            if price > r.premium_zone:
                return f"Prix en zone PREMIUM ({r.premium_zone:.2f}) — potentiel retracement. Attendre discount pour BUY."
            if price < r.discount_zone:
                return f"Prix en zone DISCOUNT ({r.discount_zone:.2f}) — zone d'accumulation. BUY optimal."
            return f"Prix entre équilibre et premium. Structure haussière maintenue."
        if r.trend == "BEARISH":
            if price < r.discount_zone:
                return f"Prix en zone DISCOUNT — zone de distribution. SELL optimal."
            if price > r.premium_zone:
                return f"Prix en zone PREMIUM — retracement attendu. SELL confirmé."
            return f"Prix entre discount et équilibre. Structure baissière maintenue."
        return "Marché en range — attendre breakout avec volume pour confirmer direction."
