import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../../api/client'
import {
  Badge, EmptyState, Loading, PageHeader, Panel, StatTile,
} from '../../components/ui'
import { DataTable } from '../../components/tables/DataTable'
import { number, percent } from '../../lib/format'

export default function DataQuality() {
  const [instrumentId, setInstrumentId] = useState('')

  const { data: summary, isLoading } = useQuery({
    queryKey: ['dq-summary'],
    queryFn: async () => (await api.get('/market-data/quality/summary')).data,
  })

  const { data: availability } = useQuery({
    queryKey: ['availability'],
    queryFn: async () =>
      (await api.get('/market-data/availability', { params: { page_size: 200 } })).data,
  })

  const { data: report, isFetching } = useQuery({
    queryKey: ['dq-report', instrumentId],
    queryFn: async () =>
      (await api.get(`/market-data/quality/${instrumentId}`, { params: { timeframe: '1m' } }))
        .data,
    enabled: !!instrumentId,
  })

  if (isLoading) return <Loading />

  return (
    <>
      <PageHeader
        title="Data Quality"
        description="Coverage, gaps and integrity per instrument. Incomplete history is surfaced rather than quietly excluded from a backtest."
      />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatTile
          label="Intraday candle rows"
          value={number(summary.intraday_candle_rows, 0)}
          sub={summary.earliest_intraday_ts?.slice(0, 10) ?? 'no data'}
        />
        <StatTile label="Daily candle rows" value={number(summary.daily_candle_rows, 0)} />
        <StatTile
          label="Tracked instrument/TF"
          value={summary.instrument_timeframes_tracked}
        />
        <StatTile
          label="Usable for research"
          value={summary.usable_instrument_timeframes}
          tone={
            summary.usable_instrument_timeframes < summary.instrument_timeframes_tracked
              ? 'warn'
              : 'profit'
          }
          sub="≥90% session coverage"
        />
      </div>

      <Panel title="Availability by instrument" className="mt-4" bodyClass="p-0">
        <DataTable
          columns={[
            { key: 'tradingsymbol', header: 'Symbol' },
            { key: 'timeframe', header: 'TF' },
            { key: 'record_count', header: 'Rows', align: 'right', numeric: true, render: (r) => number(r.record_count, 0) },
            { key: 'first_ts', header: 'From', render: (r) => r.first_ts?.slice(0, 10) ?? '—' },
            { key: 'last_ts', header: 'To', render: (r) => r.last_ts?.slice(0, 10) ?? '—' },
            {
              key: 'completeness_pct',
              header: 'Complete',
              align: 'right',
              numeric: true,
              render: (r) => percent(r.completeness_pct),
            },
            {
              key: 'is_usable',
              header: 'Usable',
              render: (r) => (
                <Badge tone={r.is_usable ? 'profit' : 'warn'}>{r.is_usable ? 'Yes' : 'No'}</Badge>
              ),
            },
          ]}
          rows={availability?.items ?? []}
          rowKey={(r) => `${r.instrument_id}-${r.timeframe}`}
          exportName="data-availability"
          onRowClick={(r) => setInstrumentId(r.instrument_id)}
          emptyTitle="No availability recorded"
          emptyDescription="Run an import, or load demo data, to populate this."
        />
      </Panel>

      {instrumentId && (
        <Panel
          title="Instrument detail"
          subtitle="Gaps, thin sessions and OHLC integrity at 1m"
          className="mt-4"
          actions={
            <button type="button" className="btn-ghost py-1 text-xs" onClick={() => setInstrumentId('')}>
              Clear
            </button>
          }
        >
          {isFetching ? (
            <Loading />
          ) : !report ? (
            <EmptyState title="No report" />
          ) : (
            <>
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                {[
                  ['Records', number(report.total_records, 0)],
                  ['Sessions present', `${report.present_sessions} / ${report.expected_sessions}`],
                  ['Completeness', percent(report.completeness_pct)],
                  ['Invalid OHLC rows', report.invalid_ohlc_records],
                ].map(([label, value]) => (
                  <div key={label} className="rounded-md bg-base-800 p-2.5">
                    <p className="label">{label}</p>
                    <p className="mt-1 tnum font-mono text-sm">{value}</p>
                  </div>
                ))}
              </div>

              {report.missing_session_dates?.length > 0 && (
                <div className="mt-4">
                  <p className="label mb-1.5">
                    Missing sessions ({report.missing_session_dates.length})
                  </p>
                  <div className="flex max-h-32 flex-wrap gap-1 overflow-y-auto">
                    {report.missing_session_dates.slice(0, 120).map((d) => (
                      <Badge key={d} tone="warn">
                        {d}
                      </Badge>
                    ))}
                  </div>
                </div>
              )}

              {report.thin_sessions?.length > 0 && (
                <div className="mt-4">
                  <p className="label mb-1.5">
                    Thin sessions ({report.thin_sessions.length}) — present but far short of 375
                    one-minute candles
                  </p>
                  <div className="flex max-h-32 flex-wrap gap-1 overflow-y-auto">
                    {report.thin_sessions.slice(0, 60).map((s) => (
                      <Badge key={s.date} tone="warn">
                        {s.date}: {s.candles}
                      </Badge>
                    ))}
                  </div>
                </div>
              )}
            </>
          )}
        </Panel>
      )}
    </>
  )
}
