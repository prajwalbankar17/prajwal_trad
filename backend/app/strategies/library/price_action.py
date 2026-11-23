"""Category A - Price action strategies.

Research candidates. None of these is assumed profitable; each must earn its
place through backtesting and paper trading.
"""

from __future__ import annotations

import pandas as pd

from app.core.enums import Direction, StrategyCategory
from app.strategies.base import BaseStrategy, Condition, SignalProposal, StrategyContext
from app.strategies.indicators import atr, ema, relative_volume, swing_levels


class BreakoutStrategy(BaseStrategy):
    code = "breakout"
    name = "Breakout"
    category = StrategyCategory.PRICE_ACTION
    description = (
        "Enters when price closes beyond the highest high (or lowest low) of the "
        "lookback window, with a volume expansion filter. The window excludes the "
        "current bar, so the level being broken is one that existed before the break."
    )
    default_parameters = {
        "lookback": 20,
        "volume_multiple": 1.5,
        "atr_period": 14,
        "atr_stop_multiple": 1.5,
        "risk_reward": 2.0,
        "min_breakout_pct": 0.1,
        "allow_short": True,
    }
    parameter_schema = {
        "lookback": {"type": "int", "min": 5, "max": 200, "label": "Lookback bars"},
        "volume_multiple": {"type": "float", "min": 0.5, "max": 10, "label": "Volume multiple"},
        "atr_period": {"type": "int", "min": 5, "max": 50, "label": "ATR period"},
        "atr_stop_multiple": {"type": "float", "min": 0.2, "max": 5, "label": "ATR stop x"},
        "risk_reward": {"type": "float", "min": 0.5, "max": 10, "label": "Risk/reward"},
        "min_breakout_pct": {"type": "float", "min": 0, "max": 5, "label": "Min breakout %"},
        "allow_short": {"type": "bool", "label": "Allow short signals"},
    }
    min_bars = 60

    def prepare(self, df: pd.DataFrame) -> pd.DataFrame:
        lookback = int(self.params["lookback"])
        out = df.copy()
        # shift(1): the level must be formed by *prior* bars only.
        out["range_high"] = df["high"].shift(1).rolling(lookback, min_periods=lookback).max()
        out["range_low"] = df["low"].shift(1).rolling(lookback, min_periods=lookback).min()
        out["atr"] = atr(df, int(self.params["atr_period"]))
        out["rel_volume"] = relative_volume(df["volume"], 20)
        return out

    def evaluate(self, ctx: StrategyContext) -> SignalProposal | None:
        row = ctx.last
        if pd.isna(row.get("range_high")) or pd.isna(row.get("atr")):
            return None

        min_pct = float(ctx.param("min_breakout_pct", 0.1)) / 100
        vol_multiple = float(ctx.param("volume_multiple", 1.5))
        rel_vol = row.get("rel_volume")

        long_break = row["close"] > row["range_high"] * (1 + min_pct)
        short_break = row["close"] < row["range_low"] * (1 - min_pct)

        if not long_break and not (short_break and ctx.param("allow_short", True)):
            return None

        direction = Direction.BUY if long_break else Direction.SELL
        level = row["range_high"] if long_break else row["range_low"]

        conditions = [
            Condition(
                "price_breaks_level",
                True,
                f"close {row['close']:.2f} {'>' if long_break else '<'} "
                f"{'high' if long_break else 'low'} of last "
                f"{ctx.param('lookback')} bars ({level:.2f})",
                float(level),
            ),
            Condition(
                "volume_expansion",
                bool(pd.notna(rel_vol) and rel_vol >= vol_multiple),
                f"relative volume {rel_vol:.2f}x vs required {vol_multiple}x"
                if pd.notna(rel_vol)
                else "relative volume unavailable",
                float(rel_vol) if pd.notna(rel_vol) else None,
            ),
        ]
        if not self._ok(conditions):
            return None

        stop_distance = float(row["atr"]) * float(ctx.param("atr_stop_multiple", 1.5))
        entry = float(row["close"])
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
                f"{direction} breakout of the {ctx.param('lookback')}-bar "
                f"{'high' if long_break else 'low'} at {level:.2f} on "
                f"{rel_vol:.2f}x average volume."
            ),
            confidence=min(0.9, 0.5 + 0.1 * float(rel_vol)),
            indicator_snapshot={
                "range_high": round(float(row["range_high"]), 4),
                "range_low": round(float(row["range_low"]), 4),
                "atr": round(float(row["atr"]), 4),
                "rel_volume": round(float(rel_vol), 3),
            },
        )


class BreakoutRetestStrategy(BaseStrategy):
    code = "breakout_retest"
    name = "Breakout Retest"
    category = StrategyCategory.PRICE_ACTION
    description = (
        "Waits for a breakout, then for price to return to the broken level and "
        "hold it. Fewer signals than a raw breakout and a tighter stop, at the "
        "cost of missing breaks that never come back."
    )
    default_parameters = {
        "lookback": 20,
        "retest_window": 10,
        "retest_tolerance_pct": 0.3,
        "atr_period": 14,
        "atr_stop_multiple": 1.0,
        "risk_reward": 2.0,
        "allow_short": True,
    }
    min_bars = 80

    def prepare(self, df: pd.DataFrame) -> pd.DataFrame:
        lookback = int(self.params["lookback"])
        out = df.copy()
        out["range_high"] = df["high"].shift(1).rolling(lookback, min_periods=lookback).max()
        out["range_low"] = df["low"].shift(1).rolling(lookback, min_periods=lookback).min()
        out["atr"] = atr(df, int(self.params["atr_period"]))
        out["broke_up"] = df["close"] > out["range_high"]
        out["broke_down"] = df["close"] < out["range_low"]
        return out

    def evaluate(self, ctx: StrategyContext) -> SignalProposal | None:
        df = ctx.df
        row = ctx.last
        window = int(ctx.param("retest_window", 10))
        tol = float(ctx.param("retest_tolerance_pct", 0.3)) / 100

        if len(df) < window + 2 or pd.isna(row.get("atr")):
            return None

        recent = df.iloc[-(window + 1) : -1]
        broke_up = bool(recent["broke_up"].any())
        broke_down = bool(recent["broke_down"].any())
        if not broke_up and not broke_down:
            return None

        if broke_up:
            level = float(recent.loc[recent["broke_up"], "range_high"].iloc[-1])
            touched = bool((df["low"].iloc[-2:] <= level * (1 + tol)).any())
            holding = bool(row["close"] > level)
            direction = Direction.BUY
        else:
            level = float(recent.loc[recent["broke_down"], "range_low"].iloc[-1])
            touched = bool((df["high"].iloc[-2:] >= level * (1 - tol)).any())
            holding = bool(row["close"] < level)
            direction = Direction.SELL

        if direction == Direction.SELL and not ctx.param("allow_short", True):
            return None

        conditions = [
            Condition("prior_breakout", True, f"level {level:.2f} broken within {window} bars",
                      level),
            Condition("retested_level", touched,
                      f"price returned to within {tol * 100:.2f}% of {level:.2f}"),
            Condition("level_held", holding,
                      f"close {row['close']:.2f} is back on the breakout side of {level:.2f}"),
        ]
        if not self._ok(conditions):
            return None

        entry = float(row["close"])
        stop_distance = max(
            abs(entry - level) + float(row["atr"]) * 0.25,
            float(row["atr"]) * float(ctx.param("atr_stop_multiple", 1.0)),
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
            reason=f"{direction} on successful retest of the broken level {level:.2f}.",
            confidence=0.65,
            indicator_snapshot={"level": round(level, 4), "atr": round(float(row["atr"]), 4)},
        )


class FalseBreakoutStrategy(BaseStrategy):
    code = "false_breakout"
    name = "False Breakout (Reversal)"
    category = StrategyCategory.PRICE_ACTION
    description = (
        "Fades a failed break: price pushes beyond the range, then closes back "
        "inside it. Trades against the breakout crowd; expect a lower win rate "
        "with larger winners when the reversal runs."
    )
    default_parameters = {
        "lookback": 20,
        "atr_period": 14,
        "atr_stop_multiple": 1.0,
        "risk_reward": 2.0,
        "min_penetration_pct": 0.1,
    }
    min_bars = 60

    def prepare(self, df: pd.DataFrame) -> pd.DataFrame:
        lookback = int(self.params["lookback"])
        out = df.copy()
        out["range_high"] = df["high"].shift(1).rolling(lookback, min_periods=lookback).max()
        out["range_low"] = df["low"].shift(1).rolling(lookback, min_periods=lookback).min()
        out["atr"] = atr(df, int(self.params["atr_period"]))
        return out

    def evaluate(self, ctx: StrategyContext) -> SignalProposal | None:
        row = ctx.last
        if pd.isna(row.get("range_high")) or pd.isna(row.get("atr")):
            return None

        pen = float(ctx.param("min_penetration_pct", 0.1)) / 100
        high_break_failed = (
            row["high"] > row["range_high"] * (1 + pen) and row["close"] < row["range_high"]
        )
        low_break_failed = (
            row["low"] < row["range_low"] * (1 - pen) and row["close"] > row["range_low"]
        )
        if not high_break_failed and not low_break_failed:
            return None

        direction = Direction.SELL if high_break_failed else Direction.BUY
        level = float(row["range_high"] if high_break_failed else row["range_low"])
        extreme = float(row["high"] if high_break_failed else row["low"])

        conditions = [
            Condition("penetrated_level", True,
                      f"bar traded through {level:.2f} to {extreme:.2f}", extreme),
            Condition("closed_back_inside", True,
                      f"close {row['close']:.2f} returned inside the range", float(row["close"])),
        ]
        entry = float(row["close"])
        stop_distance = abs(entry - extreme) + float(row["atr"]) * 0.2
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
            reason=f"Failed break of {level:.2f}; closed back inside the range.",
            confidence=0.6,
            indicator_snapshot={"level": round(level, 4), "extreme": round(extreme, 4)},
        )


class CandlestickReversalStrategy(BaseStrategy):
    code = "candlestick_reversal"
    name = "Candlestick Reversal"
    category = StrategyCategory.PRICE_ACTION
    description = (
        "Engulfing bars, hammers and shooting stars taken only in the direction "
        "that opposes a short-term extreme - a hammer in the middle of a range "
        "is noise, so location is part of the condition set."
    )
    default_parameters = {
        "extreme_lookback": 10,
        "body_ratio": 0.5,
        "wick_ratio": 2.0,
        "atr_period": 14,
        "risk_reward": 2.0,
    }
    min_bars = 40

    def prepare(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        out["atr"] = atr(df, int(self.params["atr_period"]))
        lookback = int(self.params["extreme_lookback"])
        out["recent_low"] = df["low"].shift(1).rolling(lookback, min_periods=lookback).min()
        out["recent_high"] = df["high"].shift(1).rolling(lookback, min_periods=lookback).max()
        return out

    @staticmethod
    def _anatomy(row: pd.Series) -> dict:
        body = abs(row["close"] - row["open"])
        total = row["high"] - row["low"]
        upper = row["high"] - max(row["close"], row["open"])
        lower = min(row["close"], row["open"]) - row["low"]
        return {"body": body, "total": total, "upper": upper, "lower": lower}

    def evaluate(self, ctx: StrategyContext) -> SignalProposal | None:
        df = ctx.df
        if len(df) < 3:
            return None
        row, prev = df.iloc[-1], df.iloc[-2]
        if pd.isna(row.get("atr")) or pd.isna(row.get("recent_low")):
            return None

        a = self._anatomy(row)
        if a["total"] <= 0:
            return None

        wick_ratio = float(ctx.param("wick_ratio", 2.0))
        at_low = row["low"] <= row["recent_low"]
        at_high = row["high"] >= row["recent_high"]

        bullish_engulf = (
            row["close"] > row["open"]
            and prev["close"] < prev["open"]
            and row["close"] >= prev["open"]
            and row["open"] <= prev["close"]
        )
        bearish_engulf = (
            row["close"] < row["open"]
            and prev["close"] > prev["open"]
            and row["close"] <= prev["open"]
            and row["open"] >= prev["close"]
        )
        hammer = a["lower"] >= wick_ratio * a["body"] and a["upper"] <= a["body"]
        shooting_star = a["upper"] >= wick_ratio * a["body"] and a["lower"] <= a["body"]

        bullish = (bullish_engulf or hammer) and at_low
        bearish = (bearish_engulf or shooting_star) and at_high
        if not bullish and not bearish:
            return None

        direction = Direction.BUY if bullish else Direction.SELL
        pattern = (
            "bullish engulfing" if bullish_engulf and bullish
            else "hammer" if bullish
            else "bearish engulfing" if bearish_engulf
            else "shooting star"
        )
        conditions = [
            Condition("reversal_pattern", True, f"{pattern} detected", pattern),
            Condition(
                "at_short_term_extreme",
                True,
                "pattern formed at the "
                f"{'low' if bullish else 'high'} of the last "
                f"{ctx.param('extreme_lookback')} bars",
            ),
        ]
        entry = float(row["close"])
        stop_distance = (
            abs(entry - float(row["low"])) if bullish else abs(float(row["high"]) - entry)
        ) + float(row["atr"]) * 0.2
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
            reason=f"{pattern.title()} at a short-term {'low' if bullish else 'high'}.",
            confidence=0.58,
            indicator_snapshot={"pattern": pattern, "atr": round(float(row["atr"]), 4)},
        )


class TrendFollowingStrategy(BaseStrategy):
    code = "trend_following"
    name = "Trend Following (Pullback)"
    category = StrategyCategory.PRICE_ACTION
    description = (
        "Buys pullbacks to a fast EMA inside an established up-trend (and the "
        "mirror image for shorts). Structure is judged by EMA stack plus higher "
        "swing lows rather than by a single moving average."
    )
    default_parameters = {
        "fast_ema": 20,
        "slow_ema": 50,
        "pullback_atr": 0.5,
        "atr_period": 14,
        "atr_stop_multiple": 1.5,
        "risk_reward": 2.0,
        "allow_short": True,
    }
    min_bars = 120

    def prepare(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        out["ema_fast"] = ema(df["close"], int(self.params["fast_ema"]))
        out["ema_slow"] = ema(df["close"], int(self.params["slow_ema"]))
        out["atr"] = atr(df, int(self.params["atr_period"]))
        swings = swing_levels(df, 5)
        out["swing_low"] = swings["swing_low"]
        out["swing_high"] = swings["swing_high"]
        return out

    def evaluate(self, ctx: StrategyContext) -> SignalProposal | None:
        row = ctx.last
        if any(pd.isna(row.get(c)) for c in ("ema_fast", "ema_slow", "atr")):
            return None

        atr_value = float(row["atr"])
        pullback = float(ctx.param("pullback_atr", 0.5)) * atr_value

        uptrend = row["ema_fast"] > row["ema_slow"] and row["close"] > row["ema_slow"]
        downtrend = row["ema_fast"] < row["ema_slow"] and row["close"] < row["ema_slow"]
        near_fast = abs(float(row["close"]) - float(row["ema_fast"])) <= pullback

        if uptrend:
            direction = Direction.BUY
        elif downtrend and ctx.param("allow_short", True):
            direction = Direction.SELL
        else:
            return None

        conditions = [
            Condition("trend_structure", True,
                      f"EMA{ctx.param('fast_ema')} {'above' if uptrend else 'below'} "
                      f"EMA{ctx.param('slow_ema')}"),
            Condition("pullback_to_ema", near_fast,
                      f"close within {pullback:.2f} of the fast EMA "
                      f"({float(row['ema_fast']):.2f})"),
        ]
        if not self._ok(conditions):
            return None

        entry = float(row["close"])
        stop_distance = atr_value * float(ctx.param("atr_stop_multiple", 1.5))
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
            reason=f"Pullback entry inside an established {'up' if uptrend else 'down'}-trend.",
            confidence=0.62,
            indicator_snapshot={
                "ema_fast": round(float(row["ema_fast"]), 4),
                "ema_slow": round(float(row["ema_slow"]), 4),
                "atr": round(atr_value, 4),
            },
        )
