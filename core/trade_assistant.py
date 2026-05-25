"""
GoldX Assistant — AI-Powered Trading Decision Assistant

The core intelligence layer. Combines all analysis into structured
decision support with:
  - Full setup validation with grade (A/B/C/D)
  - Natural language market explanation via LLM
  - Trade management guidance (when to add, when to cut)
  - "Ask anything" conversational mode
  - Pre-trade ritual (step-by-step checklist walkthrough)
  - Optimal entry zone calculation
  - Position size recommendation
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional, TYPE_CHECKING

from utils.logger import logger
from config import ANTHROPIC_API_KEY, SYMBOL, MAX_RISK_PERCENT

if TYPE_CHECKING:
    from core.scoring_engine import GlobalScore
    from core.decision_engine import TradeDecision
    from core.mtf_analyzer import MTFResult
    from core.trade_checklist import ChecklistResult
    from core.market_structure import MarketStructureResult
    from core.technical_analyzer import TechnicalResult
    from core.fundamental_analyzer import FundamentalResult
    from core.news_analyzer import NewsResult

Grade = Literal["A", "B", "C", "D"]


@dataclass
class SetupAnalysis:
    """Complete setup evaluation for one trading opportunity."""
    direction: str
    grade: Grade
    entry_zone: tuple[float, float]      # (low, high) optimal entry range
    stop_loss: float
    take_profit_1: float                 # Conservative TP (1:1.5 RR)
    take_profit_2: float                 # Primary TP (1:2 RR)
    take_profit_3: float                 # Extended TP (1:3 RR)
    lot_size: float
    risk_amount: float
    confluence_score: float
    checklist_score: float
    strengths: list[str] = field(default_factory=list)
    weaknesses: list[str] = field(default_factory=list)
    verdict: str = ""
    management_plan: str = ""
    ai_narrative: str = ""

    def format_card(self) -> str:
        grade_icon = {"A": "🏆", "B": "✅", "C": "⚠️", "D": "❌"}.get(self.grade, "❓")
        dir_icon = "📈" if self.direction == "BUY" else "📉"
        lines = [
            f"┌────────────────────────────────────┐",
            f"│  {dir_icon} SETUP {self.direction} — Grade {self.grade} {grade_icon}          │",
            f"└────────────────────────────────────┘",
            "",
            f"🎯 **ZONE D'ENTRÉE**",
            f"  Optimal low  : `{self.entry_zone[0]:.2f}`",
            f"  Optimal high : `{self.entry_zone[1]:.2f}`",
            "",
            f"🛡 **GESTION DU RISQUE**",
            f"  Stop Loss    : `{self.stop_loss:.2f}`",
            f"  TP1 (1.5:1)  : `{self.take_profit_1:.2f}`",
            f"  TP2 (2:1)    : `{self.take_profit_2:.2f}`  ← cible principale",
            f"  TP3 (3:1)    : `{self.take_profit_3:.2f}`  ← extension",
            f"  Lots         : `{self.lot_size:.2f}`  (risque ${self.risk_amount:.0f})",
            "",
            f"📊 **SCORES**",
            f"  Confluence MTF : {self.confluence_score:.0f}/100",
            f"  Checklist      : {self.checklist_score:.0f}/10",
            "",
        ]
        if self.strengths:
            lines.append("💪 **POINTS FORTS**")
            for s in self.strengths:
                lines.append(f"  ✅ {s}")
            lines.append("")
        if self.weaknesses:
            lines.append("⚠️ **POINTS FAIBLES**")
            for w in self.weaknesses:
                lines.append(f"  ⚠️ {w}")
            lines.append("")
        if self.verdict:
            lines += [f"🧠 **VERDICT**: {self.verdict}", ""]
        if self.management_plan:
            lines += ["📋 **PLAN DE GESTION**", self.management_plan, ""]
        if self.ai_narrative:
            lines += ["🤖 **ANALYSE IA**", self.ai_narrative]
        return "\n".join(lines)


class TradeAssistant:
    """
    The main decision support engine.
    Integrates all analysis modules into structured trading guidance.
    """

    def __init__(self) -> None:
        self._llm = None
        if ANTHROPIC_API_KEY:
            try:
                import anthropic
                self._llm = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
                logger.info("TradeAssistant: LLM ready.")
            except ImportError:
                pass

    # ── Main Setup Analysis ────────────────────────────────────────────

    def evaluate_setup(
        self,
        direction: str,
        current_price: float,
        score: "GlobalScore",
        mtf: Optional["MTFResult"],
        checklist: Optional["ChecklistResult"],
        market_structure: Optional["MarketStructureResult"],
        tech: Optional["TechnicalResult"],
        fund: Optional["FundamentalResult"],
        news: Optional["NewsResult"],
        account_balance: float = 10000.0,
    ) -> SetupAnalysis:

        # ── Entry zone ────────────────────────────────────────────────
        atr = tech.atr if tech else 10.0
        entry_low = current_price - atr * 0.2
        entry_high = current_price + atr * 0.2

        # ── SL/TP calculation ─────────────────────────────────────────
        sl_dist = atr * 1.5
        if direction == "BUY":
            stop_loss = current_price - sl_dist
            tp1 = current_price + sl_dist * 1.5
            tp2 = current_price + sl_dist * 2.0
            tp3 = current_price + sl_dist * 3.0
        else:
            stop_loss = current_price + sl_dist
            tp1 = current_price - sl_dist * 1.5
            tp2 = current_price - sl_dist * 2.0
            tp3 = current_price - sl_dist * 3.0

        # Override with market structure levels if available
        if market_structure:
            if direction == "BUY" and market_structure.nearest_support > 0:
                stop_loss = market_structure.nearest_support - atr * 0.5
                tp2 = market_structure.nearest_resistance
            elif direction == "SELL" and market_structure.nearest_resistance > 0:
                stop_loss = market_structure.nearest_resistance + atr * 0.5
                tp2 = market_structure.nearest_support

        # Recalculate tp1, tp3 from adjusted SL
        sl_distance = abs(current_price - stop_loss)
        if direction == "BUY":
            tp1 = current_price + sl_distance * 1.5
            tp3 = current_price + sl_distance * 3.0
        else:
            tp1 = current_price - sl_distance * 1.5
            tp3 = current_price - sl_distance * 3.0

        # ── Position size ─────────────────────────────────────────────
        risk_amount = account_balance * MAX_RISK_PERCENT / 100
        pips = sl_distance / 0.1
        lot = risk_amount / (pips * 10) if pips > 0 else 0.01
        lot = max(0.01, min(lot, 5.0))

        # ── Grade ─────────────────────────────────────────────────────
        grade = self._determine_grade(score, mtf, checklist)

        # ── Strengths / Weaknesses ────────────────────────────────────
        strengths, weaknesses = self._extract_sw(score, mtf, checklist, market_structure, tech, fund, news)

        # ── Verdict ───────────────────────────────────────────────────
        verdict = self._build_verdict(grade, direction, score)

        # ── Management Plan ───────────────────────────────────────────
        management = self._build_management_plan(direction, tp1, tp2, tp3, stop_loss, lot)

        # ── AI Narrative ──────────────────────────────────────────────
        ai_narrative = ""
        if self._llm:
            ai_narrative = self._llm_narrative(direction, score, mtf, market_structure, tech, fund, news)

        confluence = mtf.confluence_score if mtf else score.global_score
        checklist_score = checklist.total_score if checklist else 5.0

        return SetupAnalysis(
            direction=direction,
            grade=grade,
            entry_zone=(round(entry_low, 2), round(entry_high, 2)),
            stop_loss=round(stop_loss, 2),
            take_profit_1=round(tp1, 2),
            take_profit_2=round(tp2, 2),
            take_profit_3=round(tp3, 2),
            lot_size=round(lot, 2),
            risk_amount=round(risk_amount, 2),
            confluence_score=confluence,
            checklist_score=checklist_score,
            strengths=strengths,
            weaknesses=weaknesses,
            verdict=verdict,
            management_plan=management,
            ai_narrative=ai_narrative,
        )

    # ── Conversational Q&A ─────────────────────────────────────────────

    def ask(
        self,
        question: str,
        score: Optional["GlobalScore"] = None,
        market_structure: Optional["MarketStructureResult"] = None,
        tech: Optional["TechnicalResult"] = None,
        fund: Optional["FundamentalResult"] = None,
        news: Optional["NewsResult"] = None,
    ) -> str:
        """Answer any trading question about current market context."""
        if not self._llm:
            return self._fallback_answer(question, score, tech, fund)

        context_parts = [f"Symbole: {SYMBOL} (Or / XAU USD)"]
        if score:
            context_parts.append(
                f"Score global: {score.global_score:.0f}/100 | Direction: {score.direction}\n"
                f"  Technique: {score.technical:.0f} | Fondamental: {score.fundamental:.0f} | "
                f"Géopolitique: {score.geopolitical:.0f} | News: {score.news:.0f}"
            )
        if tech:
            context_parts.append(
                f"RSI: {tech.rsi:.0f} | Session: {tech.session} | ATR: {tech.atr:.1f} | "
                f"EMA trend: {tech.ema_trend} | Breakout: {tech.breakout}"
            )
        if fund:
            md = fund.macro_data
            context_parts.append(
                f"FED: {md.fed_stance} @ {md.fed_rate}% | DXY: {md.dxy_trend} | "
                f"CPI: {md.cpi_trend} ({md.cpi_yoy}%) | Régime: {md.risk_regime}"
            )
        if market_structure:
            context_parts.append(
                f"Structure: {market_structure.trend} | BOS: {market_structure.last_bos} | "
                f"Support: {market_structure.nearest_support:.2f} | "
                f"Résistance: {market_structure.nearest_resistance:.2f}"
            )
        if news:
            context_parts.append(f"Sentiment: {news.sentiment} ({news.score:.0f}/100)")

        context = "\n".join(context_parts)
        prompt = f"""Tu es GoldX, un assistant de trading professionnel spécialisé sur XAU/USD.

**Contexte de marché actuel:**
{context}

**Question du trader:**
{question}

Réponds de manière concise et professionnelle (max 4-5 phrases).
Utilise des données concrètes du contexte si disponibles.
Termine par une recommandation actionnable si pertinente."""

        try:
            resp = self._llm.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=300,
                messages=[{"role": "user", "content": prompt}],
            )
            return resp.content[0].text.strip()
        except Exception as exc:
            logger.warning("LLM ask failed: {}", exc)
            return self._fallback_answer(question, score, tech, fund)

    def market_brief(
        self,
        score: Optional["GlobalScore"] = None,
        mtf: Optional["MTFResult"] = None,
        market_structure: Optional["MarketStructureResult"] = None,
    ) -> str:
        """Generate a concise market briefing narrative."""
        if not self._llm:
            parts = []
            if score:
                parts.append(f"Score global {score.global_score:.0f}/100 en faveur du {score.direction}.")
            if mtf:
                parts.append(f"MTF grade {mtf.grade}: {mtf.aligned_count}/5 TF alignés.")
            if market_structure:
                parts.append(f"Structure {market_structure.trend}: support {market_structure.nearest_support:.2f}, résistance {market_structure.nearest_resistance:.2f}.")
            return " ".join(parts) if parts else "Analyse en cours..."

        parts = []
        if score:
            parts.append(f"Scores: global={score.global_score:.0f} tech={score.technical:.0f} fund={score.fundamental:.0f} geo={score.geopolitical:.0f} news={score.news:.0f}")
        if mtf:
            parts.append(f"MTF grade={mtf.grade} confluence={mtf.confluence_score:.0f}% dir={mtf.dominant_direction}")
        if market_structure:
            parts.append(f"Structure={market_structure.trend} BOS={market_structure.last_bos} support={market_structure.nearest_support:.2f} resistance={market_structure.nearest_resistance:.2f}")

        context = " | ".join(parts)
        prompt = f"""En 3 phrases maximum, résume le contexte actuel de XAU/USD pour un trader:
{context}
Sois direct et actionnable. Français."""

        try:
            resp = self._llm.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=150,
                messages=[{"role": "user", "content": prompt}],
            )
            return resp.content[0].text.strip()
        except Exception as exc:
            logger.warning("LLM brief failed: {}", exc)
            return " ".join(parts)

    # ── Private Helpers ────────────────────────────────────────────────

    def _determine_grade(self, score, mtf, checklist) -> Grade:
        points = 0
        if score and score.global_score >= 75:
            points += 3
        elif score and score.global_score >= 65:
            points += 2
        elif score and score.global_score >= 55:
            points += 1

        if mtf and mtf.grade in ("A", "B"):
            points += 2
        elif mtf and mtf.grade == "C":
            points += 1

        if checklist and checklist.total_score >= 8:
            points += 3
        elif checklist and checklist.total_score >= 6:
            points += 2
        elif checklist and checklist.total_score >= 4:
            points += 1

        if points >= 7:
            return "A"
        if points >= 5:
            return "B"
        if points >= 3:
            return "C"
        return "D"

    def _extract_sw(self, score, mtf, checklist, ms, tech, fund, news) -> tuple[list[str], list[str]]:
        strengths, weaknesses = [], []

        if score:
            if score.global_score >= 75:
                strengths.append(f"Score global élevé ({score.global_score:.0f}/100)")
            elif score.global_score < 60:
                weaknesses.append(f"Score global faible ({score.global_score:.0f}/100)")

        if mtf:
            if mtf.aligned_count >= 4:
                strengths.append(f"Forte confluence MTF ({mtf.aligned_count}/5 TF alignés)")
            elif mtf.aligned_count <= 2:
                weaknesses.append(f"Faible confluence MTF ({mtf.aligned_count}/5)")
            if mtf.htf_bias == (score.direction if score else "NEUTRAL"):
                strengths.append("HTF (D1+H4) confirme la direction")

        if tech:
            if tech.rsi < 35:
                strengths.append(f"RSI sur-vendu ({tech.rsi:.0f}) — zone de rebond")
            elif tech.rsi > 65:
                strengths.append(f"RSI sur-acheté ({tech.rsi:.0f}) — zone de rejet")
            if "LONDON" in tech.session or "NY" in tech.session:
                strengths.append(f"Session liquide: {tech.session}")

        if fund:
            if fund.macro_data.fed_stance == "DOVISH":
                strengths.append("FED dovish — haussier pour l'or")
            elif fund.macro_data.fed_stance == "HAWKISH":
                weaknesses.append("FED hawkish — potentiel frein pour l'or")
            if fund.macro_data.dxy_trend == "DOWN":
                strengths.append("DXY en baisse — haussier pour l'or")

        if ms:
            if ms.trend == "BULLISH" and ms.last_bos == "BOS_UP":
                strengths.append("Break of Structure haussier confirmé")
            elif ms.trend == "RANGING":
                weaknesses.append("Marché en range — direction incertaine")

        if checklist and checklist.fail_count > 0:
            weaknesses += checklist.blockers[:2]

        return strengths[:5], weaknesses[:4]

    def _build_verdict(self, grade: Grade, direction: str, score) -> str:
        if grade == "A":
            return f"Setup {direction} EXCEPTIONNEL — haute probabilité. Entrée autorisée avec confiance."
        if grade == "B":
            return f"Setup {direction} SOLIDE — conditions favorables réunies. Entrer sur pullback."
        if grade == "C":
            return f"Setup {direction} PARTIEL — attendre confirmation supplémentaire avant entrée."
        return f"Setup {direction} INSUFFISANT — ne pas trader. Revoir les conditions."

    def _build_management_plan(
        self, direction: str,
        tp1: float, tp2: float, tp3: float, sl: float, lot: float,
    ) -> str:
        if direction == "BUY":
            return (
                f"1️⃣ Entrée: {lot:.2f} lots (full size)\n"
                f"2️⃣ TP1 @ `{tp1:.2f}` → fermer 30%, déplacer SL au BE\n"
                f"3️⃣ TP2 @ `{tp2:.2f}` → fermer 50% restant\n"
                f"4️⃣ TP3 @ `{tp3:.2f}` → laisser runner les 20% restants\n"
                f"5️⃣ SL à `{sl:.2f}` — ne jamais élargir le stop"
            )
        return (
            f"1️⃣ Entrée: {lot:.2f} lots (full size)\n"
            f"2️⃣ TP1 @ `{tp1:.2f}` → fermer 30%, déplacer SL au BE\n"
            f"3️⃣ TP2 @ `{tp2:.2f}` → fermer 50% restant\n"
            f"4️⃣ TP3 @ `{tp3:.2f}` → laisser runner les 20% restants\n"
            f"5️⃣ SL à `{sl:.2f}` — ne jamais élargir le stop"
        )

    def _llm_narrative(self, direction, score, mtf, ms, tech, fund, news) -> str:
        parts = []
        if score:
            parts.append(f"Score: {score.global_score:.0f}/100 {direction}")
        if mtf:
            parts.append(f"MTF grade {mtf.grade}: {mtf.narrative}")
        if ms:
            parts.append(f"Structure {ms.trend}: {ms.narrative}")
        if tech and fund:
            parts.append(f"RSI {tech.rsi:.0f}, FED {fund.macro_data.fed_stance}, DXY {fund.macro_data.dxy_trend}")

        context = ". ".join(parts)
        prompt = f"""En 3 phrases max, justifie ce trade {direction} XAU/USD pour un trader:
{context}
Parle comme un mentor de trading: concis, confiant, factuel. Français."""

        try:
            resp = self._llm.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=200,
                messages=[{"role": "user", "content": prompt}],
            )
            return resp.content[0].text.strip()
        except Exception as exc:
            logger.warning("LLM narrative failed: {}", exc)
            return ""

    def _fallback_answer(self, question: str, score, tech, fund) -> str:
        q_lower = question.lower()
        if "rsi" in q_lower and tech:
            return f"RSI actuel: {tech.rsi:.0f}. {'Zone sur-vendue — potentiel rebond.' if tech.rsi < 35 else 'Zone sur-achetée — potentiel rejet.' if tech.rsi > 65 else 'Zone neutre.'}"
        if "trend" in q_lower or "tendance" in q_lower:
            if score:
                return f"Tendance actuelle: {score.direction} avec un score de {score.global_score:.0f}/100."
            return "Pas de données de tendance disponibles."
        if "fed" in q_lower or "dollar" in q_lower:
            if fund:
                return f"FED: {fund.macro_data.fed_stance} @ {fund.macro_data.fed_rate}% | DXY: {fund.macro_data.dxy_trend}."
            return "Données macro non disponibles — configurer ANTHROPIC_API_KEY pour l'assistant IA complet."
        return "Pour répondre à cette question, configurez ANTHROPIC_API_KEY dans votre .env."
