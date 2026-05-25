"""
GoldX Bot — MT5 Execution Module

Handles:
  - Order placement (BUY / SELL)
  - Position monitoring
  - Trade history retrieval
  - Account metrics

Safety features:
  - Dry-run mode (AUTO_TRADE=false)
  - Max daily trade limit
  - Risk checks before execution
"""

from __future__ import annotations

import platform
from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Literal, Optional

from utils.logger import logger
from config import (
    SYMBOL, LOT_SIZE, SL_PIPS, TP_PIPS,
    AUTO_TRADE, MAX_DAILY_TRADES,
)
from core.decision_engine import TradeDecision

MT5_AVAILABLE = False
try:
    if platform.system() == "Windows":
        import MetaTrader5 as mt5
        MT5_AVAILABLE = True
except ImportError:
    pass

OrderType = Literal["BUY", "SELL"]


@dataclass
class TradeResult:
    success: bool
    ticket: Optional[int] = None
    order_type: str = ""
    volume: float = 0.0
    entry_price: float = 0.0
    stop_loss: float = 0.0
    take_profit: float = 0.0
    error_msg: str = ""
    dry_run: bool = False

    def __str__(self) -> str:
        if self.dry_run:
            return (
                f"[DRY RUN] {self.order_type} {self.volume:.2f} lots @ {self.entry_price:.2f} "
                f"SL={self.stop_loss:.2f} TP={self.take_profit:.2f}"
            )
        if self.success:
            return (
                f"✅ Trade exécuté #{self.ticket}: {self.order_type} {self.volume:.2f} lots "
                f"@ {self.entry_price:.2f} SL={self.stop_loss:.2f} TP={self.take_profit:.2f}"
            )
        return f"❌ Trade échoué: {self.error_msg}"


@dataclass
class OpenPosition:
    ticket: int
    symbol: str
    order_type: str
    volume: float
    entry_price: float
    current_price: float
    stop_loss: float
    take_profit: float
    profit: float
    open_time: datetime


class MT5Executor:
    """Executes trades on MetaTrader 5 with safety guards."""

    def __init__(self, price_feed) -> None:
        self._price_feed = price_feed
        self._daily_trade_count: dict[date, int] = {}

    # ── Trade Execution ────────────────────────────────────────────────

    def execute(self, decision: TradeDecision) -> TradeResult:
        """Execute a trade decision. Respects AUTO_TRADE setting."""
        if not decision.is_tradeable:
            logger.info("No trade — skipping execution.")
            return TradeResult(success=False, error_msg="Decision is NO_TRADE")

        # Check daily limit
        today = date.today()
        count = self._daily_trade_count.get(today, 0)
        if count >= MAX_DAILY_TRADES:
            logger.warning("Daily trade limit reached ({}/{})", count, MAX_DAILY_TRADES)
            return TradeResult(success=False, error_msg=f"Limite journalière atteinte ({MAX_DAILY_TRADES})")

        if not AUTO_TRADE or not MT5_AVAILABLE:
            # Dry run — log and return mock result
            result = TradeResult(
                success=True,
                order_type=decision.action,
                volume=decision.lot_size,
                entry_price=decision.entry_price,
                stop_loss=decision.stop_loss,
                take_profit=decision.take_profit,
                dry_run=True,
            )
            logger.info("DRY RUN: {}", result)
            return result

        return self._place_order_mt5(decision, today)

    def _place_order_mt5(self, decision: TradeDecision, today: date) -> TradeResult:
        """Place actual order on MT5."""
        order_type = mt5.ORDER_TYPE_BUY if decision.action == "BUY" else mt5.ORDER_TYPE_SELL  # type: ignore[name-defined]
        price = decision.entry_price
        if decision.action == "BUY":
            tick = mt5.symbol_info_tick(decision.symbol)  # type: ignore[name-defined]
            price = tick.ask if tick else decision.entry_price
        else:
            tick = mt5.symbol_info_tick(decision.symbol)  # type: ignore[name-defined]
            price = tick.bid if tick else decision.entry_price

        request = {
            "action": mt5.TRADE_ACTION_DEAL,  # type: ignore[name-defined]
            "symbol": decision.symbol,
            "volume": decision.lot_size,
            "type": order_type,
            "price": price,
            "sl": decision.stop_loss,
            "tp": decision.take_profit,
            "deviation": 20,
            "magic": 202501,
            "comment": f"GoldX-{decision.global_score:.0f}",
            "type_time": mt5.ORDER_TIME_GTC,  # type: ignore[name-defined]
            "type_filling": mt5.ORDER_FILLING_IOC,  # type: ignore[name-defined]
        }

        result = mt5.order_send(request)  # type: ignore[name-defined]
        if result.retcode == mt5.TRADE_RETCODE_DONE:  # type: ignore[name-defined]
            self._daily_trade_count[today] = self._daily_trade_count.get(today, 0) + 1
            logger.info("MT5 order placed: ticket={} price={}", result.order, result.price)
            return TradeResult(
                success=True,
                ticket=result.order,
                order_type=decision.action,
                volume=decision.lot_size,
                entry_price=result.price,
                stop_loss=decision.stop_loss,
                take_profit=decision.take_profit,
            )
        else:
            error = f"retcode={result.retcode} comment={result.comment}"
            logger.error("MT5 order failed: {}", error)
            return TradeResult(success=False, error_msg=error)

    # ── Position Monitoring ────────────────────────────────────────────

    def get_open_positions(self) -> list[OpenPosition]:
        if not MT5_AVAILABLE:
            return []
        positions = mt5.positions_get(symbol=SYMBOL)  # type: ignore[name-defined]
        if positions is None:
            return []
        result = []
        for p in positions:
            order_type = "BUY" if p.type == 0 else "SELL"
            current_price = float(p.price_current)
            result.append(OpenPosition(
                ticket=p.ticket,
                symbol=p.symbol,
                order_type=order_type,
                volume=p.volume,
                entry_price=p.price_open,
                current_price=current_price,
                stop_loss=p.sl,
                take_profit=p.tp,
                profit=p.profit,
                open_time=datetime.fromtimestamp(p.time),
            ))
        return result

    def close_position(self, ticket: int) -> bool:
        if not MT5_AVAILABLE:
            logger.info("DRY RUN: Would close position #{}", ticket)
            return True
        positions = mt5.positions_get(ticket=ticket)  # type: ignore[name-defined]
        if not positions:
            return False
        pos = positions[0]
        order_type = mt5.ORDER_TYPE_SELL if pos.type == 0 else mt5.ORDER_TYPE_BUY  # type: ignore[name-defined]
        tick = mt5.symbol_info_tick(pos.symbol)  # type: ignore[name-defined]
        price = tick.bid if pos.type == 0 else tick.ask

        request = {
            "action": mt5.TRADE_ACTION_DEAL,  # type: ignore[name-defined]
            "symbol": pos.symbol,
            "volume": pos.volume,
            "type": order_type,
            "position": ticket,
            "price": price,
            "deviation": 20,
            "magic": 202501,
            "comment": "GoldX-close",
            "type_time": mt5.ORDER_TIME_GTC,  # type: ignore[name-defined]
            "type_filling": mt5.ORDER_FILLING_IOC,  # type: ignore[name-defined]
        }
        result = mt5.order_send(request)  # type: ignore[name-defined]
        success = result.retcode == mt5.TRADE_RETCODE_DONE  # type: ignore[name-defined]
        if success:
            logger.info("Position #{} closed.", ticket)
        else:
            logger.error("Close failed: retcode={}", result.retcode)
        return success

    def get_daily_stats(self) -> dict:
        today = date.today()
        return {
            "trades_today": self._daily_trade_count.get(today, 0),
            "max_daily": MAX_DAILY_TRADES,
            "auto_trade": AUTO_TRADE,
        }
