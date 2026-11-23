import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api, errorMessage } from '../../api/client'
import {
  Badge, EmptyState, ErrorState, Loading, PageHeader, Panel,
} from '../../components/ui'
import { CandleChart } from '../../components/charts/CandleChart'

const TIMEFRAMES = ['1m', '3m', '5m', '10m', '15m', '30m', '1h', '1d']

export default function HistoricalData() {
  const [instrumentId, setInstrumentId] = useState('')
  const [timeframe, setTimeframe] = useState('15m')

  const { data: instruments } = useQuery({
    queryKey: ['instruments', 'chart-picker'],
    queryFn: async () => (await api.get('/instruments', { params: { page_size: 200 } })).data,
  })

  const { data, isLoading, error } = useQuery({
    queryKey: ['candles', instrumentId, timeframe],
    queryFn: async () =>
      (
        await api.get('/market-data/candles', {
          params: { instrument_id: instrumentId, timeframe, limit: 1000 },
        })
      ).data,
    enabled: !!instrumentId,
  })

  return (
    <>
      <PageHeader
        title="Historical Data"
        description="Stored candles. Intraday timeframes above one minute are aggregated from 1m data on read, anchored to the 09:15 session open."
      />

      <Panel bodyClass="p-0">
        <div className="flex flex-wrap items-center gap-2 border-b border-base-700 px-4 py-3">
          <select
            className="input max-w-xs"
            value={instrumentId}
            onChange={(e) => setInstrumentId(e.target.value)}
            aria-label="Instrument"
          >
            <option value="">Select an instrument…</option>
            {(instruments?.items ?? []).map((i) => (
              <option key={i.id} value={i.id}>
                {i.tradingsymbol} {i.is_demo ? '(demo)' : ''}
              </option>
            ))}
          </select>

          <div className="flex gap-1">
            {TIMEFRAMES.map((tf) => (
              <button
                key={tf}
                type="button"
                onClick={() => setTimeframe(tf)}
                className={
                  tf === timeframe
                    ? 'btn-primary px-2.5 py-1 text-xs'
                    : 'btn-ghost px-2.5 py-1 text-xs'
                }
              >
                {tf}
              </button>
            ))}
          </div>

          {data && (
            <div className="ml-auto flex items-center gap-2">
              <Badge tone={data.source === 'MOCK' ? 'warn' : 'neutral'}>
                {data.source === 'MOCK' ? 'Synthetic demo data' : 'Imported historical'}
              </Badge>
              <span className="text-2xs text-ink-faint tnum">{data.count} candles</span>
            </div>
          )}
        </div>

        <div className="p-4">
          {!instrumentId ? (
            <EmptyState
              title="Pick an instrument"
              description="Choose an instrument above to plot its stored candles."
            />
          ) : isLoading ? (
            <Loading label="Loading candles…" />
          ) : error ? (
            <ErrorState message={errorMessage(error)} />
          ) : data.candles.length === 0 ? (
            <EmptyState
              title="No candles stored"
              description="This instrument has no data at this timeframe yet. Import historical data under Data Imports."
            />
          ) : (
            <CandleChart candles={data.candles} />
          )}
        </div>
      </Panel>
    </>
  )
}
