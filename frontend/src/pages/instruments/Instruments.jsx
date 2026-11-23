import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../../api/client'
import { Badge, PageHeader, Panel } from '../../components/ui'
import { DataTable } from '../../components/tables/DataTable'
import { money, number } from '../../lib/format'

export default function Instruments() {
  const [page, setPage] = useState(1)
  const [filters, setFilters] = useState({ q: '', exchange: '', sector: '' })

  const { data: sectors } = useQuery({
    queryKey: ['sectors'],
    queryFn: async () => (await api.get('/sectors')).data,
  })

  const { data, isLoading } = useQuery({
    queryKey: ['instruments', page, filters],
    queryFn: async () =>
      (
        await api.get('/instruments', {
          params: {
            page,
            page_size: 25,
            q: filters.q || undefined,
            exchange: filters.exchange || undefined,
            sector: filters.sector || undefined,
          },
        })
      ).data,
    keepPreviousData: true,
  })

  const columns = [
    {
      key: 'tradingsymbol',
      header: 'Symbol',
      render: (r) => (
        <span className="flex items-center gap-1.5">
          <span className="font-medium">{r.tradingsymbol}</span>
          {r.is_demo && <Badge tone="warn">Demo</Badge>}
        </span>
      ),
    },
    { key: 'name', header: 'Company' },
    { key: 'exchange', header: 'Exchange' },
    { key: 'sector', header: 'Sector', render: (r) => r.sector ?? '—' },
    {
      key: 'last_price',
      header: 'Last price',
      align: 'right',
      numeric: true,
      render: (r) => (r.last_price != null ? money(r.last_price) : '—'),
    },
    {
      key: 'avg_daily_volume',
      header: 'Avg volume',
      align: 'right',
      numeric: true,
      render: (r) => (r.avg_daily_volume != null ? number(r.avg_daily_volume, 0) : '—'),
    },
    {
      key: 'is_active',
      header: 'Status',
      render: (r) => (
        <Badge tone={r.is_active ? 'profit' : 'neutral'}>
          {r.is_active ? 'Active' : 'Inactive'}
        </Badge>
      ),
    },
  ]

  return (
    <>
      <PageHeader
        title="Instruments"
        description="The tradable universe. Search by symbol or company, and filter by exchange and sector."
      />

      <Panel bodyClass="p-0">
        <div className="flex flex-wrap gap-2 border-b border-base-700 px-4 py-3">
          <input
            className="input max-w-xs"
            placeholder="Symbol or company name…"
            value={filters.q}
            onChange={(e) => {
              setFilters({ ...filters, q: e.target.value })
              setPage(1)
            }}
            aria-label="Search instruments"
          />
          <select
            className="input max-w-[140px]"
            value={filters.exchange}
            onChange={(e) => {
              setFilters({ ...filters, exchange: e.target.value })
              setPage(1)
            }}
            aria-label="Exchange"
          >
            <option value="">All exchanges</option>
            <option value="NSE">NSE</option>
            <option value="BSE">BSE</option>
          </select>
          <select
            className="input max-w-[180px]"
            value={filters.sector}
            onChange={(e) => {
              setFilters({ ...filters, sector: e.target.value })
              setPage(1)
            }}
            aria-label="Sector"
          >
            <option value="">All sectors</option>
            {sectors?.map((s) => (
              <option key={s.id} value={s.name}>
                {s.name}
              </option>
            ))}
          </select>
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
          exportName="instruments"
          emptyTitle="No instruments match"
          emptyDescription="Adjust the filters, or import an instrument master from the broker once credentials are configured."
        />
      </Panel>
    </>
  )
}
