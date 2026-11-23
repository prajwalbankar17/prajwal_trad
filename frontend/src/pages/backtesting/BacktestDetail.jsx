import { useQuery } from '@tanstack/react-query'
import { useParams } from 'react-router-dom'
import {
  Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { AlertTriangle, Info } from 'lucide-react'
import { api, errorMessage } from '../../api/client'
import {
  Badge, ErrorState, Loading, PageHeader, Panel, StatTile, StateBadge,
} from '../../components/ui'
import { DataTable } from '../../components/tables/DataTable'
import { money, number, percent, pnlClass, signed, timeIST } from '../../lib/format'

export default function BacktestDetail() {
  const { jobId } = useParams()

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['backtest', jobId],
    queryFn: async () => (await api.get(`/backtests/${jobId}`)).data,
    refetchInterval: (query) =>
      ['QUEUED', 'RUNNING'].includes(query.state.data?.status) ? 2000 : false,
  })

  const { data: trades } = useQuery({
    queryKey: ['backtest-trades', jobId],
    queryFn: async () => (await api.get(`/backtests/${jobId}/trades`)).data,
    enabled: data?.status === 'COMPLETED',
  })

  if (isLoading) return <Loading />
  if (error) return <ErrorState message={errorMessage(error)} onRetry={refetch} />

  const overall = data.overall
  const oos = data.breakdowns?.find((b) => b.window === 'OUT_OF_SAMPLE')

  const tradeColumns = [
    { key: 'tradingsymbol', header: 'Symbol' },
    { key: 'direction', header: 'Side', render: (r) => <StateBadge state={r.direction} /> },
    { key: 'quantity', header: 'Qty', align: 'right', numeric: true },
    { key: 'entry_price', header: 'Entry', align: 'right', numeric: true, render: (r) => number(r.entry_price) },
    { key: 'exit_price', header: 'Exit', align: 'right', numeric: true, render: (r) => number(r.exit_price) },
    { key: 'charges', header: 'Charges', align: 'right', numeric: true, render: (r) => money(r.charges) },
    {
      key: 'net_pnl',
      header: 'Net P&L',
      align: 'right',
      numeric: true,
      render: (r) => <span className={pnlClass(r.net_pnl)}>{signed(r.net_pnl, money)}</span>,
    },
    { key: 'exit_reason', header: 'Exit', render: (r) => <StateBadge state={r.exit_reason} /> },
    {
      key: 'entry_time',
      header: 'Entered',
      render: (r) => <span className="text-2xs text-ink-faint">{timeIST(r.entry_time, { withDate: true })}</span>,
    },
  ]

  return (
    <>
      <PageHeader
        title={data.name}
        description={`${data.timeframe} · ${data.start_date} → ${data.end_date} · ${data.mode} mode`}
        actions={<StateBadge state={data.status} />}
      />

      {data.status === 'RUNNING' && (
        <Panel className="mb-4">
          <div className="flex items-center gap-3">
            <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-base-700">
              <div
                className="h-full bg-accent transition-all"
                style={{ width: `${data.progress_pct}%` }}
              />
            </div>
            <span className="tnum font-mono text-xs">{data.progress_pct}%</span>
          </div>
        </Panel>
      )}

      {data.error && <ErrorState title="This backtest failed" message={data.error} />}

      {data.warnings?.length > 0 && (
        <div className="mb-4 space-y-1.5">
          {data.warnings.slice(0, 5).map((w, i) => (
            <div
              key={i}
              className="flex items-start gap-2 rounded-md border border-warn/25 bg-warn-soft px-3 py-2"
            >
              <AlertTriangle size={13} className="mt-0.5 shrink-0 text-warn" />
              <p className="text-2xs leading-relaxed text-warn">{w}</p>
            </div>
          ))}
        </div>
      )}

      {overall && (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
            <StatTile label="Total trades" value={overall.total_trades} />
            <StatTile
              label="Win rate"
              value={percent(overall.win_rate)}
              sub={`${overall.winning_trades}W / ${overall.losing_trades}L`}
            />
            <StatTile
              label="Net profit"
              value={signed(overall.net_profit, (v) => money(v, { compact: true }))}
              tone={overall.net_profit >= 0 ? 'profit' : 'loss'}
              sub={`after ${money(overall.total_charges, { compact: true })} costs`}
            />
            <StatTile
              label="Profit factor"
              value={overall.profit_factor != null ? number(overall.profit_factor) : '—'}
              tone={
                overall.profit_factor == null
                  ? 'neutral'
                  : overall.profit_factor >= 1.5
                    ? 'profit'
                    : overall.profit_factor >= 1
                      ? 'neutral'
                      : 'loss'
              }
            />
            <StatTile
              label="Max drawdown"
              value={percent(overall.max_drawdown_pct)}
              sub={money(overall.max_drawdown, { compact: true })}
              tone="loss"
            />
          </div>

          <div className="mt-3 grid grid-cols-2 gap-3 lg:grid-cols-5">
            <StatTile label="Expectancy" value={overall.expectancy != null ? money(overall.expectancy) : '—'} />
            <StatTile label="Avg R:R" value={overall.average_rr != null ? number(overall.average_rr) : '—'} />
            <StatTile
              label="Sharpe"
              value={overall.sharpe_ratio != null ? number(overall.sharpe_ratio) : '—'}
              hint={overall.sharpe_ratio == null ? 'Too few trading days to be meaningful.' : undefined}
            />
            <StatTile
              label="Sortino"
              value={overall.sortino_ratio != null ? number(overall.sortino_ratio) : '—'}
            />
            <StatTile
              label="Max losing streak"
              value={overall.max_consecutive_losses}
              sub={`best run ${overall.max_consecutive_wins}`}
            />
          </div>

          {overall.notes?.length > 0 && (
            <div className="mt-3 space-y-1.5">
              {overall.notes.map((n, i) => (
                <div
                  key={i}
                  className="flex items-start gap-2 rounded-md border border-base-600 bg-base-800 px-3 py-2"
                >
                  <Info size={13} className="mt-0.5 shrink-0 text-ink-faint" />
                  <p className="text-2xs leading-relaxed text-ink-muted">{n}</p>
                </div>
              ))}
            </div>
          )}

          {oos?.overfitting_flags && (
            <Panel
              title="In-sample vs out-of-sample"
              subtitle="Does the edge survive data the parameters never saw?"
              className="mt-4"
            >
              <div className="flex flex-wrap items-center gap-2">
                <Badge tone={oos.overfitting_flags.likely_overfit ? 'loss' : 'profit'}>
                  {oos.overfitting_flags.likely_overfit
                    ? 'Likely overfitted'
                    : 'No strong overfitting signal'}
                </Badge>
              </div>
              {oos.overfitting_flags.flags?.length > 0 && (
                <ul className="mt-2.5 space-y-1">
                  {oos.overfitting_flags.flags.map((f, i) => (
                    <li key={i} className="text-2xs leading-relaxed text-warn">
                      • {f}
                    </li>
                  ))}
                </ul>
              )}
              <div className="mt-3 grid gap-3 sm:grid-cols-2">
                {['in_sample', 'out_of_sample'].map((key) => {
                  const w = oos.overfitting_flags[key]
                  return (
                    <div key={key} className="rounded-md bg-base-800 p-3">
                      <p className="label mb-2">{key.replace(/_/g, ' ')}</p>
                      <dl className="space-y-1 text-2xs">
                        <div className="flex justify-between">
                          <dt className="text-ink-faint">Trades</dt>
                          <dd className="tnum font-mono">{w.trades}</dd>
                        </div>
                        <div className="flex justify-between">
                          <dt className="text-ink-faint">Win rate</dt>
                          <dd className="tnum font-mono">{percent(w.win_rate)}</dd>
                        </div>
                        <div className="flex justify-between">
                          <dt className="text-ink-faint">Profit factor</dt>
                          <dd className="tnum font-mono">
                            {w.profit_factor != null ? number(w.profit_factor) : '—'}
                          </dd>
                        </div>
                        <div className="flex justify-between">
                          <dt className="text-ink-faint">Net profit</dt>
                          <dd className={`tnum font-mono ${pnlClass(w.net_profit)}`}>
                            {signed(w.net_profit, (v) => money(v, { compact: true }))}
                          </dd>
                        </div>
                      </dl>
                    </div>
                  )
                })}
              </div>
            </Panel>
          )}

          {data.equity_curve?.length > 1 && (
            <Panel title="Equity curve" subtitle="Net of all modelled costs" className="mt-4">
              <ResponsiveContainer width="100%" height={260}>
                <AreaChart data={data.equity_curve.map((p, i) => ({ ...p, i }))}>
                  <defs>
                    <linearGradient id="equityFill" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#4c8dff" stopOpacity={0.35} />
                      <stop offset="100%" stopColor="#4c8dff" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid stroke="#1e2430" strokeDasharray="3 3" />
                  <XAxis dataKey="i" hide />
                  <YAxis
                    stroke="#6b7585"
                    tick={{ fontSize: 10 }}
                    tickFormatter={(v) => money(v, { compact: true })}
                    domain={['dataMin', 'dataMax']}
                    width={70}
                  />
                  <Tooltip
                    contentStyle={{
                      background: '#131720',
                      border: '1px solid #2a3140',
                      borderRadius: 6,
                      fontSize: 11,
                    }}
                    formatter={(v) => money(v)}
                    labelFormatter={() => ''}
                  />
                  <Area
                    type="monotone"
                    dataKey="equity"
                    stroke="#4c8dff"
                    strokeWidth={1.5}
                    fill="url(#equityFill)"
                  />
                </AreaChart>
              </ResponsiveContainer>
            </Panel>
          )}

          {data.breakdowns?.filter((b) => b.scope === 'INSTRUMENT').length > 0 && (
            <Panel title="By instrument" className="mt-4" bodyClass="p-0">
              <DataTable
                searchable={false}
                columns={[
                  { key: 'scope_ref', header: 'Instrument' },
                  { key: 'total_trades', header: 'Trades', align: 'right', numeric: true },
                  {
                    key: 'win_rate',
                    header: 'Win rate',
                    align: 'right',
                    numeric: true,
                    render: (r) => percent(r.win_rate),
                  },
                  {
                    key: 'total_charges',
                    header: 'Charges',
                    align: 'right',
                    numeric: true,
                    render: (r) => money(r.total_charges),
                  },
                  {
                    key: 'net_profit',
                    header: 'Net',
                    align: 'right',
                    numeric: true,
                    render: (r) => (
                      <span className={pnlClass(r.net_profit)}>{signed(r.net_profit, money)}</span>
                    ),
                  },
                  {
                    key: 'max_drawdown_pct',
                    header: 'Max DD',
                    align: 'right',
                    numeric: true,
                    render: (r) => percent(r.max_drawdown_pct),
                  },
                ]}
                rows={data.breakdowns.filter((b) => b.scope === 'INSTRUMENT')}
                rowKey={(r) => r.id}
                exportName="backtest-by-instrument"
              />
            </Panel>
          )}

          {trades?.length > 0 && (
            <Panel title="Trade by trade" className="mt-4" bodyClass="p-0">
              <DataTable
                columns={tradeColumns}
                rows={trades}
                rowKey={(r, i) => i}
                exportName="backtest-trades"
                pageSize={50}
              />
            </Panel>
          )}
        </>
      )}
    </>
  )
}
