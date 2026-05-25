"""
GoldX Assistant — Multi-Timeframe Confluence Analyzer

Analyzes XAU/USD across 5 timeframes simultaneously:
  D1  → Macro trend & key levels
  H4  → Intermediate structure
  H1  → Entry zone context
  M15 → Entry timeframe
  M5  → Precision entry / confirmation

Returns a MTFResult with:
  - Per-timeframe bias
  - Confluence score (how many TF agree)
  - Alignment grade (A / B / C / D)
  - Recommended entry timeframe
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import pandas as pd

from utils.logger import logger
from data.price_feed import PriceFeed
from core.technical_analyzer import TechnicalAnalyzer, TechnicalResult
from config import SYMBOL

Direction = Literal["BUY", "SELL", "NEUTRAL"]
Grade = Literal["A", "B", "C", "D"]

TIMEFRAMES = ["D1", "H4", "H1", "M15", "M5"]
TF_LABELS = {
    "D1":  "Journalier (macro)",
    "H4":  "4 Heures (structure)",
    "H1":  "1 Heure (contexte)",
    "M15": "15 Min (entrée)",
    "M5":  "5 Min (précision)",
}
TF_WEIGHT = {"D1": 3, "H4": 2.5, "H1": 2, "M15": 1.5, "M5": 1}


@dataclass
class TimeframeResult:
    timeframe: str
    direction: Direction
    score: float          # 0–100
    rsi: float
    ema_trend: Direction
    breakout: Direction
    key_level: float      # nearest support/resistance
    candle_count: int


@dataclass
class MTFResult:
    timeframes: dict[str, TimeframeResult] = field(default_factory=dict)
    dominant_direction: Direction = "NEUTRAL"
    confluence_score: float = 0.0     # 0–100
    aligned_count: int = 0            # how many TF agree
    grade: Grade = "D"
    entry_tf: str = "M15"
    htf_bias: Direction = "NEUTRAL"   # D1 + H4 consensus
    ltf_signal: Direction = "NEUTRAL" # M15 + M5 consensus
    narrative: str = ""
    key_levels: list[float] = field(default_factory=list)

    def summary_lines(self) -> list[str]:
        lines = []
        icons = {"BUY": "📈", "SELL": "📉", "NEUTRAL": "➡️"}
        for tf in TIMEFRAMES:
            if tf not in self.timeframes:
                continue
            r = self.timeframes[tf]
            bar = "█" * int(r.score / 10) + "░" * (10 - int(r.score / 10))
            lines.append(
                f"  {icons[r.direction]} **{tf}** — {TF_LABELS[tf]}\n"
                f"     Score: {r.score:.0f}/100  {bar}\n"
                f"     RSI: {r.rsi:.0f}  EMA: {r.ema_trend}  Break: {r.breakout}"
            )
        return lines


class MTFAnalyzer:
    """Multi-timeframe confluence analysis."""

    def __init__(self) -> None:
        self._price_feed = PriceFeed()
        self._tech = TechnicalAnalyzer()

    def analyze(self, symbol: str = SYMBOL, use_mock: bool = False) -> MTFResult:
        result = MTFResult()
        tf_results: dict[str, TimeframeResult] = {}

        for tf in TIMEFRAMES:
            bars = {"D1": 200, "H4": 200, "H1": 200, "M15": 300, "M5": 300}.get(tf, 200)
            try:
                df = self._price_feed.get_ohlcv(symbol=symbol, timeframe=tf, bars=bars)
                tech = self._tech.analyze(df)
                key_level = self._nearest_key_level(df)
                tf_results[tf] = TimeframeResult(
                    timeframe=tf,
                    direction=tech.direction,
                    score=tech.score,
                    rsi=tech.rsi,
                    ema_trend=tech.ema_trend,
                    breakout=tech.breakout,
                    key_level=key_level,
                    candle_count=len(df),
                )
            except Exception as exc:
                logger.warning("MTF {} analysis failed: {}", tf, exc)

        result.timeframes = tf_results

        # HTF bias: D1 + H4
        htf_dirs = [tf_results[t].direction for t in ("D1", "H4") if t in tf_results]
        result.htf_bias = self._majority_direction(htf_dirs)

        # LTF signal: M15 + M5
        ltf_dirs = [tf_results[t].direction for t in ("M15", "M5") if t in tf_results]
        result.ltf_signal = self._majority_direction(ltf_dirs)

        # All TF consensus
        all_dirs = [r.direction for r in tf_results.values()]
        result.dominant_direction = self._majority_direction(all_dirs)
        result.aligned_count = sum(1 for d in all_dirs if d == result.dominant_direction and d != "NEUTRAL")

        # Weighted confluence score
        result.confluence_score = self._compute_confluence(tf_results, result.dominant_direction)
        result.grade = self._grade(result.aligned_count, result.confluence_score)

        # Recommended entry timeframe
        result.entry_tf = self._recommend_entry_tf(result)

        # Key levels
        result.key_levels = sorted({
            r.key_level for r in tf_results.values() if r.key_level > 0
        })[:5]

        # Narrative
        result.narrative = self._build_narrative(result)

        logger.info(
            "MTF: dir={} confluence={:.0f} grade={} aligned={}/{}",
            result.dominant_direction, result.confluence_score,
            result.grade, result.aligned_count, len(tf_results),
        )
        return result

    # ── Helpers ────────────────────────────────────────────────────────────

    def _majority_direction(self, dirs: list[Direction]) -> Direction:
        if not dirs:
            return "NEUTRAL"
        buy = dirs.count("BUY")
        sell = dirs.count("SELL")
        if buy > sell:
            return "BUY"
        if sell > buy:
            return "SELL"
        return "NEUTRAL"

    def _compute_confluence(self, tf_results: dict[str, TimeframeResult], dominant: Direction) -> float:
        if dominant == "NEUTRAL":
            return 50.0
        total_w = 0.0
        aligned_w = 0.0
        for tf, r in tf_results.items():
            w = TF_WEIGHT.get(tf, 1)
            total_w += w
            if r.direction == dominant:
                aligned_w += w * (r.score / 100)
        return round((aligned_w / total_w) * 100 if total_w > 0 else 50.0, 1)

    def _grade(self, aligned: int, confluence: float) -> Grade:
        if aligned >= 4 and confluence >= 75:
            return "A"
        if aligned >= 3 and confluence >= 60:
            return "B"
        if aligned >= 2 and confluence >= 45:
            return "C"
        return "D"

    def _recommend_entry_tf(self, result: MTFResult) -> str:
        # Enter on M15 when HTF agrees; use M5 for precision if grade A
        if result.grade == "A" and "M5" in result.timeframes:
            return "M5"
        if result.htf_bias == result.dominant_direction and "M15" in result.timeframes:
            return "M15"
        return "H1"

    def _nearest_key_level(self, df: pd.DataFrame, lookback: int = 50) -> float:
        if len(df) < lookback:
            return 0.0
        recent = df.tail(lookback)
        highs = recent["high"].nlargest(3).mean()
        lows = recent["low"].nsmallest(3).mean()
        current = float(df["close"].iloc[-1])
        return highs if abs(current - highs) < abs(current - lows) else lows

    def _build_narrative(self, r: MTFResult) -> str:
        if r.grade == "A":
            return (
                f"Configuration {r.grade} — confluence exceptionnelle. "
                f"{r.aligned_count}/5 timeframes alignés en {r.dominant_direction}. "
                f"HTF confirme, LTF prêt. Entrée sur {r.entry_tf}."
            )
        if r.grade == "B":
            return (
                f"Configuration {r.grade} — bonne confluence. "
                f"HTF bias={r.htf_bias}, signal LTF={r.ltf_signal}. "
                f"Attendre confirmation sur {r.entry_tf}."
            )
        if r.grade == "C":
            return (
                f"Configuration {r.grade} — confluence partielle. "
                f"Seulement {r.aligned_count} TF alignés. "
                f"Prudence — réduire la taille de position."
            )
        return (
            f"Configuration {r.grade} — peu de confluence. "
            f"TF en désaccord. Ne pas trader en l'état."
        )
