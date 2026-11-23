import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../../api/client'
import { PageHeader, Panel, PaperTradingBanner, StateBadge, StatTile } from '../../components/ui'
import { DataTable } from '../../components/tables/DataTable'
import { money, percent, pnlClass, signed, timeIST } from '../../lib/format'

export default function TradeHistory() {
  const [page, setPage] = useState(1)

  const { data, isLoading } = useQuery({
    queryKey: ['trade-history', page],
    queryFn: async () =>
      (await api.get('/trading/history', { params: { page, page_size: 50 } })).data,
    keepPreviousData: true,
  })

  const rows = data?.items ?? []
  const netTotal = rows.reduce((sum, r) => sum + Number(r.net_pnl), 0)
  const grossTotal = rows.reduce((sum, r) => sum + Number(r.gross_pnl), 0)
  const chargesTotal = rows.reduce((sum, r) => sum + Number(r.charges), 0)
  const wins = rows.filter((r) => Number(r.net_pnl) > 0).length

  const columns = [
    { key: 'tradingsymbol', header: 'Symbol', render: (r) => <span className="font-medium">{r.tradingsymbol}</span> },
    { key: 'direction', header: 'Side', render: (r) => <StateBadge state={r.direction} /> },
    { key: 'quantity', header: 'Qty', align: 'right', numeric: true },
    { key: 'entry_price', header: 'Entry', align: 'right', numeric: true, render: (r) => money(r.entry_price) },
    { key: 'exit_price', header: 'Exit', align: 'right', numeric: true, render: (r) => money(r.exit_price) },
    {
      key: 'gross_pnl',
      header: 'Gross',
      align: 'right',
      numeric: true,
      render: (r) => <span className={pnlClass(r.gross_pnl)}>{signed(r.gross_pnl, money)}</span>,
    },
    { key: 'charges', header: 'Charges', align: 'right', numeric: true, render: (r) => money(r.charges) },
    {
      key: 'net_pnl',
      header: 'Net',
      align: 'right',
      numeric: true,
      render: (r) => (
        <span className={`font-semibold ${pnlClass(r.net_pnl)}`}>{signed(r.net_pnl, money)}</span>
      ),
    },
    { key: 'exit_reason', header: 'Exit reason', render: (r) => <StateBadge state={r.exit_reason} /> },
    { key: 'exit_time', header: 'Closed', render: (r) => <span className="text-2xs text-ink-faint">{timeIST(r.exit_time, { withDate: true })}</span> },
  ]

  return (
    <>
      <PageHeader
        title="Trade History"
        description="Closed paper trades. Gross, charges and net are shown separately — net is what actually matters."
      >
        <PaperTradingBanner />
      </PageHeader>

      <div className="mb-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatTile label="Gross P&L (page)" value={signed(grossTotal, money)} tone={grossTotal >= 0 ? 'profit' : 'loss'} />
        <StatTile label="Charges (page)" value={money(chargesTotal)} tone="warn" />
        <StatTile
          label="Net P&L (page)"
          value={signed(netTotal, money)}
          tone={netTotal >= 0 ? 'profit' : 'loss'}
          sub="After brokerage, taxes and slippage"
        />
        <StatTile
          label="Win rate (page)"
          value={rows.length ? percent((wins / rows.length) * 100) : '—'}
          sub={`${wins} of ${rows.length}`}
        />
      </div>

      <Panel bodyClass="p-0">
        <DataTable
          columns={columns}
          rows={rows}
          loading={isLoading}
          searchable
          page={page}
          total={data?.total}
          pageSize={50}
          onPageChange={setPage}
          exportName="trade-history"
          emptyTitle="No closed trades yet"
        />
      </Panel>
    </>
  )
}
