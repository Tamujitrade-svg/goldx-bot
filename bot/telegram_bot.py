"""
GoldX Bot — Telegram Bot Interface

Commands:
  /start    — Welcome message
  /signal   — Run full analysis and show current signal
  /score    — Show live pillar scores dashboard
  /calendar — Show upcoming high-impact events
  /news     — Show latest news sentiment
  /status   — Bot status and configuration
  /briefing — Daily market briefing
  /help     — Command list

The bot also sends automatic alerts when:
  - A new high-confidence trade signal is detected
  - A news blackout window opens/closes
  - A HIGH impact event is approaching
"""

from __future__ import annotations

import asyncio
from typing import Optional, TYPE_CHECKING

from utils.logger import logger
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, SYMBOL

try:
    from telegram import Update, Bot
    from telegram.ext import Application, CommandHandler, ContextTypes
    from telegram.constants import ParseMode
    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False
    logger.warning("python-telegram-bot not installed — Telegram features disabled.")

if TYPE_CHECKING:
    from main import GoldXBot


class TelegramInterface:
    """Manages the Telegram bot lifecycle and command handlers."""

    def __init__(self, goldx_bot: "GoldXBot") -> None:
        self._bot = goldx_bot
        self._app: Optional[object] = None
        self._initialized = False

    def setup(self) -> bool:
        if not TELEGRAM_AVAILABLE:
            return False
        if not TELEGRAM_BOT_TOKEN:
            logger.warning("TELEGRAM_BOT_TOKEN not set — Telegram disabled.")
            return False

        app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()  # type: ignore[attr-defined]

        app.add_handler(CommandHandler("start", self._cmd_start))
        app.add_handler(CommandHandler("help", self._cmd_help))
        app.add_handler(CommandHandler("signal", self._cmd_signal))
        app.add_handler(CommandHandler("score", self._cmd_score))
        app.add_handler(CommandHandler("calendar", self._cmd_calendar))
        app.add_handler(CommandHandler("news", self._cmd_news))
        app.add_handler(CommandHandler("status", self._cmd_status))
        app.add_handler(CommandHandler("briefing", self._cmd_briefing))

        self._app = app
        self._initialized = True
        logger.info("Telegram bot configured.")
        return True

    def run_polling(self) -> None:
        if self._initialized and self._app:
            logger.info("Starting Telegram polling...")
            self._app.run_polling(drop_pending_updates=True)  # type: ignore[union-attr]

    # ── Push notifications ─────────────────────────────────────────────

    async def send_message_async(self, text: str, chat_id: Optional[str] = None) -> bool:
        if not TELEGRAM_AVAILABLE or not TELEGRAM_BOT_TOKEN:
            logger.info("[TELEGRAM MOCK] {}", text[:100])
            return True
        target = chat_id or TELEGRAM_CHAT_ID
        if not target:
            logger.warning("No TELEGRAM_CHAT_ID configured.")
            return False
        try:
            bot = Bot(token=TELEGRAM_BOT_TOKEN)  # type: ignore[attr-defined]
            async with bot:
                await bot.send_message(
                    chat_id=target,
                    text=text,
                    parse_mode=ParseMode.MARKDOWN,  # type: ignore[attr-defined]
                )
            return True
        except Exception as exc:
            logger.error("Telegram send failed: {}", exc)
            return False

    def send_message(self, text: str, chat_id: Optional[str] = None) -> bool:
        """Sync wrapper for async send."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(self.send_message_async(text, chat_id))
                return True
            else:
                return loop.run_until_complete(self.send_message_async(text, chat_id))
        except Exception as exc:
            logger.error("Telegram sync send failed: {}", exc)
            return False

    # ── Command Handlers ───────────────────────────────────────────────

    async def _cmd_start(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> None:
        msg = (
            "🏆 **GoldX Pro Bot — Bienvenue!**\n\n"
            "Je suis votre AI Macro Trading pour XAU/USD.\n\n"
            "**Mes 4 piliers d'analyse:**\n"
            "  📊 Technique (RSI, MACD, structure)\n"
            "  🌍 Fondamental (CPI, FED, DXY)\n"
            "  🧨 Géopolitique (guerres, tensions)\n"
            "  🗣 News & Discours (Trump, FED)\n\n"
            "Tapez /help pour voir toutes les commandes."
        )
        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)  # type: ignore[union-attr]

    async def _cmd_help(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> None:
        msg = (
            "📖 **COMMANDES GOLDX PRO**\n\n"
            "/signal — Analyse complète + signal de trading\n"
            "/score — Dashboard des scores en temps réel\n"
            "/calendar — Calendrier économique haute impact\n"
            "/news — Sentiment des dernières nouvelles\n"
            "/briefing — Briefing quotidien du marché\n"
            "/status — Statut et configuration du bot\n"
            "/help — Cette aide\n\n"
            "⚡ Signaux automatiques envoyés dès détection."
        )
        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)  # type: ignore[union-attr]

    async def _cmd_signal(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> None:
        await update.message.reply_text("⏳ Analyse en cours...", parse_mode=ParseMode.MARKDOWN)  # type: ignore[union-attr]
        result = await asyncio.get_event_loop().run_in_executor(None, self._bot.run_analysis)
        await update.message.reply_text(result, parse_mode=ParseMode.MARKDOWN)  # type: ignore[union-attr]

    async def _cmd_score(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> None:
        await update.message.reply_text("⏳ Calcul des scores...", parse_mode=ParseMode.MARKDOWN)  # type: ignore[union-attr]
        result = await asyncio.get_event_loop().run_in_executor(None, self._bot.get_score_dashboard)
        await update.message.reply_text(result, parse_mode=ParseMode.MARKDOWN)  # type: ignore[union-attr]

    async def _cmd_calendar(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> None:
        result = await asyncio.get_event_loop().run_in_executor(None, self._bot.get_calendar_digest)
        await update.message.reply_text(result, parse_mode=ParseMode.MARKDOWN)  # type: ignore[union-attr]

    async def _cmd_news(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> None:
        await update.message.reply_text("⏳ Analyse des news...", parse_mode=ParseMode.MARKDOWN)  # type: ignore[union-attr]
        result = await asyncio.get_event_loop().run_in_executor(None, self._bot.get_news_summary)
        await update.message.reply_text(result, parse_mode=ParseMode.MARKDOWN)  # type: ignore[union-attr]

    async def _cmd_status(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> None:
        result = self._bot.get_status()
        await update.message.reply_text(result, parse_mode=ParseMode.MARKDOWN)  # type: ignore[union-attr]

    async def _cmd_briefing(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> None:
        await update.message.reply_text("⏳ Préparation du briefing...", parse_mode=ParseMode.MARKDOWN)  # type: ignore[union-attr]
        result = await asyncio.get_event_loop().run_in_executor(None, self._bot.get_daily_briefing)
        await update.message.reply_text(result, parse_mode=ParseMode.MARKDOWN)  # type: ignore[union-attr]
