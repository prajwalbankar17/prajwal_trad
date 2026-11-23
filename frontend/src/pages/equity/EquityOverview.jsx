import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api, errorMessage } from '../../api/client'
import {
  Badge, ErrorState, Loading, PageHeader, Panel, PaperTradingBanner, StatTile, Toggle,
} from '../../components/ui'
import { money, percent, signed } from '../../lib/format'
import { useHasPermission } from '../../store/auth'

export default function EquityOverview() {
  const queryClient = useQueryClient()
  const canActivate = useHasPermission('module:activate')

  const { data: dashboard, isLoading, error } = useQuery({
    queryKey: ['dashboard'],
    queryFn: async () => (await api.get('/dashboard')).data,
  })

  const { data: modules } = useQuery({
    queryKey: ['trading-modules'],
    queryFn: async () => (await api.get('/trading-modules')).data,
  })

  const toggleModule = useMutation({
    mutationFn: async ({ module, active }) =>
      (await api.post(`/trading-modules/${module}`, null, { params: { active } })).data,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['trading-modules'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    },
  })

  if (isLoading) return <Loading />
  if (error) return <ErrorState message={errorMessage(error)} />

  const equity = modules?.find((m) => m.module === 'EQUITY')
  const { pnl, trades, risk } = dashboard

  return (
    <>
      <PageHeader
        title="Equity Trading"
        description="Module status, today's simulated performance and quick links into signals and positions."
      >
        <PaperTradingBanner />
      </PageHeader>

      <Panel
        title="Equity module"
        subtitle="Controls new signals and new entries only"
        className="mb-4"
        actions={
          <Toggle
            checked={!!equity?.is_active}
            disabled={!canActivate || toggleModule.isPending}
            onChange={(next) => toggleModule.mutate({ module: 'EQUITY', active: next })}
            label={equity?.is_active ? 'Active' : 'Inactive'}
            hint={canActivate ? undefined : 'You do not have the module:activate permission.'}
          />
        }
      >
        <p className="text-xs leading-relaxed text-ink-muted">
          Deactivating stops new signal generation and blocks new positions.{' '}
          <strong className="text-ink">Open positions are not abandoned</strong> — stop-loss,
          target and exit processing continue until every position is closed.
        </p>
        {toggleModule.isError && (
          <p className="mt-2 text-xs text-loss">{errorMessage(toggleModule.error)}</p>
        )}
      </Panel>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatTile
          label="Today's net P&L"
          value={signed(pnl.today_total, money)}
          tone={pnl.today_total >= 0 ? 'profit' : 'loss'}
        />
        <StatTile label="Open positions" value={trades.open_positions} />
        <StatTile label="Trades today" value={`${risk.trades_taken} / ${risk.max_trades_per_day}`} />
        <StatTile
          label="Capital utilisation"
          value={percent(risk.utilisation_pct)}
          sub={`cap ${percent(risk.max_capital_utilisation_pct)}`}
        />
      </div>

      <div className="mt-4 grid gap-3 sm:grid-cols-3">
        {[
          ['Signals', '/equity/signals', 'Review proposals and why each passed or failed'],
          ['Active Positions', '/equity/positions', 'Monitor and exit open simulated positions'],
          ['Trade History', '/equity/history', 'Closed trades with gross, charges and net'],
        ].map(([label, to, description]) => (
          <Link key={to} to={to} className="panel p-4 transition-colors hover:border-accent/40">
            <p className="text-sm font-medium">{label}</p>
            <p className="mt-1 text-2xs leading-relaxed text-ink-faint">{description}</p>
          </Link>
        ))}
      </div>

      <Panel title="Risk guardrails" className="mt-4">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {[
            ['Daily loss limit', money(Math.abs(risk.daily_loss_limit))],
            ['Used', percent(risk.daily_loss_used_pct)],
            ['Max open positions', risk.max_open_positions],
            ['Kill switch', risk.kill_switch ? 'ENGAGED' : 'Off'],
          ].map(([label, value]) => (
            <div key={label}>
              <p className="label">{label}</p>
              <p className="mt-1 tnum font-mono text-sm">{value}</p>
            </div>
          ))}
        </div>
        {risk.trading_halted && (
          <Badge tone="loss" className="mt-3">
            Trading halted: {risk.halt_reason}
          </Badge>
        )}
      </Panel>
    </>
  )
}
