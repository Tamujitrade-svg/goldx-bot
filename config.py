"""
GoldX Bot — Central Configuration
All settings are loaded from environment variables (.env file).
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ─── Telegram ─────────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "")

# ─── MetaTrader 5 ─────────────────────────────────────────────────────────────
MT5_LOGIN: int = int(os.getenv("MT5_LOGIN", "0"))
MT5_PASSWORD: str = os.getenv("MT5_PASSWORD", "")
MT5_SERVER: str = os.getenv("MT5_SERVER", "MetaQuotes-Demo")
MT5_PATH: str = os.getenv("MT5_PATH", "")

# ─── APIs ─────────────────────────────────────────────────────────────────────
NEWS_API_KEY: str = os.getenv("NEWS_API_KEY", "")
GNEWS_API_KEY: str = os.getenv("GNEWS_API_KEY", "")
ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")

TWITTER_BEARER_TOKEN: str = os.getenv("TWITTER_BEARER_TOKEN", "")
TWITTER_API_KEY: str = os.getenv("TWITTER_API_KEY", "")
TWITTER_API_SECRET: str = os.getenv("TWITTER_API_SECRET", "")
TWITTER_ACCESS_TOKEN: str = os.getenv("TWITTER_ACCESS_TOKEN", "")
TWITTER_ACCESS_TOKEN_SECRET: str = os.getenv("TWITTER_ACCESS_TOKEN_SECRET", "")

# ─── Trading Parameters ───────────────────────────────────────────────────────
SYMBOL: str = os.getenv("SYMBOL", "XAUUSD")
TIMEFRAME: str = os.getenv("TIMEFRAME", "M15")
LOT_SIZE: float = float(os.getenv("LOT_SIZE", "0.01"))
MAX_RISK_PERCENT: float = float(os.getenv("MAX_RISK_PERCENT", "1.0"))
SL_PIPS: int = int(os.getenv("SL_PIPS", "200"))
TP_PIPS: int = int(os.getenv("TP_PIPS", "400"))
MAX_DAILY_TRADES: int = int(os.getenv("MAX_DAILY_TRADES", "5"))
MIN_SCORE_TO_TRADE: int = int(os.getenv("MIN_SCORE_TO_TRADE", "70"))

AUTO_TRADE: bool = os.getenv("AUTO_TRADE", "false").lower() == "true"

# ─── Logging ──────────────────────────────────────────────────────────────────
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE: str = os.getenv("LOG_FILE", "logs/goldx.log")

# ─── Scoring Weights (must sum to 1.0) ────────────────────────────────────────
SCORE_WEIGHT_TECHNICAL: float = 0.30
SCORE_WEIGHT_FUNDAMENTAL: float = 0.25
SCORE_WEIGHT_GEOPOLITICAL: float = 0.20
SCORE_WEIGHT_NEWS: float = 0.25

# ─── High-Impact News Filter ──────────────────────────────────────────────────
HIGH_IMPACT_EVENTS = ["CPI", "NFP", "FOMC", "Fed Rate", "Unemployment", "GDP", "PPI"]
SUSPEND_MINUTES_BEFORE_NEWS = 30
SUSPEND_MINUTES_AFTER_NEWS = 30

# ─── Geopolitical Keywords ────────────────────────────────────────────────────
GEO_BULLISH_KEYWORDS = [
    "war", "conflict", "attack", "missile", "nuclear", "sanction",
    "crisis", "tension", "invasion", "bombing", "terror", "troops",
    "military", "escalation", "ceasefire failed", "coup",
]
GEO_BEARISH_KEYWORDS = [
    "ceasefire", "peace deal", "de-escalation", "diplomacy",
    "agreement", "treaty", "stability", "withdrawal",
]

# ─── Key Twitter Accounts to Monitor ─────────────────────────────────────────
TWITTER_ACCOUNTS_TO_MONITOR = [
    "realDonaldTrump",
    "federalreserve",
    "JeromeHPowell",
    "GoldmanSachs",
    "BloombergMarkets",
]

# ─── Trading Sessions (UTC) ───────────────────────────────────────────────────
SESSIONS = {
    "ASIA":   {"open": 0,  "close": 9},
    "LONDON": {"open": 7,  "close": 16},
    "NY":     {"open": 13, "close": 22},
}

# ─── Decision Thresholds ──────────────────────────────────────────────────────
SCORE_BUY_MIN: int = 65
SCORE_SELL_MIN: int = 65
SCORE_NO_TRADE_MAX: int = 50
