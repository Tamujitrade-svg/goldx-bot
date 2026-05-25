"""
GoldX Bot — Alert Formatter

Generates beautiful, information-dense Telegram messages for:
  - Trade signals
  - News blackouts
  - Score summaries
  - Economic calendar alerts
  - Daily briefings
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
import pytz

from core.scoring_engine import GlobalScore
from core.decision_engine import TradeDecision
from data.calendar_feed import EconomicEvent

UTC = pytz.UTC


def _score_bar(score: float, width: int = 10) -> str:
    filled = int(round(score / 100 * width))
    filled = max(0, min(width, filled))
    return "█" * filled + "░" * (width - filled)


def _direction_emoji(direction: str) -> str:
    return {"BUY": "📈", "SELL": "📉", "NEUTRAL": "➡️"}.get(direction, "❓")


def _confidence_emoji(confidence: str) -> str:
    return {"HIGH": "🔥", "MEDIUM": "✅", "LOW": "⚠️"}.get(confidence, "❓")


def _impact_emoji(impact: str) -> str:
    return {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🟢"}.get(impact, "⚪")


# ── Main Signal Alert ──────────────────────────────────────────────────────────

def format_signal(
    decision: TradeDecision,
    score: GlobalScore,
    current_price: float,
    llm_summary: str = "",
    geo_summary: str = "",
) -> str:
    now = datetime.now(tz=UTC).strftime("%Y-%m-%d %H:%M UTC")
    dir_emoji = _direction_emoji(decision.action)
    conf_emoji = _confidence_emoji(decision.confidence)

    lines = [
        "┌─────────────────────────────────┐",
        f"│   🏆 GOLDX PRO SIGNAL            │",
        "└─────────────────────────────────┘",
        "",
        f"📅 {now}",
        f"💰 {decision.symbol} @ **{current_price:.2f}**",
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"{dir_emoji} **ACTION : {decision.action}**",
        f"{conf_emoji} Confiance : **{decision.confidence}**",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "",
    ]

    if decision.action != "NO_TRADE":
        lines += [
            "🎯 **NIVEAUX DE TRADING**",
            f"  ▶ Entrée  : `{decision.entry_price:.2f}`",
            f"  🛡 Stop   : `{decision.stop_loss:.2f}`",
            f"  🎯 Target : `{decision.take_profit:.2f}`",
            f"  📦 Lots   : `{decision.lot_size:.2f}`",
            f"  ⚖️  R/R    : `{decision.risk_reward:.1f}:1`",
            "",
        ]

    lines += [
        "📊 **SCORING PAR PILIER**",
        f"  Technique    : {score.technical:.0f}/100  {_score_bar(score.technical, 8)}  {_direction_emoji(score.technical_direction)}",
        f"  Fondamental  : {score.fundamental:.0f}/100  {_score_bar(score.fundamental, 8)}  {_direction_emoji(score.fundamental_direction)}",
        f"  Géopolitique : {score.geopolitical:.0f}/100  {_score_bar(score.geopolitical, 8)}  {_direction_emoji(score.geopolitical_direction)}",
        f"  News/Discours: {score.news:.0f}/100  {_score_bar(score.news, 8)}  {_direction_emoji(score.news_direction)}",
        "",
        f"🧠 **SCORE GLOBAL : {score.global_score:.0f}/100**  {_score_bar(score.global_score)}",
        f"   Alignement  : {score.pillar_alignment}/4 piliers convergents",
        "",
    ]

    if score.notes:
        lines.append("📌 **NOTES CLÉS**")
        for note in score.notes[:4]:
            lines.append(f"  • {note}")
        lines.append("")

    if geo_summary:
        lines += ["🌍 **ANALYSE GÉOPOLITIQUE**", f"  {geo_summary}", ""]

    if llm_summary:
        lines += ["🤖 **IA NARRATIVE**", f"  {llm_summary}", ""]

    if decision.action == "NO_TRADE":
        lines += [
            "🚫 **RÉSULTAT : PAS DE TRADE**",
            f"  Raison : {decision.reason}",
        ]
    else:
        lines += [
            f"✅ **TRADE VALIDÉ**",
            f"  {decision.reason}",
        ]

    lines += [
        "",
        "─────────────────────────────────",
        "⚡ GoldX Pro Bot | XAU/USD AI Trading",
    ]

    return "\n".join(lines)


# ── News Blackout Alert ────────────────────────────────────────────────────────

def format_news_blackout(event: EconomicEvent) -> str:
    impact_e = _impact_emoji(event.impact)
    t = event.datetime_utc.strftime("%H:%M UTC") if event.datetime_utc else "TBD"
    mins = event.minutes_until
    time_str = f"{mins:.0f} min" if mins is not None else "bientôt"

    return (
        f"⏸ **TRADING SUSPENDU — NEWS HAUTE IMPACT**\n\n"
        f"{impact_e} Événement : **{event.name}**\n"
        f"🕐 Heure    : **{t}** (dans {time_str})\n"
        f"💵 Devise   : {event.currency}\n"
        f"📊 Forecast : {event.forecast or 'N/A'}\n"
        f"📅 Précédent: {event.previous or 'N/A'}\n\n"
        f"⚠️ Trading repris {30} min après la publication.\n"
        f"📡 Surveiller la volatilité XAU/USD."
    )


# ── Economic Calendar Digest ───────────────────────────────────────────────────

def format_calendar(events: list[EconomicEvent]) -> str:
    if not events:
        return "📅 **CALENDRIER** — Aucun événement haute impact prévu dans les prochaines 24h"

    lines = ["📅 **CALENDRIER ÉCONOMIQUE — Prochains HIGH IMPACT**", ""]
    for e in events[:5]:
        impact_e = _impact_emoji(e.impact)
        t = e.datetime_utc.strftime("%a %H:%M UTC") if e.datetime_utc else "TBD"
        mins = e.minutes_until
        countdown = f" ⏱ dans {mins:.0f}m" if mins is not None and 0 < mins < 600 else ""
        lines.append(f"{impact_e} **{e.name}** — {t}{countdown}")
        if e.forecast:
            lines.append(f"   Forecast: {e.forecast} | Précédent: {e.previous}")
    return "\n".join(lines)


# ── Score Dashboard ────────────────────────────────────────────────────────────

def format_score_dashboard(score: GlobalScore, price: float) -> str:
    dir_e = _direction_emoji(score.direction)
    conf_e = _confidence_emoji(score.confidence)

    return (
        f"📊 **DASHBOARD GOLDX**\n\n"
        f"💰 XAU/USD : **{price:.2f}**\n\n"
        f"🧮 **Scores temps réel**\n"
        f"  Technique    : {score.technical:.0f}/100  {_score_bar(score.technical, 8)}\n"
        f"  Fondamental  : {score.fundamental:.0f}/100  {_score_bar(score.fundamental, 8)}\n"
        f"  Géopolitique : {score.geopolitical:.0f}/100  {_score_bar(score.geopolitical, 8)}\n"
        f"  News/Discours: {score.news:.0f}/100  {_score_bar(score.news, 8)}\n\n"
        f"🏆 **GLOBAL : {score.global_score:.0f}/100**\n"
        f"  {dir_e} Direction  : **{score.direction}**\n"
        f"  {conf_e} Confiance : **{score.confidence}**\n"
        f"  Piliers alignés : {score.pillar_alignment}/4"
    )


# ── Daily Briefing ─────────────────────────────────────────────────────────────

def format_daily_briefing(
    score: GlobalScore,
    price: float,
    upcoming_events: list[EconomicEvent],
    geo_summary: str = "",
) -> str:
    now = datetime.now(tz=UTC).strftime("%A %d %B %Y")
    dir_e = _direction_emoji(score.direction)

    lines = [
        f"🌅 **BRIEFING QUOTIDIEN — {now}**",
        "",
        f"💰 XAU/USD ouverture : **{price:.2f}**",
        f"{dir_e} Biais du jour : **{score.direction}**  (score {score.global_score:.0f}/100)",
        "",
        "📋 **POINTS CLÉS**",
    ]

    for note in score.notes[:5]:
        lines.append(f"  • {note}")

    if geo_summary:
        lines += ["", "🌍 **GÉOPOLITIQUE**", f"  {geo_summary}"]

    if upcoming_events:
        lines += ["", "⚠️ **ÉVÉNEMENTS À SURVEILLER**"]
        for e in upcoming_events[:3]:
            t = e.datetime_utc.strftime("%a %H:%M UTC") if e.datetime_utc else "TBD"
            lines.append(f"  🔴 {e.name} — {t}")

    lines += ["", "─────────────────────────────────", "⚡ GoldX Pro Bot"]
    return "\n".join(lines)
