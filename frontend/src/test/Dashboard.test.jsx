import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'

vi.mock('../api/client', () => ({
  api: { get: vi.fn() },
  errorMessage: (e) => e?.message ?? 'error',
  errorDetails: () => null,
}))

import { api } from '../api/client'
import Dashboard from '../pages/dashboard/Dashboard'

const payload = {
  execution_mode: 'paper',
  is_paper_trading: true,
  disclaimer: 'All capital and P&L figures below are SIMULATED paper trading.',
  market: { status: 'OPEN', server_time_ist: '2024-06-03T10:00:00+05:30', feed_connected: false },
  capital: {
    total_capital: 1000000,
    current_capital: 1012000,
    available_capital: 900000,
    used_capital: 112000,
    total_charges_paid: 850,
  },
  pnl: {
    today_realised: 5000,
    today_unrealised: -800,
    today_total: 4200,
    all_time_realised: 12000,
  },
  trades: { total: 40, winning: 24, losing: 16, win_rate: 60, today: 3, open_positions: 2 },
  strategies: { total: 20, active: 3, configured: 5, enabled_configs: 2 },
  signals: { active: 4, last_24h: 11 },
  risk: {
    capital: 1000000,
    deployed_capital: 112000,
    utilisation_pct: 11.2,
    max_capital_utilisation_pct: 80,
    realised_pnl: 5000,
    unrealised_pnl: -800,
    daily_loss_limit: -30000,
    daily_loss_used_pct: 0,
    open_positions: 2,
    max_open_positions: 5,
    trades_taken: 3,
    max_trades_per_day: 20,
    trading_halted: false,
    halt_reason: null,
    kill_switch: false,
  },
  modules: [
    { module: 'EQUITY', is_active: true },
    { module: 'FNO', is_active: false },
  ],
  data: { instruments: 5, instruments_with_usable_data: 5 },
  recent_trades: [
    {
      id: 'a',
      tradingsymbol: 'DEMOBANK',
      direction: 'BUY',
      quantity: 100,
      entry_price: 1450,
      exit_price: 1470,
      status: 'CLOSED',
      net_pnl: 1850,
      entry_time: '2024-06-03T09:30:00+05:30',
    },
  ],
}

function renderDashboard() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <Dashboard />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('Dashboard', () => {
  beforeEach(() => {
    api.get.mockReset()
  })

  it('renders headline metrics once loaded', async () => {
    api.get.mockResolvedValue({ data: payload })
    renderDashboard()

    await waitFor(() => expect(screen.getByText('Dashboard')).toBeInTheDocument())
    expect(screen.getByText('60.00%')).toBeInTheDocument()       // win rate
    expect(screen.getByText('24W / 16L of 40 closed')).toBeInTheDocument()
    expect(screen.getByText('2 / 5')).toBeInTheDocument()        // open positions
    expect(screen.getByText('DEMOBANK')).toBeInTheDocument()
  })

  it('always states that figures are simulated', async () => {
    api.get.mockResolvedValue({ data: payload })
    renderDashboard()
    await waitFor(() =>
      expect(screen.getByText(/Paper trading only\./)).toBeInTheDocument(),
    )
  })

  it('shows module activation state', async () => {
    api.get.mockResolvedValue({ data: payload })
    renderDashboard()
    await waitFor(() => expect(screen.getByText('EQUITY')).toBeInTheDocument())
    expect(screen.getByText('Active')).toBeInTheDocument()
    expect(screen.getByText('Inactive')).toBeInTheDocument()
  })

  it('surfaces a trading halt prominently', async () => {
    api.get.mockResolvedValue({
      data: {
        ...payload,
        risk: {
          ...payload.risk,
          trading_halted: true,
          halt_reason: 'Daily loss limit reached.',
        },
      },
    })
    renderDashboard()
    await waitFor(() =>
      expect(screen.getByText('Trading halted for today')).toBeInTheDocument(),
    )
    expect(screen.getByText('Daily loss limit reached.')).toBeInTheDocument()
  })

  it('shows an error state when the API fails', async () => {
    api.get.mockRejectedValue(new Error('backend unavailable'))
    renderDashboard()
    await waitFor(() =>
      expect(screen.getByText('Could not load this')).toBeInTheDocument(),
    )
  })
})
