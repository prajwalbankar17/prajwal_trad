"""Paper trading engine.

Turns VALIDATED signals into simulated positions and manages their whole life:
entry fill, stop-loss and target monitoring, trailing stops, partial exits,
session square-off and final P&L with real transaction costs.

Two rules this engine exists to uphold:

* **Real orders are impossible here.** Every write sets execution_mode='PAPER',
  and the database has a CHECK constraint enforcing it. There is no code path
  from this module to a broker order endpoint.
* **Deactivating a module never abandons a position.** `enter_from_signal`
  respects the module switch; `monitor_positions` ignores it entirely. An open
  position keeps its stop-loss and target monitoring until it is closed.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.charges import ChargesConfig
from app.core.enums import (
    Direction,
    ExitReason,
    OrderStatus,
    OrderType,
    PositionStatus,
    ProductType,
    SignalState,
)
from app.core.exceptions import ConflictError, NotFoundError
from app.core.logging import get_logger
from app.core.market_calendar import MARKET_CLOSE, now_ist, to_ist
from app.core.safety import execution_mode
from app.engines.execution import (
    SlippageModel,
    check_exit_on_candle,
    excursions,
    round_trip_pnl,
    simulate_entry,
    simulate_exit,
    update_trailing_stop,
)
from app.engines.risk import RiskEngine
from app.models.instrument import Instrument
from app.models.portfolio import Portfolio
from app.models.signal import SignalHistory, TradingSignal
from app.models.strategy import StrategyConfig, TradingModuleState
from app.models.trading import ExitRecord, Order, Position, TradeExecution
from app.services import candles as candle_service

log = get_logger(__name__)


@dataclass
class EntryResult:
    created: bool
    position: Position | None = None
    reason: str = ""


class PaperTradingEngine:
    def __init__(
        self,
        db: Session,
        risk: RiskEngine,
        *,
        slippage: SlippageModel | None = None,
        charges: ChargesConfig | None = None,
    ) -> None:
        self.db = db
        self.risk = risk
        self.slippage = slippage or SlippageModel(base_pct=0.05)
        self.charges = charges or ChargesConfig()

    # -- module switch ---------------------------------------------------

    def module_active(self, module: str) -> bool:
        state = self.db.scalar(
            select(TradingModuleState).where(TradingModuleState.module == module)
        )
        return bool(state and state.is_active)

    # -- entry -----------------------------------------------------------

    def enter_from_signal(
        self,
        signal: TradingSignal,
        *,
        portfolio: Portfolio | None = None,
        as_of: datetime | None = None,
        reference_price: float | None = None,
    ) -> EntryResult:
        as_of = as_of or now_ist()

        if signal.state != SignalState.VALIDATED:
            return EntryResult(False, reason=f"Signal is {signal.state}, not VALIDATED.")
        if not self.module_active(signal.module):
            return EntryResult(
                False,
                reason=(
                    f"The {signal.module} module is inactive - no new positions. "
                    "Existing positions continue to be monitored."
                ),
            )

        instrument = self.db.get(Instrument, signal.instrument_id)
        if instrument is None:
            raise NotFoundError("Instrument for this signal no longer exists.")

        direction = Direction(signal.direction)
        available = float(portfolio.available_capital) if portfolio else None

        decision = self.risk.validate_entry(
            instrument=instrument,
            direction=direction,
            entry_price=float(signal.entry_price),
            stop_loss=float(signal.stop_loss),
            available_capital=available,
            min_risk_reward=None,
            risk_reward=float(signal.risk_reward) if signal.risk_reward else None,
        )
        signal.risk_validation = decision.as_dict()
        if not decision.allowed:
            signal.state = SignalState.REJECTED
            signal.rejection_reason = "; ".join(decision.reasons)
            self.risk.record_breach(decision, signal_id=signal.id)
            self._transition(signal, SignalState.VALIDATED, SignalState.REJECTED,
                             signal.rejection_reason)
            self.db.commit()
            return EntryResult(False, reason=signal.rejection_reason)

        quantity = decision.quantity
        reference = reference_price if reference_price is not None else float(signal.entry_price)
        fill = simulate_entry(
            reference_price=reference,
            direction=direction,
            quantity=quantity,
            slippage=self.slippage,
        )

        position = Position(
            execution_mode="PAPER",
            module=signal.module,
            instrument_id=instrument.id,
            signal_id=signal.id,
            strategy_config_id=signal.strategy_config_id,
            risk_profile_id=self.risk.profile.id,
            portfolio_id=portfolio.id if portfolio else None,
            direction=str(direction),
            product=ProductType.MIS,
            quantity=quantity,
            remaining_quantity=quantity,
            entry_price=fill.price,
            entry_time=as_of,
            trade_date=to_ist(as_of).date(),
            stop_loss=float(signal.stop_loss),
            initial_stop_loss=float(signal.stop_loss),
            target=float(signal.target),
            status=PositionStatus.OPEN,
            capital_deployed=decision.capital_required,
            margin_used=decision.capital_required,
            highest_price_seen=fill.price,
            lowest_price_seen=fill.price,
        )
        self.db.add(position)
        self.db.flush()

        order = Order(
            execution_mode="PAPER",
            position_id=position.id,
            signal_id=signal.id,
            instrument_id=instrument.id,
            side=str(direction),
            order_type=OrderType.MARKET,
            product=ProductType.MIS,
            quantity=quantity,
            filled_quantity=quantity,
            price=reference,
            average_price=fill.price,
            status=OrderStatus.COMPLETE,
            placed_at=as_of,
            filled_at=as_of,
            simulation={"slippage_model": self.slippage.__dict__, "fill": fill.as_dict()},
        )
        self.db.add(order)
        self.db.flush()

        self.db.add(
            TradeExecution(
                position_id=position.id,
                order_id=order.id,
                side=str(direction),
                quantity=quantity,
                price=fill.price,
                requested_price=reference,
                slippage=fill.slippage,
                executed_at=as_of,
                leg="ENTRY",
                details=fill.as_dict(),
            )
        )

        signal.state = SignalState.PAPER_EXECUTED
        self._transition(
            signal, SignalState.VALIDATED, SignalState.PAPER_EXECUTED,
            f"Paper position opened for {quantity} @ {fill.price:.2f}.",
        )

        self.risk.register_entry(capital_required=decision.capital_required)
        if portfolio:
            portfolio.available_capital = float(portfolio.available_capital) - (
                decision.capital_required
            )
            portfolio.deployed_capital = float(portfolio.deployed_capital) + (
                decision.capital_required
            )
        self.db.commit()
        self.db.refresh(position)

        log.info(
            "paper_position_opened",
            position_id=str(position.id),
            symbol=instrument.tradingsymbol,
            direction=str(direction),
            quantity=quantity,
            entry=round(fill.price, 2),
            execution_mode=execution_mode(),
        )
        return EntryResult(True, position, "Paper position opened.")

    # -- monitoring ------------------------------------------------------

    def monitor_positions(
        self,
        *,
        as_of: datetime | None = None,
        price_lookup: dict[uuid.UUID, dict] | None = None,
    ) -> list[dict]:
        """Walk every open position and act on stop-loss / target / square-off.

        Runs regardless of module activation state - by design.
        """
        as_of = as_of or now_ist()
        results: list[dict] = []

        positions = self.db.scalars(
            select(Position).where(
                Position.status.in_([PositionStatus.OPEN, PositionStatus.PARTIALLY_CLOSED]),
                Position.is_backtest.is_(False),
            )
        ).all()

        for position in positions:
            candle = (
                price_lookup.get(position.instrument_id)
                if price_lookup
                else candle_service.latest_candle(self.db, position.instrument_id)
            )
            if candle is None:
                results.append(
                    {
                        "position_id": str(position.id),
                        "action": "skipped",
                        "reason": "No price data available - position left untouched.",
                    }
                )
                continue
            results.append(self._process_candle(position, candle, as_of))

        self.db.commit()
        return results

    def _process_candle(self, position: Position, candle: dict, as_of: datetime) -> dict:
        direction = Direction(position.direction)
        config = (
            self.db.get(StrategyConfig, position.strategy_config_id)
            if position.strategy_config_id
            else None
        )

        high, low, close = float(candle["high"]), float(candle["low"]), float(candle["close"])

        # Excursions, for MAE/MFE analytics.
        mfe, mae = excursions(
            direction=direction,
            entry_price=float(position.entry_price),
            high=high,
            low=low,
            quantity=position.remaining_quantity,
        )
        position.max_favourable_excursion = max(float(position.max_favourable_excursion), mfe)
        position.max_adverse_excursion = min(float(position.max_adverse_excursion), mae)
        position.highest_price_seen = max(float(position.highest_price_seen or high), high)
        position.lowest_price_seen = min(float(position.lowest_price_seen or low), low)

        exit_check = check_exit_on_candle(
            direction=direction,
            stop_loss=float(position.stop_loss),
            target=float(position.target),
            candle_open=float(candle["open"]),
            candle_high=high,
            candle_low=low,
        )
        if exit_check.triggered:
            self.close_position(
                position,
                exit_price=exit_check.price,
                reason=exit_check.reason,
                as_of=as_of,
                note=exit_check.note,
            )
            return {
                "position_id": str(position.id),
                "action": "closed",
                "reason": str(exit_check.reason),
                "exit_price": round(exit_check.price, 2),
                "gapped": exit_check.gapped,
                "note": exit_check.note,
            }

        # Session square-off for intraday products.
        if (
            position.product == ProductType.MIS
            and config is not None
            and to_ist(as_of).time() >= config.square_off_time
        ):
            self.close_position(
                position,
                exit_price=close,
                reason=ExitReason.SESSION_END,
                as_of=as_of,
                note=f"Intraday square-off at {config.square_off_time}.",
            )
            return {
                "position_id": str(position.id),
                "action": "closed",
                "reason": str(ExitReason.SESSION_END),
                "exit_price": round(close, 2),
            }

        if config is not None and config.trailing_stop_enabled and config.trailing_stop_value:
            new_stop = update_trailing_stop(
                direction=direction,
                current_stop=float(position.stop_loss),
                entry_price=float(position.entry_price),
                last_price=close,
                trail_value=float(config.trailing_stop_value),
                trail_type=config.stop_loss_type,
            )
            if abs(new_stop - float(position.stop_loss)) > 1e-9:
                position.stop_loss = new_stop
                position.trailing_stop_active = True

        # Mark to market.
        gross = (
            (close - float(position.entry_price)) * position.remaining_quantity
            if direction == Direction.BUY
            else (float(position.entry_price) - close) * position.remaining_quantity
        )
        position.unrealised_pnl = round(gross, 2)
        return {
            "position_id": str(position.id),
            "action": "held",
            "last_price": close,
            "unrealised_pnl": float(position.unrealised_pnl),
            "stop_loss": float(position.stop_loss),
        }

    # -- exit ------------------------------------------------------------

    def close_position(
        self,
        position: Position,
        *,
        exit_price: float,
        reason: ExitReason,
        as_of: datetime | None = None,
        quantity: int | None = None,
        note: str = "",
    ) -> Position:
        if position.status == PositionStatus.CLOSED:
            raise ConflictError("Position is already closed.")

        as_of = as_of or now_ist()
        direction = Direction(position.direction)
        qty = quantity or position.remaining_quantity
        qty = min(qty, position.remaining_quantity)
        is_partial = qty < position.remaining_quantity

        fill = simulate_exit(
            reference_price=exit_price,
            direction=direction,
            quantity=qty,
            slippage=self.slippage,
        )
        pnl = round_trip_pnl(
            direction=direction,
            entry_price=float(position.entry_price),
            exit_price=fill.price,
            quantity=qty,
            intraday=position.product == ProductType.MIS,
            charges_config=self.charges,
        )

        order = Order(
            execution_mode="PAPER",
            position_id=position.id,
            instrument_id=position.instrument_id,
            side=str(Direction.SELL if direction == Direction.BUY else Direction.BUY),
            order_type=OrderType.MARKET,
            product=position.product,
            quantity=qty,
            filled_quantity=qty,
            price=exit_price,
            average_price=fill.price,
            status=OrderStatus.COMPLETE,
            placed_at=as_of,
            filled_at=as_of,
            simulation={"fill": fill.as_dict(), "note": note},
        )
        self.db.add(order)
        self.db.flush()

        self.db.add(
            TradeExecution(
                position_id=position.id,
                order_id=order.id,
                side=order.side,
                quantity=qty,
                price=fill.price,
                requested_price=exit_price,
                slippage=fill.slippage,
                charges=pnl["charges"],
                executed_at=as_of,
                leg="EXIT",
                details=fill.as_dict(),
            )
        )
        self.db.add(
            ExitRecord(
                position_id=position.id,
                quantity=qty,
                exit_price=fill.price,
                exit_time=as_of,
                reason=str(reason),
                gross_pnl=pnl["gross_pnl"],
                charges=pnl["charges"],
                net_pnl=pnl["net_pnl"],
                is_partial=is_partial,
                details={"note": note, "charge_breakdown": pnl["charge_breakdown"]},
            )
        )

        position.remaining_quantity -= qty
        position.gross_pnl = float(position.gross_pnl) + pnl["gross_pnl"]
        position.charges = float(position.charges) + pnl["charges"]
        position.net_pnl = float(position.net_pnl) + pnl["net_pnl"]
        position.charge_breakdown = pnl["charge_breakdown"]

        capital_released = float(position.capital_deployed) * (qty / position.quantity)

        if position.remaining_quantity <= 0:
            position.status = PositionStatus.CLOSED
            position.exit_price = fill.price
            position.exit_time = as_of
            position.exit_reason = str(reason)
            position.unrealised_pnl = 0
        else:
            position.status = PositionStatus.PARTIALLY_CLOSED

        self.risk.register_exit(
            net_pnl=pnl["net_pnl"],
            charges=pnl["charges"],
            capital_released=capital_released,
        )

        if position.portfolio_id:
            portfolio = self.db.get(Portfolio, position.portfolio_id)
            if portfolio:
                portfolio.available_capital = (
                    float(portfolio.available_capital) + capital_released + pnl["net_pnl"]
                )
                portfolio.deployed_capital = max(
                    float(portfolio.deployed_capital) - capital_released, 0.0
                )
                portfolio.realised_pnl = float(portfolio.realised_pnl) + pnl["net_pnl"]
                portfolio.total_charges = float(portfolio.total_charges) + pnl["charges"]
                portfolio.current_capital = (
                    float(portfolio.starting_capital) + float(portfolio.realised_pnl)
                )

        self.db.flush()
        log.info(
            "paper_position_closed",
            position_id=str(position.id),
            reason=str(reason),
            net_pnl=pnl["net_pnl"],
            charges=pnl["charges"],
        )
        return position

    def square_off_all(self, *, reason: ExitReason = ExitReason.SESSION_END) -> int:
        """End-of-day safety net: nothing intraday is carried overnight."""
        count = 0
        for position in self.db.scalars(
            select(Position).where(
                Position.status.in_([PositionStatus.OPEN, PositionStatus.PARTIALLY_CLOSED]),
                Position.is_backtest.is_(False),
                Position.product == ProductType.MIS,
            )
        ).all():
            candle = candle_service.latest_candle(self.db, position.instrument_id)
            if candle is None:
                continue
            self.close_position(
                position,
                exit_price=float(candle["close"]),
                reason=reason,
                note=f"Automatic square-off before {MARKET_CLOSE}.",
            )
            count += 1
        self.db.commit()
        return count

    def _transition(self, signal: TradingSignal, from_state, to_state, reason: str) -> None:
        self.db.add(
            SignalHistory(
                signal_id=signal.id,
                from_state=str(from_state) if from_state else None,
                to_state=str(to_state),
                changed_at=now_ist(),
                reason=reason,
            )
        )
