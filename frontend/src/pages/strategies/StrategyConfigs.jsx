import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Plus } from 'lucide-react'
import { api, errorMessage } from '../../api/client'
import {
  Badge, EmptyState, Loading, PageHeader, Panel, Toggle,
} from '../../components/ui'
import { number } from '../../lib/format'

function ConfigForm({ strategies, onClose, onSaved }) {
  const [form, setForm] = useState({
    strategy_id: '',
    name: '',
    timeframe: '',
    min_risk_reward: 1.5,
    max_signals_per_day: 10,
  })
  const [error, setError] = useState('')

  const selected = strategies.find((s) => s.id === form.strategy_id)

  const save = useMutation({
    mutationFn: async () =>
      (
        await api.post('/strategy-configs', {
          ...form,
          timeframe: form.timeframe || selected?.default_timeframe,
          parameters: selected?.default_parameters ?? {},
        })
      ).data,
    onSuccess: () => {
      onSaved()
      onClose()
    },
    onError: (err) => setError(errorMessage(err)),
  })

  const actions = (
    <div className="flex justify-end gap-2">
      <button type="button" className="btn-ghost" onClick={onClose}>
        Cancel
      </button>
      <button
        type="submit"
        className="btn-primary"
        disabled={!form.strategy_id || !form.name || save.isPending}
      >
        {save.isPending ? 'Saving…' : 'Save configuration'}
      </button>
    </div>
  )

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault()
        setError('')
        save.mutate()
      }}
      className="panel mb-4 p-4 space-y-4"
    >
      {/* Actions at top and bottom, as long forms should have. */}
      {actions}

      <div className="grid gap-3 md:grid-cols-2">
        <div>
          <label className="label mb-1.5 block" htmlFor="strategy">
            Strategy
          </label>
          <select
            id="strategy"
            className="input"
            value={form.strategy_id}
            onChange={(e) => setForm({ ...form, strategy_id: e.target.value, timeframe: '' })}
            required
          >
            <option value="">Select a strategy…</option>
            {strategies
              .filter((s) => !s.blocked_reason)
              .map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
          </select>
        </div>

        <div>
          <label className="label mb-1.5 block" htmlFor="name">
            Configuration name
          </label>
          <input
            id="name"
            className="input"
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            placeholder="e.g. EMA 9/21 on large caps"
            required
          />
        </div>

        <div>
          <label className="label mb-1.5 block" htmlFor="timeframe">
            Timeframe
          </label>
          <select
            id="timeframe"
            className="input"
            value={form.timeframe}
            onChange={(e) => setForm({ ...form, timeframe: e.target.value })}
            disabled={!selected}
          >
            {(selected?.supported_timeframes ?? []).map((tf) => (
              <option key={tf} value={tf}>
                {tf}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="label mb-1.5 block" htmlFor="rr">
            Minimum risk/reward
          </label>
          <input
            id="rr"
            type="number"
            step="0.1"
            min="0.5"
            className="input"
            value={form.min_risk_reward}
            onChange={(e) => setForm({ ...form, min_risk_reward: Number(e.target.value) })}
          />
        </div>
      </div>

      {selected && (
        <p className="text-2xs leading-relaxed text-ink-faint">
          Parameters are seeded from the strategy defaults and can be edited after saving.
        </p>
      )}
      {error && <p className="text-xs text-loss">{error}</p>}

      {actions}
    </form>
  )
}

export default function StrategyConfigs() {
  const queryClient = useQueryClient()
  const [creating, setCreating] = useState(false)

  const { data: strategies } = useQuery({
    queryKey: ['strategies'],
    queryFn: async () => (await api.get('/strategies')).data,
  })

  const { data: configs, isLoading } = useQuery({
    queryKey: ['strategy-configs'],
    queryFn: async () => (await api.get('/strategy-configs')).data,
  })

  const toggle = useMutation({
    mutationFn: async ({ id, is_enabled }) =>
      (await api.patch(`/strategy-configs/${id}`, { is_enabled })).data,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['strategy-configs'] }),
  })

  const refresh = () => queryClient.invalidateQueries({ queryKey: ['strategy-configs'] })

  return (
    <>
      <PageHeader
        title="Strategy Configurations"
        description="A configuration is a runnable instance of a strategy: its parameters, timeframe, universe and exits."
        actions={
          <button type="button" className="btn-primary" onClick={() => setCreating((v) => !v)}>
            <Plus size={14} /> New configuration
          </button>
        }
      />

      {creating && strategies && (
        <ConfigForm
          strategies={strategies}
          onClose={() => setCreating(false)}
          onSaved={refresh}
        />
      )}

      {isLoading ? (
        <Loading />
      ) : !configs?.length ? (
        <Panel>
          <EmptyState
            title="No configurations yet"
            description="Create one to turn a strategy from the library into something that can generate signals."
            action={
              <button type="button" className="btn-primary" onClick={() => setCreating(true)}>
                <Plus size={14} /> New configuration
              </button>
            }
          />
        </Panel>
      ) : (
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {configs.map((c) => (
            <article key={c.id} className="panel p-4">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <h3 className="text-sm font-medium truncate">{c.name}</h3>
                  <code className="text-2xs text-ink-faint">{c.strategy.code}</code>
                </div>
                <Toggle
                  checked={c.is_enabled}
                  onChange={(next) => toggle.mutate({ id: c.id, is_enabled: next })}
                  disabled={toggle.isPending}
                />
              </div>

              <div className="mt-2.5 flex flex-wrap gap-1">
                <Badge tone="neutral">{c.timeframe}</Badge>
                <Badge tone="neutral">min R:R {number(c.min_risk_reward, 1)}</Badge>
                <Badge tone="neutral">
                  SL {number(c.stop_loss_value, 1)} {c.stop_loss_type === 'PERCENT' ? '%' : ''}
                </Badge>
                {c.trailing_stop_enabled && <Badge tone="accent">Trailing</Badge>}
              </div>

              <dl className="mt-3 space-y-1 text-2xs">
                <div className="flex justify-between">
                  <dt className="text-ink-faint">Session</dt>
                  <dd className="tnum font-mono">
                    {c.session_start.slice(0, 5)}–{c.session_end.slice(0, 5)}
                  </dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-ink-faint">Square-off</dt>
                  <dd className="tnum font-mono">{c.square_off_time.slice(0, 5)}</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-ink-faint">Max signals/day</dt>
                  <dd className="tnum font-mono">{c.max_signals_per_day}</dd>
                </div>
              </dl>
            </article>
          ))}
        </div>
      )}
    </>
  )
}
