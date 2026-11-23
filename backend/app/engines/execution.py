"""Fill simulation for the paper engine and the backtester.

Both use this module, so a paper trade and its backtest equivalent are filled
by identical rules.

Modelling choices, stated plainly because they decide whether results mean
anything:

* **Slippage always hurts.** A buy fills above the reference price, a sell
  below. Modelling it symmetrically (or at zero) is the single most common way
  a backtest flatters itself.
* **Stop-loss before target when a single candle contains both.** Without tick
  data we cannot know which came first, so we take the unfavourable one. This
  understates results rather than overstating them.
* **Gaps fill at the open.** If a candle opens beyond the stop, the fill is the
  open price, not the stop price - that is what actually happens.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.charges import ChargesConfig, compute_charges
from app.core.enums import Direction, ExitReason


@dataclass
class SlippageModel:
    """Percent-of-price slippage, optionally widened for illiquid names."""

    base_pct: float = 0.05
    market_order_extra_pct: float = 0.0

    def apply(self, price: float, side: Direction, *, is_market: bool = True) -> float:
        pct = self.base_pct + (self.market_order_extra_pct if is_market else 0.0)
        factor = pct / 100
        return price * (1 + factor) if side == Direction.BUY else price * (1 - factor)


@dataclass
class Fill:
    price: float
    requested_price: float
    slippage: float
    quantity: int

    def as_dict(self) -> dict:
        return {
            "price": round(self.price, 4),
            "requested_price": round(self.requested_price, 4),
            "slippage": round(self.slippage, 4),
            "quantity": self.quantity,
        }


def simulate_entry(
    *, reference_price: float, direction: Direction, quantity: int, slippage: SlippageModel
) -> Fill:
    filled = slippage.apply(reference_price, direction)
    return Fill(
        price=filled,
        requested_price=reference_price,
        slippage=abs(filled - reference_price),
        quantity=quantity,
    )


def simulate_exit(
    *, reference_price: float, direction: Direction, quantity: int, slippage: SlippageModel
) -> Fill:
    # Exiting a long is a sell, and vice versa.
    exit_side = Direction.SELL if direction == Direction.BUY else Direction.BUY
    filled = slippage.apply(reference_price, exit_side)
    return Fill(
        price=filled,
        requested_price=reference_price,
        slippage=abs(filled - reference_price),
        quantity=quantity,
    )


@dataclass
class CandleExit:
    triggered: bool
    reason: ExitReason | None = None
    price: float = 0.0
    gapped: bool = False
    note: str = ""


def check_exit_on_candle(
    *,
    direction: Direction,
    stop_loss: float,
    target: float,
    candle_open: float,
    candle_high: float,
    candle_low: float,
) -> CandleExit:
    """Decide whether a candle closes the position, and at what price."""
    if direction == Direction.BUY:
        # Gap through the stop: filled at the open, worse than the stop.
        if candle_open <= stop_loss:
            return CandleExit(True, ExitReason.STOP_LOSS_HIT, candle_open, True,
                              "Opened at or below the stop - filled at the open.")
        if candle_open >= target:
            return CandleExit(True, ExitReason.TARGET_HIT, candle_open, True,
                              "Opened at or above the target - filled at the open.")
        stop_hit = candle_low <= stop_loss
        target_hit = candle_high >= target
        if stop_hit and target_hit:
            return CandleExit(True, ExitReason.STOP_LOSS_HIT, stop_loss, False,
                              "Both levels traded in one candle; the stop is assumed first.")
        if stop_hit:
            return CandleExit(True, ExitReason.STOP_LOSS_HIT, stop_loss)
        if target_hit:
            return CandleExit(True, ExitReason.TARGET_HIT, target)
        return CandleExit(False)

    if candle_open >= stop_loss:
        return CandleExit(True, ExitReason.STOP_LOSS_HIT, candle_open, True,
                          "Opened at or above the stop - filled at the open.")
    if candle_open <= target:
        return CandleExit(True, ExitReason.TARGET_HIT, candle_open, True,
                          "Opened at or below the target - filled at the open.")
    stop_hit = candle_high >= stop_loss
    target_hit = candle_low <= target
    if stop_hit and target_hit:
        return CandleExit(True, ExitReason.STOP_LOSS_HIT, stop_loss, False,
                          "Both levels traded in one candle; the stop is assumed first.")
    if stop_hit:
        return CandleExit(True, ExitReason.STOP_LOSS_HIT, stop_loss)
    if target_hit:
        return CandleExit(True, ExitReason.TARGET_HIT, target)
    return CandleExit(False)


def update_trailing_stop(
    *,
    direction: Direction,
    current_stop: float,
    entry_price: float,
    last_price: float,
    trail_value: float,
    trail_type: str = "PERCENT",
) -> float:
    """A trailing stop only ever moves in the favourable direction."""
    distance = last_price * trail_value / 100 if trail_type == "PERCENT" else trail_value
    if direction == Direction.BUY:
        return max(current_stop, last_price - distance)
    return min(current_stop, last_price + distance)


def round_trip_pnl(
    *,
    direction: Direction,
    entry_price: float,
    exit_price: float,
    quantity: int,
    intraday: bool = True,
    charges_config: ChargesConfig | None = None,
) -> dict:
    """Gross, charges and net - always all three, never net reported as gross."""
    gross = (
        (exit_price - entry_price) * quantity
        if direction == Direction.BUY
        else (entry_price - exit_price) * quantity
    )
    breakdown = compute_charges(
        entry_price=entry_price,
        exit_price=exit_price,
        quantity=quantity,
        intraday=intraday,
        side="BUY" if direction == Direction.BUY else "SELL",
        config=charges_config,
    )
    return {
        "gross_pnl": round(gross, 2),
        "charges": round(breakdown.total, 2),
        "net_pnl": round(gross - breakdown.total, 2),
        "charge_breakdown": breakdown.as_dict(),
    }


def excursions(
    *, direction: Direction, entry_price: float, high: float, low: float, quantity: int
) -> tuple[float, float]:
    """(MFE, MAE) in rupees for one candle, from the position's point of view."""
    if direction == Direction.BUY:
        return (high - entry_price) * quantity, (low - entry_price) * quantity
    return (entry_price - low) * quantity, (entry_price - high) * quantity
