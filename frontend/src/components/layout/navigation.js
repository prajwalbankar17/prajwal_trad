import {
  Activity, BarChart3, Bell, BookOpen, Boxes, Brain, Building2, CandlestickChart,
  Database, FileText, Gauge, LayoutDashboard, LineChart, ListChecks, Settings,
  Shield, Star, Users, Wallet,
} from 'lucide-react'

/**
 * Sidebar structure. `permission` hides a section the user cannot use at all;
 * `blocked` marks a section that exists but needs something we do not have yet
 * (the F&O module), so it is visible and honest rather than silently missing.
 */
export const NAVIGATION = [
  { label: 'Dashboard', to: '/', icon: LayoutDashboard, permission: 'trade:read', end: true },
  { label: 'Market Overview', to: '/market', icon: Activity, permission: 'marketdata:read' },
  { label: 'Instruments', to: '/instruments', icon: Boxes, permission: 'instrument:read' },
  { label: 'Watchlists', to: '/watchlists', icon: Star, permission: 'watchlist:read' },
  {
    label: 'Equity Trading',
    icon: CandlestickChart,
    permission: 'trade:read',
    children: [
      { label: 'Overview', to: '/equity' },
      { label: 'Signals', to: '/equity/signals' },
      { label: 'Active Positions', to: '/equity/positions' },
      { label: 'Trade History', to: '/equity/history' },
    ],
  },
  {
    label: 'F&O Trading',
    icon: LineChart,
    permission: 'trade:read',
    blocked: 'Phase 9',
    children: [{ label: 'Overview', to: '/fno' }],
  },
  {
    label: 'Strategies',
    icon: BookOpen,
    permission: 'strategy:read',
    children: [
      { label: 'Strategy Library', to: '/strategies' },
      { label: 'Configurations', to: '/strategies/configs' },
      { label: 'Combinations', to: '/strategies/combinations' },
    ],
  },
  {
    label: 'Backtesting',
    icon: BarChart3,
    permission: 'backtest:read',
    children: [
      { label: 'Run Backtest', to: '/backtesting' },
      { label: 'History', to: '/backtesting/history' },
    ],
  },
  {
    label: 'Market Data',
    icon: Database,
    permission: 'marketdata:read',
    children: [
      { label: 'Historical Data', to: '/data' },
      { label: 'Data Imports', to: '/data/imports' },
      { label: 'Data Quality', to: '/data/quality' },
    ],
  },
  { label: 'Portfolio', to: '/portfolio', icon: Wallet, permission: 'portfolio:read' },
  { label: 'Risk Management', to: '/risk', icon: Shield, permission: 'risk:read' },
  { label: 'AI Research', to: '/ai', icon: Brain, permission: 'ai:read' },
  { label: 'Notifications', to: '/notifications', icon: Bell, permission: 'notification:read' },
  { label: 'Reports', to: '/reports', icon: FileText, permission: 'report:read' },
  { label: 'Broker', to: '/broker', icon: Building2, permission: 'broker:read' },
  { label: 'System', to: '/system', icon: Gauge, permission: 'system:monitor' },
  { label: 'Audit Log', to: '/audit', icon: ListChecks, permission: 'audit:read' },
  { label: 'Users & Roles', to: '/users', icon: Users, permission: 'user:read' },
  { label: 'Settings', to: '/settings', icon: Settings },
]
