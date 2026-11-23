"""Strategy registry.

Maps a database `strategies.code` to the class that implements it. The seed
data for the `strategies` table is derived from the classes themselves, so a
strategy's documented parameters and its real ones cannot drift apart.
"""

from __future__ import annotations

from app.core.exceptions import NotFoundError
from app.strategies.base import BaseStrategy
from app.strategies.library.indicator_based import (
    BollingerBandsStrategy,
    EmaCrossoverStrategy,
    EmaVwapComboStrategy,
    MacdCrossoverStrategy,
    RsiMacdComboStrategy,
    RsiReversalStrategy,
    SupertrendStrategy,
    VwapStrategy,
)
from app.strategies.library.intraday import (
    CprStrategy,
    LiquiditySweepStrategy,
    OpeningRangeBreakoutStrategy,
    PreviousDayLevelsStrategy,
    SmartMoneyConceptsStrategy,
)
from app.strategies.library.price_action import (
    BreakoutRetestStrategy,
    BreakoutStrategy,
    CandlestickReversalStrategy,
    FalseBreakoutStrategy,
    TrendFollowingStrategy,
)
from app.strategies.library.volume_based import (
    OpenInterestPriceActionStrategy,
    VolumePriceActionStrategy,
)

STRATEGY_CLASSES: list[type[BaseStrategy]] = [
    # A - Price action
    BreakoutStrategy,
    BreakoutRetestStrategy,
    FalseBreakoutStrategy,
    CandlestickReversalStrategy,
    TrendFollowingStrategy,
    # B - Indicator based
    EmaCrossoverStrategy,
    SupertrendStrategy,
    VwapStrategy,
    RsiReversalStrategy,
    MacdCrossoverStrategy,
    BollingerBandsStrategy,
    EmaVwapComboStrategy,
    RsiMacdComboStrategy,
    # C - Intraday
    OpeningRangeBreakoutStrategy,
    CprStrategy,
    PreviousDayLevelsStrategy,
    LiquiditySweepStrategy,
    SmartMoneyConceptsStrategy,
    # D - Volume / market analysis
    VolumePriceActionStrategy,
    OpenInterestPriceActionStrategy,
]

REGISTRY: dict[str, type[BaseStrategy]] = {cls.code: cls for cls in STRATEGY_CLASSES}

if len(REGISTRY) != len(STRATEGY_CLASSES):  # pragma: no cover - import-time guard
    raise RuntimeError("Duplicate strategy code in STRATEGY_CLASSES")


def get_strategy_class(code: str) -> type[BaseStrategy]:
    cls = REGISTRY.get(code)
    if cls is None:
        raise NotFoundError(
            f"No strategy implementation registered for code '{code}'.",
            details={"available": sorted(REGISTRY)},
        )
    return cls


def build_strategy(code: str, params: dict | None = None) -> BaseStrategy:
    return get_strategy_class(code)(params)


def _seed(cls: type[BaseStrategy]) -> dict:
    return {
        "code": cls.code,
        "name": cls.name,
        "category": str(cls.category),
        "module": cls.module,
        "description": " ".join(cls.description.split()),
        "default_timeframe": cls.default_timeframe,
        "supported_timeframes": list(cls.supported_timeframes),
        "default_parameters": dict(cls.default_parameters),
        "parameter_schema": dict(cls.parameter_schema),
        "min_bars": cls.min_bars,
        "blocked_reason": getattr(cls, "blocked_reason", None),
    }


#: Consumed by `scripts/seed.py` to populate the `strategies` table.
STRATEGY_SEEDS: list[dict] = [_seed(cls) for cls in STRATEGY_CLASSES]


def catalogue() -> list[dict]:
    """What the Strategy Library page renders."""
    return STRATEGY_SEEDS
