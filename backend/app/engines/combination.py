"""Strategy combination engine.

Runs several strategy configs over the same instrument and candle, then applies
the combination's logic to decide whether the group as a whole wants a trade.

Design notes:

* Legs must agree on **direction**. Two strategies, one long and one short,
  are a disagreement, not a confirmation - the engine never nets them off.
* A **mandatory** leg that fails blocks the trade regardless of score. That is
  what makes "trend confirmation" meaningfully different from "one more vote".
* Entry levels come from the highest-weighted agreeing leg rather than an
  average, so the stop sits at a level that a real strategy actually chose.
* More confirmations is not assumed to be better. The engine reports the score
  and which legs passed; whether a 5-leg combination beats a 2-leg one is an
  empirical question for the backtester.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.core.enums import CombinationLogic, Direction
from app.core.logging import get_logger
from app.engines.signal_engine import SignalEngine
from app.models.instrument import Instrument
from app.models.strategy import StrategyCombination
from app.strategies.base import SignalProposal

log = get_logger(__name__)


@dataclass
class LegOutcome:
    strategy_code: str
    config_id: str
    weight: float
    is_mandatory: bool
    role: str | None
    fired: bool
    direction: str | None = None
    reason: str = ""
    conditions: list[dict] = field(default_factory=list)
    proposal: SignalProposal | None = None

    def as_dict(self) -> dict:
        return {
            "strategy": self.strategy_code,
            "config_id": self.config_id,
            "weight": self.weight,
            "is_mandatory": self.is_mandatory,
            "role": self.role,
            "fired": self.fired,
            "direction": self.direction,
            "reason": self.reason,
            "conditions": self.conditions,
        }


@dataclass
class CombinationResult:
    passed: bool
    direction: Direction | None = None
    score: float = 0.0
    threshold: float = 0.0
    legs: list[LegOutcome] = field(default_factory=list)
    reason: str = ""
    proposal: SignalProposal | None = None

    def as_dict(self) -> dict:
        return {
            "passed": self.passed,
            "direction": str(self.direction) if self.direction else None,
            "score": round(self.score, 4),
            "threshold": round(self.threshold, 4),
            "reason": self.reason,
            "legs": [leg.as_dict() for leg in self.legs],
            "confirmations": sum(1 for leg in self.legs if leg.fired),
            "total_legs": len(self.legs),
        }


class CombinationEngine:
    def __init__(self, db: Session, signal_engine: SignalEngine) -> None:
        self.db = db
        self.signals = signal_engine

    def evaluate(
        self,
        combination: StrategyCombination,
        instrument: Instrument,
        *,
        as_of=None,
        is_backtest: bool = False,
    ) -> CombinationResult:
        legs: list[LegOutcome] = []

        for leg in sorted(combination.legs, key=lambda item: item.sort_order):
            config = leg.strategy_config
            outcome = LegOutcome(
                strategy_code=config.strategy.code if config.strategy else "unknown",
                config_id=str(leg.strategy_config_id),
                weight=float(leg.weight),
                is_mandatory=bool(leg.is_mandatory),
                role=leg.role,
                fired=False,
            )
            result = self.signals.evaluate(
                config,
                instrument,
                as_of=as_of,
                is_backtest=is_backtest,
                persist=False,                # legs are evaluated, not recorded
            )
            outcome.fired = result.produced_signal and result.proposal is not None
            outcome.reason = result.reason
            outcome.conditions = result.conditions or []
            if outcome.fired:
                outcome.proposal = result.proposal
                outcome.direction = str(result.proposal.direction)
            legs.append(outcome)

        return self._decide(combination, legs)

    def _decide(
        self, combination: StrategyCombination, legs: list[LegOutcome]
    ) -> CombinationResult:
        if not legs:
            return CombinationResult(False, reason="The combination has no legs configured.")

        fired = [leg for leg in legs if leg.fired]
        if not fired:
            return CombinationResult(
                False, legs=legs, reason="No leg produced a signal on this candle."
            )

        # Direction agreement: take the side with the most weight, then require
        # that no mandatory leg points the other way.
        weight_by_direction: dict[str, float] = {}
        for leg in fired:
            weight_by_direction[leg.direction] = (
                weight_by_direction.get(leg.direction, 0.0) + leg.weight
            )
        direction_str = max(weight_by_direction, key=weight_by_direction.get)
        direction = Direction(direction_str)

        agreeing = [leg for leg in fired if leg.direction == direction_str]
        disagreeing = [leg for leg in fired if leg.direction != direction_str]

        conflicting_mandatory = [leg for leg in disagreeing if leg.is_mandatory]
        if conflicting_mandatory:
            return CombinationResult(
                False,
                direction=direction,
                legs=legs,
                reason=(
                    "A mandatory leg ("
                    + ", ".join(leg.strategy_code for leg in conflicting_mandatory)
                    + ") signalled the opposite direction."
                ),
            )

        missing_mandatory = [
            leg for leg in legs if leg.is_mandatory and leg not in agreeing
        ]
        if missing_mandatory:
            return CombinationResult(
                False,
                direction=direction,
                legs=legs,
                reason=(
                    "Mandatory leg(s) did not confirm: "
                    + ", ".join(leg.strategy_code for leg in missing_mandatory)
                ),
            )

        total_weight = sum(leg.weight for leg in legs) or 1.0
        score = sum(leg.weight for leg in agreeing) / total_weight
        logic = CombinationLogic(combination.logic)
        threshold = float(combination.entry_threshold)

        if logic == CombinationLogic.AND:
            passed = len(agreeing) == len(legs)
            reason = (
                f"All {len(legs)} legs agree on {direction_str}."
                if passed
                else f"AND logic requires every leg; {len(agreeing)}/{len(legs)} agreed."
            )
        elif logic == CombinationLogic.OR:
            passed = True
            reason = f"OR logic satisfied by {len(agreeing)} leg(s) on {direction_str}."
        elif logic == CombinationLogic.MIN_CONFIRMATIONS:
            needed = int(combination.min_confirmations)
            passed = len(agreeing) >= needed
            reason = (
                f"{len(agreeing)} confirmations vs {needed} required."
            )
        else:  # WEIGHTED
            passed = score >= threshold
            reason = (
                f"Weighted score {score:.3f} vs entry threshold {threshold:.3f} "
                f"({len(agreeing)}/{len(legs)} legs agreeing)."
            )

        result = CombinationResult(
            passed=passed,
            direction=direction,
            score=score,
            threshold=threshold,
            legs=legs,
            reason=reason,
        )

        if passed:
            # Levels come from the heaviest agreeing leg, not an average.
            anchor = max(agreeing, key=lambda leg: (leg.weight, leg.proposal.confidence))
            proposal = anchor.proposal
            proposal.confidence = min(0.99, score)
            proposal.reason = (
                f"Combination '{combination.name}': {reason} "
                f"Levels taken from {anchor.strategy_code}."
            )
            result.proposal = proposal
        return result
