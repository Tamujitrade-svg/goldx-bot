"""
GoldX Assistant — Pre-Trade Checklist

10-criteria professional checklist evaluated BEFORE any entry.
Each criterion is scored PASS / WARN / FAIL.

Criteria:
  1.  HTF Trend Alignment      — D1/H4 support the direction
  2.  LTF Entry Signal         — M15/M5 give entry trigger
  3.  RSI Zone                 — Not overbought/oversold against direction
  4.  MACD Confirmation        — MACD histogram supports direction
  5.  Key Level Context        — Entering near support/resistance
  6.  News Blackout Clear      — No HIGH impact event in ±30 min
  7.  Session Active           — Trading during liquid session
  8.  Risk/Reward ≥ 2:1        — Minimum acceptable R/R
  9.  Macro Filter             — FED/DXY/CPI not opposing trade
  10. Sentiment Alignment      — News/Twitter not strongly opposing

Overall verdict:
  8-10 PASS → TRADE CONFIRMÉ (Grade A/B)
  6-7  PASS → TRADE CONDITIONNEL (Grade C)
  <6   PASS → NO TRADE
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from utils.logger import logger

Status = Literal["PASS", "WARN", "FAIL"]
Verdict = Literal["TRADE_CONFIRMED", "TRADE_CONDITIONAL", "NO_TRADE"]


@dataclass
class CheckItem:
    number: int
    name: str
    status: Status
    message: str        # Short explanation
    detail: str = ""    # Optional deeper context

    @property
    def icon(self) -> str:
        return {"PASS": "✅", "WARN": "⚠️", "FAIL": "❌"}[self.status]

    @property
    def score_points(self) -> float:
        return {"PASS": 1.0, "WARN": 0.5, "FAIL": 0.0}[self.status]


@dataclass
class ChecklistResult:
    items: list[CheckItem] = field(default_factory=list)
    verdict: Verdict = "NO_TRADE"
    pass_count: int = 0
    warn_count: int = 0
    fail_count: int = 0
    total_score: float = 0.0      # 0–10
    grade: str = "D"
    summary: str = ""
    blockers: list[str] = field(default_factory=list)

    def format_checklist(self) -> str:
        lines = ["📋 **CHECKLIST PRÉ-TRADE**", ""]
        for item in self.items:
            lines.append(f"{item.icon} **{item.number}. {item.name}**")
            lines.append(f"   {item.message}")
            if item.detail:
                lines.append(f"   _{item.detail}_")
        lines += [
            "",
            "─────────────────────────────",
            f"✅ PASS: {self.pass_count}  ⚠️ WARN: {self.warn_count}  ❌ FAIL: {self.fail_count}",
            f"Score: **{self.total_score:.1f}/10**  Grade: **{self.grade}**",
            "",
        ]
        verdict_text = {
            "TRADE_CONFIRMED":    "🟢 **TRADE CONFIRMÉ** — Entrée autorisée",
            "TRADE_CONDITIONAL":  "🟡 **TRADE CONDITIONNEL** — Attendre signal supplémentaire",
            "NO_TRADE":           "🔴 **NO TRADE** — Trop de critères non remplis",
        }[self.verdict]
        lines.append(verdict_text)
        if self.blockers:
            lines.append("")
            lines.append("🚫 **Bloquants:**")
            for b in self.blockers:
                lines.append(f"  • {b}")
        return "\n".join(lines)


class TradeChecklist:
    """Evaluates 10 pre-trade criteria and produces a verdict."""

    def evaluate(
        self,
        direction: str,
        mtf_result=None,
        tech_result=None,
        fund_result=None,
        news_result=None,
        calendar_feed=None,
        rr_ratio: float = 0.0,
        current_price: float = 0.0,
    ) -> ChecklistResult:

        items: list[CheckItem] = []

        # ── 1. HTF Trend Alignment ────────────────────────────────────
        items.append(self._check_htf_trend(direction, mtf_result))

        # ── 2. LTF Entry Signal ───────────────────────────────────────
        items.append(self._check_ltf_signal(direction, mtf_result))

        # ── 3. RSI Zone ───────────────────────────────────────────────
        items.append(self._check_rsi_zone(direction, tech_result))

        # ── 4. MACD Confirmation ──────────────────────────────────────
        items.append(self._check_macd(direction, tech_result))

        # ── 5. Key Level Context ──────────────────────────────────────
        items.append(self._check_key_level(direction, mtf_result, current_price))

        # ── 6. News Blackout Clear ────────────────────────────────────
        items.append(self._check_news_blackout(calendar_feed))

        # ── 7. Session Active ─────────────────────────────────────────
        items.append(self._check_session(tech_result))

        # ── 8. Risk/Reward ≥ 2:1 ─────────────────────────────────────
        items.append(self._check_rr(rr_ratio))

        # ── 9. Macro Filter ───────────────────────────────────────────
        items.append(self._check_macro(direction, fund_result))

        # ── 10. Sentiment Alignment ───────────────────────────────────
        items.append(self._check_sentiment(direction, news_result))

        # Number them
        for i, item in enumerate(items, 1):
            item.number = i

        return self._compute_result(items, direction)

    # ── Criteria ───────────────────────────────────────────────────────

    def _check_htf_trend(self, direction: str, mtf) -> CheckItem:
        if mtf is None:
            return CheckItem(0, "Tendance HTF (D1/H4)", "WARN", "Données MTF non disponibles.")
        htf = mtf.htf_bias
        if htf == direction:
            return CheckItem(0, "Tendance HTF (D1/H4)", "PASS",
                             f"D1+H4 alignés en {direction} ✓",
                             f"HTF bias = {htf}")
        if htf == "NEUTRAL":
            return CheckItem(0, "Tendance HTF (D1/H4)", "WARN",
                             "HTF neutre — pas de tendance claire",
                             "Trading en range, risque accru")
        return CheckItem(0, "Tendance HTF (D1/H4)", "FAIL",
                         f"HTF en {htf} — CONTRE le trade {direction}",
                         "Trading contre la tendance — risque élevé")

    def _check_ltf_signal(self, direction: str, mtf) -> CheckItem:
        if mtf is None:
            return CheckItem(0, "Signal LTF (M15/M5)", "WARN", "Données MTF non disponibles.")
        ltf = mtf.ltf_signal
        if ltf == direction:
            return CheckItem(0, "Signal LTF (M15/M5)", "PASS",
                             f"M15+M5 confirment le {direction} ✓")
        if ltf == "NEUTRAL":
            return CheckItem(0, "Signal LTF (M15/M5)", "WARN",
                             "Signal LTF neutre — attendre trigger")
        return CheckItem(0, "Signal LTF (M15/M5)", "FAIL",
                         f"M15/M5 en {ltf} — signal LTF opposé")

    def _check_rsi_zone(self, direction: str, tech) -> CheckItem:
        if tech is None:
            return CheckItem(0, "Zone RSI", "WARN", "RSI non disponible.")
        rsi = tech.rsi
        if direction == "BUY":
            if rsi < 30:
                return CheckItem(0, "Zone RSI", "PASS", f"RSI {rsi:.0f} — Zone de rebond ✓", "Sur-vendu = bon timing BUY")
            if rsi < 50:
                return CheckItem(0, "Zone RSI", "PASS", f"RSI {rsi:.0f} — Zone neutre favorable ✓")
            if rsi < 65:
                return CheckItem(0, "Zone RSI", "WARN", f"RSI {rsi:.0f} — Milieu de range", "RSI montera vers résistance")
            return CheckItem(0, "Zone RSI", "FAIL", f"RSI {rsi:.0f} — Sur-acheté pour BUY", "Attendre un repli RSI")
        else:  # SELL
            if rsi > 70:
                return CheckItem(0, "Zone RSI", "PASS", f"RSI {rsi:.0f} — Zone de rejet ✓", "Sur-acheté = bon timing SELL")
            if rsi > 50:
                return CheckItem(0, "Zone RSI", "PASS", f"RSI {rsi:.0f} — Zone neutre favorable ✓")
            if rsi > 35:
                return CheckItem(0, "Zone RSI", "WARN", f"RSI {rsi:.0f} — Milieu de range", "RSI baissera vers support")
            return CheckItem(0, "Zone RSI", "FAIL", f"RSI {rsi:.0f} — Sur-vendu pour SELL", "Attendre un rebond RSI")

    def _check_macd(self, direction: str, tech) -> CheckItem:
        if tech is None:
            return CheckItem(0, "MACD Confirmation", "WARN", "MACD non disponible.")
        macd = tech.macd_signal
        if macd == direction:
            return CheckItem(0, "MACD Confirmation", "PASS", f"MACD confirme {direction} ✓")
        if macd == "NEUTRAL":
            return CheckItem(0, "MACD Confirmation", "WARN", "MACD neutre — pas de croisement récent")
        return CheckItem(0, "MACD Confirmation", "FAIL",
                         f"MACD en {macd} — oppose le {direction}",
                         "Attendre croisement MACD favorable")

    def _check_key_level(self, direction: str, mtf, price: float) -> CheckItem:
        if mtf is None or not mtf.key_levels or price == 0:
            return CheckItem(0, "Niveau Clé (S/R)", "WARN", "Niveaux non calculés.")
        nearest = min(mtf.key_levels, key=lambda x: abs(x - price))
        distance = abs(price - nearest)
        pct = distance / price * 100
        if pct < 0.3:
            if direction == "BUY":
                return CheckItem(0, "Niveau Clé (S/R)", "PASS",
                                 f"Près d'un niveau clé @ {nearest:.2f} ✓",
                                 "Entrée en zone de support/résistance")
            return CheckItem(0, "Niveau Clé (S/R)", "PASS",
                             f"Près d'un niveau clé @ {nearest:.2f} ✓",
                             "Rejet de résistance possible")
        if pct < 0.8:
            return CheckItem(0, "Niveau Clé (S/R)", "WARN",
                             f"Niveau clé à {distance:.1f} pts ({pct:.1f}%)",
                             f"Niveau @ {nearest:.2f} — pas idéalement positionné")
        return CheckItem(0, "Niveau Clé (S/R)", "WARN",
                         f"Loin des niveaux clés ({pct:.1f}%)",
                         "Préférable d'entrer près d'un niveau")

    def _check_news_blackout(self, calendar_feed) -> CheckItem:
        if calendar_feed is None:
            return CheckItem(0, "Blackout News", "WARN", "Calendrier non disponible.")
        try:
            is_blackout, event = calendar_feed.is_news_blackout()
            if is_blackout and event:
                return CheckItem(0, "Blackout News", "FAIL",
                                 f"NEWS HAUTE IMPACT dans {event.minutes_until:.0f} min: {event.name}",
                                 "Trading suspendu — attendre après la publication")
            next_event = calendar_feed.get_next_event()
            if next_event:
                m = next_event.minutes_until
                if m is not None and m < 120:
                    return CheckItem(0, "Blackout News", "WARN",
                                     f"{next_event.name} dans {m:.0f} min",
                                     "Événement proche — surveiller")
            return CheckItem(0, "Blackout News", "PASS", "Aucune news haute impact imminente ✓")
        except Exception:
            return CheckItem(0, "Blackout News", "WARN", "Vérification calendrier impossible.")

    def _check_session(self, tech) -> CheckItem:
        if tech is None:
            return CheckItem(0, "Session Active", "WARN", "Session non déterminée.")
        session = tech.session
        if "LONDON" in session or "NY" in session:
            return CheckItem(0, "Session Active", "PASS",
                             f"Session liquide: {session} ✓",
                             "London/NY = volume et volatilité optimaux")
        if "ASIA" in session:
            return CheckItem(0, "Session Active", "WARN",
                             "Session Asie — liquidité réduite",
                             "Spreads plus larges, mouvements plus lents")
        return CheckItem(0, "Session Active", "WARN",
                         f"Hors session ({session})",
                         "Attendre ouverture London (07:00 UTC)")

    def _check_rr(self, rr_ratio: float) -> CheckItem:
        if rr_ratio <= 0:
            return CheckItem(0, "Risk/Reward ≥ 2:1", "WARN", "R/R non calculé.")
        if rr_ratio >= 3.0:
            return CheckItem(0, "Risk/Reward ≥ 2:1", "PASS",
                             f"R/R excellent: {rr_ratio:.1f}:1 ✓",
                             "Setup très favorable")
        if rr_ratio >= 2.0:
            return CheckItem(0, "Risk/Reward ≥ 2:1", "PASS",
                             f"R/R acceptable: {rr_ratio:.1f}:1 ✓")
        if rr_ratio >= 1.5:
            return CheckItem(0, "Risk/Reward ≥ 2:1", "WARN",
                             f"R/R faible: {rr_ratio:.1f}:1",
                             "Minimum recommandé = 2:1")
        return CheckItem(0, "Risk/Reward ≥ 2:1", "FAIL",
                         f"R/R insuffisant: {rr_ratio:.1f}:1",
                         "Ajuster SL ou TP pour atteindre 2:1")

    def _check_macro(self, direction: str, fund) -> CheckItem:
        if fund is None:
            return CheckItem(0, "Filtre Macro (FED/DXY)", "WARN", "Données macro non disponibles.")
        macro_dir = fund.direction
        if macro_dir == direction:
            fed = fund.macro_data.fed_stance if hasattr(fund, "macro_data") else "N/A"
            return CheckItem(0, "Filtre Macro (FED/DXY)", "PASS",
                             f"Macro supporte {direction} ✓",
                             f"FED: {fed}")
        if macro_dir == "NEUTRAL":
            return CheckItem(0, "Filtre Macro (FED/DXY)", "WARN",
                             "Macro neutre — pas de vent portant")
        return CheckItem(0, "Filtre Macro (FED/DXY)", "FAIL",
                         f"Macro s'oppose au {direction}",
                         "FED/DXY travaillent contre le trade")

    def _check_sentiment(self, direction: str, news) -> CheckItem:
        if news is None:
            return CheckItem(0, "Sentiment News/Twitter", "WARN", "Sentiment non disponible.")
        news_dir = news.direction
        if news_dir == direction:
            return CheckItem(0, "Sentiment News/Twitter", "PASS",
                             f"Sentiment confirme {direction} ✓",
                             f"Score sentiment: {news.score:.0f}/100")
        if news_dir == "NEUTRAL":
            return CheckItem(0, "Sentiment News/Twitter", "WARN",
                             "Sentiment neutre — pas de consensus news")
        return CheckItem(0, "Sentiment News/Twitter", "FAIL",
                         f"Sentiment opposé au {direction}",
                         "News et Twitter ne supportent pas ce trade")

    # ── Result Compilation ─────────────────────────────────────────────

    def _compute_result(self, items: list[CheckItem], direction: str) -> ChecklistResult:
        pass_count = sum(1 for i in items if i.status == "PASS")
        warn_count = sum(1 for i in items if i.status == "WARN")
        fail_count = sum(1 for i in items if i.status == "FAIL")
        total_score = sum(i.score_points for i in items)
        blockers = [i.message for i in items if i.status == "FAIL"]

        if total_score >= 8.0:
            verdict: Verdict = "TRADE_CONFIRMED"
            grade = "A" if total_score >= 9.0 else "B"
        elif total_score >= 6.0:
            verdict = "TRADE_CONDITIONAL"
            grade = "C"
        else:
            verdict = "NO_TRADE"
            grade = "D"

        summary_map = {
            "TRADE_CONFIRMED":   f"Setup validé {direction} — {pass_count}/10 critères remplis",
            "TRADE_CONDITIONAL": f"Setup partiel — compléter les critères manquants avant entrée",
            "NO_TRADE":          f"Setup rejeté — {fail_count} bloquants à corriger",
        }

        return ChecklistResult(
            items=items,
            verdict=verdict,
            pass_count=pass_count,
            warn_count=warn_count,
            fail_count=fail_count,
            total_score=total_score,
            grade=grade,
            summary=summary_map[verdict],
            blockers=blockers,
        )
