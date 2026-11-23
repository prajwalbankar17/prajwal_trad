"""Category B - Indicator-based strategies."""

from __future__ import annotations

import pandas as pd

from app.core.enums import Direction, StrategyCategory
from app.strategies.base import BaseStrategy, Condition, SignalProposal, StrategyContext
from app.strategies.indicators import (
    atr,
    bollinger_bands,
    ema,
    macd,
    relative_volume,
    rsi,
    supertrend,
    vwap,
)
from app.strategies.indicators.trend import crossover, crossunder


class EmaCrossoverStrategy(BaseStrategy):
    code = "ema_crossover"
    name = "EMA Crossover (9/21)"
    category = StrategyCategory.INDICATOR
    description = (
        "Classic fast/slow EMA cross. Fires only on the bar the cross happens, "
        "never on every bar the fast EMA stays above the slow one."
    )
    default_parameters = {
        "fast": 9,
        "slow": 21,
        "atr_period": 14,
        "atr_stop_multiple": 1.5,
        "risk_reward": 2.0,
        "trend_filter_ema": 0,      # 0 disables the higher-period filter
        "allow_short": True,
    }
    parameter_schema = {
        "fast": {"type": "int", "min": 2, "max": 100, "label": "Fast EMA"},
        "slow": {"type": "int", "min": 3, "max": 400, "label": "Slow EMA"},
        "atr_stop_multiple": {"type": "float", "min": 0.2, "max": 5, "label": "ATR stop x"},
        "risk_reward": {"type": "float", "min": 0.5, "max": 10, "label": "Risk/reward"},
        "trend_filter_ema": {"type": "int", "min": 0, "max": 400, "label": "Trend filter EMA"},
        "allow_short": {"type": "bool", "label": "Allow short signals"},
    }
    min_bars = 80

    def prepare(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        fast, slow = int(self.params["fast"]), int(self.params["slow"])
        if fast >= slow:
            raise ValueError("fast EMA period must be smaller than slow EMA period")
        out["ema_fast"] = ema(df["close"], fast)
        out["ema_slow"] = ema(df["close"], slow)
        out["cross_up"] = crossover(out["ema_fast"], out["ema_slow"])
        out["cross_down"] = crossunder(out["ema_fast"], out["ema_slow"])
        out["atr"] = atr(df, int(self.params["atr_period"]))
        trend_period = int(self.params.get("trend_filter_ema") or 0)
        out["ema_trend"] = ema(df["close"], trend_period) if trend_period else pd.NA
        return out

    def evaluate(self, ctx: StrategyContext) -> SignalProposal | None:
        row = ctx.last
        if pd.isna(row.get("atr")) or pd.isna(row.get("ema_slow")):
            return None

        if row["cross_up"]:
            direction = Direction.BUY
        elif row["cross_down"] and ctx.param("allow_short", True):
            direction = Direction.SELL
        else:
            return None

        conditions = [
            Condition(
                "ema_cross",
                True,
                f"EMA{ctx.param('fast')} crossed "
                f"{'above' if direction == Direction.BUY else 'below'} "
                f"EMA{ctx.param('slow')}",
                round(float(row["ema_fast"]), 4),
            )
        ]

        trend_period = int(ctx.param("trend_filter_ema") or 0)
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
                Condition(
                    "trend_filter",
                    aligned,
                    f"close is {'above' if direction == Direction.BUY else 'below'} "
                    f"EMA{trend_period}",
                    round(float(trend_value), 4) if pd.notna(trend_value) else None,
                )
            )
            if not aligned:
                return None

        entry = float(row["close"])
        stop_distance = float(row["atr"]) * float(ctx.param("atr_stop_multiple", 1.5))
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
            reason=f"EMA {ctx.param('fast')}/{ctx.param('slow')} crossover ({direction}).",
            confidence=0.6,
            indicator_snapshot={
                "ema_fast": round(float(row["ema_fast"]), 4),
                "ema_slow": round(float(row["ema_slow"]), 4),
                "atr": round(float(row["atr"]), 4),
            },
        )


class SupertrendStrategy(BaseStrategy):
    code = "supertrend"
    name = "Supertrend"
    category = StrategyCategory.INDICATOR
    description = (
        "Enters on a Supertrend flip. The stop sits on the Supertrend line "
        "itself, which is what makes the indicator useful as a system rather "
        "than only a filter."
    )
    default_parameters = {
        "period": 10,
        "multiplier": 3.0,
        "risk_reward": 2.0,
        "allow_short": True,
        "min_stop_pct": 0.2,
    }
    parameter_schema = {
        "period": {"type": "int", "min": 2, "max": 100, "label": "ATR period"},
        "multiplier": {"type": "float", "min": 0.5, "max": 10, "label": "Multiplier"},
        "risk_reward": {"type": "float", "min": 0.5, "max": 10, "label": "Risk/reward"},
    }
    min_bars = 60

    def prepare(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        st = supertrend(df, int(self.params["period"]), float(self.params["multiplier"]))
        out["supertrend"] = st["supertrend"]
        out["st_trend"] = st["trend"]
        out["st_flip"] = st["trend"] != st["trend"].shift(1)
        return out

    def evaluate(self, ctx: StrategyContext) -> SignalProposal | None:
        df = ctx.df
        row = ctx.last
        if pd.isna(row.get("st_trend")) or len(df) < 2:
            return None
        if pd.isna(df["st_trend"].iloc[-2]) or not row["st_flip"]:
            return None

        direction = Direction.BUY if row["st_trend"] == 1 else Direction.SELL
        if direction == Direction.SELL and not ctx.param("allow_short", True):
            return None

        entry = float(row["close"])
        line = float(row["supertrend"])
        min_stop = entry * float(ctx.param("min_stop_pct", 0.2)) / 100
        stop_distance = max(abs(entry - line), min_stop)
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
                Condition("supertrend_flip", True,
                          f"Supertrend flipped to {'up' if direction == Direction.BUY else 'down'}",
                          round(line, 4))
            ],
            reason=(
                f"Supertrend({ctx.param('period')},{ctx.param('multiplier')}) "
                f"flip to {direction}."
            ),
            confidence=0.63,
            indicator_snapshot={"supertrend": round(line, 4), "trend": int(row["st_trend"])},
        )


class VwapStrategy(BaseStrategy):
    code = "vwap"
    name = "VWAP Reclaim / Rejection"
    category = StrategyCategory.INDICATOR
    description = (
        "Trades the session VWAP as a decision line: a reclaim from below is a "
        "long, a rejection from above is a short. Intraday only - VWAP resets "
        "every session and is meaningless on daily candles."
    )
    default_parameters = {
        "atr_period": 14,
        "atr_stop_multiple": 1.2,
        "risk_reward": 2.0,
        "min_distance_pct": 0.05,
        "require_volume": True,
        "volume_multiple": 1.2,
        "allow_short": True,
    }
    supported_timeframes = ["1m", "3m", "5m", "10m", "15m", "30m"]
    min_bars = 40

    def prepare(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        out["vwap"] = vwap(df)
        out["atr"] = atr(df, int(self.params["atr_period"]))
        out["rel_volume"] = relative_volume(df["volume"], 20)
        return out

    def evaluate(self, ctx: StrategyContext) -> SignalProposal | None:
        df = ctx.df
        row = ctx.last
        if len(df) < 2 or pd.isna(row.get("vwap")) or pd.isna(row.get("atr")):
            return None
        prev = df.iloc[-2]
        if pd.isna(prev.get("vwap")):
            return None

        min_dist = float(ctx.param("min_distance_pct", 0.05)) / 100 * float(row["vwap"])
        reclaim = prev["close"] < prev["vwap"] and row["close"] > row["vwap"] + min_dist
        reject = prev["close"] > prev["vwap"] and row["close"] < row["vwap"] - min_dist

        if reclaim:
            direction = Direction.BUY
        elif reject and ctx.param("allow_short", True):
            direction = Direction.SELL
        else:
            return None

        conditions = [
            Condition("vwap_cross", True,
                      f"close crossed {'above' if reclaim else 'below'} VWAP "
                      f"({float(row['vwap']):.2f})", round(float(row["vwap"]), 4))
        ]
        if ctx.param("require_volume", True):
            rel = row.get("rel_volume")
            needed = float(ctx.param("volume_multiple", 1.2))
            passed = bool(pd.notna(rel) and rel >= needed)
            conditions.append(
                Condition("volume_confirmation", passed,
                          f"relative volume {rel:.2f}x vs {needed}x required"
                          if pd.notna(rel) else "relative volume unavailable",
                          float(rel) if pd.notna(rel) else None)
            )
            if not passed:
                return None

        entry = float(row["close"])
        stop_distance = max(
            abs(entry - float(row["vwap"])),
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
            reason=f"VWAP {'reclaim' if reclaim else 'rejection'} at {float(row['vwap']):.2f}.",
            confidence=0.6,
            indicator_snapshot={"vwap": round(float(row["vwap"]), 4)},
        )


class RsiReversalStrategy(BaseStrategy):
    code = "rsi_reversal"
    name = "RSI Reversal"
    category = StrategyCategory.INDICATOR
    description = (
        "Enters as RSI exits oversold/overbought, not while it sits there. "
        "Buying at RSI < 30 and holding is how mean-reversion systems bleed in "
        "a trend; requiring the cross back out is the whole discipline."
    )
    default_parameters = {
        "period": 14,
        "oversold": 30,
        "overbought": 70,
        "atr_period": 14,
        "atr_stop_multiple": 1.5,
        "risk_reward": 2.0,
        "allow_short": True,
    }
    min_bars = 60

    def prepare(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        out["rsi"] = rsi(df["close"], int(self.params["period"]))
        out["atr"] = atr(df, int(self.params["atr_period"]))
        return out

    def evaluate(self, ctx: StrategyContext) -> SignalProposal | None:
        df = ctx.df
        row = ctx.last
        if len(df) < 2 or pd.isna(row.get("rsi")) or pd.isna(row.get("atr")):
            return None
        prev_rsi = df["rsi"].iloc[-2]
        if pd.isna(prev_rsi):
            return None

        os_level = float(ctx.param("oversold", 30))
        ob_level = float(ctx.param("overbought", 70))

        exits_oversold = prev_rsi <= os_level and row["rsi"] > os_level
        exits_overbought = prev_rsi >= ob_level and row["rsi"] < ob_level

        if exits_oversold:
            direction = Direction.BUY
        elif exits_overbought and ctx.param("allow_short", True):
            direction = Direction.SELL
        else:
            return None

        entry = float(row["close"])
        stop_distance = float(row["atr"]) * float(ctx.param("atr_stop_multiple", 1.5))
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
                Condition("rsi_exits_zone", True,
                          f"RSI moved from {prev_rsi:.1f} to {float(row['rsi']):.1f}, "
                          f"leaving the {'oversold' if exits_oversold else 'overbought'} zone",
                          round(float(row["rsi"]), 2))
            ],
            reason=f"RSI reversal out of {'oversold' if exits_oversold else 'overbought'}.",
            confidence=0.57,
            indicator_snapshot={"rsi": round(float(row["rsi"]), 2)},
        )


class MacdCrossoverStrategy(BaseStrategy):
    code = "macd_crossover"
    name = "MACD Crossover"
    category = StrategyCategory.INDICATOR
    description = (
        "MACD line crossing its signal line. An optional zero-line filter keeps "
        "longs to positive-momentum regimes only."
    )
    default_parameters = {
        "fast": 12,
        "slow": 26,
        "signal": 9,
        "require_zero_line": False,
        "atr_period": 14,
        "atr_stop_multiple": 1.5,
        "risk_reward": 2.0,
        "allow_short": True,
    }
    min_bars = 100

    def prepare(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        m = macd(
            df["close"],
            int(self.params["fast"]),
            int(self.params["slow"]),
            int(self.params["signal"]),
        )
        out["macd"] = m["macd"]
        out["macd_signal"] = m["signal"]
        out["macd_hist"] = m["histogram"]
        out["cross_up"] = crossover(out["macd"], out["macd_signal"])
        out["cross_down"] = crossunder(out["macd"], out["macd_signal"])
        out["atr"] = atr(df, int(self.params["atr_period"]))
        return out

    def evaluate(self, ctx: StrategyContext) -> SignalProposal | None:
        row = ctx.last
        if pd.isna(row.get("macd")) or pd.isna(row.get("atr")):
            return None

        if row["cross_up"]:
            direction = Direction.BUY
        elif row["cross_down"] and ctx.param("allow_short", True):
            direction = Direction.SELL
        else:
            return None

        conditions = [
            Condition("macd_cross", True,
                      f"MACD {float(row['macd']):.4f} crossed "
                      f"{'above' if direction == Direction.BUY else 'below'} signal "
                      f"{float(row['macd_signal']):.4f}", round(float(row["macd"]), 6))
        ]
        if ctx.param("require_zero_line", False):
            ok = bool(row["macd"] > 0 if direction == Direction.BUY else row["macd"] < 0)
            conditions.append(
                Condition("zero_line_filter", ok,
                          f"MACD is {'above' if row['macd'] > 0 else 'below'} zero")
            )
            if not ok:
                return None

        entry = float(row["close"])
        stop_distance = float(row["atr"]) * float(ctx.param("atr_stop_multiple", 1.5))
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
            reason=f"MACD signal-line crossover ({direction}).",
            confidence=0.58,
            indicator_snapshot={
                "macd": round(float(row["macd"]), 6),
                "signal": round(float(row["macd_signal"]), 6),
                "histogram": round(float(row["macd_hist"]), 6),
            },
        )


class BollingerBandsStrategy(BaseStrategy):
    code = "bollinger_bands"
    name = "Bollinger Bands"
    category = StrategyCategory.INDICATOR
    description = (
        "Two opposite behaviours under one roof: 'reversion' fades a close back "
        "inside the bands, 'breakout' buys a close outside them. They are "
        "mutually exclusive, so the mode is an explicit parameter rather than "
        "something the code guesses."
    )
    default_parameters = {
        "period": 20,
        "std_dev": 2.0,
        "mode": "reversion",          # reversion | breakout
        "atr_period": 14,
        "risk_reward": 2.0,
        "allow_short": True,
    }
    parameter_schema = {
        "period": {"type": "int", "min": 5, "max": 100, "label": "Period"},
        "std_dev": {"type": "float", "min": 0.5, "max": 5, "label": "Std deviations"},
        "mode": {"type": "enum", "options": ["reversion", "breakout"], "label": "Mode"},
    }
    min_bars = 60

    def prepare(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        bb = bollinger_bands(
            df["close"], int(self.params["period"]), float(self.params["std_dev"])
        )
        out["bb_upper"] = bb["upper"]
        out["bb_lower"] = bb["lower"]
        out["bb_middle"] = bb["middle"]
        out["atr"] = atr(df, int(self.params["atr_period"]))
        return out

    def evaluate(self, ctx: StrategyContext) -> SignalProposal | None:
        df = ctx.df
        row = ctx.last
        if len(df) < 2 or pd.isna(row.get("bb_upper")) or pd.isna(row.get("atr")):
            return None
        prev = df.iloc[-2]
        if pd.isna(prev.get("bb_upper")):
            return None

        mode = str(ctx.param("mode", "reversion"))
        if mode == "reversion":
            long_signal = prev["close"] < prev["bb_lower"] and row["close"] > row["bb_lower"]
            short_signal = prev["close"] > prev["bb_upper"] and row["close"] < row["bb_upper"]
        else:
            long_signal = prev["close"] <= prev["bb_upper"] and row["close"] > row["bb_upper"]
            short_signal = prev["close"] >= prev["bb_lower"] and row["close"] < row["bb_lower"]

        if long_signal:
            direction = Direction.BUY
        elif short_signal and ctx.param("allow_short", True):
            direction = Direction.SELL
        else:
            return None

        entry = float(row["close"])
        middle = float(row["bb_middle"])
        if mode == "reversion":
            band = float(row["bb_lower"] if direction == Direction.BUY else row["bb_upper"])
            stop_distance = abs(entry - band) + float(row["atr"]) * 0.3
            target = middle
            stop = entry - stop_distance if direction == Direction.BUY else entry + stop_distance
            # A reversion target at the mid-band can sit the wrong side of entry
            # on a wide bar; fall back to a ratio target when it does.
            if (direction == Direction.BUY and target <= entry) or (
                direction == Direction.SELL and target >= entry
            ):
                stop, target = self._stop_and_target(
                    entry, direction, stop_distance=stop_distance,
                    rr=float(ctx.param("risk_reward", 2.0)),
                )
        else:
            stop_distance = abs(entry - middle)
            stop, target = self._stop_and_target(
                entry, direction, stop_distance=stop_distance,
                rr=float(ctx.param("risk_reward", 2.0)),
            )

        return SignalProposal(
            direction=direction,
            entry_price=entry,
            stop_loss=stop,
            target=target,
            candle_ts=ctx.candle_ts,
            conditions=[
                Condition(f"bollinger_{mode}", True,
                          f"{mode} signal at band "
                          f"{float(row['bb_lower']):.2f}/{float(row['bb_upper']):.2f}")
            ],
            reason=f"Bollinger {mode} signal ({direction}).",
            confidence=0.55,
            indicator_snapshot={
                "upper": round(float(row["bb_upper"]), 4),
                "middle": round(middle, 4),
                "lower": round(float(row["bb_lower"]), 4),
            },
        )


class EmaVwapComboStrategy(BaseStrategy):
    code = "ema_vwap_combo"
    name = "EMA + VWAP Combination"
    category = StrategyCategory.INDICATOR
    description = (
        "A single strategy that needs trend (EMA stack) and institutional "
        "reference (side of VWAP) to agree before it acts. Distinct from the "
        "combination engine: this is one strategy with two conditions."
    )
    default_parameters = {
        "fast": 9,
        "slow": 21,
        "atr_period": 14,
        "atr_stop_multiple": 1.5,
        "risk_reward": 2.0,
        "allow_short": True,
    }
    supported_timeframes = ["1m", "3m", "5m", "10m", "15m", "30m"]
    min_bars = 60

    def prepare(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        out["ema_fast"] = ema(df["close"], int(self.params["fast"]))
        out["ema_slow"] = ema(df["close"], int(self.params["slow"]))
        out["cross_up"] = crossover(out["ema_fast"], out["ema_slow"])
        out["cross_down"] = crossunder(out["ema_fast"], out["ema_slow"])
        out["vwap"] = vwap(df)
        out["atr"] = atr(df, int(self.params["atr_period"]))
        return out

    def evaluate(self, ctx: StrategyContext) -> SignalProposal | None:
        row = ctx.last
        if any(pd.isna(row.get(c)) for c in ("ema_slow", "vwap", "atr")):
            return None

        if row["cross_up"]:
            direction = Direction.BUY
        elif row["cross_down"] and ctx.param("allow_short", True):
            direction = Direction.SELL
        else:
            return None

        vwap_aligned = bool(
            row["close"] > row["vwap"]
            if direction == Direction.BUY
            else row["close"] < row["vwap"]
        )
        conditions = [
            Condition("ema_cross", True, f"EMA cross ({direction})"),
            Condition("vwap_alignment", vwap_aligned,
                      f"close {float(row['close']):.2f} is "
                      f"{'above' if row['close'] > row['vwap'] else 'below'} "
                      f"VWAP {float(row['vwap']):.2f}"),
        ]
        if not vwap_aligned:
            return None

        entry = float(row["close"])
        stop_distance = float(row["atr"]) * float(ctx.param("atr_stop_multiple", 1.5))
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
            reason="EMA crossover confirmed by the VWAP side.",
            confidence=0.68,
            indicator_snapshot={
                "ema_fast": round(float(row["ema_fast"]), 4),
                "ema_slow": round(float(row["ema_slow"]), 4),
                "vwap": round(float(row["vwap"]), 4),
            },
        )


class RsiMacdComboStrategy(BaseStrategy):
    code = "rsi_macd_combo"
    name = "RSI + MACD Combination"
    category = StrategyCategory.INDICATOR
    description = (
        "MACD provides the trigger, RSI the regime check: a long needs MACD to "
        "cross up while RSI is constructive but not already overbought."
    )
    default_parameters = {
        "rsi_period": 14,
        "rsi_long_min": 45,
        "rsi_long_max": 70,
        "rsi_short_max": 55,
        "rsi_short_min": 30,
        "macd_fast": 12,
        "macd_slow": 26,
        "macd_signal": 9,
        "atr_period": 14,
        "atr_stop_multiple": 1.5,
        "risk_reward": 2.0,
        "allow_short": True,
    }
    min_bars = 100

    def prepare(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        m = macd(
            df["close"],
            int(self.params["macd_fast"]),
            int(self.params["macd_slow"]),
            int(self.params["macd_signal"]),
        )
        out["macd"] = m["macd"]
        out["macd_signal_line"] = m["signal"]
        out["cross_up"] = crossover(out["macd"], out["macd_signal_line"])
        out["cross_down"] = crossunder(out["macd"], out["macd_signal_line"])
        out["rsi"] = rsi(df["close"], int(self.params["rsi_period"]))
        out["atr"] = atr(df, int(self.params["atr_period"]))
        return out

    def evaluate(self, ctx: StrategyContext) -> SignalProposal | None:
        row = ctx.last
        if any(pd.isna(row.get(c)) for c in ("macd", "rsi", "atr")):
            return None

        rsi_value = float(row["rsi"])
        if row["cross_up"]:
            direction = Direction.BUY
            in_band = (
                float(ctx.param("rsi_long_min", 45))
                <= rsi_value
                <= float(ctx.param("rsi_long_max", 70))
            )
        elif row["cross_down"] and ctx.param("allow_short", True):
            direction = Direction.SELL
            in_band = (
                float(ctx.param("rsi_short_min", 30))
                <= rsi_value
                <= float(ctx.param("rsi_short_max", 55))
            )
        else:
            return None

        conditions = [
            Condition("macd_cross", True, f"MACD crossover ({direction})"),
            Condition("rsi_in_band", in_band,
                      f"RSI {rsi_value:.1f} inside the band required for a {direction}",
                      round(rsi_value, 2)),
        ]
        if not in_band:
            return None

        entry = float(row["close"])
        stop_distance = float(row["atr"]) * float(ctx.param("atr_stop_multiple", 1.5))
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
            reason="MACD crossover with RSI in a supportive band.",
            confidence=0.66,
            indicator_snapshot={
                "rsi": round(rsi_value, 2),
                "macd": round(float(row["macd"]), 6),
            },
        )
