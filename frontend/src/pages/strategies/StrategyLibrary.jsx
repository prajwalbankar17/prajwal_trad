import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import clsx from 'clsx'
import { AlertTriangle } from 'lucide-react'
import { api, errorMessage } from '../../api/client'
import { Badge, ErrorState, Loading, PageHeader, Panel, Toggle } from '../../components/ui'
import { useHasPermission } from '../../store/auth'

const CATEGORY_LABEL = {
  PRICE_ACTION: 'Price Action',
  INDICATOR: 'Indicator-Based',
  INTRADAY: 'Intraday',
  VOLUME: 'Volume & Market Analysis',
  COMBINATION: 'Combination',
}

export default function StrategyLibrary() {
  const queryClient = useQueryClient()
  const canActivate = useHasPermission('strategy:activate')
  const [category, setCategory] = useState('')

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['strategies'],
    queryFn: async () => (await api.get('/strategies')).data,
  })

  const toggle = useMutation({
    mutationFn: async ({ id, active }) =>
      (await api.post(`/strategies/${id}/activate`, null, { params: { active } })).data,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['strategies'] }),
  })

  if (isLoading) return <Loading />
  if (error) return <ErrorState message={errorMessage(error)} onRetry={refetch} />

  const filtered = category ? data.filter((s) => s.category === category) : data
  const grouped = filtered.reduce((acc, s) => {
    ;(acc[s.category] ||= []).push(s)
    return acc
  }, {})

  return (
    <>
      <PageHeader
        title="Strategy Library"
        description="Research candidates, not proven systems. Every one must be backtested and paper traded before it is trusted with anything."
        actions={
          <select
            className="input max-w-[220px]"
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            aria-label="Filter by category"
          >
            <option value="">All categories</option>
            {Object.entries(CATEGORY_LABEL).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        }
      />

      {toggle.isError && (
        <p className="mb-3 rounded-md border border-loss/30 bg-loss-soft px-3 py-2 text-xs text-loss">
          {errorMessage(toggle.error)}
        </p>
      )}

      <div className="space-y-5">
        {Object.entries(grouped).map(([cat, strategies]) => (
          <section key={cat}>
            <h2 className="mb-2.5 text-xs font-semibold uppercase tracking-wider text-ink-faint">
              {CATEGORY_LABEL[cat] ?? cat}
              <span className="ml-2 font-normal normal-case text-ink-faint/70">
                {strategies.length}
              </span>
            </h2>
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              {strategies.map((s) => (
                <article
                  key={s.id}
                  className={clsx(
                    'panel flex flex-col p-4',
                    s.blocked_reason && 'border-warn/25',
                  )}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <h3 className="text-sm font-medium">{s.name}</h3>
                      <code className="text-2xs text-ink-faint">{s.code}</code>
                    </div>
                    <Toggle
                      checked={s.is_active}
                      disabled={!canActivate || !!s.blocked_reason || toggle.isPending}
                      onChange={(next) => toggle.mutate({ id: s.id, active: next })}
                      hint={
                        s.blocked_reason
                          ? 'Blocked by a missing dependency.'
                          : canActivate
                            ? undefined
                            : 'You do not have the strategy:activate permission.'
                      }
                    />
                  </div>

                  <p className="mt-2 flex-1 text-2xs leading-relaxed text-ink-muted">
                    {s.description}
                  </p>

                  {s.blocked_reason && (
                    <div className="mt-2.5 flex items-start gap-1.5 rounded-md bg-warn-soft px-2.5 py-2">
                      <AlertTriangle size={12} className="mt-0.5 shrink-0 text-warn" />
                      <p className="text-2xs leading-relaxed text-warn">{s.blocked_reason}</p>
                    </div>
                  )}

                  <div className="mt-3 flex flex-wrap gap-1">
                    <Badge tone="neutral">{s.module}</Badge>
                    <Badge tone="neutral">default {s.default_timeframe}</Badge>
                    {s.is_research_only && <Badge tone="warn">Research</Badge>}
                  </div>

                  {Object.keys(s.default_parameters ?? {}).length > 0 && (
                    <details className="mt-2.5">
                      <summary className="cursor-pointer text-2xs text-ink-faint hover:text-ink-muted">
                        Default parameters
                      </summary>
                      <dl className="mt-1.5 grid grid-cols-2 gap-1">
                        {Object.entries(s.default_parameters).map(([key, value]) => (
                          <div key={key} className="rounded bg-base-800 px-2 py-1">
                            <dt className="text-[10px] text-ink-faint">{key}</dt>
                            <dd className="tnum font-mono text-2xs">{String(value)}</dd>
                          </div>
                        ))}
                      </dl>
                    </details>
                  )}
                </article>
              ))}
            </div>
          </section>
        ))}
      </div>
    </>
  )
}
