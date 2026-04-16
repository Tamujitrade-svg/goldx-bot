# GoldX Pro Bot — Macro Trading AI for XAU/USD

Automated trading system that analyzes gold (XAU/USD) across **4 pillars**:

| Pillar | What it analyzes | Weight |
|--------|-----------------|--------|
| 📊 Technical | RSI, MACD, EMA, breakouts, liquidity sweeps, sessions | 30% |
| 🌍 Fundamental | CPI, FED rates (FRED API), DXY, risk regime | 25% |
| 🧨 Geopolitical | Wars, tensions, crises (news keywords + LLM) | 20% |
| 🗣 News & Discourse | Trump, FED speeches, sentiment analysis | 25% |

## Architecture

```
goldx-bot/
├── main.py                     # Orchestration loop + CLI entry point
├── config.py                   # All settings (loaded from .env)
├── requirements.txt
├── .env.example                # Copy to .env and fill in your keys
│
├── data/                       # Data sources
│   ├── price_feed.py           # MT5 connection + OHLCV (with mock fallback)
│   ├── news_feed.py            # NewsAPI + GNews fetcher
│   ├── calendar_feed.py        # ForexFactory economic calendar
│   └── twitter_feed.py        # Twitter/X API v2 monitoring
│
├── core/                       # Analysis engines (4 pillars)
│   ├── technical_analyzer.py   # RSI, MACD, EMA, breakout, liquidity, sessions
│   ├── fundamental_analyzer.py # CPI (BLS), FED (FRED), DXY, risk-on/off filter
│   ├── geopolitical_analyzer.py# Geo risk from news + LLM (Claude)
│   ├── news_analyzer.py        # Sentiment analysis + Trump/FED alerts
│   ├── scoring_engine.py       # Weighted composite score 0-100
│   └── decision_engine.py      # BUY/SELL/NO_TRADE + TP/SL/lots/risk
│
├── bot/
│   ├── telegram_bot.py         # /signal /score /calendar /news /briefing
│   └── alerts.py              # Rich signal message formatting
│
├── execution/
│   └── mt5_executor.py        # MT5 order placement + position management
│
└── utils/
    └── logger.py              # Loguru rotating logger
```

## Signal Output Example

```
┌─────────────────────────────────┐
│   🏆 GOLDX PRO SIGNAL            │
└─────────────────────────────────┘

📅 2026-04-16 08:30 UTC
💰 XAUUSD @ 2374.50

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📈 ACTION : BUY
🔥 Confiance : HIGH
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🎯 NIVEAUX DE TRADING
  ▶ Entrée  : 2374.50
  🛡 Stop   : 2354.50
  🎯 Target : 2414.50
  📦 Lots   : 0.05
  ⚖️  R/R   : 2.0:1

📊 SCORING PAR PILIER
  Technique    : 72/100 ████████░░ 📈
  Fondamental  : 85/100 █████████░ 📈
  Géopolitique : 68/100 ███████░░░ 📈
  News/Discours: 90/100 █████████░ 📈

🧠 SCORE GLOBAL : 79/100 ████████░░
   Alignement  : 4/4 piliers convergents
```

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure
cp .env.example .env
# Edit .env with your API keys

# 3. Run demo (no keys needed)
python main.py --demo

# 4. Single analysis cycle
python main.py --once

# 5. Full bot with Telegram polling
python main.py
```

## Telegram Commands

| Command | Description |
|---------|-------------|
| `/signal` | Full 4-pillar analysis + current trade signal |
| `/score` | Live pillar scores dashboard |
| `/calendar` | Upcoming HIGH impact economic events |
| `/news` | Latest news sentiment analysis |
| `/briefing` | Daily market briefing |
| `/status` | Bot status and today's trade stats |

## Key Configuration (`.env`)

```env
# Required for Telegram alerts
TELEGRAM_BOT_TOKEN=your_token
TELEGRAM_CHAT_ID=your_chat_id

# Required for live trading
MT5_LOGIN=123456
MT5_PASSWORD=password
MT5_SERVER=YourBroker-Live

# News analysis
NEWS_API_KEY=...          # newsapi.org (free tier available)
GNEWS_API_KEY=...         # gnews.io (free tier available)

# LLM interpretation (optional but powerful)
ANTHROPIC_API_KEY=...     # console.anthropic.com

# Trading parameters
AUTO_TRADE=false          # Set true only when ready for live trading
MIN_SCORE_TO_TRADE=70     # Global score threshold (0-100)
MAX_RISK_PERCENT=1.0      # Risk per trade as % of balance
```

## Scoring System

| Score | Direction | Action |
|-------|-----------|--------|
| 0–34  | SELL      | Potential short |
| 35–64 | NEUTRAL   | No trade |
| 65–100| BUY       | Potential long |

A trade is only validated when:
- Global score ≥ `MIN_SCORE_TO_TRADE`
- At least 2/4 pillars agree on direction
- No HIGH-impact news blackout active
