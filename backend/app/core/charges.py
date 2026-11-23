"""Indian equity transaction-cost model.

Rates are *configurable* (a `ChargesConfig`), seeded with the published
discount-broker equity schedule. They change with regulation, so the model is
parameterised rather than hardcoded into the paper engine, and every
computation returns a full breakdown instead of a single opaque number.

Gross P&L minus `total` is what the platform reports as net P&L - never the
other way round.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ChargesConfig:
    """Defaults reflect a discount broker's equity schedule. Verify against your
    broker's current contract note before trusting backtest net figures."""

    # Brokerage
    intraday_brokerage_pct: float = 0.03      # % of turnover per leg
    intraday_brokerage_cap: float = 20.0      # rupees per executed order
    delivery_brokerage_pct: float = 0.0

    # Statutory
    stt_intraday_sell_pct: float = 0.025      # sell leg only
    stt_delivery_pct: float = 0.1             # both legs
    exchange_txn_pct: float = 0.00297         # NSE equity
    sebi_charges_per_crore: float = 10.0
    stamp_duty_buy_intraday_pct: float = 0.003
    stamp_duty_buy_delivery_pct: float = 0.015
    gst_pct: float = 18.0                     # on brokerage + exchange + sebi
    ipft_pct: float = 0.0001                  # NSE investor protection fund


@dataclass
class ChargeBreakdown:
    brokerage: float = 0.0
    stt: float = 0.0
    exchange_txn: float = 0.0
    sebi: float = 0.0
    stamp_duty: float = 0.0
    gst: float = 0.0
    ipft: float = 0.0
    legs: list[dict] = field(default_factory=list)

    @property
    def total(self) -> float:
        return round(
            self.brokerage + self.stt + self.exchange_txn + self.sebi
            + self.stamp_duty + self.gst + self.ipft,
            2,
        )

    def as_dict(self) -> dict:
        return {
            "brokerage": round(self.brokerage, 2),
            "stt": round(self.stt, 2),
            "exchange_txn": round(self.exchange_txn, 2),
            "sebi": round(self.sebi, 2),
            "stamp_duty": round(self.stamp_duty, 2),
            "gst": round(self.gst, 2),
            "ipft": round(self.ipft, 2),
            "total": self.total,
            "legs": self.legs,
        }


def _leg(cfg: ChargesConfig, turnover: float, *, is_buy: bool, intraday: bool) -> dict:
    brokerage = (
        min(turnover * cfg.intraday_brokerage_pct / 100, cfg.intraday_brokerage_cap)
        if intraday
        else turnover * cfg.delivery_brokerage_pct / 100
    )

    if intraday:
        stt = 0.0 if is_buy else turnover * cfg.stt_intraday_sell_pct / 100
        stamp = turnover * cfg.stamp_duty_buy_intraday_pct / 100 if is_buy else 0.0
    else:
        stt = turnover * cfg.stt_delivery_pct / 100
        stamp = turnover * cfg.stamp_duty_buy_delivery_pct / 100 if is_buy else 0.0

    exch = turnover * cfg.exchange_txn_pct / 100
    sebi = turnover * cfg.sebi_charges_per_crore / 1e7
    ipft = turnover * cfg.ipft_pct / 100
    gst = (brokerage + exch + sebi) * cfg.gst_pct / 100

    return {
        "side": "BUY" if is_buy else "SELL",
        "turnover": round(turnover, 2),
        "brokerage": round(brokerage, 2),
        "stt": round(stt, 2),
        "exchange_txn": round(exch, 4),
        "sebi": round(sebi, 4),
        "stamp_duty": round(stamp, 4),
        "gst": round(gst, 4),
        "ipft": round(ipft, 4),
    }


def compute_charges(
    *,
    entry_price: float,
    exit_price: float | None,
    quantity: int,
    intraday: bool = True,
    side: str = "BUY",
    config: ChargesConfig | None = None,
) -> ChargeBreakdown:
    """Charges for a round trip, or for the entry leg alone when `exit_price`
    is None (an open position)."""
    cfg = config or ChargesConfig()
    b = ChargeBreakdown()

    entry_is_buy = side.upper() == "BUY"
    legs = [_leg(cfg, entry_price * quantity, is_buy=entry_is_buy, intraday=intraday)]
    if exit_price is not None:
        legs.append(_leg(cfg, exit_price * quantity, is_buy=not entry_is_buy, intraday=intraday))

    for leg in legs:
        b.brokerage += leg["brokerage"]
        b.stt += leg["stt"]
        b.exchange_txn += leg["exchange_txn"]
        b.sebi += leg["sebi"]
        b.stamp_duty += leg["stamp_duty"]
        b.gst += leg["gst"]
        b.ipft += leg["ipft"]
    b.legs = legs
    return b


def net_pnl(
    *,
    entry_price: float,
    exit_price: float,
    quantity: int,
    side: str = "BUY",
    intraday: bool = True,
    config: ChargesConfig | None = None,
) -> dict:
    gross = (
        (exit_price - entry_price) * quantity
        if side.upper() == "BUY"
        else (entry_price - exit_price) * quantity
    )
    charges = compute_charges(
        entry_price=entry_price,
        exit_price=exit_price,
        quantity=quantity,
        intraday=intraday,
        side=side,
        config=config,
    )
    return {
        "gross_pnl": round(gross, 2),
        "charges": charges.as_dict(),
        "net_pnl": round(gross - charges.total, 2),
    }
