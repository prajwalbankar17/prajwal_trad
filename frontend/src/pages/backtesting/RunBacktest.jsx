import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { Play } from 'lucide-react'
import { api, errorMessage } from '../../api/client'
import { Badge, PageHeader, Panel } from '../../components/ui'

const today = new Date().toISOString().slice(0, 10)
const yearAgo = new Date(Date.now() - 365 * 864e5).toISOString().slice(0, 10)

export default function RunBacktest() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [error, setError] = useState('')
  const [form, setForm] = useState({
    name: '',
    mode: 'QUICK',
    strategy_config_ids: [],
    instrument_ids: [],
    timeframe: '15m',
    start_date: yearAgo,
    end_date: today,
    initial_capital: 1000000,
    risk_per_trade_pct: 1,
    include_charges: true,
    slippage_pct: 0.05,
    out_of_sample_pct: 30,
  })

  const { data: configs } = useQuery({
    queryKey: ['strategy-configs'],
    queryFn: async () => (await api.get('/strategy-configs')).data,
  })

  const { data: instruments } = useQuery({
    queryKey: ['instruments', 'all'],
    queryFn: async () => (await api.get('/instruments', { params: { page_size: 200 } })).data,
  })

  const run = useMutation({
    mutationFn: async () => (await api.post('/backtests', form)).data,
    onSuccess: (job) => {
      queryClient.invalidateQueries({ queryKey: ['backtests'] })
      navigate(`/backtesting/${job.id}`)
    },
    onError: (err) => setError(errorMessage(err)),
  })

  const toggleIn = (key, value) =>
    setForm((prev) => ({
      ...prev,
      [key]: prev[key].includes(value)
        ? prev[key].filter((v) => v !== value)
        : [...prev[key], value],
    }))

  const canRun =
    form.name && form.strategy_config_ids.length > 0 && form.instrument_ids.length > 0

  const submitRow = (
    <div className="flex items-center justify-between gap-3">
      <p className="text-2xs text-ink-faint">
        Costs and slippage are applied to every trade. Results are reported net.
      </p>
      <button
        type="submit"
        className="btn-primary"
        disabled={!canRun || run.isPending}
      >
        <Play size={13} />
        {run.isPending ? 'Starting…' : 'Run backtest'}
      </button>
    </div>
  )

  return (
    <>
      <PageHeader
        title="Run a Backtest"
        description="Quick mode evaluates one or more configurations over a date range. Advanced mode adds an out-of-sample split and overfitting checks."
      />

      <form
        onSubmit={(e) => {
          e.preventDefault()
          setError('')
          run.mutate()
        }}
        className="space-y-4"
      >
        <Panel title="Run settings">
          {submitRow}
          <div className="mt-4 grid gap-3 md:grid-cols-3">
            <div className="md:col-span-2">
              <label className="label mb-1.5 block" htmlFor="bt-name">Name</label>
              <input
                id="bt-name"
                className="input"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                placeholder="e.g. EMA crossover, 15m, FY25"
                required
              />
            </div>
            <div>
              <label className="label mb-1.5 block" htmlFor="bt-mode">Mode</label>
              <select
                id="bt-mode"
                className="input"
                value={form.mode}
                onChange={(e) => setForm({ ...form, mode: e.target.value })}
              >
                <option value="QUICK">Quick</option>
                <option value="ADVANCED">Advanced</option>
              </select>
            </div>
            <div>
              <label className="label mb-1.5 block" htmlFor="bt-tf">Timeframe</label>
              <select
                id="bt-tf"
                className="input"
                value={form.timeframe}
                onChange={(e) => setForm({ ...form, timeframe: e.target.value })}
              >
                {['1m', '3m', '5m', '10m', '15m', '30m', '1h', '1d'].map((tf) => (
                  <option key={tf} value={tf}>{tf}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="label mb-1.5 block" htmlFor="bt-start">Start date</label>
              <input
                id="bt-start"
                type="date"
                className="input"
                value={form.start_date}
                onChange={(e) => setForm({ ...form, start_date: e.target.value })}
              />
            </div>
            <div>
              <label className="label mb-1.5 block" htmlFor="bt-end">End date</label>
              <input
                id="bt-end"
                type="date"
                className="input"
                value={form.end_date}
                onChange={(e) => setForm({ ...form, end_date: e.target.value })}
              />
            </div>
            <div>
              <label className="label mb-1.5 block" htmlFor="bt-capital">Initial capital</label>
              <input
                id="bt-capital"
                type="number"
                className="input"
                value={form.initial_capital}
                onChange={(e) => setForm({ ...form, initial_capital: Number(e.target.value) })}
              />
            </div>
            <div>
              <label className="label mb-1.5 block" htmlFor="bt-risk">Risk per trade (%)</label>
              <input
                id="bt-risk"
                type="number"
                step="0.1"
                className="input"
                value={form.risk_per_trade_pct}
                onChange={(e) => setForm({ ...form, risk_per_trade_pct: Number(e.target.value) })}
              />
            </div>
            <div>
              <label className="label mb-1.5 block" htmlFor="bt-slip">Slippage (%)</label>
              <input
                id="bt-slip"
                type="number"
                step="0.01"
                className="input"
                value={form.slippage_pct}
                onChange={(e) => setForm({ ...form, slippage_pct: Number(e.target.value) })}
              />
            </div>
            <div>
              <label className="label mb-1.5 block" htmlFor="bt-oos">
                Out-of-sample (%)
              </label>
              <input
                id="bt-oos"
                type="number"
                min="0"
                max="60"
                className="input"
                value={form.out_of_sample_pct}
                onChange={(e) => setForm({ ...form, out_of_sample_pct: Number(e.target.value) })}
              />
            </div>
          </div>
        </Panel>

        <div className="grid gap-4 lg:grid-cols-2">
          <Panel
            title="Strategy configurations"
            subtitle={`${form.strategy_config_ids.length} selected`}
            bodyClass="p-0 max-h-72 overflow-y-auto"
          >
            {!configs?.length ? (
              <p className="p-4 text-xs text-ink-faint">
                No configurations yet — create one under Strategies.
              </p>
            ) : (
              configs.map((c) => (
                <label
                  key={c.id}
                  className="flex cursor-pointer items-center gap-2.5 border-b border-base-700/60 px-4 py-2.5 hover:bg-base-800"
                >
                  <input
                    type="checkbox"
                    checked={form.strategy_config_ids.includes(c.id)}
                    onChange={() => toggleIn('strategy_config_ids', c.id)}
                  />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm">{c.name}</span>
                    <span className="text-2xs text-ink-faint">{c.strategy.code}</span>
                  </span>
                  <Badge tone="neutral">{c.timeframe}</Badge>
                </label>
              ))
            )}
          </Panel>

          <Panel
            title="Instruments"
            subtitle={`${form.instrument_ids.length} selected`}
            bodyClass="p-0 max-h-72 overflow-y-auto"
            actions={
              <button
                type="button"
                className="btn-ghost py-1 text-xs"
                onClick={() =>
                  setForm((p) => ({
                    ...p,
                    instrument_ids:
                      p.instrument_ids.length === instruments?.items.length
                        ? []
                        : (instruments?.items ?? []).map((i) => i.id),
                  }))
                }
              >
                Toggle all
              </button>
            }
          >
            {(instruments?.items ?? []).map((i) => (
              <label
                key={i.id}
                className="flex cursor-pointer items-center gap-2.5 border-b border-base-700/60 px-4 py-2 hover:bg-base-800"
              >
                <input
                  type="checkbox"
                  checked={form.instrument_ids.includes(i.id)}
                  onChange={() => toggleIn('instrument_ids', i.id)}
                />
                <span className="flex-1 truncate text-sm">{i.tradingsymbol}</span>
                {i.is_demo && <Badge tone="warn">Demo</Badge>}
              </label>
            ))}
          </Panel>
        </div>

        {error && (
          <p className="rounded-md border border-loss/30 bg-loss-soft px-3 py-2 text-xs text-loss">
            {error}
          </p>
        )}

        <Panel>{submitRow}</Panel>
      </form>
    </>
  )
}
