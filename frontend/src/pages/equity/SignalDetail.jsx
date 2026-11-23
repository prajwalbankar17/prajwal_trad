import { useQuery } from '@tanstack/react-query'
import { Check, X } from 'lucide-react'
import { api, errorMessage } from '../../api/client'
import { Badge, ErrorState, Loading, StateBadge } from '../../components/ui'
import { money, number, timeIST } from '../../lib/format'

/**
 * Why this signal exists — or why it was rejected. Every condition the
 * strategy evaluated and every risk check that ran is listed, pass or fail.
 */
export function SignalDetail({ signalId, onClose }) {
  const { data, isLoading, error } = useQuery({
    queryKey: ['signal', signalId],
    queryFn: async () => (await api.get(`/signals/${signalId}`)).data,
  })

  return (
    <div
      className="fixed inset-0 z-50 flex justify-end bg-black/60"
      onClick={onClose}
      role="presentation"
    >
      <div
        className="h-full w-full max-w-xl overflow-y-auto border-l border-base-700 bg-base-850"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="sticky top-0 flex items-center justify-between border-b border-base-700 bg-base-850 px-5 py-3.5">
          <h2 className="text-sm font-semibold">Signal detail</h2>
          <button type="button" onClick={onClose} className="btn-ghost p-1.5" aria-label="Close">
            <X size={15} />
          </button>
        </header>

        {isLoading && <Loading />}
        {error && <ErrorState message={errorMessage(error)} />}

        {data && (
          <div className="space-y-5 p-5">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-base font-semibold">{data.tradingsymbol}</span>
              <StateBadge state={data.direction} />
              <StateBadge state={data.state} />
              <Badge tone="neutral">{data.timeframe}</Badge>
              <Badge tone={data.data_source === 'BROKER_LIVE' ? 'profit' : 'warn'}>
                {data.data_source === 'BROKER_LIVE' ? 'Live data' : 'Historical data'}
              </Badge>
            </div>

            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              {[
                ['Entry', money(data.entry_price)],
                ['Stop-loss', money(data.stop_loss)],
                ['Target', money(data.target)],
                ['Risk/reward', data.risk_reward ? number(data.risk_reward, 2) : '—'],
              ].map(([label, value]) => (
                <div key={label} className="rounded-md bg-base-800 p-2.5">
                  <p className="label">{label}</p>
                  <p className="mt-1 tnum font-mono text-sm">{value}</p>
                </div>
              ))}
            </div>

            {data.entry_reason && (
              <div>
                <p className="label mb-1.5">Reason</p>
                <p className="text-sm leading-relaxed text-ink-muted">{data.entry_reason}</p>
              </div>
            )}

            {data.rejection_reason && (
              <div className="rounded-md border border-loss/30 bg-loss-soft p-3">
                <p className="text-2xs font-semibold uppercase tracking-wide text-loss">
                  Rejected
                </p>
                <p className="mt-1 text-xs text-loss/90">{data.rejection_reason}</p>
              </div>
            )}

            <section>
              <p className="label mb-2">Strategy conditions</p>
              <ul className="space-y-1.5">
                {(data.conditions?.checks ?? []).map((c, i) => (
                  <li
                    key={`${c.name}-${i}`}
                    className="flex items-start gap-2 rounded-md bg-base-800 px-3 py-2"
                  >
                    {c.passed ? (
                      <Check size={13} className="mt-0.5 shrink-0 text-profit" />
                    ) : (
                      <X size={13} className="mt-0.5 shrink-0 text-loss" />
                    )}
                    <div className="min-w-0">
                      <p className="text-xs font-medium">{c.name.replace(/_/g, ' ')}</p>
                      <p className="mt-0.5 text-2xs text-ink-faint">{c.detail}</p>
                    </div>
                  </li>
                ))}
              </ul>
            </section>

            {data.risk_validation?.checks && (
              <section>
                <p className="label mb-2">Risk checks</p>
                <ul className="space-y-1.5">
                  {data.risk_validation.checks.map((c, i) => (
                    <li
                      key={`${c.name}-${i}`}
                      className="flex items-start gap-2 rounded-md bg-base-800 px-3 py-2"
                    >
                      {c.passed ? (
                        <Check size={13} className="mt-0.5 shrink-0 text-profit" />
                      ) : (
                        <X size={13} className="mt-0.5 shrink-0 text-loss" />
                      )}
                      <div className="min-w-0 flex-1">
                        <p className="text-xs font-medium">{c.name.replace(/_/g, ' ')}</p>
                        <p className="mt-0.5 text-2xs text-ink-faint">
                          {c.detail ?? c.reason ?? ''}
                        </p>
                      </div>
                    </li>
                  ))}
                </ul>
              </section>
            )}

            {data.market_context?.indicators && (
              <section>
                <p className="label mb-2">Indicator values at signal time</p>
                <div className="grid grid-cols-2 gap-2">
                  {Object.entries(data.market_context.indicators).map(([key, value]) => (
                    <div key={key} className="rounded bg-base-800 px-2.5 py-1.5">
                      <p className="text-2xs text-ink-faint">{key}</p>
                      <p className="tnum font-mono text-xs">{String(value)}</p>
                    </div>
                  ))}
                </div>
              </section>
            )}

            <section>
              <p className="label mb-2">State history</p>
              <ol className="space-y-1.5">
                {data.history.map((h, i) => (
                  <li key={i} className="flex items-start gap-2 text-2xs">
                    <span className="text-ink-faint tnum">{timeIST(h.changed_at)}</span>
                    <StateBadge state={h.to_state} />
                    <span className="text-ink-faint">{h.reason}</span>
                  </li>
                ))}
              </ol>
            </section>
          </div>
        )}
      </div>
    </div>
  )
}
