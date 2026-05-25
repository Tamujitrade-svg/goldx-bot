"""
GoldX Assistant — Telegram Interface

Commands:
  /start     — Welcome
  /help      — All commands
  /signal    — Full 4-pillar signal
  /setup     — Complete setup analysis with grade
  /check     — 10-point pre-trade checklist
  /mtf       — Multi-timeframe confluence
  /structure — Market structure (SMC/ICT)
  /validate <BUY|SELL> — Validate your trade idea
  /ask <question>      — Ask the AI anything
  /score     — Live scoring dashboard
  /calendar  — Economic calendar
  /news      — News sentiment
  /levels    — Key support/resistance levels
  /briefing  — Daily market briefing
  /manage    — Trade management guidance
  /status    — Bot status
"""

from __future__ import annotations

import asyncio
from typing import Optional, TYPE_CHECKING

from utils.logger import logger
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, SYMBOL

try:
    from telegram import Update, Bot
    from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
    from telegram.constants import ParseMode
    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False
    logger.warning("python-telegram-bot not installed — Telegram features disabled.")

if TYPE_CHECKING:
    from main import GoldXBot


class TelegramInterface:
    """Manages Telegram bot lifecycle with full assistant capabilities."""

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

        # Original commands
        app.add_handler(CommandHandler("start", self._cmd_start))
        app.add_handler(CommandHandler("help", self._cmd_help))
        app.add_handler(CommandHandler("signal", self._cmd_signal))
        app.add_handler(CommandHandler("score", self._cmd_score))
        app.add_handler(CommandHandler("calendar", self._cmd_calendar))
        app.add_handler(CommandHandler("news", self._cmd_news))
        app.add_handler(CommandHandler("status", self._cmd_status))
        app.add_handler(CommandHandler("briefing", self._cmd_briefing))

        # New assistant commands
        app.add_handler(CommandHandler("setup", self._cmd_setup))
        app.add_handler(CommandHandler("check", self._cmd_check))
        app.add_handler(CommandHandler("mtf", self._cmd_mtf))
        app.add_handler(CommandHandler("structure", self._cmd_structure))
        app.add_handler(CommandHandler("validate", self._cmd_validate))
        app.add_handler(CommandHandler("ask", self._cmd_ask))
        app.add_handler(CommandHandler("levels", self._cmd_levels))
        app.add_handler(CommandHandler("manage", self._cmd_manage))

        self._app = app
        self._initialized = True
        logger.info("Telegram assistant configured with {} commands.", 16)
        return True

    def run_polling(self) -> None:
        if self._initialized and self._app:
            logger.info("Starting Telegram polling...")
            self._app.run_polling(drop_pending_updates=True)  # type: ignore[union-attr]

    # ── Push ───────────────────────────────────────────────────────────

    async def send_message_async(self, text: str, chat_id: Optional[str] = None) -> bool:
        if not TELEGRAM_AVAILABLE or not TELEGRAM_BOT_TOKEN:
            logger.info("[TELEGRAM MOCK] {}", text[:120])
            return True
        target = chat_id or TELEGRAM_CHAT_ID
        if not target:
            return False
        try:
            bot = Bot(token=TELEGRAM_BOT_TOKEN)  # type: ignore[attr-defined]
            # Telegram has 4096 char limit — split if needed
            chunks = [text[i:i+4000] for i in range(0, len(text), 4000)]
            async with bot:
                for chunk in chunks:
                    await bot.send_message(
                        chat_id=target,
                        text=chunk,
                        parse_mode=ParseMode.MARKDOWN,  # type: ignore[attr-defined]
                    )
            return True
        except Exception as exc:
            logger.error("Telegram send failed: {}", exc)
            return False

    def send_message(self, text: str, chat_id: Optional[str] = None) -> bool:
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(self.send_message_async(text, chat_id))
                return True
            return loop.run_until_complete(self.send_message_async(text, chat_id))
        except Exception as exc:
            logger.error("Telegram sync send failed: {}", exc)
            return False

    # ── Helper ─────────────────────────────────────────────────────────

    async def _run(self, update, fn, *args, loading_msg: str = "⏳ Analyse en cours...") -> None:
        """Run a blocking analysis function in executor and send result."""
        await update.message.reply_text(loading_msg, parse_mode=ParseMode.MARKDOWN)  # type: ignore[union-attr]
        result = await asyncio.get_event_loop().run_in_executor(None, fn, *args)
        await update.message.reply_text(result, parse_mode=ParseMode.MARKDOWN)  # type: ignore[union-attr]

    # ── Original Commands ──────────────────────────────────────────────

    async def _cmd_start(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> None:
        msg = (
            "🏆 **GoldX Pro — Assistant de Trading XAU/USD**\n\n"
            "Ton assistant IA pour les meilleures prises de décision.\n\n"
            "**Analyse sur 4 piliers:**\n"
            "  📊 Technique | 🌍 Macro | 🧨 Géopolitique | 🗣 News\n\n"
            "**Assistant avancé:**\n"
            "  🏗 Structure de marché (SMC/ICT)\n"
            "  📐 Multi-timeframe (D1→M5)\n"
            "  📋 Checklist pré-trade (10 critères)\n"
            "  🤖 IA conversationnelle\n\n"
            "Tape /help pour toutes les commandes."
        )
        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)  # type: ignore[union-attr]

    async def _cmd_help(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> None:
        msg = (
            "📖 **COMMANDES GOLDX ASSISTANT**\n\n"
            "**📊 Analyse de marché**\n"
            "`/signal`    — Signal complet 4 piliers\n"
            "`/setup`     — Analyse complète du setup (grade A-D)\n"
            "`/mtf`       — Confluence multi-timeframe\n"
            "`/structure` — Structure de marché (SMC/ICT)\n"
            "`/score`     — Dashboard des scores\n"
            "\n**✅ Validation de trade**\n"
            "`/check`     — Checklist pré-trade (10 critères)\n"
            "`/validate BUY` — Valider ton idée de trade\n"
            "`/validate SELL` — Valider une idée SELL\n"
            "\n**💬 Assistant IA**\n"
            "`/ask <question>` — Poser une question au marché\n"
            "`/levels`    — Niveaux clés (support/résistance)\n"
            "`/manage`    — Gestion de position ouverte\n"
            "\n**📰 Contexte**\n"
            "`/news`      — Sentiment des news\n"
            "`/calendar`  — Calendrier économique\n"
            "`/briefing`  — Briefing quotidien\n"
            "`/status`    — Statut du bot\n\n"
            "💡 _Exemple: `/ask Est-ce que l'or peut casser 2400?`_"
        )
        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)  # type: ignore[union-attr]

    async def _cmd_signal(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> None:
        await self._run(update, self._bot.run_analysis, loading_msg="⏳ Analyse 4 piliers en cours...")

    async def _cmd_score(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> None:
        await self._run(update, self._bot.get_score_dashboard, loading_msg="⏳ Calcul des scores...")

    async def _cmd_calendar(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> None:
        result = await asyncio.get_event_loop().run_in_executor(None, self._bot.get_calendar_digest)
        await update.message.reply_text(result, parse_mode=ParseMode.MARKDOWN)  # type: ignore[union-attr]

    async def _cmd_news(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> None:
        await self._run(update, self._bot.get_news_summary, loading_msg="⏳ Analyse des news...")

    async def _cmd_status(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> None:
        result = self._bot.get_status()
        await update.message.reply_text(result, parse_mode=ParseMode.MARKDOWN)  # type: ignore[union-attr]

    async def _cmd_briefing(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> None:
        await self._run(update, self._bot.get_daily_briefing, loading_msg="⏳ Préparation du briefing...")

    # ── New Assistant Commands ─────────────────────────────────────────

    async def _cmd_setup(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> None:
        """Full setup analysis with grade, entry zone, and management plan."""
        await self._run(
            update, self._bot.get_setup_analysis,
            loading_msg="🔍 Analyse complète du setup en cours...\n_(MTF + Structure + Checklist)_",
        )

    async def _cmd_check(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> None:
        """10-point pre-trade checklist."""
        await self._run(
            update, self._bot.get_trade_checklist,
            loading_msg="📋 Exécution de la checklist pré-trade...",
        )

    async def _cmd_mtf(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> None:
        """Multi-timeframe confluence analysis."""
        await self._run(
            update, self._bot.get_mtf_analysis,
            loading_msg="📐 Analyse multi-timeframe (D1 → M5)...",
        )

    async def _cmd_structure(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> None:
        """Market structure (SMC/ICT) analysis."""
        await self._run(
            update, self._bot.get_market_structure,
            loading_msg="🏗 Analyse de la structure de marché...",
        )

    async def _cmd_validate(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> None:
        """Validate a trade idea: /validate BUY or /validate SELL"""
        args = context.args or []
        direction = args[0].upper() if args else None
        if direction not in ("BUY", "SELL"):
            await update.message.reply_text(  # type: ignore[union-attr]
                "Usage: `/validate BUY` ou `/validate SELL`",
                parse_mode=ParseMode.MARKDOWN,
            )
            return
        await self._run(
            update,
            lambda: self._bot.validate_trade_idea(direction),
            loading_msg=f"🔍 Validation de ton idée {direction}...",
        )

    async def _cmd_ask(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> None:
        """Ask the AI: /ask <question>"""
        question = " ".join(context.args or [])
        if not question:
            await update.message.reply_text(  # type: ignore[union-attr]
                "Usage: `/ask <ta question>`\n\nExemple:\n"
                "`/ask Est-ce que l'or peut casser 2400 aujourd'hui?`\n"
                "`/ask Quel est l'impact du CPI sur l'or?`",
                parse_mode=ParseMode.MARKDOWN,
            )
            return
        await self._run(
            update,
            lambda: self._bot.ask_assistant(question),
            loading_msg=f"🤖 Traitement de ta question...",
        )

    async def _cmd_levels(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> None:
        """Key support/resistance levels."""
        await self._run(
            update, self._bot.get_key_levels,
            loading_msg="📍 Calcul des niveaux clés...",
        )

    async def _cmd_manage(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> None:
        """Trade management guidance for open positions."""
        await self._run(
            update, self._bot.get_management_guidance,
            loading_msg="📋 Analyse des positions ouvertes...",
        )
