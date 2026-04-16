"""
GoldX Bot — Telegram Alert System
====================================
Sends formatted alerts to Telegram with:
  - Global score + pillar breakdown
  - Trade recommendation (BUY / SELL / WAIT)
  - Entry, SL, TP levels
  - Macro context summary
  - News sentiment signals

Usage:
    sender = TelegramSender()
    sender.send_signal(decision, score, price)
    sender.send_macro_alert(macro_context)
    sender.send_news_alert(sentiment_result)
    sender.send_blackout(event)
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Optional, TYPE_CHECKING

import pytz

from utils.logger import logger
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

if TYPE_CHECKING:
    from core.scoring_engine import GlobalScore
    from core.decision_engine import TradeDecision
    from fundamental.macro_filter import MacroContext
    from news.sentiment_analysis import SentimentResult
    from data.calendar_feed import EconomicEvent

UTC = pytz.UTC

TELEGRAM_AVAILABLE = False
try:
    from telegram import Bot
    from telegram.constants import ParseMode
    TELEGRAM_AVAILABLE = True
except ImportError:
    pass


def _bar(score: float, width: int = 10) -> str:
    n = max(0, min(width, int(round(score / 100 * width))))
    return "█" * n + "░" * (width - n)


def _dir_icon(direction: str) -> str:
    return {"BUY": "📈", "SELL": "📉", "NEUTRAL": "➡️", "WAIT": "⏸"}.get(direction, "❓")


def _conf_icon(confidence: str) -> str:
    return {"HIGH": "🔥", "MEDIUM": "✅", "LOW": "⚠️"}.get(confidence, "")


class TelegramSender:
    """
    Sends formatted GoldX signals to a Telegram chat.
    Falls back to console print if Telegram is not configured.
    """

    def __init__(self) -> None:
        self._bot: Optional[object] = None
        if TELEGRAM_AVAILABLE and TELEGRAM_BOT_TOKEN:
            try:
                self._bot = Bot(token=TELEGRAM_BOT_TOKEN)  # type: ignore[attr-defined]
                logger.info("TelegramSender initialized.")
            except Exception as exc:
                logger.warning("Telegram bot init failed: {}", exc)

    # ── Core Send ──────────────────────────────────────────────────────────

    def send(self, message: str, chat_id: Optional[str] = None) -> bool:
        """Send a raw message. Returns True on success."""
        target = chat_id or TELEGRAM_CHAT_ID
        if not target or not self._bot:
            # Fallback: print to console
            print("\n" + "=" * 60)
            print(message)
            print("=" * 60 + "\n")
            return True
        try:
            asyncio.get_event_loop().run_until_complete(
                self._bot.send_message(  # type: ignore[union-attr]
                    chat_id=target,
                    text=message,
                    parse_mode=ParseMode.MARKDOWN,  # type: ignore[attr-defined]
                )
            )
            return True
        except Exception as exc:
            logger.error("Telegram send error: {}", exc)
            return False

    # ── Signal Alert ───────────────────────────────────────────────────────

    def send_signal(
        self,
        decision: "TradeDecision",
        score: "GlobalScore",
        current_price: float,
        macro_context: Optional["MacroContext"] = None,
        sentiment: Optional["SentimentResult"] = None,
    ) -> bool:
        """Send the main trade signal with full scoring breakdown."""
        msg = self._format_signal(decision, score, current_price, macro_context, sentiment)
        return self.send(msg)

    def _format_signal(
        self,
        decision: "TradeDecision",
        score: "GlobalScore",
        price: float,
        macro: Optional["MacroContext"],
        sentiment: Optional["SentimentResult"],
    ) -> str:
        now = datetime.now(tz=UTC).strftime("%Y-%m-%d %H:%M UTC")
        dir_e = _dir_icon(decision.action)
        conf_e = _conf_icon(decision.confidence)

        lines = [
            "┌──────────────────────────────────┐",
            "│  🏆 GOLDX PRO — SIGNAL DE TRADING  │",
            "└──────────────────────────────────┘",
            "",
            f"📅 {now}",
            f"💰 **XAUUSD** @ `{price:.2f}`",
            "",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            f"{dir_e} **ACTION : {decision.action}**",
            f"{conf_e} Confiance : **{decision.confidence}**",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        ]

        # Trade levels
        if decision.action not in ("NO_TRADE", "WAIT"):
            lines += [
                "",
                "🎯 **NIVEAUX**",
                f"  ▶ Entrée  : `{decision.entry_price:.2f}`",
                f"  🛡 Stop   : `{decision.stop_loss:.2f}`",
                f"  🎯 Target : `{decision.take_profit:.2f}`",
                f"  📦 Lots   : `{decision.lot_size:.2f}`",
                f"  ⚖️  R/R   : `{decision.risk_reward:.1f}:1`",
            ]

        # Scoring breakdown
        lines += [
            "",
            "📊 **SCORING PAR PILIER**",
            f"  Technique    : **{score.technical:.0f}**/100  {_bar(score.technical)}  {_dir_icon(score.technical_direction)}",
            f"  Fondamental  : **{score.fundamental:.0f}**/100  {_bar(score.fundamental)}  {_dir_icon(score.fundamental_direction)}",
            f"  Géopolitique : **{score.geopolitical:.0f}**/100  {_bar(score.geopolitical)}  {_dir_icon(score.geopolitical_direction)}",
            f"  News/Discours: **{score.news:.0f}**/100  {_bar(score.news)}  {_dir_icon(score.news_direction)}",
            "",
            f"🧠 **SCORE GLOBAL : {score.global_score:.0f}/100**  {_bar(score.global_score)}",
            f"   {score.pillar_alignment}/4 piliers convergents",
        ]

        # Macro context block
        if macro:
            lines += [
                "",
                "🌍 **CONTEXTE MACRO**",
                f"  FED    : {macro.fed_stance} ({macro.fed_rate}%)",
                f"  USD    : {macro.usd_trend}  (DXY {macro.dxy_value})",
                f"  CPI    : {macro.inflation_trend} ({macro.cpi_yoy}%)",
                f"  Régime : {macro.risk_regime}",
            ]

        # News sentiment block
        if sentiment:
            lines += [
                "",
                "📰 **SENTIMENT NEWS**",
                f"  {sentiment.sentiment}  ({sentiment.score:.0f}/100)",
            ]
            if sentiment.trump_signal:
                lines.append("  🚨 Déclaration Trump détectée!")
            if sentiment.fed_signal:
                lines.append("  🏦 Communication FED détectée!")

        # Decision notes
        if score.notes:
            lines += ["", "📌 **POINTS CLÉS**"]
            for note in score.notes[:4]:
                lines.append(f"  • {note}")

        # Result
        if decision.action in ("NO_TRADE", "WAIT"):
            lines += ["", f"🚫 **PAS DE TRADE** — {decision.reason}"]
        else:
            lines += ["", f"✅ **TRADE VALIDÉ**", f"  {decision.reason}"]

        lines += [
            "",
            "─────────────────────────────────────",
            "⚡ GoldX Pro Bot | XAU/USD Macro AI",
        ]
        return "\n".join(lines)

    # ── Macro Alert ────────────────────────────────────────────────────────

    def send_macro_alert(self, macro: "MacroContext") -> bool:
        """Send a standalone macro context update."""
        lines = [
            "🌍 **MISE À JOUR MACRO**",
            "",
            f"📊 Score macro : **{macro.macro_score:.0f}/100**",
            f"🔮 Biais or    : **{macro.gold_bias}**",
            f"⚡ Filtre trade : **{macro.trade_filter}**",
            "",
            f"FED    : {macro.fed_stance} @ {macro.fed_rate}%",
            f"USD    : {macro.usd_trend} (DXY {macro.dxy_value})",
            f"CPI    : {macro.inflation_trend} ({macro.cpi_yoy}% YoY)",
            f"Régime : {macro.risk_regime}",
        ]
        if macro.notes:
            lines += ["", "📌 Notes:"]
            for n in macro.notes:
                lines.append(f"  • {n}")
        return self.send("\n".join(lines))

    # ── News Alert ─────────────────────────────────────────────────────────

    def send_news_alert(self, sentiment: "SentimentResult") -> bool:
        """Send news sentiment summary."""
        icon = {"BULLISH": "📈", "BEARISH": "📉", "NEUTRAL": "➡️"}.get(sentiment.sentiment, "")
        lines = [
            f"📰 **NEWS SENTIMENT** {icon}",
            "",
            f"Sentiment  : **{sentiment.sentiment}**",
            f"Score      : **{sentiment.score:.0f}/100**",
            f"Impact     : **{sentiment.impact}**",
            f"Sources    : {len(sentiment.article_sentiments)} articles analysés",
        ]
        if sentiment.dominant_theme:
            lines.append(f"Thème clé  : {sentiment.dominant_theme}")
        if sentiment.trump_signal:
            lines.append("\n🚨 **Déclaration Trump** détectée — impact USD potentiel!")
        if sentiment.fed_signal:
            lines.append("\n🏦 **Communication FED** détectée — surveiller volatilité!")
        return self.send("\n".join(lines))

    # ── Blackout Alert ─────────────────────────────────────────────────────

    def send_blackout(self, event: "EconomicEvent") -> bool:
        """Alert when entering a news blackout window."""
        t = event.datetime_utc.strftime("%H:%M UTC") if event.datetime_utc else "TBD"
        mins = event.minutes_until
        countdown = f" (dans {mins:.0f} min)" if mins is not None else ""
        msg = (
            f"⏸ **TRADING SUSPENDU — NEWS HAUTE IMPACT**\n\n"
            f"🔴 **{event.name}**{countdown}\n"
            f"🕐 Heure : {t}\n"
            f"📊 Forecast : {event.forecast or 'N/A'}\n"
            f"📅 Précédent : {event.previous or 'N/A'}\n\n"
            f"⚠️ Trading reprendra 30 min après la publication."
        )
        return self.send(msg)

    # ── Blackout Lift ──────────────────────────────────────────────────────

    def send_blackout_lift(self, event: "EconomicEvent") -> bool:
        """Alert when blackout period ends."""
        actual = event.actual or "N/A"
        forecast = event.forecast or "N/A"
        surprise = ""
        try:
            act_val = float(actual.strip("%").strip("K").strip("B"))
            fcst_val = float(forecast.strip("%").strip("K").strip("B"))
            if act_val > fcst_val:
                surprise = " 📈 Surprise haussière"
            elif act_val < fcst_val:
                surprise = " 📉 Surprise baissière"
        except Exception:
            pass
        msg = (
            f"✅ **TRADING REPRIS — {event.name}**\n\n"
            f"📊 Résultat  : **{actual}**  (forecast: {forecast}){surprise}\n\n"
            f"⚡ Analyse en cours..."
        )
        return self.send(msg)
