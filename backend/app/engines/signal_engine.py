"""Signal engine.

One place where a strategy's proposal becomes a persisted, risk-validated
signal. Responsibilities, in order:

1. Load enough history and refuse to evaluate without it.
2. Check data freshness - stale data never produces a live signal.
3. Run the strategy on completed candles only.
4. Check coherence (a long whose stop is above entry is a bug, not a trade).
5. Deduplicate: one signal per strategy/instrument/timeframe/candle.
6. Validate against the risk engine and record the outcome either way.

A signal is never an order. Turning a VALIDATED signal into a paper position is
`app.engines.paper_trading`'s job, and nothing here can place a live order.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import TIMEFRAME_MINUTES, Direction, SignalState
from app.core.logging import get_logger
from app.core.market_calendar import now_ist, to_ist
from app.engines.risk import RiskEngine
from app.models.instrument import Instrument
from app.models.signal import SignalHistory, TradingSignal
from app.models.strategy import StrategyConfig, StrategyExecutionLog
from app.services import candles as candle_service
from app.strategies.base import SignalProposal, StrategyContext
from app.strategies.registry import build_strategy

log = get_logger(__name__)

#: A signal built on data older than this is not a live signal.
DEFAULT_MAX_DATA_AGE_SECONDS = 300


@dataclass
class EvaluationResult:
    produced_signal: bool
    signal: TradingSignal | None = None
    reason: str = ""
    conditions: list[dict] | None = None
    proposal: SignalProposal | None = None


def dedupe_key(
    *, strategy_config_id, instrument_id, timeframe: str, candle_ts: datetime, nonce: str = ""
) -> str:
    base = f"{strategy_config_id}:{instrument_id}:{timeframe}:{candle_ts.isoformat()}"
    return f"{base}:{nonce}" if nonce else base


def _expiry(candle_ts: datetime, timeframe: str, bars: int = 3) -> datetime:
    minutes = TIMEFRAME_MINUTES.get(timeframe, 5)
    return to_ist(candle_ts) + timedelta(minutes=minutes * bars)


class SignalEngine:
    def __init__(self, db: Session, risk: RiskEngine | None = None) -> None:
        self.db = db
        self.risk = risk

    # -- evaluation ------------------------------------------------------

    def evaluate(
        self,
        config: StrategyConfig,
        instrument: Instrument,
        *,
        as_of: datetime | None = None,
        is_backtest: bool = False,
        candles=None,
        enforce_freshness: bool | None = None,
        max_data_age_seconds: int = DEFAULT_MAX_DATA_AGE_SECONDS,
        persist: bool = True,
    ) -> EvaluationResult:
        started = now_ist()
        as_of = as_of or started
        strategy = build_strategy(config.strategy.code, dict(config.parameters or {}))
        enforce_freshness = (not is_backtest) if enforce_freshness is None else enforce_freshness

        frame = (
            candles
            if candles is not None
            else candle_service.load_candles(
                self.db,
                instrument.id,
                config.timeframe,
                end=as_of,
                limit=strategy.min_bars + 10,
            )
        )

        if frame is None or len(frame) < strategy.min_bars:
            have = 0 if frame is None else len(frame)
            return self._no_signal(
                config,
                instrument,
                as_of,
                started,
                reason=(
                    f"Insufficient history: {have} candles available, "
                    f"{strategy.min_bars} required by {strategy.code}."
                ),
                persist=persist,
            )

        candle_ts = to_ist(frame["ts"].iloc[-1])

        if enforce_freshness:
            age = int((to_ist(as_of) - candle_ts).total_seconds())
            if age > max_data_age_seconds:
                return self._no_signal(
                    config,
                    instrument,
                    as_of,
                    started,
                    reason=(
                        f"Market data is stale: newest candle is {age}s old, "
                        f"limit is {max_data_age_seconds}s. No signal generated."
                    ),
                    persist=persist,
                )
        else:
            age = None

        prepared = strategy.prepare(frame)
        ctx = StrategyContext(
            df=prepared,
            params=strategy.params,
            timeframe=config.timeframe,
            instrument_id=instrument.id,
            tradingsymbol=instrument.tradingsymbol,
        )

        try:
            proposal = strategy.evaluate(ctx)
        except Exception as exc:
            log.exception("strategy_evaluation_failed", strategy=strategy.code)
            return self._no_signal(
                config,
                instrument,
                as_of,
                started,
                reason=f"Strategy raised {type(exc).__name__}: {exc}",
                persist=persist,
                error=str(exc),
            )

        if proposal is None:
            return self._no_signal(
                config,
                instrument,
                as_of,
                started,
                reason="Entry conditions were not met on this candle.",
                persist=persist,
                candle_ts=candle_ts,
            )

        coherent, problem = proposal.is_coherent()
        if not coherent:
            log.error("incoherent_proposal", strategy=strategy.code, problem=problem)
            return self._no_signal(
                config,
                instrument,
                as_of,
                started,
                reason=f"Strategy produced an invalid trade ({problem}); discarded.",
                persist=persist,
                candle_ts=candle_ts,
            )

        return self._create_signal(
            config,
            instrument,
            proposal,
            candle_ts=candle_ts,
            as_of=as_of,
            started=started,
            is_backtest=is_backtest,
            data_age_seconds=age,
            persist=persist,
        )

    # -- persistence -----------------------------------------------------

    def _create_signal(
        self,
        config: StrategyConfig,
        instrument: Instrument,
        proposal: SignalProposal,
        *,
        candle_ts: datetime,
        as_of: datetime,
        started: datetime,
        is_backtest: bool,
        data_age_seconds: int | None,
        persist: bool,
    ) -> EvaluationResult:
        conditions = [c.as_dict() for c in proposal.conditions]

        if not persist:
            return EvaluationResult(True, None, proposal.reason, conditions, proposal)

        nonce = uuid.uuid4().hex[:8] if config.allow_repeat_signal_same_candle else ""
        key = dedupe_key(
            strategy_config_id=config.id,
            instrument_id=instrument.id,
            timeframe=config.timeframe,
            candle_ts=candle_ts,
            nonce=nonce,
        )
        if self.db.scalar(select(TradingSignal).where(TradingSignal.dedupe_key == key)):
            return EvaluationResult(
                False, None, "A signal already exists for this candle (deduplicated).", conditions
            )

        signal = TradingSignal(
            instrument_id=instrument.id,
            exchange=instrument.exchange,
            strategy_id=config.strategy_id,
            strategy_config_id=config.id,
            combination_id=None,
            module=config.strategy.module if config.strategy else "EQUITY",
            direction=str(proposal.direction),
            entry_price=proposal.entry_price,
            stop_loss=proposal.stop_loss,
            target=proposal.target,
            risk_reward=proposal.risk_reward,
            timeframe=config.timeframe,
            candle_ts=candle_ts,
            generated_at=as_of,
            expires_at=_expiry(candle_ts, config.timeframe),
            state=SignalState.GENERATED,
            confidence=proposal.confidence,
            score=proposal.confidence,
            entry_reason=proposal.reason,
            conditions={"checks": conditions},
            market_context={"indicators": proposal.indicator_snapshot},
            data_source="HISTORICAL_IMPORT" if is_backtest else "BROKER_LIVE",
            data_age_seconds=data_age_seconds,
            dedupe_key=key,
            is_backtest=is_backtest,
        )
        self.db.add(signal)
        self.db.flush()
        self._transition(signal, None, SignalState.GENERATED, "Signal generated.")

        # Risk validation
        if self.risk is not None:
            decision = self.risk.validate_entry(
                instrument=instrument,
                direction=Direction(str(proposal.direction)),
                entry_price=proposal.entry_price,
                stop_loss=proposal.stop_loss,
                min_risk_reward=float(config.min_risk_reward),
                risk_reward=proposal.risk_reward,
            )
            signal.risk_validation = decision.as_dict()
            signal.suggested_quantity = decision.quantity
            if decision.allowed:
                signal.state = SignalState.VALIDATED
                self._transition(
                    signal, SignalState.GENERATED, SignalState.VALIDATED,
                    "Passed every risk check.",
                )
            else:
                signal.state = SignalState.REJECTED
                signal.rejection_reason = "; ".join(decision.reasons)
                self.risk.record_breach(decision, signal_id=signal.id)
                self._transition(
                    signal, SignalState.GENERATED, SignalState.REJECTED,
                    signal.rejection_reason,
                )

        self._log_execution(
            config, instrument, as_of, started, True, conditions,
            proposal.indicator_snapshot, candle_ts,
        )
        self.db.commit()
        self.db.refresh(signal)
        log.info(
            "signal_generated",
            signal_id=str(signal.id),
            symbol=instrument.tradingsymbol,
            strategy=config.strategy.code if config.strategy else None,
            state=signal.state,
        )
        return EvaluationResult(True, signal, proposal.reason, conditions, proposal)

    def _no_signal(
        self,
        config: StrategyConfig,
        instrument: Instrument,
        as_of: datetime,
        started: datetime,
        *,
        reason: str,
        persist: bool,
        candle_ts: datetime | None = None,
        error: str | None = None,
    ) -> EvaluationResult:
        if persist:
            self._log_execution(
                config, instrument, as_of, started, False, [], {}, candle_ts, error
            )
            self.db.commit()
        return EvaluationResult(False, None, reason, [])

    def _log_execution(
        self,
        config: StrategyConfig,
        instrument: Instrument,
        as_of: datetime,
        started: datetime,
        produced: bool,
        conditions: list[dict],
        indicators: dict,
        candle_ts: datetime | None,
        error: str | None = None,
    ) -> None:
        self.db.add(
            StrategyExecutionLog(
                created_at=now_ist(),
                strategy_config_id=config.id,
                instrument_id=instrument.id,
                evaluated_at=as_of,
                candle_ts=candle_ts,
                timeframe=config.timeframe,
                produced_signal=produced,
                conditions={"checks": conditions},
                indicator_snapshot=indicators,
                duration_ms=int((now_ist() - started).total_seconds() * 1000),
                error=error,
            )
        )

    def _transition(
        self, signal: TradingSignal, from_state, to_state, reason: str
    ) -> None:
        self.db.add(
            SignalHistory(
                signal_id=signal.id,
                from_state=str(from_state) if from_state else None,
                to_state=str(to_state),
                changed_at=now_ist(),
                reason=reason,
            )
        )

    # -- housekeeping ----------------------------------------------------

    def expire_stale_signals(self, *, as_of: datetime | None = None) -> int:
        """Signals that were never acted on stop being actionable."""
        as_of = as_of or now_ist()
        stale = self.db.scalars(
            select(TradingSignal).where(
                TradingSignal.state.in_([SignalState.GENERATED, SignalState.VALIDATED]),
                TradingSignal.expires_at.is_not(None),
                TradingSignal.expires_at < as_of,
                TradingSignal.is_backtest.is_(False),
            )
        ).all()
        for signal in stale:
            previous, signal.state = signal.state, SignalState.EXPIRED
            self._transition(signal, previous, SignalState.EXPIRED, "Signal expired unexecuted.")
        if stale:
            self.db.commit()
        return len(stale)
