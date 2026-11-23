import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../../api/client'
import {
  Badge, PageHeader, Panel, PaperTradingBanner, StateBadge,
} from '../../components/ui'
import { DataTable } from '../../components/tables/DataTable'
import { money, number, timeIST } from '../../lib/format'
import { SignalDetail } from './SignalDetail'

export default function Signals() {
  const [page, setPage] = useState(1)
  const [state, setState] = useState('')
  const [selected, setSelected] = useState(null)

  const { data, isLoading } = useQuery({
    queryKey: ['signals', page, state],
    queryFn: async () =>
      (await api.get('/signals', { params: { page, page_size: 25, state: state || undefined } }))
        .data,
    keepPreviousData: true,
    refetchInterval: 30_000,
  })

  const columns = [
    { key: 'tradingsymbol', header: 'Symbol', render: (r) => <span className="font-medium">{r.tradingsymbol}</span> },
    { key: 'direction', header: 'Side', render: (r) => <StateBadge state={r.direction} /> },
    { key: 'timeframe', header: 'TF' },
    { key: 'entry_price', header: 'Entry', align: 'right', numeric: true, render: (r) => money(r.entry_price) },
    { key: 'stop_loss', header: 'Stop', align: 'right', numeric: true, render: (r) => money(r.stop_loss) },
    { key: 'target', header: 'Target', align: 'right', numeric: true, render: (r) => money(r.target) },
    {
      key: 'risk_reward',
      header: 'R:R',
      align: 'right',
      numeric: true,
      render: (r) => (r.risk_reward ? `${number(r.risk_reward, 2)}` : '—'),
    },
    { key: 'suggested_quantity', header: 'Qty', align: 'right', numeric: true },
    { key: 'state', header: 'State', render: (r) => <StateBadge state={r.state} /> },
    {
      key: 'generated_at',
      header: 'Generated',
      render: (r) => <span className="text-2xs text-ink-faint">{timeIST(r.generated_at, { withDate: true })}</span>,
    },
  ]

  return (
    <>
      <PageHeader
        title="Signals"
        description="Proposals from strategy configurations. A signal is not a trade — it becomes one only after risk validation and paper execution."
      >
        <PaperTradingBanner />
      </PageHeader>

      <Panel bodyClass="p-0">
        <div className="flex flex-wrap items-center gap-2 border-b border-base-700 px-4 py-3">
          <select
            className="input max-w-[200px]"
            value={state}
            onChange={(e) => {
              setState(e.target.value)
              setPage(1)
            }}
            aria-label="Filter by state"
          >
            <option value="">All states</option>
            {['GENERATED', 'VALIDATED', 'REJECTED', 'PAPER_EXECUTED', 'EXPIRED', 'CANCELLED'].map(
              (s) => (
                <option key={s} value={s}>
                  {s.replace('_', ' ')}
                </option>
              ),
            )}
          </select>
          <Badge tone="neutral">Click a row for the full condition breakdown</Badge>
        </div>

        <DataTable
          columns={columns}
          rows={data?.items ?? []}
          loading={isLoading}
          searchable={false}
          page={page}
          total={data?.total}
          pageSize={25}
          onPageChange={setPage}
          exportName="signals"
          onRowClick={(row) => setSelected(row.id)}
          emptyTitle="No signals yet"
          emptyDescription="Signals appear once a strategy configuration is enabled and evaluated against market data."
        />
      </Panel>

      {selected && <SignalDetail signalId={selected} onClose={() => setSelected(null)} />}
    </>
  )
}
