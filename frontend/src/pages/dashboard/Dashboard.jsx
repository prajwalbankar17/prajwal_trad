import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import {
  Activity, AlertTriangle, BarChart3, Layers, Shield, TrendingUp, Wallet,
} from 'lucide-react'
import { api, errorMessage } from '../../api/client'
import {
  Badge, ErrorState, Loading, PageHeader, Panel, PaperTradingBanner, StatTile, StateBadge,
} from '../../components/ui'
import { money, percent, pnlClass, signed, timeIST } from '../../lib/format'

export default function Dashboard() {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['dashboard'],
    queryFn: async () => (await api.get('/dashboard')).data,
    refetchInterval: 30_000,
  })

  if (isLoading) return <Loading label="Loading dashboard…" />
  if (error) return <ErrorState message={errorMessage(error)} onRetry={refetch} />

  const { capital, pnl, trades, strategies, signals, risk, data: coverage } = data

  return (
    <>
      <PageHeader
        title="Dashboard"
        description="Simulated portfolio, risk utilisation and strategy activity at a glance."
        actions={
          <Badge tone={data.market.status === 'OPEN' ? 'profit' : 'neutral'}>
            Market {data.market.status.replace('_', ' ')}
          </Badge>
        }
      >
        <PaperTradingBanner />
      </PageHeader>

      {risk.trading_halted && (
        <div className="mb-4 flex items-start gap-2 rounded-md border border-loss/30 bg-loss-soft px-3 py-2.5">
          <AlertTriangle size={15} className="text-loss mt-0.5 shrink-0" />
          <div>
            <p className="text-xs font-semibold text-loss">Trading halted for today</p>
            <p className="mt-0.5 text-2xs text-loss/80">{risk.halt_reason}</p>
          </div>
        </div>
      )}

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatTile
          label="Total capital"
          value={money(capital.total_capital, { compact: true })}
          sub={`${money(capital.available_capital, { compact: true })} available`}
          icon={Wallet}
        />
        <StatTile
          label="Today's P&L"
          value={signed(pnl.today_total, (v) => money(v, { compact: true }))}
          sub={`Realised ${money(pnl.today_realised, { compact: true })} · Unrealised ${money(pnl.today_unrealised, { compact: true })}`}
          tone={pnl.today_total > 0 ? 'profit' : pnl.today_total < 0 ? 'loss' : 'neutral'}
          icon={TrendingUp}
          hint="Net of modelled brokerage, taxes and slippage."
        />
        <StatTile
          label="Win rate"
          value={percent(trades.win_rate)}
          sub={`${trades.winning}W / ${trades.losing}L of ${trades.total} closed`}
          tone={trades.total < 30 ? 'warn' : 'neutral'}
          icon={BarChart3}
          hint={
            trades.total < 30
              ? 'Fewer than 30 trades — too small a sample to be meaningful.'
              : undefined
          }
        />
        <StatTile
          label="Risk used"
          value={percent(risk.daily_loss_used_pct)}
          sub={`of the ${money(Math.abs(risk.daily_loss_limit), { compact: true })} daily loss limit`}
          tone={risk.daily_loss_used_pct > 70 ? 'loss' : 'neutral'}
          icon={Shield}
        />
      </div>

      <div className="mt-3 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatTile
          label="Open positions"
          value={`${trades.open_positions} / ${risk.max_open_positions}`}
          sub={`${money(risk.deployed_capital, { compact: true })} deployed`}
          icon={Layers}
        />
        <StatTile
          label="Trades today"
          value={`${risk.trades_taken} / ${risk.max_trades_per_day}`}
          sub="Daily cap from the risk profile"
        />
        <StatTile
          label="Active signals"
          value={signals.active}
          sub={`${signals.last_24h} generated in 24h`}
          icon={Activity}
        />
        <StatTile
          label="Strategies"
          value={`${strategies.enabled_configs} enabled`}
          sub={`${strategies.configured} configured of ${strategies.total} available`}
        />
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-3">
        <Panel
          title="Recent paper trades"
          subtitle="Most recent simulated positions"
          className="lg:col-span-2"
          bodyClass="p-0"
          actions={
            <Link to="/equity/history" className="btn-ghost py-1 text-xs">
              View all
            </Link>
          }
        >
          {data.recent_trades.length === 0 ? (
            <p className="px-4 py-8 text-center text-xs text-ink-faint">
              No paper trades yet. Enable a strategy configuration and activate the Equity
              module to start generating them.
            </p>
          ) : (
            <table className="w-full">
              <thead className="bg-base-800">
                <tr>
                  <th className="th">Symbol</th>
                  <th className="th">Side</th>
                  <th className="th text-right">Qty</th>
                  <th className="th text-right">Entry</th>
                  <th className="th text-right">Exit</th>
                  <th className="th text-right">Net P&L</th>
                  <th className="th">Status</th>
                  <th className="th">Time</th>
                </tr>
              </thead>
              <tbody>
                {data.recent_trades.map((t) => (
                  <tr key={t.id} className="border-t border-base-700/60">
                    <td className="td font-medium">{t.tradingsymbol}</td>
                    <td className="td">
                      <StateBadge state={t.direction} />
                    </td>
                    <td className="td text-right tnum font-mono text-xs">{t.quantity}</td>
                    <td className="td text-right tnum font-mono text-xs">{t.entry_price}</td>
                    <td className="td text-right tnum font-mono text-xs">
                      {t.exit_price ?? '—'}
                    </td>
                    <td
                      className={`td text-right tnum font-mono text-xs font-semibold ${pnlClass(t.net_pnl)}`}
                    >
                      {signed(t.net_pnl, (v) => money(v))}
                    </td>
                    <td className="td">
                      <StateBadge state={t.status} />
                    </td>
                    <td className="td text-2xs text-ink-faint">{timeIST(t.entry_time)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Panel>

        <div className="space-y-4">
          <Panel title="Trading modules" subtitle="Independent activation">
            <div className="space-y-2">
              {data.modules.map((m) => (
                <div
                  key={m.module}
                  className="flex items-center justify-between rounded-md bg-base-800 px-3 py-2"
                >
                  <span className="text-sm">{m.module}</span>
                  <Badge tone={m.is_active ? 'profit' : 'neutral'}>
                    {m.is_active ? 'Active' : 'Inactive'}
                  </Badge>
                </div>
              ))}
            </div>
            <p className="mt-3 text-2xs leading-relaxed text-ink-faint">
              An inactive module stops new signals and entries. Open positions keep being
              monitored for stop-loss and target.
            </p>
          </Panel>

          <Panel title="Data coverage">
            <dl className="space-y-2 text-sm">
              <div className="flex justify-between">
                <dt className="text-ink-muted">Instruments</dt>
                <dd className="tnum font-mono text-xs">{coverage.instruments}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-ink-muted">With usable history</dt>
                <dd className="tnum font-mono text-xs">
                  {coverage.instruments_with_usable_data}
                </dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-ink-muted">Charges paid</dt>
                <dd className="tnum font-mono text-xs">{money(capital.total_charges_paid)}</dd>
              </div>
            </dl>
            <Link to="/data/quality" className="btn-ghost mt-3 w-full text-xs">
              Inspect data quality
            </Link>
          </Panel>
        </div>
      </div>
    </>
  )
}
