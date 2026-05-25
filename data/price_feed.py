"""
GoldX Bot — Price Feed
Connects to MetaTrader 5 and returns OHLCV DataFrames.
Falls back to a mock feed when MT5 is unavailable (dev/test mode).
"""

from __future__ import annotations

import platform
from datetime import datetime
from typing import Optional

import numpy as np
import pandas as pd
import pytz

from utils.logger import logger
from config import MT5_LOGIN, MT5_PASSWORD, MT5_SERVER, MT5_PATH, SYMBOL

# MT5 is Windows-only; graceful degradation on Linux/Mac
MT5_AVAILABLE = False
try:
    if platform.system() == "Windows":
        import MetaTrader5 as mt5
        MT5_AVAILABLE = True
except ImportError:
    pass

# MT5 timeframe map
_TF_MAP = {
    "M1":  1,
    "M5":  5,
    "M15": 15,
    "M30": 30,
    "H1":  60,
    "H4":  240,
    "D1":  1440,
}


class PriceFeed:
    """Wraps MT5 connection and OHLCV retrieval."""

    def __init__(self) -> None:
        self._connected = False

    # ── Connection ─────────────────────────────────────────────────────────

    def connect(self) -> bool:
        if not MT5_AVAILABLE:
            logger.warning("MT5 not available on this OS — using mock price feed.")
            return False

        kwargs: dict = {"login": MT5_LOGIN, "password": MT5_PASSWORD, "server": MT5_SERVER}
        if MT5_PATH:
            kwargs["path"] = MT5_PATH

        if not mt5.initialize(**kwargs):  # type: ignore[name-defined]
            logger.error("MT5 initialize failed: {}", mt5.last_error())  # type: ignore[name-defined]
            return False

        info = mt5.account_info()  # type: ignore[name-defined]
        logger.info("MT5 connected — account={} balance={}", info.login, info.balance)
        self._connected = True
        return True

    def disconnect(self) -> None:
        if MT5_AVAILABLE and self._connected:
            mt5.shutdown()  # type: ignore[name-defined]
            self._connected = False
            logger.info("MT5 disconnected.")

    # ── Data Retrieval ─────────────────────────────────────────────────────

    def get_ohlcv(
        self,
        symbol: str = SYMBOL,
        timeframe: str = "M15",
        bars: int = 300,
    ) -> pd.DataFrame:
        """Return OHLCV DataFrame sorted oldest→newest."""
        if self._connected and MT5_AVAILABLE:
            return self._fetch_mt5(symbol, timeframe, bars)
        return self._mock_ohlcv(bars)

    def _fetch_mt5(self, symbol: str, timeframe: str, bars: int) -> pd.DataFrame:
        tf_minutes = _TF_MAP.get(timeframe, 15)
        tf_const = getattr(mt5, f"TIMEFRAME_M{tf_minutes}", mt5.TIMEFRAME_M15)  # type: ignore[name-defined]
        rates = mt5.copy_rates_from_pos(symbol, tf_const, 0, bars)  # type: ignore[name-defined]
        if rates is None or len(rates) == 0:
            logger.error("MT5 returned no rates for {}", symbol)
            return self._mock_ohlcv(bars)
        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
        df.rename(columns={"tick_volume": "volume"}, inplace=True)
        df = df[["time", "open", "high", "low", "close", "volume"]].copy()
        df.sort_values("time", inplace=True)
        df.reset_index(drop=True, inplace=True)
        return df

    def _mock_ohlcv(self, bars: int) -> pd.DataFrame:
        """Synthetic OHLCV for testing without MT5."""
        rng = pd.date_range(end=datetime.utcnow(), periods=bars, freq="15min", tz="UTC")
        np.random.seed(42)
        base = 2350.0
        noise = np.cumsum(np.random.randn(bars) * 3)
        close = base + noise
        high = close + np.abs(np.random.randn(bars) * 2)
        low = close - np.abs(np.random.randn(bars) * 2)
        open_ = close - np.random.randn(bars) * 1.5
        volume = np.random.randint(100, 1000, bars).astype(float)
        df = pd.DataFrame({"time": rng, "open": open_, "high": high, "low": low, "close": close, "volume": volume})
        return df

    def get_current_price(self, symbol: str = SYMBOL) -> Optional[float]:
        if self._connected and MT5_AVAILABLE:
            tick = mt5.symbol_info_tick(symbol)  # type: ignore[name-defined]
            if tick:
                return (tick.ask + tick.bid) / 2
        df = self._mock_ohlcv(5)
        return float(df["close"].iloc[-1])

    def get_account_info(self) -> dict:
        if self._connected and MT5_AVAILABLE:
            info = mt5.account_info()  # type: ignore[name-defined]
            return {"balance": info.balance, "equity": info.equity, "margin_free": info.margin_free}
        return {"balance": 10000.0, "equity": 10000.0, "margin_free": 9500.0}
