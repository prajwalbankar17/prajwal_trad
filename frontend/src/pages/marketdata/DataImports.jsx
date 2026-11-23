import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Database, Search } from 'lucide-react'
import { api, errorDetails, errorMessage } from '../../api/client'
import { Badge, PageHeader, Panel, StateBadge } from '../../components/ui'
import { DataTable } from '../../components/tables/DataTable'
import { number, timeIST } from '../../lib/format'

export default function DataImports() {
  const queryClient = useQueryClient()
  const [path, setPath] = useState('')
  const [schema, setSchema] = useState(null)
  const [error, setError] = useState(null)

  const { data: jobs, isLoading } = useQuery({
    queryKey: ['imports'],
    queryFn: async () => (await api.get('/market-data/imports')).data,
    refetchInterval: 5000,
  })

  const inspect = useMutation({
    mutationFn: async () =>
      (await api.post('/market-data/imports/inspect', { source_path: path })).data,
    onSuccess: (data) => {
      setSchema(data)
      setError(null)
    },
    onError: (err) => {
      setSchema(null)
      setError({ message: errorMessage(err), details: errorDetails(err) })
    },
  })

  const start = useMutation({
    mutationFn: async () =>
      (
        await api.post('/market-data/imports', {
          name: `Import ${path.split('/').pop()}`,
          source_path: path,
          timeframe: '1m',
        })
      ).data,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['imports'] })
      setSchema(null)
      setPath('')
    },
    onError: (err) => setError({ message: errorMessage(err), details: errorDetails(err) }),
  })

  const resume = useMutation({
    mutationFn: async (id) => (await api.post(`/market-data/imports/${id}/resume`)).data,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['imports'] }),
  })

  const columns = [
    { key: 'name', header: 'Name', render: (r) => <span className="font-medium">{r.name}</span> },
    { key: 'status', header: 'Status', render: (r) => <StateBadge state={r.status} /> },
    {
      key: 'progress_pct',
      header: 'Progress',
      align: 'right',
      numeric: true,
      render: (r) => `${r.completed_symbols}/${r.total_symbols} (${r.progress_pct}%)`,
    },
    { key: 'rows_inserted', header: 'Inserted', align: 'right', numeric: true, render: (r) => number(r.rows_inserted, 0) },
    { key: 'rows_skipped_duplicate', header: 'Duplicates', align: 'right', numeric: true, render: (r) => number(r.rows_skipped_duplicate, 0) },
    { key: 'rows_rejected', header: 'Rejected', align: 'right', numeric: true, render: (r) => number(r.rows_rejected, 0) },
    { key: 'started_at', header: 'Started', render: (r) => <span className="text-2xs text-ink-faint">{timeIST(r.started_at, { withDate: true })}</span> },
    {
      key: 'actions',
      header: '',
      sortable: false,
      render: (r) =>
        r.resumable && r.status !== 'RUNNING' ? (
          <button
            type="button"
            className="btn-ghost py-1 text-xs"
            onClick={() => resume.mutate(r.id)}
          >
            Resume
          </button>
        ) : null,
    },
  ]

  return (
    <>
      <PageHeader
        title="Data Imports"
        description="Import a historical SQLite candle database. The importer streams in batches, never loads the file into memory, and resumes exactly where it stopped."
      />

      <Panel title="Import from SQLite" className="mb-4">
        <div className="flex flex-wrap gap-2">
          <input
            className="input flex-1 min-w-[280px]"
            placeholder="/absolute/path/to/equity_1min.sqlite"
            value={path}
            onChange={(e) => setPath(e.target.value)}
            aria-label="SQLite file path"
          />
          <button
            type="button"
            className="btn-ghost"
            onClick={() => inspect.mutate()}
            disabled={!path || inspect.isPending}
          >
            <Search size={13} /> {inspect.isPending ? 'Inspecting…' : 'Inspect schema'}
          </button>
          <button
            type="button"
            className="btn-primary"
            onClick={() => start.mutate()}
            disabled={!schema || start.isPending}
          >
            <Database size={13} /> Start import
          </button>
        </div>

        <p className="mt-2 text-2xs leading-relaxed text-ink-faint">
          Inspect first: the schema is read, never assumed. Importing only begins once the
          column mapping below looks right.
        </p>

        {error && (
          <div className="mt-3 rounded-md border border-loss/30 bg-loss-soft px-3 py-2">
            <p className="text-xs text-loss">{error.message}</p>
            {error.details && (
              <pre className="mt-1.5 max-h-40 overflow-auto text-2xs text-loss/80">
                {JSON.stringify(error.details, null, 2)}
              </pre>
            )}
          </div>
        )}

        {schema && (
          <div className="mt-4 space-y-3 rounded-md border border-base-600 bg-base-800 p-3">
            <div className="flex flex-wrap gap-2">
              <Badge tone="accent">{schema.layout.replace(/_/g, ' ')}</Badge>
              <Badge tone="neutral">{schema.table_count} tables</Badge>
              {schema.row_estimate != null && (
                <Badge tone="neutral">~{number(schema.row_estimate, 0)} rows in probe table</Badge>
              )}
            </div>

            <div>
              <p className="label mb-1.5">Column mapping</p>
              <div className="grid grid-cols-2 gap-1.5 sm:grid-cols-3">
                {Object.entries(schema.column_map).map(([ours, theirs]) => (
                  <div key={ours} className="rounded bg-base-750 px-2 py-1">
                    <p className="text-[10px] text-ink-faint">{ours}</p>
                    <p className="font-mono text-2xs">{theirs}</p>
                  </div>
                ))}
              </div>
            </div>

            {schema.warnings?.length > 0 && (
              <ul className="space-y-1">
                {schema.warnings.map((w, i) => (
                  <li key={i} className="text-2xs text-warn">
                    • {w}
                  </li>
                ))}
              </ul>
            )}

            {schema.sample_rows?.length > 0 && (
              <details>
                <summary className="cursor-pointer text-2xs text-ink-faint">Sample rows</summary>
                <pre className="mt-1.5 max-h-40 overflow-auto text-2xs text-ink-muted">
                  {JSON.stringify(schema.sample_rows, null, 2)}
                </pre>
              </details>
            )}
          </div>
        )}
      </Panel>

      <Panel title="Import jobs" bodyClass="p-0">
        <DataTable
          columns={columns}
          rows={jobs ?? []}
          loading={isLoading}
          exportName="import-jobs"
          emptyTitle="No imports yet"
          emptyDescription="Point the importer at a SQLite file above to get started."
        />
      </Panel>
    </>
  )
}
