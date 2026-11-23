"""All ORM models.

Imported here so Alembic autogenerate and `Base.metadata` see every table.
"""

from app.db.base import Base
from app.models.ai import AIAnalysis, AIPromptVersion, AIRecommendation, AIUsageLog
from app.models.backtest import (
    BacktestConfiguration,
    BacktestJob,
    BacktestResult,
    BacktestTrade,
)
from app.models.instrument import (
    CorporateAction,
    ExchangeRef,
    Instrument,
    MarketHoliday,
    Sector,
    SymbolMapping,
    Watchlist,
    WatchlistItem,
)
from app.models.market_data import (
    DailyCandle,
    DataAvailability,
    DataImportFailure,
    DataImportJob,
    DataQualityReport,
    DataSource,
    IntradayCandle,
    LiveTick,
    MarketStatusLog,
)
from app.models.portfolio import Holding, Portfolio, PortfolioSnapshot
from app.models.risk import DailyRiskState, ExposureRecord, RiskLimitBreach, RiskProfile
from app.models.signal import SignalHistory, TradingSignal
from app.models.strategy import (
    Strategy,
    StrategyCombination,
    StrategyCombinationLeg,
    StrategyConfig,
    StrategyExecutionLog,
    StrategyVersion,
    TradingModuleState,
)
from app.models.system import (
    AuditLog,
    BrokerConnection,
    Notification,
    NotificationPreference,
    Permission,
    Role,
    SystemSetting,
    User,
    UserSession,
)
from app.models.trading import ExitRecord, Order, Position, TradeExecution

__all__ = [
    "Base",
    "AIAnalysis", "AIPromptVersion", "AIRecommendation", "AIUsageLog",
    "BacktestConfiguration", "BacktestJob", "BacktestResult", "BacktestTrade",
    "CorporateAction", "ExchangeRef", "Instrument", "MarketHoliday", "Sector",
    "SymbolMapping", "Watchlist", "WatchlistItem",
    "DailyCandle", "DataAvailability", "DataImportFailure", "DataImportJob",
    "DataQualityReport", "DataSource", "IntradayCandle", "LiveTick", "MarketStatusLog",
    "Holding", "Portfolio", "PortfolioSnapshot",
    "DailyRiskState", "ExposureRecord", "RiskLimitBreach", "RiskProfile",
    "SignalHistory", "TradingSignal",
    "Strategy", "StrategyCombination", "StrategyCombinationLeg", "StrategyConfig",
    "StrategyExecutionLog", "StrategyVersion", "TradingModuleState",
    "AuditLog", "BrokerConnection", "Notification", "NotificationPreference",
    "Permission", "Role", "SystemSetting", "User", "UserSession",
    "ExitRecord", "Order", "Position", "TradeExecution",
]
