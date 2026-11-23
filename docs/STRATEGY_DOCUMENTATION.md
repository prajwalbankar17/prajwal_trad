# Strategy Documentation

20 strategies in 4 categories. **None is known to be profitable.** They are
research candidates; the platform exists to find out honestly.

Every strategy:
- receives only completed candles and evaluates the last row,
- returns a `SignalProposal` or `None` — never an order,
- reports every condition it checked, passed or failed,
- never sizes a position or consults risk.

`test_evaluate_only_reads_rows_up_to_the_last` asserts for all 20 that
appending future bars does not change today's decision.

---

## Category A — Price action

### 1. `breakout`
Close beyond the highest high (or lowest low) of the last *N* bars, with a
volume-expansion filter. The range **excludes the current bar** (`shift(1)`), so
the level being broken existed before the break.

Conditions: `price_breaks_level`, `volume_expansion`.
Stop: ATR × multiplier. Target: stop distance × risk/reward.
Parameters: `lookback` 20, `volume_multiple` 1.5, `atr_stop_multiple` 1.5,
`risk_reward` 2.0, `min_breakout_pct` 0.1.

### 2. `breakout_retest`
Waits for a breakout within `retest_window` bars, then for price to return to
within `retest_tolerance_pct` of the broken level and close back on the
breakout side. Fewer signals and a tighter stop than a raw breakout, at the
cost of missing breaks that never come back.

Conditions: `prior_breakout`, `retested_level`, `level_held`.

### 3. `false_breakout`
Fades a failed break: the bar trades through the level by at least
`min_penetration_pct` but closes back inside the range. Stop goes beyond the
failed extreme. Expect a lower win rate with larger winners.

### 4. `candlestick_reversal`
Engulfing bars, hammers and shooting stars — but only at a short-term extreme.
A hammer mid-range is noise, so **location is part of the condition set**.

Parameters: `extreme_lookback` 10, `wick_ratio` 2.0.

### 5. `trend_following`
Pullback to the fast EMA inside an established trend (EMA stack plus price on
the correct side of the slow EMA). Entry when price is within
`pullback_atr` × ATR of the fast EMA.

---

## Category B — Indicator-based

### 6. `ema_crossover` (9/21)
Fires **only on the bar the cross happens**, never on every bar the fast EMA
stays above. Optional higher-period trend filter. Raises `ValueError` if
`fast >= slow` rather than silently inverting.

### 7. `supertrend` (10, 3)
Enters on a trend flip. The stop sits on the Supertrend line itself, with a
`min_stop_pct` floor so a flip at a tight band cannot produce a near-zero risk.

### 8. `vwap`
Session VWAP as a decision line: a reclaim from below is long, a rejection from
above is short, with a `min_distance_pct` buffer and optional volume
confirmation. **Intraday only** — VWAP resets each session and is meaningless
on daily candles.

### 9. `rsi_reversal` (14)
Enters as RSI *exits* oversold/overbought, not while it sits there. Buying at
RSI < 30 and holding is how mean-reversion systems bleed in a trend; requiring
the cross back out is the whole discipline.

### 10. `macd_crossover` (12, 26, 9)
MACD line crossing its signal line, with an optional zero-line regime filter.

### 11. `bollinger_bands` (20, 2)
Two opposite behaviours under one roof, so the mode is an **explicit
parameter** rather than something the code guesses:
- `reversion` — close returns inside the band; target is the mid-band.
- `breakout` — close moves outside the band.

If a reversion target lands on the wrong side of entry on a wide bar, it falls
back to a ratio target.

### 12. `ema_vwap_combo`
One strategy needing trend (EMA cross) *and* institutional reference (side of
VWAP) to agree. Distinct from the combination engine: this is a single strategy
with two conditions.

### 13. `rsi_macd_combo`
MACD provides the trigger, RSI the regime check: a long needs MACD to cross up
while RSI sits in a constructive but not overbought band (45–70 by default).

---

## Category C — Intraday

All session-aware, intraday timeframes only. Levels come from strictly prior
sessions.

### 14. `orb` — Opening Range Breakout
Breakout of the first *N* minutes (15 and 30 are the usual settings).

- Signals suppressed **while the range is still forming** — the levels do not
  exist yet.
- Suppressed after `max_minutes_after_open`; a 2 pm "opening range" break is a
  different trade.
- Only the **first break of the session** is taken.
- Skipped if the range is wider than `max_range_pct` (a gap day is not an ORB).
- Stop at the opposite side of the range, or ATR-based.

### 15. `cpr` — Central Pivot Range
Previous session's CPR. `pivot = (H+L+C)/3`, `BC = (H+L)/2`, `TC = 2·pivot−BC`,
then TC and BC are **ordered** so `tc >= bc` (a narrow CPR often inverts them).
A narrow CPR suggests an expansion day, so breaks are taken only when the width
is under `max_cpr_width_pct`.

### 16. `pdh_pdl` — Previous Day High / Low
Break of the prior session's high or low with a `buffer_pct` so a one-tick poke
does not fire.

### 17. `liquidity_sweep`
Price takes out a confirmed swing level (where stops cluster) by at least
`min_sweep_atr` × ATR and immediately reverses back through it. Traded in the
reversal direction with the sweep extreme as the stop.

### 18. `smc` — Smart Money Concepts
SMC terminology is widely used and loosely defined, so the exact rules are:

- **Break of Structure** — close beyond the last *confirmed* swing high/low
  (confirmed means shifted forward by `swing_lookback`, so it was knowable).
- **Fair Value Gap** — a three-bar imbalance where bar *i−2* and bar *i* do not
  overlap: `low[i] − high[i−2] > 0` for bullish, `low[i−2] − high[i] > 0` for
  bearish. Required to exceed `fvg_min_atr` × ATR.
- **Change of Character** — a BOS against the prior structural direction.
- **Order Blocks** — not implemented; the definition is too contested to encode
  without inventing one.

Judge the results against those stated rules, not against a vibe.

---

## Category D — Volume and market analysis

### 19. `volume_price_action`
A wide-range bar closing near its extreme on exceptional volume, aligned with
the EMA trend. Volume confirms a move that has already happened; it is not
treated as a predictor.

Conditions: `volume_spike`, `wide_range_bar`, `close_near_extreme`,
`trend_alignment`.

### 20. `oi_option_chain_price_action` — **BLOCKED**
Reserved for the F&O module. Open interest, change in OI, PCR and option-chain
data do not exist for cash equity instruments, and this build has no options
feed. The strategy is registered and documented but **returns no signals**.
It is not a stub standing in for a working equity strategy.

---

## Combination engine

Combine 2–5 configurations:

| Logic | Rule |
|---|---|
| `AND` | Every leg must fire, in the same direction. |
| `OR` | Any leg firing is enough. |
| `MIN_CONFIRMATIONS` | At least *n* legs agree. |
| `WEIGHTED` | Weighted agreement score ≥ `entry_threshold`. |

Regardless of logic:
- Legs must **agree on direction**. One long and one short is a disagreement,
  never netted off.
- A **mandatory** leg that fails blocks the trade whatever the score. That is
  what makes "trend confirmation" different from "one more vote".
- Entry levels come from the **highest-weighted agreeing leg**, not an average,
  so the stop sits where a real strategy put it.

More confirmations is **not** assumed to be better. The engine reports the
score and which legs passed; whether a 5-leg combination beats a 2-leg one is
an empirical question for the backtester.

---

## Adding a strategy

1. Subclass `BaseStrategy` in `app/strategies/library/`.
2. Set `code`, `name`, `category`, `description`, `default_parameters`,
   `parameter_schema`, `supported_timeframes`, `min_bars`.
3. Implement `prepare()` (attach indicator columns once) and `evaluate()`
   (inspect the last row only).
4. Add it to `STRATEGY_CLASSES` in `app/strategies/registry.py`.
5. Run `make seed` to insert the row.
6. `pytest tests/unit/test_strategies.py` — the parametrised tests pick it up
   automatically, including the look-ahead check.
