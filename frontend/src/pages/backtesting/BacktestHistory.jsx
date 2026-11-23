import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { api } from '../../api/client'
import { PageHeader, Panel, StateBadge } from '../../components/ui'
import { DataTable } from '../../components/tables/DataTable'
import { dateIST, timeIST } from '../../lib/format'

export default function BacktestHistory() {
  const navigate = useNavigate()
  const { data, isLoading } = useQuery({
    queryKey: ['backtests'],
    queryFn: async () => (await api.get('/backtests')).data,
    refetchInterval: 10_000,
  })

  const columns = [
    { key: 'name', header: 'Name', render: (r) => <span className="font-medium">{r.name}</span> },
    { key: 'mode', header: 'Mode' },
    { key: 'timeframe', header: 'TF' },
    {
      key: 'period',
      header: 'Period',
      value: (r) => r.start_date,
      render: (r) => (
        <span className="text-2xs text-ink-faint">
          {dateIST(r.start_date)} → {dateIST(r.end_date)}
        </span>
      ),
    },
    { key: 'status', header: 'Status', render: (r) => <StateBadge state={r.status} /> },
    {
      key: 'progress_pct',
      header: 'Progress',
      align: 'right',
      numeric: true,
      render: (r) => `${r.progress_pct}%`,
    },
    {
      key: 'duration_seconds',
      header: 'Duration',
      align: 'right',
      numeric: true,
      render: (r) => (r.duration_seconds != null ? `${r.duration_seconds}s` : '—'),
    },
    {
      key: 'created',
      header: 'Started',
      value: (r) => r.started_at,
      render: (r) => (
        <span className="text-2xs text-ink-faint">{timeIST(r.started_at, { withDate: true })}</span>
      ),
    },
  ]

  return (
    <>
      <PageHeader
        title="Backtest History"
        description="Past runs. Open one for metrics, the equity curve and the trade-by-trade record."
      />
      <Panel bodyClass="p-0">
        <DataTable
          columns={columns}
          rows={data ?? []}
          loading={isLoading}
          exportName="backtests"
          onRowClick={(row) => navigate(`/backtesting/${row.id}`)}
          emptyTitle="No backtests yet"
          emptyDescription="Run one to see how a strategy would have performed — including costs."
        />
      </Panel>
    </>
  )
}
