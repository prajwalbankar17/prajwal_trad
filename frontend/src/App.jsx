import { Navigate, Route, Routes } from 'react-router-dom'
import { AppLayout } from './components/layout/AppLayout'
import { useAuthStore } from './store/auth'

import Login from './pages/auth/Login'
import Dashboard from './pages/dashboard/Dashboard'
import Instruments from './pages/instruments/Instruments'
import EquityOverview from './pages/equity/EquityOverview'
import Signals from './pages/equity/Signals'
import Positions from './pages/equity/Positions'
import TradeHistory from './pages/equity/TradeHistory'
import StrategyLibrary from './pages/strategies/StrategyLibrary'
import StrategyConfigs from './pages/strategies/StrategyConfigs'
import RunBacktest from './pages/backtesting/RunBacktest'
import BacktestHistory from './pages/backtesting/BacktestHistory'
import BacktestDetail from './pages/backtesting/BacktestDetail'
import HistoricalData from './pages/marketdata/HistoricalData'
import DataImports from './pages/marketdata/DataImports'
import DataQuality from './pages/marketdata/DataQuality'
import RiskManagement from './pages/risk/RiskManagement'
import {
  AIResearch, AuditLog, Broker, FnoModule, MarketOverview, Notifications, Portfolio,
  Reports, Settings, StrategyCombinations, SystemMonitoring, Users, Watchlists,
} from './pages/misc'

function RequireAuth({ children }) {
  const token = useAuthStore((s) => s.accessToken)
  return token ? children : <Navigate to="/login" replace />
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route
        element={
          <RequireAuth>
            <AppLayout />
          </RequireAuth>
        }
      >
        <Route index element={<Dashboard />} />
        <Route path="market" element={<MarketOverview />} />
        <Route path="instruments" element={<Instruments />} />
        <Route path="watchlists" element={<Watchlists />} />

        <Route path="equity" element={<EquityOverview />} />
        <Route path="equity/signals" element={<Signals />} />
        <Route path="equity/positions" element={<Positions />} />
        <Route path="equity/history" element={<TradeHistory />} />

        <Route path="fno" element={<FnoModule />} />

        <Route path="strategies" element={<StrategyLibrary />} />
        <Route path="strategies/configs" element={<StrategyConfigs />} />
        <Route path="strategies/combinations" element={<StrategyCombinations />} />

        <Route path="backtesting" element={<RunBacktest />} />
        <Route path="backtesting/history" element={<BacktestHistory />} />
        <Route path="backtesting/:jobId" element={<BacktestDetail />} />

        <Route path="data" element={<HistoricalData />} />
        <Route path="data/imports" element={<DataImports />} />
        <Route path="data/quality" element={<DataQuality />} />

        <Route path="portfolio" element={<Portfolio />} />
        <Route path="risk" element={<RiskManagement />} />
        <Route path="ai" element={<AIResearch />} />
        <Route path="notifications" element={<Notifications />} />
        <Route path="reports" element={<Reports />} />
        <Route path="broker" element={<Broker />} />
        <Route path="system" element={<SystemMonitoring />} />
        <Route path="audit" element={<AuditLog />} />
        <Route path="users" element={<Users />} />
        <Route path="settings" element={<Settings />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
