import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ShieldAlert } from 'lucide-react'
import { api, errorMessage } from '../../api/client'
import {
  Badge, ErrorState, Loading, PageHeader, Panel, StatTile,
} from '../../components/ui'
import { DataTable } from '../../components/tables/DataTable'
import { money, number, percent, pnlClass, signed, timeIST } from '../../lib/format'
import { useHasPermission } from '../../store/auth'

const EDITABLE = [
  ['capital', 'Capital', 'Base capital the limits are computed against'],
  ['max_risk_per_trade_pct', 'Max risk per trade (%)', 'Drives position size'],
  ['max_daily_loss_pct', 'Max daily loss (%)', 'Halts new entries when reached'],
  ['max_open_positions', 'Max open positions', ''],
  ['max_trades_per_day', 'Max trades per day', ''],
  ['max_total_exposure_pct', 'Max total exposure (%)', ''],
  ['max_sector_exposure_pct', 'Max sector exposure (%)', ''],
  ['max_position_size_pct', 'Max position size (%)', ''],
  ['assumed_leverage', 'Assumed leverage', 'Never assume broker leverage is guaranteed'],
]

export default function RiskManagement() {
  const queryClient = useQueryClient()
  const canEdit = useHasPermission('risk:write')
  const canKill = useHasPermission('risk:killswitch')
  const [draft, setDraft] = useState(null)
  const [notice, setNotice] = useState('')

  const { data: profiles, isLoading, error } = useQuery({
    queryKey: ['risk-profiles'],
    queryFn: async () => (await api.get('/risk/profiles')).data,
  })

  const { data: utilisation } = useQuery({
    queryKey: ['risk-utilisation'],
    queryFn: async () => (await api.get('/risk/utilisation')).data,
    refetchInterval: 20_000,
  })

  const { data: breaches } = useQuery({
    queryKey: ['risk-breaches'],
    queryFn: async () => (await api.get('/risk/breaches')).data,
  })

  const save = useMutation({
    mutationFn: async ({ id, changes }) => (await api.patch(`/risk/profiles/${id}`, changes)).data,
    onSuccess: () => {
      setDraft(null)
      setNotice('Risk limits updated.')
      queryClient.invalidateQueries({ queryKey: ['risk-profiles'] })
      queryClient.invalidateQueries({ queryKey: ['risk-utilisation'] })
    },
    onError: (err) => setNotice(errorMessage(err)),
  })

  const killSwitch = useMutation({
    mutationFn: async (active) =>
      (await api.post('/risk/kill-switch', null, { params: { active, reason: 'From the UI' } }))
        .data,
    onSuccess: (data) => {
      setNotice(data.message)
      queryClient.invalidateQueries({ queryKey: ['risk-utilisation'] })
    },
    onError: (err) => setNotice(errorMessage(err)),
  })

  if (isLoading) return <Loading />
  if (error) return <ErrorState message={errorMessage(error)} />

  const profile = profiles?.find((p) => p.is_default) ?? profiles?.[0]
  const values = draft ?? profile

  return (
    <>
      <PageHeader
        title="Risk Management"
        description="Limits are enforced independently of strategy logic. A strategy proposes; risk decides whether and how large."
        actions={
          <button
            type="button"
            className={utilisation?.kill_switch ? 'btn-primary' : 'btn-danger'}
            disabled={!canKill || killSwitch.isPending}
            onClick={() => killSwitch.mutate(!utilisation?.kill_switch)}
          >
            <ShieldAlert size={14} />
            {utilisation?.kill_switch ? 'Release kill switch' : 'Engage kill switch'}
          </button>
        }
      />

      {notice && (
        <p className="mb-3 rounded-md border border-base-600 bg-base-800 px-3 py-2 text-xs text-ink-muted">
          {notice}
        </p>
      )}

      {utilisation?.kill_switch && (
        <div className="mb-4 rounded-md border border-loss/30 bg-loss-soft px-3 py-2.5">
          <p className="text-xs font-semibold text-loss">Kill switch engaged</p>
          <p className="mt-0.5 text-2xs text-loss/80">
            No new positions will be opened. Open positions are still monitored and exited.
          </p>
        </div>
      )}

      {utilisation && (
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <StatTile
            label="Realised P&L today"
            value={signed(utilisation.realised_pnl, money)}
            tone={utilisation.realised_pnl >= 0 ? 'profit' : 'loss'}
          />
          <StatTile
            label="Daily loss used"
            value={percent(utilisation.daily_loss_used_pct)}
            sub={`limit ${money(Math.abs(utilisation.daily_loss_limit))}`}
            tone={utilisation.daily_loss_used_pct > 70 ? 'loss' : 'neutral'}
          />
          <StatTile
            label="Capital utilisation"
            value={percent(utilisation.utilisation_pct)}
            sub={`cap ${percent(utilisation.max_capital_utilisation_pct)}`}
          />
          <StatTile
            label="Positions / trades"
            value={`${utilisation.open_positions}/${utilisation.max_open_positions} · ${utilisation.trades_taken}/${utilisation.max_trades_per_day}`}
          />
        </div>
      )}

      {profile && (
        <Panel
          title="Risk profile"
          subtitle={profile.name}
          className="mt-4"
          actions={
            canEdit &&
            (draft ? (
              <div className="flex gap-2">
                <button type="button" className="btn-ghost" onClick={() => setDraft(null)}>
                  Cancel
                </button>
                <button
                  type="button"
                  className="btn-primary"
                  disabled={save.isPending}
                  onClick={() =>
                    save.mutate({
                      id: profile.id,
                      changes: Object.fromEntries(
                        EDITABLE.map(([key]) => [key, Number(draft[key])]),
                      ),
                    })
                  }
                >
                  Save limits
                </button>
              </div>
            ) : (
              <button type="button" className="btn-ghost" onClick={() => setDraft({ ...profile })}>
                Edit
              </button>
            ))
          }
        >
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {EDITABLE.map(([key, label, hint]) => (
              <div key={key}>
                <label className="label mb-1.5 block" htmlFor={`risk-${key}`}>
                  {label}
                </label>
                <input
                  id={`risk-${key}`}
                  type="number"
                  step="0.1"
                  className="input tnum font-mono"
                  value={values[key]}
                  disabled={!draft}
                  onChange={(e) => setDraft({ ...draft, [key]: e.target.value })}
                />
                {hint && <p className="mt-1 text-[10px] text-ink-faint">{hint}</p>}
              </div>
            ))}
          </div>
        </Panel>
      )}

      <Panel
        title="Risk limit breaches"
        subtitle="Signals blocked before they became trades"
        className="mt-4"
        bodyClass="p-0"
      >
        <DataTable
          columns={[
            {
              key: 'limit_name',
              header: 'Limit',
              render: (r) => <Badge tone="loss">{r.limit_name.replace(/_/g, ' ')}</Badge>,
            },
            { key: 'limit_value', header: 'Limit', align: 'right', numeric: true, render: (r) => (r.limit_value != null ? number(r.limit_value) : '—') },
            { key: 'actual_value', header: 'Actual', align: 'right', numeric: true, render: (r) => (r.actual_value != null ? number(r.actual_value) : '—') },
            { key: 'action_taken', header: 'Action' },
            {
              key: 'occurred_at',
              header: 'When',
              render: (r) => <span className="text-2xs text-ink-faint">{timeIST(r.occurred_at, { withDate: true })}</span>,
            },
          ]}
          rows={breaches ?? []}
          exportName="risk-breaches"
          emptyTitle="No breaches recorded"
          emptyDescription="Nothing has been blocked by a risk limit yet."
        />
      </Panel>
    </>
  )
}
