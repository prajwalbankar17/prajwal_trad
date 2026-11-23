"""Risk engine.

Independent of strategy logic by design. A strategy proposes a trade; this
decides whether it is allowed and how large it may be. The two never import
each other.

Position sizing is capital x risk% / stop distance, then clamped by every other
limit that applies. Broker leverage is never assumed: `assumed_leverage` is what
*we* model, and when the broker reports real margin the lower of the two wins.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.enums import Direction, PositionStatus
from app.core.logging import get_logger
from app.core.market_calendar import now_ist
from app.db.redis_client import Keys, get_redis
from app.models.instrument import Instrument
from app.models.risk import DailyRiskState, RiskLimitBreach, RiskProfile
from app.models.trading import Position

log = get_logger(__name__)


@dataclass
class RiskDecision:
    allowed: bool
    quantity: int = 0
    reasons: list[str] = field(default_factory=list)
    checks: list[dict] = field(default_factory=list)
    capital_required: float = 0.0
    risk_amount: float = 0.0
    blocking_limit: str | None = None

    def add(self, name: str, passed: bool, detail: str, limit=None, actual=None) -> None:
        self.checks.append(
            {
                "name": name,
                "passed": passed,
                "detail": detail,
                "limit": limit,
                "actual": actual,
            }
        )
        if not passed:
            self.reasons.append(detail)
            self.allowed = False
            if self.blocking_limit is None:
                self.blocking_limit = name

    def as_dict(self) -> dict:
        return {
            "allowed": self.allowed,
            "quantity": self.quantity,
            "capital_required": round(self.capital_required, 2),
            "risk_amount": round(self.risk_amount, 2),
            "blocking_limit": self.blocking_limit,
            "reasons": self.reasons,
            "checks": self.checks,
        }


class RiskEngine:
    def __init__(self, db: Session, profile: RiskProfile) -> None:
        self.db = db
        self.profile = profile

    # -- state -----------------------------------------------------------

    def daily_state(self, trade_date: date | None = None) -> DailyRiskState:
        trade_date = trade_date or now_ist().date()
        state = self.db.scalar(
            select(DailyRiskState).where(
                DailyRiskState.risk_profile_id == self.profile.id,
                DailyRiskState.trade_date == trade_date,
            )
        )
        if state is None:
            state = DailyRiskState(risk_profile_id=self.profile.id, trade_date=trade_date)
            self.db.add(state)
            self.db.flush()
        return state

    def kill_switch_active(self) -> bool:
        """Redis for speed, the profile column as the durable record. Either
        one being set stops trading - fail closed."""
        try:
            if get_redis().get(Keys.KILL_SWITCH) == "1":
                return True
        except Exception:  # pragma: no cover - Redis down must not open the gate
            log.warning("kill_switch_check_failed_assuming_profile_value")
        return bool(self.profile.kill_switch_enabled)

    def set_kill_switch(self, active: bool, *, reason: str = "") -> None:
        self.profile.kill_switch_enabled = active
        try:
            redis = get_redis()
            redis.set(Keys.KILL_SWITCH, "1" if active else "0")
        except Exception:  # pragma: no cover
            log.warning("kill_switch_redis_write_failed", active=active)
        state = self.daily_state()
        if active:
            state.trading_halted = True
            state.halt_reason = reason or "Kill switch engaged."
            state.halted_at = now_ist()
        self.db.commit()
        log.warning("kill_switch_set", active=active, reason=reason)

    def open_positions(self) -> list[Position]:
        return list(
            self.db.scalars(
                select(Position).where(
                    Position.risk_profile_id == self.profile.id,
                    Position.status.in_([PositionStatus.OPEN, PositionStatus.PARTIALLY_CLOSED]),
                    Position.is_backtest.is_(False),
                )
            ).all()
        )

    def sector_exposure(self) -> dict[str, float]:
        rows = self.db.execute(
            select(Instrument.sector_id, func.sum(Position.capital_deployed))
            .join(Position, Position.instrument_id == Instrument.id)
            .where(
                Position.risk_profile_id == self.profile.id,
                Position.status.in_([PositionStatus.OPEN, PositionStatus.PARTIALLY_CLOSED]),
                Position.is_backtest.is_(False),
            )
            .group_by(Instrument.sector_id)
        ).all()
        return {str(sector_id): float(total or 0) for sector_id, total in rows}

    # -- sizing ----------------------------------------------------------

    def position_size(
        self,
        *,
        entry_price: float,
        stop_loss: float,
        available_capital: float | None = None,
        lot_size: int = 1,
    ) -> tuple[int, dict]:
        """Risk-based sizing, then clamped by position-size and margin limits."""
        capital = float(self.profile.capital)
        risk_amount = capital * float(self.profile.max_risk_per_trade_pct) / 100
        stop_distance = abs(entry_price - stop_loss)

        detail = {
            "capital": capital,
            "risk_pct": float(self.profile.max_risk_per_trade_pct),
            "risk_amount": round(risk_amount, 2),
            "stop_distance": round(stop_distance, 4),
        }
        if stop_distance <= 0 or entry_price <= 0:
            detail["reason"] = "stop distance is zero - cannot size a position"
            return 0, detail

        qty_by_risk = int(risk_amount // stop_distance)

        max_position_value = capital * float(self.profile.max_position_size_pct) / 100
        leverage = max(float(self.profile.assumed_leverage), 1.0)
        # Leverage increases how much exposure a rupee of capital can carry.
        qty_by_position_cap = int((max_position_value * leverage) // entry_price)

        spendable = (
            float(available_capital) if available_capital is not None else capital
        ) * leverage
        qty_by_capital = int(spendable // entry_price)

        quantity = max(min(qty_by_risk, qty_by_position_cap, qty_by_capital), 0)
        if lot_size > 1:
            quantity = (quantity // lot_size) * lot_size

        detail.update(
            {
                "qty_by_risk": qty_by_risk,
                "qty_by_position_cap": qty_by_position_cap,
                "qty_by_available_capital": qty_by_capital,
                "assumed_leverage": leverage,
                "lot_size": lot_size,
                "final_quantity": quantity,
                "binding_constraint": _binding(
                    quantity, qty_by_risk, qty_by_position_cap, qty_by_capital
                ),
            }
        )
        return quantity, detail

    # -- validation ------------------------------------------------------

    def validate_entry(
        self,
        *,
        instrument: Instrument,
        direction: Direction,
        entry_price: float,
        stop_loss: float,
        available_capital: float | None = None,
        min_risk_reward: float | None = None,
        risk_reward: float | None = None,
    ) -> RiskDecision:
        decision = RiskDecision(allowed=True)
        state = self.daily_state()

        decision.add(
            "kill_switch",
            not self.kill_switch_active(),
            "Kill switch is engaged - no new positions." if self.kill_switch_active()
            else "Kill switch is off.",
        )
        decision.add(
            "daily_halt",
            not state.trading_halted,
            state.halt_reason or "Trading halted for today."
            if state.trading_halted
            else "Trading is not halted today.",
        )

        # Daily loss limit
        max_daily_loss = float(self.profile.capital) * float(self.profile.max_daily_loss_pct) / 100
        realised = float(state.realised_pnl)
        decision.add(
            "max_daily_loss",
            realised > -max_daily_loss,
            f"Daily loss {realised:.2f} has reached the limit of -{max_daily_loss:.2f}."
            if realised <= -max_daily_loss
            else f"Daily P&L {realised:.2f} is within the -{max_daily_loss:.2f} limit.",
            limit=-max_daily_loss,
            actual=realised,
        )

        open_positions = self.open_positions()
        decision.add(
            "max_open_positions",
            len(open_positions) < self.profile.max_open_positions,
            f"{len(open_positions)} open positions; limit is "
            f"{self.profile.max_open_positions}.",
            limit=self.profile.max_open_positions,
            actual=len(open_positions),
        )
        decision.add(
            "max_trades_per_day",
            state.trades_taken < self.profile.max_trades_per_day,
            f"{state.trades_taken} trades today; limit is "
            f"{self.profile.max_trades_per_day}.",
            limit=self.profile.max_trades_per_day,
            actual=state.trades_taken,
        )

        # One position per instrument - no silent pyramiding.
        already_open = any(p.instrument_id == instrument.id for p in open_positions)
        decision.add(
            "no_duplicate_position",
            not already_open,
            f"A position in {instrument.tradingsymbol} is already open."
            if already_open
            else f"No existing position in {instrument.tradingsymbol}.",
        )

        if min_risk_reward is not None and risk_reward is not None:
            decision.add(
                "min_risk_reward",
                risk_reward >= min_risk_reward,
                f"Risk/reward {risk_reward:.2f} is below the required "
                f"{min_risk_reward:.2f}."
                if risk_reward < min_risk_reward
                else f"Risk/reward {risk_reward:.2f} meets the {min_risk_reward:.2f} minimum.",
                limit=min_risk_reward,
                actual=round(risk_reward, 3),
            )

        quantity, sizing = self.position_size(
            entry_price=entry_price,
            stop_loss=stop_loss,
            available_capital=available_capital,
            lot_size=instrument.lot_size or 1,
        )
        decision.quantity = quantity
        decision.checks.append({"name": "position_sizing", "passed": quantity > 0, **sizing})
        if quantity <= 0:
            decision.allowed = False
            decision.blocking_limit = decision.blocking_limit or "position_sizing"
            decision.reasons.append(
                sizing.get("reason", "Calculated position size is zero.")
            )
            return decision

        capital_required = quantity * entry_price / max(
            float(self.profile.assumed_leverage), 1.0
        )
        decision.capital_required = capital_required
        decision.risk_amount = quantity * abs(entry_price - stop_loss)

        # Total exposure
        deployed = float(state.deployed_capital) + capital_required
        max_exposure = (
            float(self.profile.capital) * float(self.profile.max_total_exposure_pct) / 100
        )
        decision.add(
            "max_total_exposure",
            deployed <= max_exposure,
            f"Deployed capital would be {deployed:.2f}, above the "
            f"{max_exposure:.2f} exposure limit."
            if deployed > max_exposure
            else f"Deployed capital {deployed:.2f} is within {max_exposure:.2f}.",
            limit=round(max_exposure, 2),
            actual=round(deployed, 2),
        )

        # Sector exposure
        if instrument.sector_id:
            by_sector = self.sector_exposure()
            sector_total = by_sector.get(str(instrument.sector_id), 0.0) + capital_required
            max_sector = (
                float(self.profile.capital) * float(self.profile.max_sector_exposure_pct) / 100
            )
            decision.add(
                "max_sector_exposure",
                sector_total <= max_sector,
                f"Sector exposure would be {sector_total:.2f}, above the "
                f"{max_sector:.2f} limit."
                if sector_total > max_sector
                else f"Sector exposure {sector_total:.2f} is within {max_sector:.2f}.",
                limit=round(max_sector, 2),
                actual=round(sector_total, 2),
            )

        return decision

    # -- recording -------------------------------------------------------

    def record_breach(
        self, decision: RiskDecision, *, signal_id: uuid.UUID | None = None
    ) -> None:
        if decision.allowed:
            return
        failing = next((c for c in decision.checks if not c.get("passed")), {})
        self.db.add(
            RiskLimitBreach(
                risk_profile_id=self.profile.id,
                signal_id=signal_id,
                limit_name=decision.blocking_limit or "unknown",
                limit_value=_as_float(failing.get("limit")),
                actual_value=_as_float(failing.get("actual")),
                occurred_at=now_ist(),
                action_taken="SIGNAL_REJECTED",
                details=decision.as_dict(),
            )
        )
        self.db.flush()

    def register_entry(self, *, capital_required: float) -> None:
        state = self.daily_state()
        state.trades_taken += 1
        state.open_positions += 1
        state.deployed_capital = float(state.deployed_capital) + capital_required
        self.db.flush()

    def register_exit(self, *, net_pnl: float, charges: float, capital_released: float) -> None:
        state = self.daily_state()
        state.open_positions = max(state.open_positions - 1, 0)
        state.realised_pnl = float(state.realised_pnl) + net_pnl
        state.charges_paid = float(state.charges_paid) + charges
        state.deployed_capital = max(float(state.deployed_capital) - capital_released, 0.0)

        max_daily_loss = float(self.profile.capital) * float(self.profile.max_daily_loss_pct) / 100
        if float(state.realised_pnl) <= -max_daily_loss and not state.trading_halted:
            state.trading_halted = True
            state.halted_at = now_ist()
            state.halt_reason = (
                f"Daily loss limit reached: {float(state.realised_pnl):.2f} vs "
                f"-{max_daily_loss:.2f}. New entries are blocked; open positions "
                "continue to be monitored."
            )
            log.warning("daily_loss_limit_reached", profile=str(self.profile.id))
        self.db.flush()

    def utilisation(self) -> dict:
        state = self.daily_state()
        capital = float(self.profile.capital)
        max_daily_loss = capital * float(self.profile.max_daily_loss_pct) / 100
        return {
            "capital": capital,
            "deployed_capital": float(state.deployed_capital),
            "utilisation_pct": round(float(state.deployed_capital) / capital * 100, 2)
            if capital
            else 0,
            "max_capital_utilisation_pct": float(self.profile.max_capital_utilisation_pct),
            "realised_pnl": float(state.realised_pnl),
            "unrealised_pnl": float(state.unrealised_pnl),
            "daily_loss_limit": -max_daily_loss,
            "daily_loss_used_pct": round(
                min(max(-float(state.realised_pnl) / max_daily_loss * 100, 0), 100), 2
            )
            if max_daily_loss
            else 0,
            "open_positions": state.open_positions,
            "max_open_positions": self.profile.max_open_positions,
            "trades_taken": state.trades_taken,
            "max_trades_per_day": self.profile.max_trades_per_day,
            "trading_halted": state.trading_halted,
            "halt_reason": state.halt_reason,
            "kill_switch": self.kill_switch_active(),
        }


def _binding(final: int, by_risk: int, by_position: int, by_capital: int) -> str:
    if final == 0:
        return "none - size rounded to zero"
    mapping = {
        "risk_per_trade": by_risk,
        "max_position_size": by_position,
        "available_capital": by_capital,
    }
    return min(mapping, key=mapping.get)


def _as_float(value) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def get_default_profile(db: Session) -> RiskProfile:
    profile = db.scalar(select(RiskProfile).where(RiskProfile.is_default.is_(True)))
    if profile is None:
        raise ValueError("No default risk profile exists. Run scripts/seed.py.")
    return profile
