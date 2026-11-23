"""Backtesting engine.

A bar-by-bar simulation that shares its fill logic with the paper engine, so a
backtest and a paper trade of the same signal are filled by identical rules.

Bias controls, which are the only reason to trust any of this:

* The strategy sees `df.iloc[:i + 1]` and nothing beyond it. Indicators are
  computed once over the whole series, which is safe only because every
  indicator in the library is causal - the tests assert that directly.
* Entries fill on the **next** bar's open, never on the signal bar's close.
  Filling at the close of the bar that generated the signal assumes you could
  trade at a price you only knew once the bar had ended.
* Exits are checked before new entries within a bar.
* Data coverage is reported: instruments with no usable history are listed as
  skipped rather than quietly dropped from the denominator.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime

import pandas as pd
from sqlalchemy.orm import Session

from app.core.charges import ChargesConfig
from app.core.enums import Direction, ExitReason, JobStatus
from app.core.logging import get_logger
from app.core.market_calendar import now_ist, to_ist
from app.engines.execution import (
    SlippageModel,
    check_exit_on_candle,
    excursions,
    round_trip_pnl,
    simulate_entry,
    simulate_exit,
)
from app.engines.metrics import Metrics, Trade, compute, group_by, overfitting_flags
from app.models.backtest import BacktestJob, BacktestResult, BacktestTrade
from app.models.instrument import Instrument
from app.models.strategy import StrategyConfig
from app.services import candles as candle_service
from app.strategies.base import StrategyContext
from app.strategies.registry import build_strategy

log = get_logger(__name__)


@dataclass
class BacktestConfig:
    initial_capital: float = 1_000_000.0
    risk_per_trade_pct: float = 1.0
    max_open_positions: int = 5
    slippage_pct: float = 0.05
    include_charges: bool = True
    intraday: bool = True
    square_off_eod: bool = True
    max_position_size_pct: float = 20.0


@dataclass
class OpenTrade:
    instrument_id: uuid.UUID
    instrument: str
    strategy: str
    direction: Direction
    quantity: int
    entry_price: float
    entry_time: datetime
    stop_loss: float
    target: float
    entry_index: int
    mae: float = 0.0
    mfe: float = 0.0
    conditions: list = field(default_factory=list)


@dataclass
class BacktestOutcome:
    trades: list[Trade]
    raw_trades: list[dict]
    bars_processed: int
    warnings: list[str] = field(default_factory=list)


class BacktestEngine:
    def __init__(self, db: Session, config: BacktestConfig | None = None) -> None:
        self.db = db
        self.config = config or BacktestConfig()
        self.slippage = SlippageModel(base_pct=self.config.slippage_pct)
        self.charges = ChargesConfig() if self.config.include_charges else None

    # -- single instrument ----------------------------------------------

    def run_instrument(
        self,
        strategy_config: StrategyConfig,
        instrument: Instrument,
        *,
        start: date,
        end: date,
        frame: pd.DataFrame | None = None,
    ) -> BacktestOutcome:
        strategy = build_strategy(
            strategy_config.strategy.code, dict(strategy_config.parameters or {})
        )
        df = (
            frame
            if frame is not None
            else candle_service.load_candles(
                self.db, instrument.id, strategy_config.timeframe, start=start, end=end
            )
        )

        warnings: list[str] = []
        if df is None or len(df) <= strategy.min_bars:
            return BacktestOutcome(
                [], [], 0,
                [
                    f"{instrument.tradingsymbol}: only {0 if df is None else len(df)} "
                    f"candles available at {strategy_config.timeframe}; "
                    f"{strategy.min_bars} needed. Skipped."
                ],
            )

        prepared = strategy.prepare(df)
        trades: list[Trade] = []
        raw: list[dict] = []
        open_trade: OpenTrade | None = None
        pending_entry: dict | None = None

        capital = self.config.initial_capital
        risk_amount = capital * self.config.risk_per_trade_pct / 100
        max_position_value = capital * self.config.max_position_size_pct / 100

        for i in range(strategy.min_bars, len(prepared)):
            bar = prepared.iloc[i]
            bar_ts = to_ist(bar["ts"])

            # 1. Exits first - a position opened earlier may close on this bar.
            if open_trade is not None:
                result = self._check_exit(open_trade, bar, bar_ts, strategy_config)
                if result is not None:
                    trades.append(result["trade"])
                    raw.append(result["raw"])
                    open_trade = None

            # 2. A signal from the previous bar fills at this bar's open.
            if open_trade is None and pending_entry is not None:
                open_trade = self._open_from_pending(pending_entry, bar, bar_ts, i)
                pending_entry = None

            # 3. Evaluate the strategy on bars up to and including this one.
            if open_trade is None and pending_entry is None:
                ctx = StrategyContext(
                    df=prepared.iloc[: i + 1],
                    params=strategy.params,
                    timeframe=strategy_config.timeframe,
                    instrument_id=instrument.id,
                    tradingsymbol=instrument.tradingsymbol,
                )
                try:
                    proposal = strategy.evaluate(ctx)
                except Exception as exc:  # a broken strategy must not kill the run
                    warnings.append(
                        f"{instrument.tradingsymbol} @ {bar_ts}: "
                        f"{type(exc).__name__}: {exc}"
                    )
                    continue

                if proposal is not None:
                    coherent, problem = proposal.is_coherent()
                    if not coherent:
                        warnings.append(
                            f"{instrument.tradingsymbol} @ {bar_ts}: "
                            f"incoherent proposal discarded ({problem})."
                        )
                    elif proposal.risk_reward >= float(strategy_config.min_risk_reward):
                        stop_distance = proposal.risk_per_unit
                        quantity = int(risk_amount // stop_distance) if stop_distance else 0
                        quantity = min(
                            quantity, int(max_position_value // proposal.entry_price)
                        )
                        if quantity > 0:
                            pending_entry = {
                                "proposal": proposal,
                                "quantity": quantity,
                                "instrument": instrument,
                                "strategy": strategy_config.strategy.code,
                            }

        # Close anything still open at the end of the window.
        if open_trade is not None:
            last = prepared.iloc[-1]
            result = self._force_exit(
                open_trade, float(last["close"]), to_ist(last["ts"]), ExitReason.SESSION_END
            )
            trades.append(result["trade"])
            raw.append(result["raw"])
            warnings.append(
                f"{instrument.tradingsymbol}: a position was still open at the end of "
                "the window and was closed at the final close."
            )

        return BacktestOutcome(trades, raw, len(prepared) - strategy.min_bars, warnings)

    # -- helpers ---------------------------------------------------------

    def _open_from_pending(
        self, pending: dict, bar: pd.Series, bar_ts: datetime, index: int
    ) -> OpenTrade:
        proposal = pending["proposal"]
        direction = Direction(str(proposal.direction))
        fill = simulate_entry(
            reference_price=float(bar["open"]),      # next bar's open, never the signal close
            direction=direction,
            quantity=pending["quantity"],
            slippage=self.slippage,
        )
        # Shift stop and target by the same amount the fill moved, so the
        # risk/reward the strategy intended survives the slippage.
        shift = fill.price - proposal.entry_price
        return OpenTrade(
            instrument_id=pending["instrument"].id,
            instrument=pending["instrument"].tradingsymbol,
            strategy=pending["strategy"],
            direction=direction,
            quantity=pending["quantity"],
            entry_price=fill.price,
            entry_time=bar_ts,
            stop_loss=proposal.stop_loss + shift,
            target=proposal.target + shift,
            entry_index=index,
            conditions=[c.as_dict() for c in proposal.conditions],
        )

    def _check_exit(
        self,
        trade: OpenTrade,
        bar: pd.Series,
        bar_ts: datetime,
        strategy_config: StrategyConfig,
    ) -> dict | None:
        mfe, mae = excursions(
            direction=trade.direction,
            entry_price=trade.entry_price,
            high=float(bar["high"]),
            low=float(bar["low"]),
            quantity=trade.quantity,
        )
        trade.mfe = max(trade.mfe, mfe)
        trade.mae = min(trade.mae, mae)

        check = check_exit_on_candle(
            direction=trade.direction,
            stop_loss=trade.stop_loss,
            target=trade.target,
            candle_open=float(bar["open"]),
            candle_high=float(bar["high"]),
            candle_low=float(bar["low"]),
        )
        if check.triggered:
            return self._force_exit(trade, check.price, bar_ts, check.reason)

        if (
            self.config.square_off_eod
            and self.config.intraday
            and bar_ts.time() >= strategy_config.square_off_time
        ):
            return self._force_exit(
                trade, float(bar["close"]), bar_ts, ExitReason.SESSION_END
            )
        return None

    def _force_exit(
        self, trade: OpenTrade, exit_price: float, exit_time: datetime, reason: ExitReason
    ) -> dict:
        fill = simulate_exit(
            reference_price=exit_price,
            direction=trade.direction,
            quantity=trade.quantity,
            slippage=self.slippage,
        )
        pnl = round_trip_pnl(
            direction=trade.direction,
            entry_price=trade.entry_price,
            exit_price=fill.price,
            quantity=trade.quantity,
            intraday=self.config.intraday,
            charges_config=self.charges,
        )
        risk = abs(trade.entry_price - trade.stop_loss) * trade.quantity

        return {
            "trade": Trade(
                entry_time=trade.entry_time,
                exit_time=exit_time,
                net_pnl=pnl["net_pnl"],
                gross_pnl=pnl["gross_pnl"],
                charges=pnl["charges"],
                mae=trade.mae,
                mfe=trade.mfe,
                risk=risk,
                instrument=trade.instrument,
                strategy=trade.strategy,
                direction=str(trade.direction),
                exit_reason=str(reason),
            ),
            "raw": {
                "instrument_id": trade.instrument_id,
                "instrument": trade.instrument,
                "strategy": trade.strategy,
                "direction": str(trade.direction),
                "quantity": trade.quantity,
                "entry_time": trade.entry_time,
                "entry_price": trade.entry_price,
                "exit_time": exit_time,
                "exit_price": fill.price,
                "exit_reason": str(reason),
                "stop_loss": trade.stop_loss,
                "target": trade.target,
                "gross_pnl": pnl["gross_pnl"],
                "charges": pnl["charges"],
                "net_pnl": pnl["net_pnl"],
                "mae": trade.mae,
                "mfe": trade.mfe,
                "conditions": trade.conditions,
            },
        }

    # -- job runner ------------------------------------------------------

    def run_job(self, job: BacktestJob) -> BacktestJob:
        job.status = JobStatus.RUNNING
        job.started_at = now_ist()
        self.db.commit()

        all_trades: list[Trade] = []
        all_raw: list[dict] = []
        warnings: list[str] = []
        coverage = {"requested": 0, "with_data": 0, "skipped": [] }

        try:
            configs = [
                self.db.get(StrategyConfig, uuid.UUID(cid))
                for cid in job.strategy_config_ids
            ]
            configs = [c for c in configs if c is not None]
            instruments = [
                self.db.get(Instrument, uuid.UUID(iid)) for iid in job.instrument_ids
            ]
            instruments = [i for i in instruments if i is not None]
            coverage["requested"] = len(instruments)

            total = max(len(configs) * len(instruments), 1)
            done = 0

            for config in configs:
                for instrument in instruments:
                    outcome = self.run_instrument(
                        config, instrument, start=job.start_date, end=job.end_date
                    )
                    if outcome.bars_processed == 0 and not outcome.trades:
                        coverage["skipped"].append(instrument.tradingsymbol)
                    else:
                        coverage["with_data"] += 1
                    all_trades.extend(outcome.trades)
                    all_raw.extend(outcome.raw_trades)
                    warnings.extend(outcome.warnings)

                    done += 1
                    job.progress_pct = round(done / total * 100, 2)
                    self.db.commit()

            coverage["with_data"] = min(coverage["with_data"], coverage["requested"])
            self._persist_results(job, all_trades, all_raw, coverage, warnings)

            job.status = JobStatus.COMPLETED
            job.finished_at = now_ist()
            job.progress_pct = 100
            job.duration_seconds = int(
                (job.finished_at - job.started_at).total_seconds()
            )
        except Exception as exc:
            self.db.rollback()
            job = self.db.get(BacktestJob, job.id)
            job.status = JobStatus.FAILED
            job.error = f"{type(exc).__name__}: {exc}"
            self.db.commit()
            log.exception("backtest_failed", job_id=str(job.id))
            raise

        self.db.commit()
        self.db.refresh(job)
        return job

    def _persist_results(
        self,
        job: BacktestJob,
        trades: list[Trade],
        raw: list[dict],
        coverage: dict,
        warnings: list[str],
    ) -> None:
        capital = float(job.initial_capital)
        overall = compute(trades, initial_capital=capital)

        job.data_coverage = coverage
        job.warnings = warnings[:200]
        if coverage["skipped"]:
            job.warnings.insert(
                0,
                f"{len(coverage['skipped'])} of {coverage['requested']} instruments had "
                "insufficient data and were skipped. Results cover only the rest.",
            )

        overall_row = self._result_row(job, overall, scope="OVERALL")
        self.db.add(overall_row)
        self.db.flush()

        # Per-instrument and per-strategy breakdowns.
        for scope, key in (("INSTRUMENT", "instrument"), ("STRATEGY", "strategy")):
            for name, bucket in group_by(trades, key).items():
                row = self._result_row(
                    job, compute(bucket, initial_capital=capital), scope=scope, scope_ref=name
                )
                self.db.add(row)

        # In-sample / out-of-sample split when the job asks for one.
        split = (job.validation or {}).get("out_of_sample_pct")
        if split and trades:
            ordered = sorted(trades, key=lambda t: (t.exit_time or t.entry_time))
            cut = int(len(ordered) * (1 - float(split) / 100))
            in_sample = compute(ordered[:cut], initial_capital=capital)
            out_sample = compute(ordered[cut:], initial_capital=capital)
            self.db.add(
                self._result_row(job, in_sample, scope="WINDOW", window="IN_SAMPLE")
            )
            oos_row = self._result_row(
                job, out_sample, scope="WINDOW", window="OUT_OF_SAMPLE"
            )
            oos_row.overfitting_flags = overfitting_flags(in_sample, out_sample)
            self.db.add(oos_row)

        for item in raw:
            self.db.add(
                BacktestTrade(
                    job_id=job.id,
                    result_id=overall_row.id,
                    instrument_id=item["instrument_id"],
                    direction=item["direction"],
                    quantity=item["quantity"],
                    entry_time=item["entry_time"],
                    entry_price=item["entry_price"],
                    exit_time=item["exit_time"],
                    exit_price=item["exit_price"],
                    exit_reason=item["exit_reason"],
                    stop_loss=item["stop_loss"],
                    target=item["target"],
                    gross_pnl=item["gross_pnl"],
                    charges=item["charges"],
                    net_pnl=item["net_pnl"],
                    mae=item["mae"],
                    mfe=item["mfe"],
                    conditions={"checks": item["conditions"]},
                )
            )
        self.db.flush()

    def _result_row(
        self,
        job: BacktestJob,
        m: Metrics,
        *,
        scope: str,
        scope_ref: str | None = None,
        window: str | None = None,
    ) -> BacktestResult:
        return BacktestResult(
            job_id=job.id,
            scope=scope,
            scope_ref=scope_ref,
            window=window,
            start_date=job.start_date,
            end_date=job.end_date,
            total_trades=m.total_trades,
            winning_trades=m.winning_trades,
            losing_trades=m.losing_trades,
            win_rate=m.win_rate,
            gross_profit=m.gross_profit,
            gross_loss=m.gross_loss,
            total_charges=m.total_charges,
            net_profit=m.net_profit,
            profit_factor=m.profit_factor,
            expectancy=m.expectancy,
            average_profit=m.average_profit,
            average_loss=m.average_loss,
            average_rr=m.average_rr,
            max_drawdown=m.max_drawdown,
            max_drawdown_pct=m.max_drawdown_pct,
            sharpe_ratio=m.sharpe_ratio,
            sortino_ratio=m.sortino_ratio,
            max_consecutive_wins=m.max_consecutive_wins,
            max_consecutive_losses=m.max_consecutive_losses,
            avg_mae=m.avg_mae,
            avg_mfe=m.avg_mfe,
            equity_curve=m.equity_curve[:5000],
            monthly_performance=m.monthly_performance,
            metrics_extra={"notes": m.notes},
        )
