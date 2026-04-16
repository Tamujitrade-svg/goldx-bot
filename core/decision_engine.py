"""
GoldX Bot — Decision Engine

Takes the GlobalScore and produces a final trading decision:
  - BUY / SELL / NO_TRADE
  - Entry price, Stop Loss, Take Profit
  - Risk/reward ratio
  - Position size calculation
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional

from utils.logger import logger
from config import (
    SYMBOL, LOT_SIZE, MAX_RISK_PERCENT, SL_PIPS, TP_PIPS,
    AUTO_TRADE, MIN_SCORE_TO_TRADE, SCORE_BUY_MIN, SCORE_SELL_MIN,
)
from core.scoring_engine import GlobalScore

Action = Literal["BUY", "SELL", "NO_TRADE"]


@dataclass
class TradeDecision:
    action: Action
    symbol: str = SYMBOL
    entry_price: float = 0.0
    stop_loss: float = 0.0
    take_profit: float = 0.0
    lot_size: float = LOT_SIZE
    risk_reward: float = 0.0
    global_score: float = 0.0
    confidence: str = "LOW"
    reason: str = ""
    notes: list[str] = field(default_factory=list)

    @property
    def is_tradeable(self) -> bool:
        return self.action != "NO_TRADE"

    def summary(self) -> str:
        if self.action == "NO_TRADE":
            return f"NO TRADE — Score: {self.global_score:.0f}/100 | {self.reason}"
        rr = f"R/R {self.risk_reward:.1f}" if self.risk_reward > 0 else ""
        return (
            f"{self.action} {self.symbol}\n"
            f"  Entry  : {self.entry_price:.2f}\n"
            f"  SL     : {self.stop_loss:.2f}\n"
            f"  TP     : {self.take_profit:.2f}\n"
            f"  Lots   : {self.lot_size:.2f}  {rr}\n"
            f"  Score  : {self.global_score:.0f}/100  [{self.confidence}]\n"
            f"  Raison : {self.reason}"
        )


class DecisionEngine:
    """Converts a GlobalScore into a concrete trade instruction."""

    def decide(
        self,
        score: GlobalScore,
        current_price: float,
        account_balance: float = 10000.0,
        is_news_blackout: bool = False,
    ) -> TradeDecision:

        # ── News blackout override ─────────────────────────────────────
        if is_news_blackout:
            logger.warning("News blackout active — NO TRADE.")
            return TradeDecision(
                action="NO_TRADE",
                global_score=score.global_score,
                confidence=score.confidence,
                reason="⏸ NEWS HAUTE IMPACT — trading suspendu",
            )

        # ── Score threshold checks ─────────────────────────────────────
        if score.direction == "BUY" and score.global_score >= SCORE_BUY_MIN and score.trade_valid:
            action: Action = "BUY"
        elif score.direction == "SELL" and score.global_score >= SCORE_SELL_MIN and score.trade_valid:
            action = "SELL"
        else:
            reason = self._no_trade_reason(score)
            return TradeDecision(
                action="NO_TRADE",
                global_score=score.global_score,
                confidence=score.confidence,
                reason=reason,
                notes=score.notes,
            )

        # ── Entry / SL / TP calculation ────────────────────────────────
        entry, sl, tp = self._calculate_levels(action, current_price, score)

        # ── Position size ──────────────────────────────────────────────
        lot = self._calculate_lot_size(account_balance, entry, sl)

        # ── Risk/Reward ────────────────────────────────────────────────
        sl_distance = abs(entry - sl)
        tp_distance = abs(tp - entry)
        rr = tp_distance / sl_distance if sl_distance > 0 else 0.0

        reason = self._build_reason(score, action)

        decision = TradeDecision(
            action=action,
            symbol=SYMBOL,
            entry_price=round(entry, 2),
            stop_loss=round(sl, 2),
            take_profit=round(tp, 2),
            lot_size=round(lot, 2),
            risk_reward=round(rr, 2),
            global_score=score.global_score,
            confidence=score.confidence,
            reason=reason,
            notes=score.notes,
        )

        logger.info(
            "Decision: {} @ {:.2f} SL={:.2f} TP={:.2f} RR={:.1f} score={:.0f}",
            action, entry, sl, tp, rr, score.global_score,
        )
        return decision

    # ── Level Calculation ──────────────────────────────────────────────

    def _calculate_levels(
        self, action: Action, price: float, score: GlobalScore
    ) -> tuple[float, float, float]:
        """
        Dynamic SL/TP based on ATR (from technical analysis details).
        Falls back to pip-based calculation.
        """
        # ATR-based (preferred)
        atr = score.technical  # We use technical score as proxy — improve by passing ATR
        # Use config pip values for now (override if ATR available)
        pip_value = 0.1  # XAUUSD: 1 pip = $0.10 price movement

        sl_distance = SL_PIPS * pip_value
        tp_distance = TP_PIPS * pip_value

        if action == "BUY":
            entry = price
            sl = price - sl_distance
            tp = price + tp_distance
        else:
            entry = price
            sl = price + sl_distance
            tp = price - tp_distance

        return entry, sl, tp

    def _calculate_lot_size(
        self, balance: float, entry: float, sl: float
    ) -> float:
        """
        Risk-based position sizing:
          risk_amount = balance * MAX_RISK_PERCENT / 100
          lot = risk_amount / (sl_distance_in_price * pip_value * contract_size)
        For XAUUSD: contract_size = 100 oz, pip_value per lot ≈ $10 per pip
        """
        risk_amount = balance * MAX_RISK_PERCENT / 100
        sl_distance = abs(entry - sl)
        if sl_distance < 0.01:
            return LOT_SIZE
        # Approximate: 1 lot XAUUSD ≈ $1 per pip ($0.1 price move)
        dollar_per_pip = 10.0
        pips = sl_distance / 0.1
        lot = risk_amount / (pips * dollar_per_pip)
        lot = max(0.01, min(lot, 5.0))  # Cap between 0.01 and 5 lots
        return round(lot, 2)

    def _no_trade_reason(self, score: GlobalScore) -> str:
        if score.global_score < MIN_SCORE_TO_TRADE:
            return f"Score insuffisant ({score.global_score:.0f} < {MIN_SCORE_TO_TRADE})"
        if score.direction == "NEUTRAL":
            return "Direction neutre — pas de consensus entre les piliers"
        if score.pillar_alignment < 2:
            return f"Alignement faible ({score.pillar_alignment}/4 piliers)"
        return "Conditions de marché défavorables"

    def _build_reason(self, score: GlobalScore, action: Action) -> str:
        drivers = []
        if score.technical_direction == action:
            drivers.append("Technique")
        if score.fundamental_direction == action:
            drivers.append("Fondamental")
        if score.geopolitical_direction == action:
            drivers.append("Géopolitique")
        if score.news_direction == action:
            drivers.append("News")
        if drivers:
            return f"Confirmé par: {', '.join(drivers)}"
        return f"Score global: {score.global_score:.0f}/100"
