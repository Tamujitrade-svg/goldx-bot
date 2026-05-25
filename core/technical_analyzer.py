"""
GoldX Bot — Technical Analyzer (Pillar 1)

Computes:
  - RSI, MACD, EMA (20/50/200), Bollinger Bands, ATR
  - Breakout detection (structure highs/lows)
  - Liquidity sweep detection
  - Session context (Asia / London / NY)
  - Returns a score 0–100 and a directional bias (BUY / SELL / NEUTRAL)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

import numpy as np
import pandas as pd
import pytz

from utils.logger import logger
from config import SESSIONS

try:
    import ta
    TA_AVAILABLE = True
except ImportError:
    TA_AVAILABLE = False
    logger.warning("'ta' library not installed — using manual indicators.")

UTC = pytz.UTC
Direction = Literal["BUY", "SELL", "NEUTRAL"]


@dataclass
class TechnicalResult:
    score: float                      # 0–100
    direction: Direction              # BUY / SELL / NEUTRAL
    rsi: float = 0.0
    macd_signal: Direction = "NEUTRAL"
    ema_trend: Direction = "NEUTRAL"
    breakout: Direction = "NEUTRAL"
    liquidity_sweep: Direction = "NEUTRAL"
    session: str = "UNKNOWN"
    atr: float = 0.0
    details: dict = field(default_factory=dict)


class TechnicalAnalyzer:
    """Runs full technical analysis on an OHLCV DataFrame."""

    # ── Public Interface ───────────────────────────────────────────────────

    def analyze(self, df: pd.DataFrame) -> TechnicalResult:
        if df is None or len(df) < 50:
            logger.warning("Not enough bars for technical analysis.")
            return TechnicalResult(score=50.0, direction="NEUTRAL")

        df = df.copy()
        df = self._add_indicators(df)

        rsi = self._get_rsi_signal(df)
        macd = self._get_macd_signal(df)
        ema = self._get_ema_trend(df)
        breakout = self._get_breakout(df)
        liquidity = self._get_liquidity_sweep(df)
        session = self._get_current_session()
        atr = float(df["atr"].iloc[-1]) if "atr" in df.columns else 0.0

        score, direction = self._compute_score(rsi, macd, ema, breakout, liquidity, session)

        result = TechnicalResult(
            score=score,
            direction=direction,
            rsi=float(df["rsi"].iloc[-1]) if "rsi" in df.columns else 50.0,
            macd_signal=macd,
            ema_trend=ema,
            breakout=breakout,
            liquidity_sweep=liquidity,
            session=session,
            atr=atr,
            details={
                "close": float(df["close"].iloc[-1]),
                "ema20": float(df["ema20"].iloc[-1]) if "ema20" in df.columns else 0.0,
                "ema50": float(df["ema50"].iloc[-1]) if "ema50" in df.columns else 0.0,
                "ema200": float(df["ema200"].iloc[-1]) if "ema200" in df.columns else 0.0,
            },
        )
        logger.info(
            "Technical: score={:.1f} dir={} RSI={:.1f} session={}",
            score, direction, result.rsi, session,
        )
        return result

    # ── Indicators ─────────────────────────────────────────────────────────

    def _add_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        if TA_AVAILABLE:
            df["rsi"] = ta.momentum.RSIIndicator(close=df["close"], window=14).rsi()
            macd_obj = ta.trend.MACD(close=df["close"])
            df["macd"] = macd_obj.macd()
            df["macd_signal_line"] = macd_obj.macd_signal()
            df["macd_hist"] = macd_obj.macd_diff()
            df["ema20"] = ta.trend.EMAIndicator(close=df["close"], window=20).ema_indicator()
            df["ema50"] = ta.trend.EMAIndicator(close=df["close"], window=50).ema_indicator()
            df["ema200"] = ta.trend.EMAIndicator(close=df["close"], window=200).ema_indicator()
            df["atr"] = ta.volatility.AverageTrueRange(
                high=df["high"], low=df["low"], close=df["close"], window=14
            ).average_true_range()
            bb = ta.volatility.BollingerBands(close=df["close"], window=20, window_dev=2)
            df["bb_upper"] = bb.bollinger_hband()
            df["bb_lower"] = bb.bollinger_lband()
            df["bb_mid"] = bb.bollinger_mavg()
        else:
            # Manual fallback
            df["rsi"] = self._manual_rsi(df["close"], 14)
            df["ema20"] = df["close"].ewm(span=20, adjust=False).mean()
            df["ema50"] = df["close"].ewm(span=50, adjust=False).mean()
            df["ema200"] = df["close"].ewm(span=200, adjust=False).mean()
            ema12 = df["close"].ewm(span=12, adjust=False).mean()
            ema26 = df["close"].ewm(span=26, adjust=False).mean()
            df["macd"] = ema12 - ema26
            df["macd_signal_line"] = df["macd"].ewm(span=9, adjust=False).mean()
            df["macd_hist"] = df["macd"] - df["macd_signal_line"]
            tr = pd.concat([
                df["high"] - df["low"],
                (df["high"] - df["close"].shift()).abs(),
                (df["low"] - df["close"].shift()).abs(),
            ], axis=1).max(axis=1)
            df["atr"] = tr.rolling(14).mean()
        df.dropna(inplace=True)
        return df

    @staticmethod
    def _manual_rsi(series: pd.Series, window: int = 14) -> pd.Series:
        delta = series.diff()
        gain = delta.clip(lower=0).rolling(window).mean()
        loss = (-delta.clip(upper=0)).rolling(window).mean()
        rs = gain / loss.replace(0, np.nan)
        return 100 - (100 / (1 + rs))

    # ── Signal Extractors ──────────────────────────────────────────────────

    def _get_rsi_signal(self, df: pd.DataFrame) -> Direction:
        rsi = float(df["rsi"].iloc[-1])
        if rsi < 35:
            return "BUY"
        if rsi > 65:
            return "SELL"
        return "NEUTRAL"

    def _get_macd_signal(self, df: pd.DataFrame) -> Direction:
        hist = df["macd_hist"].iloc[-3:]
        if len(hist) < 3:
            return "NEUTRAL"
        # Bullish cross: histogram moving from negative to positive
        if hist.iloc[-2] < 0 and hist.iloc[-1] > 0:
            return "BUY"
        if hist.iloc[-2] > 0 and hist.iloc[-1] < 0:
            return "SELL"
        # Continuation
        if hist.iloc[-1] > 0 and hist.iloc[-1] > hist.iloc[-2]:
            return "BUY"
        if hist.iloc[-1] < 0 and hist.iloc[-1] < hist.iloc[-2]:
            return "SELL"
        return "NEUTRAL"

    def _get_ema_trend(self, df: pd.DataFrame) -> Direction:
        close = float(df["close"].iloc[-1])
        ema20 = float(df["ema20"].iloc[-1])
        ema50 = float(df["ema50"].iloc[-1])
        ema200 = float(df["ema200"].iloc[-1])
        # Strong bull: price > ema20 > ema50 > ema200
        if close > ema20 > ema50 > ema200:
            return "BUY"
        if close < ema20 < ema50 < ema200:
            return "SELL"
        # Partial alignment
        if close > ema50 and ema20 > ema50:
            return "BUY"
        if close < ema50 and ema20 < ema50:
            return "SELL"
        return "NEUTRAL"

    def _get_breakout(self, df: pd.DataFrame, lookback: int = 20) -> Direction:
        """Detect breakout above recent structure high or below structure low."""
        if len(df) < lookback + 5:
            return "NEUTRAL"
        recent = df.iloc[-(lookback + 5):-5]
        current_close = float(df["close"].iloc[-1])
        structure_high = float(recent["high"].max())
        structure_low = float(recent["low"].min())
        atr = float(df["atr"].iloc[-1]) if "atr" in df.columns else 10.0

        if current_close > structure_high + atr * 0.1:
            return "BUY"
        if current_close < structure_low - atr * 0.1:
            return "SELL"
        return "NEUTRAL"

    def _get_liquidity_sweep(self, df: pd.DataFrame, lookback: int = 15) -> Direction:
        """
        Detect liquidity sweep (stop hunt then reversal):
        Price briefly wicks below/above a key level then closes back.
        """
        if len(df) < lookback + 3:
            return "NEUTRAL"
        recent = df.iloc[-(lookback + 3):-3]
        last_candle = df.iloc[-1]
        prev_low = float(recent["low"].min())
        prev_high = float(recent["high"].max())

        # Bearish wick below low → BUY signal (liquidity taken, reversal up)
        wick_below = float(last_candle["low"]) < prev_low
        closed_above = float(last_candle["close"]) > prev_low
        if wick_below and closed_above:
            return "BUY"

        # Bullish wick above high → SELL signal
        wick_above = float(last_candle["high"]) > prev_high
        closed_below = float(last_candle["close"]) < prev_high
        if wick_above and closed_below:
            return "SELL"

        return "NEUTRAL"

    def _get_current_session(self) -> str:
        now_utc_hour = datetime.now(tz=UTC).hour
        active = []
        for name, times in SESSIONS.items():
            if times["open"] <= now_utc_hour < times["close"]:
                active.append(name)
        if not active:
            return "OFF-HOURS"
        return "+".join(active)

    # ── Scoring ────────────────────────────────────────────────────────────

    def _compute_score(
        self,
        rsi: Direction,
        macd: Direction,
        ema: Direction,
        breakout: Direction,
        liquidity: Direction,
        session: str,
    ) -> tuple[float, Direction]:
        """
        Each signal contributes to BUY or SELL score.
        Weights: RSI=20, MACD=20, EMA=25, Breakout=25, Liquidity=10.
        Session bonus: +5 during London or NY overlap.
        """
        buy_score = 0.0
        sell_score = 0.0

        weights = {"rsi": 20, "macd": 20, "ema": 25, "breakout": 25, "liquidity": 10}
        signals = {"rsi": rsi, "macd": macd, "ema": ema, "breakout": breakout, "liquidity": liquidity}

        for name, sig in signals.items():
            w = weights[name]
            if sig == "BUY":
                buy_score += w
            elif sig == "SELL":
                sell_score += w

        # Session bonus
        session_bonus = 5.0 if any(s in session for s in ("LONDON", "NY")) else 0.0

        if buy_score >= sell_score:
            raw = buy_score + session_bonus
            direction: Direction = "BUY" if buy_score > 20 else "NEUTRAL"
        else:
            raw = sell_score + session_bonus
            direction = "SELL" if sell_score > 20 else "NEUTRAL"

        if direction == "NEUTRAL":
            raw = 50.0
        else:
            raw = min(100.0, raw)

        return round(raw, 1), direction
