"""Category D - Volume and market-structure strategies."""

from __future__ import annotations

import pandas as pd

from app.core.enums import Direction, StrategyCategory
from app.strategies.base import BaseStrategy, Condition, SignalProposal, StrategyContext
from app.strategies.indicators import atr, ema, obv, relative_volume


class VolumePriceActionStrategy(BaseStrategy):
    code = "volume_price_action"
    name = "Volume + Price Action"
    category = StrategyCategory.VOLUME
    description = (
        "A wide-range bar closing near its extreme on exceptional volume, in "
        "the direction of the prevailing EMA trend. Volume is treated as "
        "confirmation of a move that has already happened - not as a predictor."
    )
    default_parameters = {
        "volume_multiple": 2.0,
        "volume_lookback": 20,
        "close_position": 0.7,       # close must be in the top/bottom 30% of the bar
        "range_multiple": 1.3,       # bar range vs its own recent average
        "trend_ema": 50,
        "atr_period": 14,
        "atr_stop_multiple": 1.5,
        "risk_reward": 2.0,
        "allow_short": True,
    }
    parameter_schema = {
        "volume_multiple": {"type": "float", "min": 1, "max": 20, "label": "Volume multiple"},
        "close_position": {"type": "float", "min": 0.5, "max": 1,
                           "label": "Close position in bar"},
        "range_multiple": {"type": "float", "min": 1, "max": 5, "label": "Range multiple"},
        "trend_ema": {"type": "int", "min": 0, "max": 400, "label": "Trend EMA (0 = off)"},
    }
    min_bars = 80

    def prepare(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        lookback = int(self.params["volume_lookback"])
        out["rel_volume"] = relative_volume(df["volume"], lookback)
        bar_range = df["high"] - df["low"]
        out["bar_range"] = bar_range
        out["avg_range"] = bar_range.shift(1).rolling(lookback, min_periods=lookback).mean()
        out["atr"] = atr(df, int(self.params["atr_period"]))
        trend_period = int(self.params.get("trend_ema") or 0)
        out["ema_trend"] = ema(df["close"], trend_period) if trend_period else pd.NA
        out["obv"] = obv(df)
        return out

    def evaluate(self, ctx: StrategyContext) -> SignalProposal | None:
        row = ctx.last
        if any(pd.isna(row.get(c)) for c in ("rel_volume", "avg_range", "atr")):
            return None

        bar_range = float(row["bar_range"])
        if bar_range <= 0:
            return None

        close_pos = (float(row["close"]) - float(row["low"])) / bar_range
        threshold = float(ctx.param("close_position", 0.7))

        bullish = close_pos >= threshold and row["close"] > row["open"]
        bearish = close_pos <= (1 - threshold) and row["close"] < row["open"]
        if not bullish and not bearish:
            return None

        direction = Direction.BUY if bullish else Direction.SELL
        if direction == Direction.SELL and not ctx.param("allow_short", True):
            return None

        rel_vol = float(row["rel_volume"])
        vol_needed = float(ctx.param("volume_multiple", 2.0))
        range_ratio = bar_range / float(row["avg_range"]) if row["avg_range"] else 0.0
        range_needed = float(ctx.param("range_multiple", 1.3))

        conditions = [
            Condition("volume_spike", rel_vol >= vol_needed,
                      f"relative volume {rel_vol:.2f}x vs {vol_needed}x required",
                      round(rel_vol, 3)),
            Condition("wide_range_bar", range_ratio >= range_needed,
                      f"bar range {range_ratio:.2f}x its recent average "
                      f"(need {range_needed}x)", round(range_ratio, 3)),
            Condition("close_near_extreme", True,
                      f"close sits at {close_pos * 100:.0f}% of the bar range",
                      round(close_pos, 3)),
        ]

        trend_period = int(ctx.param("trend_ema") or 0)
        if trend_period:
            trend_value = row.get("ema_trend")
            aligned = bool(
                pd.notna(trend_value)
                and (
                    row["close"] > trend_value
                    if direction == Direction.BUY
                    else row["close"] < trend_value
                )
            )
            conditions.append(
                Condition("trend_alignment", aligned,
                          f"close is on the {'right' if aligned else 'wrong'} side of "
                          f"EMA{trend_period}")
            )

        if not self._ok(conditions):
            return None

        entry = float(row["close"])
        stop_distance = max(
            float(row["atr"]) * float(ctx.param("atr_stop_multiple", 1.5)),
            bar_range * 0.5,
        )
        stop, target = self._stop_and_target(
            entry, direction, stop_distance=stop_distance, rr=float(ctx.param("risk_reward", 2.0))
        )
        return SignalProposal(
            direction=direction,
            entry_price=entry,
            stop_loss=stop,
            target=target,
            candle_ts=ctx.candle_ts,
            conditions=conditions,
            reason=(
                f"Wide-range {'bullish' if bullish else 'bearish'} bar closing near its "
                f"{'high' if bullish else 'low'} on {rel_vol:.1f}x average volume."
            ),
            confidence=min(0.85, 0.5 + 0.08 * rel_vol),
            indicator_snapshot={
                "rel_volume": round(rel_vol, 3),
                "range_ratio": round(range_ratio, 3),
                "close_position": round(close_pos, 3),
                "obv": round(float(row["obv"]), 2),
            },
        )


class OpenInterestPriceActionStrategy(BaseStrategy):
    code = "oi_option_chain_price_action"
    name = "Open Interest + Option Chain + Price Action"
    category = StrategyCategory.VOLUME
    module = "FNO"
    description = (
        "Reserved for the F&O module (Phase 9). Open interest, change in OI, "
        "PCR and option-chain data are not available for cash-equity "
        "instruments, and this build has no options data feed - so the "
        "strategy is registered and documented but returns no signals. It is "
        "not a stub standing in for a working equity strategy."
    )
    default_parameters = {
        "oi_change_threshold_pct": 5.0,
        "pcr_bullish_below": 0.8,
        "pcr_bearish_above": 1.2,
    }
    supported_timeframes = ["5m", "15m"]
    min_bars = 50

    #: Why this strategy cannot produce signals yet - surfaced in the UI.
    blocked_reason = (
        "Requires an options data feed (option chain, open interest, PCR). "
        "Phase 1 covers equity only; see docs/DEVELOPMENT_ROADMAP.md Phase 9."
    )

    def evaluate(self, ctx: StrategyContext) -> SignalProposal | None:
        # Deliberately returns None. Implementing this against equity candles
        # would mean inventing open-interest data that does not exist.
        return None
