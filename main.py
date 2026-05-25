"""
GoldX Pro — Macro Trading AI + Decision Assistant
==================================================

Architecture:
  Data Layer     → price_feed, news_feed, calendar_feed, twitter_feed
  Analysis Layer → technical, fundamental, geopolitical, news analyzers
  Assistant Layer→ mtf_analyzer, market_structure, trade_checklist, trade_assistant
  Decision Layer → scoring_engine, decision_engine
  Output Layer   → telegram_bot, mt5_executor

Run modes:
  python main.py           → full bot with Telegram polling
  python main.py --once    → single analysis cycle (dev/test)
  python main.py --demo    → demo mode with mock data
"""

from __future__ import annotations

import argparse
import time
from datetime import datetime
from typing import Optional

import pytz
import schedule

from utils.logger import logger
from config import SYMBOL, AUTO_TRADE

# ── Data Sources ─────────────────────────────────────────────────────────────
from data.price_feed import PriceFeed
from data.news_feed import NewsFeed
from data.calendar_feed import CalendarFeed
from data.twitter_feed import TwitterFeed

# ── Analysis Engines ─────────────────────────────────────────────────────────
from core.technical_analyzer import TechnicalAnalyzer
from core.fundamental_analyzer import FundamentalAnalyzer
from core.geopolitical_analyzer import GeopoliticalAnalyzer
from core.news_analyzer import NewsAnalyzer

# ── Assistant Engines ─────────────────────────────────────────────────────────
from core.mtf_analyzer import MTFAnalyzer
from core.market_structure import MarketStructureAnalyzer
from core.trade_checklist import TradeChecklist
from core.trade_assistant import TradeAssistant

# ── Decision ──────────────────────────────────────────────────────────────────
from core.scoring_engine import ScoringEngine, GlobalScore
from core.decision_engine import DecisionEngine, TradeDecision

# ── Output ────────────────────────────────────────────────────────────────────
from bot import alerts
from bot.telegram_bot import TelegramInterface
from execution.mt5_executor import MT5Executor

UTC = pytz.UTC


class GoldXBot:
    """
    Central orchestrator. Runs the full analysis pipeline and
    dispatches signals via Telegram and/or MT5.
    """

    def __init__(self) -> None:
        logger.info("Initializing GoldX Pro Bot...")

        # ── Data Layer ──────────────────────────────────────────────────
        self.price_feed = PriceFeed()
        self.news_feed = NewsFeed()
        self.calendar_feed = CalendarFeed()
        self.twitter_feed = TwitterFeed()

        # ── Analyzers ───────────────────────────────────────────────────
        self.technical = TechnicalAnalyzer()
        self.fundamental = FundamentalAnalyzer()
        self.geopolitical = GeopoliticalAnalyzer()
        self.news_analyzer = NewsAnalyzer()

        # ── Assistant Layer ──────────────────────────────────────────────
        self.mtf = MTFAnalyzer()
        self.market_structure_analyzer = MarketStructureAnalyzer()
        self.checklist = TradeChecklist()
        self.assistant = TradeAssistant()

        # ── Decision ────────────────────────────────────────────────────
        self.scoring = ScoringEngine()
        self.decision = DecisionEngine()

        # ── Output ──────────────────────────────────────────────────────
        self.executor = MT5Executor(price_feed=self.price_feed)
        self.telegram = TelegramInterface(goldx_bot=self)

        # ── State ───────────────────────────────────────────────────────
        self._last_signal_score: float = 0.0
        self._last_signal_direction: str = "NEUTRAL"
        self._signal_count_today: int = 0
        self._started_at = datetime.now(tz=UTC)

        logger.info("GoldX Bot initialized.")

    # ── Bootstrap ─────────────────────────────────────────────────────────

    def start(self, mode: str = "full") -> None:
        """Start the bot in the given mode."""
        logger.info("Starting GoldX Bot — mode={}", mode)

        # Connect MT5
        mt5_ok = self.price_feed.connect()
        if mt5_ok:
            logger.info("MT5 connected.")
        else:
            logger.warning("MT5 not connected — using mock price data.")

        if mode == "once":
            self._run_cycle()
            return

        if mode == "demo":
            self._run_demo()
            return

        # Full mode: schedule cycles + Telegram polling
        self._setup_schedule()
        tg_ok = self.telegram.setup()

        if tg_ok:
            # Telegram polling blocks — run analysis in background thread
            import threading
            analysis_thread = threading.Thread(target=self._run_scheduler_loop, daemon=True)
            analysis_thread.start()
            logger.info("Analysis thread started. Launching Telegram polling...")
            self.telegram.run_polling()
        else:
            logger.info("Running in CLI-only mode (no Telegram).")
            self._run_scheduler_loop()

    def _setup_schedule(self) -> None:
        """Configure recurring analysis jobs."""
        # Full analysis every 15 minutes
        schedule.every(15).minutes.do(self._run_cycle)
        # Daily briefing at 07:00 UTC
        schedule.every().day.at("07:00").do(self._send_daily_briefing)
        # Calendar check every hour
        schedule.every().hour.do(self._check_upcoming_news)
        logger.info("Scheduler configured: analysis every 15m, briefing at 07:00 UTC.")

    def _run_scheduler_loop(self) -> None:
        logger.info("Scheduler loop running...")
        # Run immediately at start
        self._run_cycle()
        while True:
            schedule.run_pending()
            time.sleep(30)

    # ── Core Analysis Cycle ───────────────────────────────────────────────

    def _run_cycle(self) -> None:
        """Full pipeline: data → analysis → decision → execute → alert."""
        logger.info("─── Starting analysis cycle ───")
        try:
            # ── 1. Check for news blackout ────────────────────────────
            is_blackout, blackout_event = self.calendar_feed.is_news_blackout()
            if is_blackout and blackout_event:
                msg = alerts.format_news_blackout(blackout_event)
                self.telegram.send_message(msg)
                logger.warning("News blackout — cycle skipped: {}", blackout_event.name)
                return

            # ── 2. Fetch price data ───────────────────────────────────
            df = self.price_feed.get_ohlcv(symbol=SYMBOL, timeframe="M15", bars=300)
            current_price = self.price_feed.get_current_price(SYMBOL) or float(df["close"].iloc[-1])
            account = self.price_feed.get_account_info()

            # ── 3. Fetch news + tweets ────────────────────────────────
            articles = self.news_feed.fetch_all(hours_back=6)
            if not articles:
                articles = self.news_feed.mock_articles()
            tweets = self.twitter_feed.fetch_all_monitored()

            # ── 4. Run 4-pillar analysis ──────────────────────────────
            tech_result = self.technical.analyze(df)
            fund_result = self.fundamental.analyze()
            geo_result = self.geopolitical.analyze(articles)
            news_result = self.news_analyzer.analyze(articles, tweets)

            # ── 5. Global scoring ─────────────────────────────────────
            score = self.scoring.compute(tech_result, fund_result, geo_result, news_result)
            logger.info("\n{}", score)

            # ── 6. Decision ───────────────────────────────────────────
            decision = self.decision.decide(
                score=score,
                current_price=current_price,
                account_balance=account["balance"],
                is_news_blackout=is_blackout,
            )

            # ── 7. Execute (if AUTO_TRADE and valid) ───────────────────
            if decision.is_tradeable and AUTO_TRADE:
                trade_result = self.executor.execute(decision)
                logger.info("Execution: {}", trade_result)

            # ── 8. Alert ──────────────────────────────────────────────
            should_alert = self._should_send_alert(score, decision)
            if should_alert:
                msg = alerts.format_signal(
                    decision=decision,
                    score=score,
                    current_price=current_price,
                    llm_summary=news_result.llm_summary,
                    geo_summary=geo_result.llm_summary,
                )
                self.telegram.send_message(msg)
                self._last_signal_score = score.global_score
                self._last_signal_direction = score.direction
                self._signal_count_today += 1
                logger.info("Signal sent to Telegram.")
            else:
                logger.info("No alert triggered (score={:.1f} dir={}).", score.global_score, score.direction)

        except Exception as exc:
            logger.exception("Analysis cycle error: {}", exc)

    def _should_send_alert(self, score: GlobalScore, decision: TradeDecision) -> bool:
        """Only send if signal is meaningfully different from last one."""
        if not decision.is_tradeable:
            return False
        score_delta = abs(score.global_score - self._last_signal_score)
        direction_changed = score.direction != self._last_signal_direction
        is_high_confidence = score.confidence == "HIGH"
        return direction_changed or score_delta >= 10 or is_high_confidence

    # ── Public Methods (called by Telegram handlers) ──────────────────────

    def run_analysis(self) -> str:
        """Full analysis → formatted signal string for Telegram command."""
        try:
            df = self.price_feed.get_ohlcv(symbol=SYMBOL, timeframe="M15", bars=300)
            current_price = self.price_feed.get_current_price(SYMBOL) or float(df["close"].iloc[-1])
            account = self.price_feed.get_account_info()

            articles = self.news_feed.fetch_all(hours_back=6) or self.news_feed.mock_articles()
            tweets = self.twitter_feed.fetch_all_monitored()

            tech = self.technical.analyze(df)
            fund = self.fundamental.analyze()
            geo = self.geopolitical.analyze(articles)
            news = self.news_analyzer.analyze(articles, tweets)

            score = self.scoring.compute(tech, fund, geo, news)
            is_blackout, _ = self.calendar_feed.is_news_blackout()
            decision = self.decision.decide(score, current_price, account["balance"], is_blackout)

            return alerts.format_signal(
                decision, score, current_price,
                llm_summary=news.llm_summary,
                geo_summary=geo.llm_summary,
            )
        except Exception as exc:
            logger.exception("run_analysis error: {}", exc)
            return f"❌ Erreur d'analyse: {exc}"

    def get_score_dashboard(self) -> str:
        try:
            df = self.price_feed.get_ohlcv(symbol=SYMBOL, timeframe="M15", bars=300)
            current_price = self.price_feed.get_current_price(SYMBOL) or float(df["close"].iloc[-1])
            articles = self.news_feed.fetch_all(hours_back=3) or self.news_feed.mock_articles()
            tweets = self.twitter_feed.fetch_all_monitored()
            tech = self.technical.analyze(df)
            fund = self.fundamental.analyze()
            geo = self.geopolitical.analyze(articles)
            news = self.news_analyzer.analyze(articles, tweets)
            score = self.scoring.compute(tech, fund, geo, news)
            return alerts.format_score_dashboard(score, current_price)
        except Exception as exc:
            return f"❌ Erreur dashboard: {exc}"

    def get_calendar_digest(self) -> str:
        try:
            events = self.calendar_feed.get_upcoming_high_impact(hours_ahead=48)
            return alerts.format_calendar(events)
        except Exception as exc:
            return f"❌ Erreur calendrier: {exc}"

    def get_news_summary(self) -> str:
        try:
            articles = self.news_feed.fetch_all(hours_back=6) or self.news_feed.mock_articles()
            tweets = self.twitter_feed.fetch_all_monitored()
            result = self.news_analyzer.analyze(articles, tweets)
            lines = [
                f"📰 **NEWS SENTIMENT** — {len(result.items)} sources analysées\n",
                f"Sentiment : **{result.sentiment}**  (score {result.score:.0f}/100)",
                f"Direction : **{result.direction}**",
            ]
            if result.trump_alert:
                lines.append("🚨 Déclaration Trump détectée!")
            if result.fed_alert:
                lines.append("🏦 Communication FED détectée!")
            if result.llm_summary:
                lines += ["", "🤖 **Analyse IA:**", result.llm_summary]
            for item in result.items[:3]:
                sentiment_icon = "📈" if item.gold_sentiment > 0.2 else ("📉" if item.gold_sentiment < -0.2 else "➡️")
                lines.append(f"\n{sentiment_icon} [{item.source}] {item.text[:100]}...")
            return "\n".join(lines)
        except Exception as exc:
            return f"❌ Erreur news: {exc}"

    def get_status(self) -> str:
        uptime = datetime.now(tz=UTC) - self._started_at
        hours, rem = divmod(int(uptime.total_seconds()), 3600)
        minutes = rem // 60
        account = self.price_feed.get_account_info()
        daily = self.executor.get_daily_stats()
        return (
            f"⚙️ **STATUT GOLDX BOT**\n\n"
            f"🟢 En ligne depuis : {hours}h{minutes:02d}m\n"
            f"💰 Symbole : {SYMBOL}\n"
            f"💼 Balance : ${account['balance']:.2f}\n"
            f"💵 Equity  : ${account['equity']:.2f}\n\n"
            f"📊 Trades aujourd'hui : {daily['trades_today']}/{daily['max_daily']}\n"
            f"🤖 Mode auto-trade : {'✅ ACTIF' if AUTO_TRADE else '❌ DÉSACTIVÉ'}\n"
            f"📡 Signaux envoyés : {self._signal_count_today}\n"
        )

    def get_daily_briefing(self) -> str:
        try:
            df = self.price_feed.get_ohlcv(symbol=SYMBOL, timeframe="H1", bars=100)
            current_price = self.price_feed.get_current_price(SYMBOL) or float(df["close"].iloc[-1])
            articles = self.news_feed.fetch_all(hours_back=12) or self.news_feed.mock_articles()
            tweets = self.twitter_feed.fetch_all_monitored()
            tech = self.technical.analyze(df)
            fund = self.fundamental.analyze()
            geo = self.geopolitical.analyze(articles)
            news = self.news_analyzer.analyze(articles, tweets)
            score = self.scoring.compute(tech, fund, geo, news)
            upcoming = self.calendar_feed.get_upcoming_high_impact(hours_ahead=24)
            return alerts.format_daily_briefing(score, current_price, upcoming, geo.llm_summary)
        except Exception as exc:
            return f"❌ Erreur briefing: {exc}"

    # ── Assistant Public Methods ──────────────────────────────────────────

    def _get_full_context(self, timeframe: str = "M15", bars: int = 300):
        """Fetch and analyze all data sources. Returns (df, price, tech, fund, geo, news, score)."""
        df = self.price_feed.get_ohlcv(symbol=SYMBOL, timeframe=timeframe, bars=bars)
        price = self.price_feed.get_current_price(SYMBOL) or float(df["close"].iloc[-1])
        articles = self.news_feed.fetch_all(hours_back=6) or self.news_feed.mock_articles()
        tweets = self.twitter_feed.fetch_all_monitored()
        tech = self.technical.analyze(df)
        fund = self.fundamental.analyze()
        geo = self.geopolitical.analyze(articles)
        news = self.news_analyzer.analyze(articles, tweets)
        score = self.scoring.compute(tech, fund, geo, news)
        return df, price, tech, fund, geo, news, score

    def get_setup_analysis(self) -> str:
        """Complete setup evaluation: MTF + structure + checklist + grade + plan."""
        try:
            df, price, tech, fund, geo, news, score = self._get_full_context()
            account = self.price_feed.get_account_info()

            # Run all assistant modules
            mtf = self.mtf.analyze(symbol=SYMBOL)
            ms = self.market_structure_analyzer.analyze(df, current_price=price)
            is_blackout, _ = self.calendar_feed.is_news_blackout()
            decision = self.decision.decide(score, price, account["balance"], is_blackout)
            direction = score.direction if score.direction != "NEUTRAL" else "BUY"

            checklist = self.checklist.evaluate(
                direction=direction,
                mtf_result=mtf,
                tech_result=tech,
                fund_result=fund,
                news_result=news,
                calendar_feed=self.calendar_feed,
                rr_ratio=decision.risk_reward,
                current_price=price,
            )

            setup = self.assistant.evaluate_setup(
                direction=direction,
                current_price=price,
                score=score,
                mtf=mtf,
                checklist=checklist,
                market_structure=ms,
                tech=tech,
                fund=fund,
                news=news,
                account_balance=account["balance"],
            )

            return setup.format_card()
        except Exception as exc:
            logger.exception("get_setup_analysis error: {}", exc)
            return f"❌ Erreur analyse setup: {exc}"

    def get_trade_checklist(self) -> str:
        """10-point pre-trade checklist for current market conditions."""
        try:
            df, price, tech, fund, geo, news, score = self._get_full_context()
            account = self.price_feed.get_account_info()
            is_blackout, _ = self.calendar_feed.is_news_blackout()
            decision = self.decision.decide(score, price, account["balance"], is_blackout)
            direction = score.direction if score.direction != "NEUTRAL" else "BUY"
            mtf = self.mtf.analyze(symbol=SYMBOL)

            result = self.checklist.evaluate(
                direction=direction,
                mtf_result=mtf,
                tech_result=tech,
                fund_result=fund,
                news_result=news,
                calendar_feed=self.calendar_feed,
                rr_ratio=decision.risk_reward,
                current_price=price,
            )
            return result.format_checklist()
        except Exception as exc:
            logger.exception("get_trade_checklist error: {}", exc)
            return f"❌ Erreur checklist: {exc}"

    def get_mtf_analysis(self) -> str:
        """Multi-timeframe confluence analysis D1 → M5."""
        try:
            result = self.mtf.analyze(symbol=SYMBOL)
            lines = [
                "📐 **ANALYSE MULTI-TIMEFRAME**",
                f"Symbole: {SYMBOL}",
                "",
                f"🎯 Direction dominante : **{result.dominant_direction}**",
                f"📊 Confluence          : **{result.confluence_score:.0f}/100**",
                f"🏅 Grade               : **{result.grade}**",
                f"🔗 TF alignés          : **{result.aligned_count}/{len(result.timeframes)}**",
                f"📡 HTF bias (D1+H4)    : **{result.htf_bias}**",
                f"⚡ Signal LTF (M15+M5) : **{result.ltf_signal}**",
                f"🕐 Entrée recommandée  : **{result.entry_tf}**",
                "",
                "─────────────────────────────",
            ]
            lines += result.summary_lines()
            if result.key_levels:
                lines += [
                    "",
                    "📍 **NIVEAUX IDENTIFIÉS**",
                    *[f"  `{lvl:.2f}`" for lvl in result.key_levels],
                ]
            lines += ["", f"💡 _{result.narrative}_"]
            return "\n".join(lines)
        except Exception as exc:
            logger.exception("get_mtf_analysis error: {}", exc)
            return f"❌ Erreur MTF: {exc}"

    def get_market_structure(self) -> str:
        """Market structure analysis (SMC/ICT concepts)."""
        try:
            df = self.price_feed.get_ohlcv(symbol=SYMBOL, timeframe="H1", bars=200)
            price = self.price_feed.get_current_price(SYMBOL) or float(df["close"].iloc[-1])
            ms = self.market_structure_analyzer.analyze(df, current_price=price)
            return ms.format_summary()
        except Exception as exc:
            logger.exception("get_market_structure error: {}", exc)
            return f"❌ Erreur structure: {exc}"

    def get_key_levels(self) -> str:
        """Key support/resistance levels from multiple timeframes."""
        try:
            mtf = self.mtf.analyze(symbol=SYMBOL)
            df_h1 = self.price_feed.get_ohlcv(symbol=SYMBOL, timeframe="H1", bars=200)
            price = self.price_feed.get_current_price(SYMBOL) or float(df_h1["close"].iloc[-1])
            ms = self.market_structure_analyzer.analyze(df_h1, current_price=price)

            lines = [
                f"📍 **NIVEAUX CLÉS — {SYMBOL}**",
                f"Prix actuel : `{price:.2f}`",
                "",
                "🔴 **RÉSISTANCES**",
            ]
            # Collect all resistance levels above price
            resistances = sorted(set(
                [ms.nearest_resistance, ms.premium_zone]
                + [lvl for lvl in mtf.key_levels if lvl > price]
            ))
            for r in resistances[:4]:
                dist = r - price
                pct = dist / price * 100
                lines.append(f"  `{r:.2f}` (+{dist:.1f} pts / +{pct:.2f}%)")

            lines += ["", "🟢 **SUPPORTS**"]
            supports = sorted(set(
                [ms.nearest_support, ms.discount_zone]
                + [lvl for lvl in mtf.key_levels if lvl < price]
            ), reverse=True)
            for s in supports[:4]:
                dist = price - s
                pct = dist / price * 100
                lines.append(f"  `{s:.2f}` (-{dist:.1f} pts / -{pct:.2f}%)")

            lines += [
                "",
                f"⚖️ Équilibre (50%): `{ms.equilibrium:.2f}`",
                f"🔼 Premium (79%): `{ms.premium_zone:.2f}`",
                f"🔽 Discount (21%): `{ms.discount_zone:.2f}`",
                "",
                f"💡 _{ms.narrative}_",
            ]
            return "\n".join(lines)
        except Exception as exc:
            logger.exception("get_key_levels error: {}", exc)
            return f"❌ Erreur niveaux: {exc}"

    def validate_trade_idea(self, direction: str) -> str:
        """Validate a specific trade direction proposed by the user."""
        try:
            df, price, tech, fund, geo, news, score = self._get_full_context()
            account = self.price_feed.get_account_info()
            mtf = self.mtf.analyze(symbol=SYMBOL)
            ms = self.market_structure_analyzer.analyze(df, current_price=price)
            is_blackout, _ = self.calendar_feed.is_news_blackout()
            decision = self.decision.decide(score, price, account["balance"], is_blackout)

            checklist = self.checklist.evaluate(
                direction=direction,
                mtf_result=mtf,
                tech_result=tech,
                fund_result=fund,
                news_result=news,
                calendar_feed=self.calendar_feed,
                rr_ratio=decision.risk_reward,
                current_price=price,
            )
            setup = self.assistant.evaluate_setup(
                direction=direction,
                current_price=price,
                score=score,
                mtf=mtf,
                checklist=checklist,
                market_structure=ms,
                tech=tech,
                fund=fund,
                news=news,
                account_balance=account["balance"],
            )

            # Add validation context header
            dir_icon = "📈" if direction == "BUY" else "📉"
            market_says = score.direction
            agree = market_says == direction
            agree_str = "✅ Le marché CONFIRME" if agree else f"⚠️ Le marché PRÉFÈRE {market_says}"

            header = (
                f"🔍 **VALIDATION {dir_icon} {direction}**\n\n"
                f"Score bot : {score.global_score:.0f}/100 ({market_says})\n"
                f"{agree_str} ton idée\n"
                f"Checklist : {checklist.total_score:.0f}/10 ({checklist.grade})\n\n"
            )
            return header + checklist.format_checklist() + "\n\n" + setup.format_card()
        except Exception as exc:
            logger.exception("validate_trade_idea error: {}", exc)
            return f"❌ Erreur validation: {exc}"

    def ask_assistant(self, question: str) -> str:
        """Answer a natural language question about the current market."""
        try:
            _, price, tech, fund, _, news, score = self._get_full_context()
            df_h1 = self.price_feed.get_ohlcv(symbol=SYMBOL, timeframe="H1", bars=100)
            ms = self.market_structure_analyzer.analyze(df_h1, current_price=price)
            return self.assistant.ask(
                question=question,
                score=score,
                market_structure=ms,
                tech=tech,
                fund=fund,
                news=news,
            )
        except Exception as exc:
            logger.exception("ask_assistant error: {}", exc)
            return f"❌ Erreur assistant: {exc}"

    def get_management_guidance(self) -> str:
        """Trade management guidance based on open positions and current structure."""
        try:
            positions = self.executor.get_open_positions()
            price = self.price_feed.get_current_price(SYMBOL) or 0.0
            df_h1 = self.price_feed.get_ohlcv(symbol=SYMBOL, timeframe="H1", bars=100)
            ms = self.market_structure_analyzer.analyze(df_h1, current_price=price)

            if not positions:
                return (
                    f"📋 **GESTION DE POSITIONS**\n\n"
                    f"Aucune position ouverte sur {SYMBOL}.\n\n"
                    f"Prix actuel : `{price:.2f}`\n"
                    f"Structure   : {ms.trend}\n"
                    f"Support     : `{ms.nearest_support:.2f}`\n"
                    f"Résistance  : `{ms.nearest_resistance:.2f}`\n\n"
                    f"💡 _{ms.narrative}_"
                )

            lines = [f"📋 **GESTION DE POSITIONS ({len(positions)} ouverte(s))**", ""]
            for pos in positions:
                pl_icon = "💚" if pos.profit >= 0 else "🔴"
                direction_from_sl = "BUY" if pos.order_type == "BUY" else "SELL"
                pips_profit = abs(pos.current_price - pos.entry_price) / 0.1

                # Management recommendation
                if pos.profit > 0:
                    if direction_from_sl == "BUY" and pos.current_price > ms.nearest_resistance:
                        advice = "🎯 Proche résistance — envisager prise de profit partielle"
                    elif direction_from_sl == "BUY":
                        advice = "✅ Position en profit — déplacer SL au breakeven"
                    else:
                        advice = "✅ Position en profit — protéger les gains"
                else:
                    advice = "⚠️ Position en perte — respecter le SL initial"

                lines += [
                    f"{'─' * 30}",
                    f"{pl_icon} **{pos.order_type}** @ `{pos.entry_price:.2f}`",
                    f"  Prix actuel   : `{pos.current_price:.2f}`",
                    f"  P&L           : `{pos.profit:+.2f}$` ({pips_profit:.0f} pips)",
                    f"  SL / TP       : `{pos.stop_loss:.2f}` / `{pos.take_profit:.2f}`",
                    f"  Lots          : `{pos.volume:.2f}`",
                    f"  💡 {advice}",
                ]
            lines += [
                "",
                f"📍 Marché actuel : `{price:.2f}` | {ms.trend}",
                f"🛡 Support : `{ms.nearest_support:.2f}` | 🎯 Résistance : `{ms.nearest_resistance:.2f}`",
            ]
            return "\n".join(lines)
        except Exception as exc:
            logger.exception("get_management_guidance error: {}", exc)
            return f"❌ Erreur gestion: {exc}"

    # ── Internal Scheduled Jobs ───────────────────────────────────────────

    def _send_daily_briefing(self) -> None:
        msg = self.get_daily_briefing()
        self.telegram.send_message(msg)

    def _check_upcoming_news(self) -> None:
        events = self.calendar_feed.get_upcoming_high_impact(hours_ahead=1)
        for e in events:
            m = e.minutes_until
            if m is not None and 20 <= m <= 35:
                msg = alerts.format_news_blackout(e)
                self.telegram.send_message(msg)

    # ── Demo Mode ─────────────────────────────────────────────────────────

    def _run_demo(self) -> None:
        logger.info("=== DEMO MODE — ASSISTANT ===")
        print("\n" + "=" * 65)
        print("  GOLDX PRO — ASSISTANT DE TRADING (DEMO)")
        print("=" * 65 + "\n")

        df = self.price_feed._mock_ohlcv(300)
        articles = self.news_feed.mock_articles()
        tweets = self.twitter_feed._mock_tweets()
        current_price = 2374.50

        tech = self.technical.analyze(df)
        fund = self.fundamental.analyze()
        geo = self.geopolitical.analyze(articles)
        news = self.news_analyzer.analyze(articles, tweets)
        score = self.scoring.compute(tech, fund, geo, news)
        decision = self.decision.decide(score, current_price, account_balance=10000.0)

        # ── 1. Signal ─────────────────────────────────────────────────
        print("━━━ 1. SIGNAL 4 PILIERS ━━━")
        signal_msg = alerts.format_signal(
            decision, score, current_price,
            llm_summary="Trump tariffs + CPI faible = haussier or. FED dovish attendu.",
            geo_summary="Moyen-Orient: tensions persistantes — prime de risque élevée.",
        )
        print(signal_msg)

        # ── 2. MTF ────────────────────────────────────────────────────
        print("\n━━━ 2. MULTI-TIMEFRAME ━━━")
        mtf = self.mtf.analyze(symbol=SYMBOL)
        print(f"Direction: {mtf.dominant_direction} | Grade: {mtf.grade} | "
              f"Confluence: {mtf.confluence_score:.0f}% | Alignés: {mtf.aligned_count}/5")
        for line in mtf.summary_lines():
            print(line)
        print(f"\n💡 {mtf.narrative}")

        # ── 3. Market Structure ───────────────────────────────────────
        print("\n━━━ 3. STRUCTURE DE MARCHÉ ━━━")
        ms = self.market_structure_analyzer.analyze(df, current_price=current_price)
        print(ms.format_summary())

        # ── 4. Checklist ──────────────────────────────────────────────
        print("\n━━━ 4. CHECKLIST PRÉ-TRADE ━━━")
        checklist = self.checklist.evaluate(
            direction=score.direction or "BUY",
            mtf_result=mtf,
            tech_result=tech,
            fund_result=fund,
            news_result=news,
            calendar_feed=self.calendar_feed,
            rr_ratio=decision.risk_reward,
            current_price=current_price,
        )
        print(checklist.format_checklist())

        # ── 5. Setup Card ─────────────────────────────────────────────
        print("\n━━━ 5. FICHE SETUP COMPLÈTE ━━━")
        setup = self.assistant.evaluate_setup(
            direction=score.direction or "BUY",
            current_price=current_price,
            score=score, mtf=mtf, checklist=checklist,
            market_structure=ms, tech=tech, fund=fund, news=news,
            account_balance=10000.0,
        )
        print(setup.format_card())
        print("=" * 65 + "\n")


# ── Entry Point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="GoldX Pro Bot — Macro Trading AI")
    parser.add_argument("--once", action="store_true", help="Run one analysis cycle and exit")
    parser.add_argument("--demo", action="store_true", help="Run demo mode with mock data")
    args = parser.parse_args()

    mode = "full"
    if args.once:
        mode = "once"
    elif args.demo:
        mode = "demo"

    bot = GoldXBot()
    try:
        bot.start(mode=mode)
    except KeyboardInterrupt:
        logger.info("Bot stopped by user.")
    finally:
        bot.price_feed.disconnect()
        logger.info("GoldX Bot shut down cleanly.")


if __name__ == "__main__":
    main()
