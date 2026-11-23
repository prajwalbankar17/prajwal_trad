import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { RefreshCw } from 'lucide-react'
import { api, errorMessage } from '../../api/client'
import { PageHeader, Panel, PaperTradingBanner, StateBadge } from '../../components/ui'
import { DataTable } from '../../components/tables/DataTable'
import { money, pnlClass, signed, timeIST } from '../../lib/format'

export default function Positions() {
  const queryClient = useQueryClient()
  const [notice, setNotice] = useState(null)

  const { data, isLoading } = useQuery({
    queryKey: ['positions', 'open'],
    queryFn: async () =>
      (await api.get('/trading/positions', { params: { open_only: true, page_size: 100 } })).data,
    refetchInterval: 15_000,
  })

  const monitor = useMutation({
    mutationFn: async () => (await api.post('/trading/positions/monitor')).data,
    onSuccess: (result) => {
      setNotice(`Checked ${result.checked} position(s).`)
      queryClient.invalidateQueries({ queryKey: ['positions'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    },
    onError: (error) => setNotice(errorMessage(error)),
  })

  const exitPosition = useMutation({
    mutationFn: async (id) =>
      (await api.post(`/trading/positions/${id}/exit`, { reason: 'MANUAL' })).data,
    onSuccess: () => {
      setNotice('Position closed at the latest available price.')
      queryClient.invalidateQueries({ queryKey: ['positions'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    },
    onError: (error) => setNotice(errorMessage(error)),
  })

  const columns = [
    { key: 'tradingsymbol', header: 'Symbol', render: (r) => <span className="font-medium">{r.tradingsymbol}</span> },
    { key: 'direction', header: 'Side', render: (r) => <StateBadge state={r.direction} /> },
    { key: 'remaining_quantity', header: 'Qty', align: 'right', numeric: true },
    { key: 'entry_price', header: 'Entry', align: 'right', numeric: true, render: (r) => money(r.entry_price) },
    { key: 'stop_loss', header: 'Stop', align: 'right', numeric: true, render: (r) => money(r.stop_loss) },
    { key: 'target', header: 'Target', align: 'right', numeric: true, render: (r) => money(r.target) },
    {
      key: 'unrealised_pnl',
      header: 'Unrealised',
      align: 'right',
      numeric: true,
      render: (r) => (
        <span className={pnlClass(r.unrealised_pnl)}>{signed(r.unrealised_pnl, money)}</span>
      ),
    },
    { key: 'capital_deployed', header: 'Deployed', align: 'right', numeric: true, render: (r) => money(r.capital_deployed) },
    { key: 'entry_time', header: 'Entered', render: (r) => <span className="text-2xs text-ink-faint">{timeIST(r.entry_time, { withDate: true })}</span> },
    {
      key: 'actions',
      header: '',
      sortable: false,
      render: (r) => (
        <button
          type="button"
          className="btn-danger py-1 text-xs"
          onClick={(e) => {
            e.stopPropagation()
            exitPosition.mutate(r.id)
          }}
          disabled={exitPosition.isPending}
        >
          Exit
        </button>
      ),
    },
  ]

  return (
    <>
      <PageHeader
        title="Active Positions"
        description="Open simulated positions. Monitoring runs for these even when the trading module is inactive."
        actions={
          <button
            type="button"
            className="btn-ghost"
            onClick={() => monitor.mutate()}
            disabled={monitor.isPending}
          >
            <RefreshCw size={13} className={monitor.isPending ? 'animate-spin' : ''} />
            Run monitor pass
          </button>
        }
      >
        <PaperTradingBanner />
      </PageHeader>

      {notice && (
        <p className="mb-3 rounded-md border border-base-600 bg-base-800 px-3 py-2 text-xs text-ink-muted">
          {notice}
        </p>
      )}

      <Panel bodyClass="p-0">
        <DataTable
          columns={columns}
          rows={data?.items ?? []}
          loading={isLoading}
          exportName="open-positions"
          emptyTitle="No open positions"
          emptyDescription="Positions appear here once a validated signal is executed on paper."
        />
      </Panel>
    </>
  )
}
