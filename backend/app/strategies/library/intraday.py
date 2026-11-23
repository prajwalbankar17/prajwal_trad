"""Category C - Intraday structure strategies.

Everything here depends on session boundaries, so these are intraday
timeframes only. The underlying level functions are in
`app.strategies.indicators.levels` and are all built from strictly prior
sessions.
"""

from __future__ import annotations

import pandas as pd

from app.core.enums import Direction, StrategyCategory
from app.strategies.base import BaseStrategy, Condition, SignalProposal, StrategyContext
from app.strategies.indicators import (
    atr,
    cpr,
    opening_range,
    previous_day_levels,
    relative_volume,
    swing_levels,
)

INTRADAY_TFS = ["1m", "3m", "5m", "10m", "15m", "30m", "1h"]


class OpeningRangeBreakoutStrategy(BaseStrategy):
    code = "orb"
    name = "Opening Range Breakout"
    category = StrategyCategory.INTRADAY
    description = (
        "Breakout of the first N minutes of the session (15 and 30 are the "
        "usual settings). Signals are suppressed while the range is still "
        "forming and after the configured cut-off, because a 2 pm 'opening "
        "range' break is a different trade entirely."
    )
    default_parameters = {
        "range_minutes": 15,
        "max_minutes_after_open": 120,
        "volume_multiple": 1.2,
        "atr_period": 14,
        "stop_mode": "range",        # range | atr
        "atr_stop_multiple": 1.5,
        "risk_reward": 2.0,
        "allow_short": True,
        "max_range_pct": 3.0,
    }
    parameter_schema = {
        "range_minutes": {"type": "enum", "options": [15, 30, 5, 60], "label": "Opening range"},
        "max_minutes_after_open": {"type": "int", "min": 15, "max": 375,
                                   "label": "Signal cut-off (min after open)"},
        "stop_mode": {"type": "enum", "options": ["range", "atr"], "label": "Stop mode"},
        "max_range_pct": {"type": "float", "min": 0.1, "max": 20,
                          "label": "Skip if range wider than %"},
    }
    supported_timeframes = ["1m", "3m", "5m", "15m"]
    default_timeframe = "5m"
    min_bars = 30

    def prepare(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        orr = opening_range(df, int(self.params["range_minutes"]))
        for col in ("or_high", "or_low", "or_range", "in_opening_range", "minutes_since_open"):
            out[col] = orr[col]
        out["atr"] = atr(df, int(self.params["atr_period"]))
        out["rel_volume"] = relative_volume(df["volume"], 20)
        return out

    def evaluate(self, ctx: StrategyContext) -> SignalProposal | None:
        df = ctx.df
        row = ctx.last
        if pd.isna(row.get("or_high")) or bool(row.get("in_opening_range")):
            return None

        cutoff = float(ctx.param("max_minutes_after_open", 120))
        if float(row["minutes_since_open"]) > cutoff:
            return None

        or_high, or_low = float(row["or_high"]), float(row["or_low"])
        range_pct = (or_high - or_low) / or_low * 100 if or_low else 0.0
        if range_pct > float(ctx.param("max_range_pct", 3.0)):
            return None

        # First break of the session only: once broken, the level is spent.
        session_rows = df[
            pd.to_datetime(df["ts"]).dt.date == pd.to_datetime(row["ts"]).date()
        ]
        earlier = session_rows.iloc[:-1]
        already_broken = bool(
            (earlier["close"] > earlier["or_high"]).any()
            or (earlier["close"] < earlier["or_low"]).any()
        )
        if already_broken:
            return None

        long_break = row["close"] > or_high
        short_break = row["close"] < or_low
        if not long_break and not (short_break and ctx.param("allow_short", True)):
            return None

        direction = Direction.BUY if long_break else Direction.SELL
        rel_vol = row.get("rel_volume")
        needed = float(ctx.param("volume_multiple", 1.2))
        volume_ok = bool(pd.notna(rel_vol) and rel_vol >= needed)

        conditions = [
            Condition("opening_range_formed", True,
                      f"OR {or_low:.2f}-{or_high:.2f} ({range_pct:.2f}% wide)"),
            Condition("first_break_of_session", True, "no earlier break of the OR today"),
            Condition("breaks_or_level", True,
                      f"close {float(row['close']):.2f} "
                      f"{'>' if long_break else '<'} OR "
                      f"{'high' if long_break else 'low'}"),
            Condition("volume_confirmation", volume_ok,
                      f"relative volume {rel_vol:.2f}x vs {needed}x"
                      if pd.notna(rel_vol) else "relative volume unavailable",
                      float(rel_vol) if pd.notna(rel_vol) else None),
        ]
        if not volume_ok:
            return None

        entry = float(row["close"])
        if str(ctx.param("stop_mode", "range")) == "range":
            stop = or_low if direction == Direction.BUY else or_high
            stop_distance = abs(entry - stop)
        else:
            stop_distance = float(row["atr"]) * float(ctx.param("atr_stop_multiple", 1.5))
        if stop_distance <= 0:
            return None

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
                f"{ctx.param('range_minutes')}-minute opening range "
                f"{'high' if long_break else 'low'} broken at "
                f"{float(row['minutes_since_open']):.0f} minutes after the open."
            ),
            confidence=0.65,
            indicator_snapshot={
                "or_high": round(or_high, 4),
                "or_low": round(or_low, 4),
                "or_range_pct": round(range_pct, 3),
            },
        )


class CprStrategy(BaseStrategy):
    code = "cpr"
    name = "Central Pivot Range"
    category = StrategyCategory.INTRADAY
    description = (
        "Uses the previous session's CPR. A narrow CPR suggests an expansion "
        "day, so breakouts above TC / below BC are taken only when the CPR "
        "width is under the configured threshold."
    )
    default_parameters = {
        "max_cpr_width_pct": 0.5,
        "atr_period": 14,
        "atr_stop_multiple": 1.2,
        "risk_reward": 2.0,
        "allow_short": True,
    }
    supported_timeframes = INTRADAY_TFS
    default_timeframe = "15m"
    min_bars = 40

    def prepare(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        levels = cpr(df)
        for col in ("pivot", "tc", "bc", "cpr_width"):
            out[col] = levels[col]
        out["atr"] = atr(df, int(self.params["atr_period"]))
        return out

    def evaluate(self, ctx: StrategyContext) -> SignalProposal | None:
        df = ctx.df
        row = ctx.last
        if len(df) < 2 or pd.isna(row.get("tc")) or pd.isna(row.get("atr")):
            return None
        prev = df.iloc[-2]

        width_pct = float(row["cpr_width"]) * 100
        narrow = width_pct <= float(ctx.param("max_cpr_width_pct", 0.5))

        breaks_up = prev["close"] <= prev["tc"] and row["close"] > row["tc"]
        breaks_down = prev["close"] >= prev["bc"] and row["close"] < row["bc"]
        if not breaks_up and not (breaks_down and ctx.param("allow_short", True)):
            return None

        direction = Direction.BUY if breaks_up else Direction.SELL
        conditions = [
            Condition("narrow_cpr", narrow,
                      f"CPR width {width_pct:.3f}% vs max "
                      f"{ctx.param('max_cpr_width_pct')}%", round(width_pct, 4)),
            Condition("breaks_cpr", True,
                      f"close crossed {'above TC' if breaks_up else 'below BC'} "
                      f"({float(row['tc'] if breaks_up else row['bc']):.2f})"),
        ]
        if not narrow:
            return None

        entry = float(row["close"])
        level = float(row["bc"] if breaks_up else row["tc"])
        stop_distance = max(
            abs(entry - level),
            float(row["atr"]) * float(ctx.param("atr_stop_multiple", 1.2)),
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
                f"Narrow CPR ({width_pct:.3f}%) broken to the "
                f"{'upside' if breaks_up else 'downside'}."
            ),
            confidence=0.62,
            indicator_snapshot={
                "pivot": round(float(row["pivot"]), 4),
                "tc": round(float(row["tc"]), 4),
                "bc": round(float(row["bc"]), 4),
                "width_pct": round(width_pct, 4),
            },
        )


class PreviousDayLevelsStrategy(BaseStrategy):
    code = "pdh_pdl"
    name = "Previous Day High / Low"
    category = StrategyCategory.INTRADAY
    description = (
        "Breaks of the previous session's high or low - among the most watched "
        "intraday levels. A buffer avoids firing on a one-tick poke."
    )
    default_parameters = {
        "buffer_pct": 0.1,
        "atr_period": 14,
        "atr_stop_multiple": 1.2,
        "risk_reward": 2.0,
        "allow_short": True,
        "max_minutes_after_open": 330,
    }
    supported_timeframes = INTRADAY_TFS
    default_timeframe = "15m"
    min_bars = 40

    def prepare(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        levels = previous_day_levels(df)
        for col in ("pdh", "pdl", "pdc"):
            out[col] = levels[col]
        out["atr"] = atr(df, int(self.params["atr_period"]))
        orr = opening_range(df, 1)
        out["minutes_since_open"] = orr["minutes_since_open"]
        return out

    def evaluate(self, ctx: StrategyContext) -> SignalProposal | None:
        df = ctx.df
        row = ctx.last
        if len(df) < 2 or pd.isna(row.get("pdh")) or pd.isna(row.get("atr")):
            return None
        if float(row["minutes_since_open"]) > float(ctx.param("max_minutes_after_open", 330)):
            return None

        prev = df.iloc[-2]
        buffer = float(ctx.param("buffer_pct", 0.1)) / 100
        pdh, pdl = float(row["pdh"]), float(row["pdl"])

        breaks_high = prev["close"] <= pdh and row["close"] > pdh * (1 + buffer)
        breaks_low = prev["close"] >= pdl and row["close"] < pdl * (1 - buffer)
        if not breaks_high and not (breaks_low and ctx.param("allow_short", True)):
            return None

        direction = Direction.BUY if breaks_high else Direction.SELL
        entry = float(row["close"])
        stop_distance = max(
            abs(entry - (pdh if breaks_high else pdl)) + float(row["atr"]) * 0.3,
            float(row["atr"]) * float(ctx.param("atr_stop_multiple", 1.2)),
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
            conditions=[
                Condition("breaks_previous_day_level", True,
                          f"close {entry:.2f} broke "
                          f"{'PDH' if breaks_high else 'PDL'} "
                          f"({pdh if breaks_high else pdl:.2f})")
            ],
            reason=f"Break of previous-day {'high' if breaks_high else 'low'}.",
            confidence=0.6,
            indicator_snapshot={"pdh": round(pdh, 4), "pdl": round(pdl, 4)},
        )


class LiquiditySweepStrategy(BaseStrategy):
    code = "liquidity_sweep"
    name = "Liquidity Sweep"
    category = StrategyCategory.INTRADAY
    description = (
        "Price takes out an obvious swing level (where stops cluster) and "
        "immediately reverses back through it. Traded in the reversal "
        "direction, with the sweep extreme as the stop."
    )
    default_parameters = {
        "swing_lookback": 5,
        "max_bars_back_inside": 2,
        "atr_period": 14,
        "risk_reward": 2.0,
        "min_sweep_atr": 0.2,
        "allow_short": True,
    }
    supported_timeframes = INTRADAY_TFS
    default_timeframe = "5m"
    min_bars = 60

    def prepare(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        swings = swing_levels(df, int(self.params["swing_lookback"]))
        out["swing_high"] = swings["swing_high"]
        out["swing_low"] = swings["swing_low"]
        out["atr"] = atr(df, int(self.params["atr_period"]))
        return out

    def evaluate(self, ctx: StrategyContext) -> SignalProposal | None:
        row = ctx.last
        if any(pd.isna(row.get(c)) for c in ("swing_high", "swing_low", "atr")):
            return None

        atr_value = float(row["atr"])
        min_sweep = atr_value * float(ctx.param("min_sweep_atr", 0.2))
        swing_high, swing_low = float(row["swing_high"]), float(row["swing_low"])

        swept_high = (
            row["high"] > swing_high + min_sweep and row["close"] < swing_high
        )
        swept_low = row["low"] < swing_low - min_sweep and row["close"] > swing_low

        # A swept high reverses into a SHORT, so that branch is the one gated
        # by allow_short; a swept low always produces a long.
        if swept_high and ctx.param("allow_short", True):
            direction = Direction.SELL
            extreme, level = float(row["high"]), swing_high
        elif swept_low:
            direction = Direction.BUY
            extreme, level = float(row["low"]), swing_low
        else:
            return None

        entry = float(row["close"])
        stop_distance = abs(entry - extreme) + atr_value * 0.15
        stop, target = self._stop_and_target(
            entry, direction, stop_distance=stop_distance, rr=float(ctx.param("risk_reward", 2.0))
        )
        return SignalProposal(
            direction=direction,
            entry_price=entry,
            stop_loss=stop,
            target=target,
            candle_ts=ctx.candle_ts,
            conditions=[
                Condition("liquidity_swept", True,
                          f"price traded through the swing "
                          f"{'high' if direction == Direction.SELL else 'low'} "
                          f"{level:.2f} to {extreme:.2f}"),
                Condition("closed_back_inside", True,
                          f"close {entry:.2f} returned past the swept level"),
            ],
            reason=(
                f"Liquidity sweep of the swing "
                f"{'high' if direction == Direction.SELL else 'low'}, then reversed."
            ),
            confidence=0.64,
            indicator_snapshot={"swept_level": round(level, 4), "extreme": round(extreme, 4)},
        )


class SmartMoneyConceptsStrategy(BaseStrategy):
    code = "smc"
    name = "Smart Money Concepts"
    category = StrategyCategory.INTRADAY
    description = (
        "Break of Structure / Change of Character with a Fair Value Gap entry. "
        "SMC terminology is widely used and loosely defined; the exact rules "
        "implemented here are documented in STRATEGY_DOCUMENTATION.md so the "
        "results can be judged against a stated definition rather than a vibe."
    )
    default_parameters = {
        "swing_lookback": 5,
        "require_fvg": True,
        "fvg_min_atr": 0.15,
        "atr_period": 14,
        "risk_reward": 2.5,
        "allow_short": True,
    }
    supported_timeframes = INTRADAY_TFS
    default_timeframe = "5m"
    min_bars = 80

    def prepare(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        swings = swing_levels(df, int(self.params["swing_lookback"]))
        out["swing_high"] = swings["swing_high"]
        out["swing_low"] = swings["swing_low"]
        out["atr"] = atr(df, int(self.params["atr_period"]))

        # Fair Value Gap: a three-bar imbalance where bar i-2 and bar i do not
        # overlap. Computed with shift(), so only completed bars are used.
        high_2 = df["high"].shift(2)
        low_2 = df["low"].shift(2)
        out["fvg_bull"] = df["low"] - high_2      # > 0 means an unfilled gap up
        out["fvg_bear"] = low_2 - df["high"]      # > 0 means an unfilled gap down

        # Break of Structure: close beyond the last confirmed swing.
        out["bos_up"] = (df["close"] > out["swing_high"]) & (
            df["close"].shift(1) <= out["swing_high"].shift(1)
        )
        out["bos_down"] = (df["close"] < out["swing_low"]) & (
            df["close"].shift(1) >= out["swing_low"].shift(1)
        )
        return out

    def evaluate(self, ctx: StrategyContext) -> SignalProposal | None:
        row = ctx.last
        if any(pd.isna(row.get(c)) for c in ("swing_high", "swing_low", "atr")):
            return None

        atr_value = float(row["atr"])
        if bool(row.get("bos_up")):
            direction = Direction.BUY
            structure_level = float(row["swing_high"])
            gap = float(row["fvg_bull"]) if pd.notna(row.get("fvg_bull")) else 0.0
        elif bool(row.get("bos_down")) and ctx.param("allow_short", True):
            direction = Direction.SELL
            structure_level = float(row["swing_low"])
            gap = float(row["fvg_bear"]) if pd.notna(row.get("fvg_bear")) else 0.0
        else:
            return None

        min_gap = atr_value * float(ctx.param("fvg_min_atr", 0.15))
        has_fvg = gap >= min_gap
        conditions = [
            Condition("break_of_structure", True,
                      f"close broke the last confirmed swing at {structure_level:.2f}",
                      round(structure_level, 4)),
            Condition("fair_value_gap", has_fvg,
                      f"three-bar imbalance {gap:.4f} vs {min_gap:.4f} required",
                      round(gap, 4)),
        ]
        if ctx.param("require_fvg", True) and not has_fvg:
            return None

        entry = float(row["close"])
        stop_distance = abs(entry - structure_level) + atr_value * 0.2
        stop, target = self._stop_and_target(
            entry, direction, stop_distance=stop_distance, rr=float(ctx.param("risk_reward", 2.5))
        )
        return SignalProposal(
            direction=direction,
            entry_price=entry,
            stop_loss=stop,
            target=target,
            candle_ts=ctx.candle_ts,
            conditions=conditions,
            reason="Break of structure with a supporting fair value gap.",
            confidence=0.6,
            indicator_snapshot={
                "structure_level": round(structure_level, 4),
                "fvg": round(gap, 4),
                "atr": round(atr_value, 4),
            },
        )
