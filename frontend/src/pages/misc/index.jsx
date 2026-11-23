/**
 * Smaller screens that are mostly a single query plus a table or a few cards.
 * Keeping them together avoids a dozen near-identical files.
 */
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { Brain, CheckCheck, Plug, Plus, Trash2 } from 'lucide-react'
import { api, errorMessage } from '../../api/client'
import {
  Badge, BlockedFeature, EmptyState, ErrorState, Loading, PageHeader, Panel,
  PaperTradingBanner, StatTile, StateBadge,
} from '../../components/ui'
import { DataTable } from '../../components/tables/DataTable'
import { money, number, percent, signed, timeIST } from '../../lib/format'

/* ------------------------------------------------------------------ Market */

export function MarketOverview() {
  const { data: status } = useQuery({
    queryKey: ['md-status'],
    queryFn: async () => (await api.get('/market-data/status')).data,
    refetchInterval: 20_000,
  })

  const { data: instruments, isLoading } = useQuery({
    queryKey: ['instruments', 'overview'],
    queryFn: async () => (await api.get('/instruments', { params: { page_size: 50 } })).data,
  })

  return (
    <>
      <PageHeader
        title="Market Overview"
        description="Session state and the instruments currently tracked."
      />

      {status && (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <StatTile label="Market status" value={status.market_status.replace('_', ' ')} />
            <StatTile label="Server time (IST)" value={timeIST(status.server_time_ist)} />
            <StatTile
              label="Live feed"
              value={status.feed_connected ? 'Connected' : 'Not connected'}
              tone={status.feed_connected ? 'profit' : 'warn'}
            />
            <StatTile label="Data mode" value={status.data_mode} tone="warn" />
          </div>
          <div className="mt-3 rounded-md border border-warn/25 bg-warn-soft px-3 py-2">
            <p className="text-2xs leading-relaxed text-warn">{status.note}</p>
          </div>
        </>
      )}

      <Panel title="Tracked instruments" className="mt-4" bodyClass="p-0">
        <DataTable
          columns={[
            { key: 'tradingsymbol', header: 'Symbol' },
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
              key: 'is_demo',
              header: '',
              sortable: false,
              render: (r) => (r.is_demo ? <Badge tone="warn">Demo</Badge> : null),
            },
          ]}
          rows={instruments?.items ?? []}
          loading={isLoading}
          exportName="market-overview"
        />
      </Panel>
    </>
  )
}

/* -------------------------------------------------------------- Watchlists */

export function Watchlists() {
  const queryClient = useQueryClient()
  const [name, setName] = useState('')

  const { data, isLoading } = useQuery({
    queryKey: ['watchlists'],
    queryFn: async () => (await api.get('/watchlists')).data,
  })

  const create = useMutation({
    mutationFn: async () => (await api.post('/watchlists', { name })).data,
    onSuccess: () => {
      setName('')
      queryClient.invalidateQueries({ queryKey: ['watchlists'] })
    },
  })

  const remove = useMutation({
    mutationFn: async (id) => (await api.delete(`/watchlists/${id}`)).data,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['watchlists'] }),
  })

  return (
    <>
      <PageHeader
        title="Watchlists"
        description="Group instruments for quick selection in strategy configurations and backtests."
      />

      <Panel className="mb-4">
        <form
          className="flex flex-wrap gap-2"
          onSubmit={(e) => {
            e.preventDefault()
            if (name.trim()) create.mutate()
          }}
        >
          <input
            className="input max-w-xs"
            placeholder="New watchlist name…"
            value={name}
            onChange={(e) => setName(e.target.value)}
            aria-label="Watchlist name"
          />
          <button type="submit" className="btn-primary" disabled={!name.trim() || create.isPending}>
            <Plus size={14} /> Create
          </button>
        </form>
        {create.isError && <p className="mt-2 text-xs text-loss">{errorMessage(create.error)}</p>}
      </Panel>

      {isLoading ? (
        <Loading />
      ) : !data?.length ? (
        <Panel>
          <EmptyState title="No watchlists" description="Create one above to get started." />
        </Panel>
      ) : (
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {data.map((w) => (
            <Panel
              key={w.id}
              title={w.name}
              subtitle={`${w.item_count} instrument${w.item_count === 1 ? '' : 's'}`}
              actions={
                <button
                  type="button"
                  className="btn-ghost p-1.5"
                  onClick={() => remove.mutate(w.id)}
                  aria-label={`Delete ${w.name}`}
                >
                  <Trash2 size={13} />
                </button>
              }
            >
              {w.items.length === 0 ? (
                <p className="text-2xs text-ink-faint">No instruments added yet.</p>
              ) : (
                <div className="flex flex-wrap gap-1">
                  {w.items.map((item) => (
                    <Badge key={item.id} tone="neutral">
                      {item.instrument.tradingsymbol}
                    </Badge>
                  ))}
                </div>
              )}
            </Panel>
          ))}
        </div>
      )}
    </>
  )
}

/* --------------------------------------------------------------- Portfolio */

export function Portfolio() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['portfolios'],
    queryFn: async () => (await api.get('/portfolio')).data,
  })

  if (isLoading) return <Loading />
  if (error) return <ErrorState message={errorMessage(error)} />

  return (
    <>
      <PageHeader title="Portfolio" description="Simulated capital, deployment and returns.">
        <PaperTradingBanner />
      </PageHeader>

      {!data?.length ? (
        <Panel>
          <EmptyState title="No portfolio" description="Run the seed script to create one." />
        </Panel>
      ) : (
        data.map((p) => (
          <Panel key={p.id} title={p.name} subtitle={p.description} className="mb-4">
            <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
              <StatTile label="Starting capital" value={money(p.starting_capital, { compact: true })} />
              <StatTile
                label="Current capital"
                value={money(p.current_capital, { compact: true })}
                tone={p.current_capital >= p.starting_capital ? 'profit' : 'loss'}
              />
              <StatTile label="Available" value={money(p.available_capital, { compact: true })} />
              <StatTile label="Deployed" value={money(p.deployed_capital, { compact: true })} />
            </div>
            <div className="mt-3 grid grid-cols-2 gap-3 lg:grid-cols-4">
              <StatTile
                label="Realised P&L"
                value={signed(p.realised_pnl, money)}
                tone={p.realised_pnl >= 0 ? 'profit' : 'loss'}
              />
              <StatTile label="Total charges" value={money(p.total_charges)} tone="warn" />
              <StatTile
                label="Return"
                value={percent(p.return_pct)}
                tone={p.return_pct >= 0 ? 'profit' : 'loss'}
              />
              <StatTile label="Mode" value={p.execution_mode} tone="warn" />
            </div>
          </Panel>
        ))
      )}
    </>
  )
}

/* ---------------------------------------------------------------------- AI */

export function AIResearch() {
  const { data: status, isLoading } = useQuery({
    queryKey: ['ai-status'],
    queryFn: async () => (await api.get('/ai/status')).data,
  })

  const { data: analyses } = useQuery({
    queryKey: ['ai-analyses'],
    queryFn: async () => (await api.get('/ai/analyses')).data,
    enabled: !!status?.enabled,
  })

  const { data: usage } = useQuery({
    queryKey: ['ai-usage'],
    queryFn: async () => (await api.get('/ai/usage')).data,
  })

  if (isLoading) return <Loading />

  return (
    <>
      <PageHeader
        title="AI Research"
        description="Claude analyses data the platform has already computed. It has no tools, no database access and cannot place an order."
      />

      {!status.enabled ? (
        <BlockedFeature
          title="AI research is not configured"
          reason={status.blocked_reason}
          docs="docs/AI_INTEGRATION.md"
        />
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <StatTile label="Model" value={status.model} icon={Brain} />
            <StatTile label="Monthly budget" value={`$${status.monthly_budget_usd}`} />
            <StatTile
              label="Spent this month"
              value={`$${number(status.month_to_date_spend_usd, 4)}`}
            />
            <StatTile
              label="Remaining"
              value={`$${number(status.budget_remaining_usd, 4)}`}
              tone={status.budget_remaining_usd <= 0 ? 'loss' : 'neutral'}
            />
          </div>

          <Panel title="Recent analyses" className="mt-4" bodyClass="p-0">
            <DataTable
              columns={[
                { key: 'task', header: 'Task' },
                { key: 'model', header: 'Model' },
                {
                  key: 'output_text',
                  header: 'Output',
                  render: (r) => (
                    <span className="block max-w-md truncate text-xs text-ink-muted">
                      {r.output_text ?? r.error ?? '—'}
                    </span>
                  ),
                },
                {
                  key: 'created_at',
                  header: 'When',
                  render: (r) => (
                    <span className="text-2xs text-ink-faint">
                      {timeIST(r.created_at, { withDate: true })}
                    </span>
                  ),
                },
              ]}
              rows={analyses ?? []}
              exportName="ai-analyses"
              emptyTitle="No analyses yet"
              emptyDescription="Ask the AI to explain a signal or review a backtest from those pages."
            />
          </Panel>
        </>
      )}

      <Panel title="Usage and cost" className="mt-4">
        {usage ? (
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <StatTile label="Total calls" value={usage.total_calls} />
            <StatTile label="Input tokens" value={number(usage.total_input_tokens, 0)} />
            <StatTile label="Output tokens" value={number(usage.total_output_tokens, 0)} />
            <StatTile
              label="Estimated cost"
              value={`$${number(usage.total_estimated_cost_usd, 4)}`}
              hint={usage.note}
            />
          </div>
        ) : (
          <Loading />
        )}
      </Panel>

      <Panel title="What the AI may and may not do" className="mt-4">
        <ul className="space-y-1.5 text-xs text-ink-muted">
          {[
            'Explain signals, backtests, failed trades and strategy performance.',
            'Suggest hypotheses to test — never instructions to trade.',
          ].map((t) => (
            <li key={t} className="flex gap-2">
              <span className="text-profit">✓</span> {t}
            </li>
          ))}
          {[
            'Place, modify or cancel any order.',
            'Change risk limits or broker credentials.',
            'Run arbitrary SQL or shell commands.',
            'Bypass paper-trading controls.',
          ].map((t) => (
            <li key={t} className="flex gap-2">
              <span className="text-loss">✗</span> {t}
            </li>
          ))}
        </ul>
      </Panel>
    </>
  )
}

/* ------------------------------------------------------------ Notifications */

export function Notifications() {
  const queryClient = useQueryClient()
  const [page, setPage] = useState(1)

  const { data, isLoading } = useQuery({
    queryKey: ['notifications', page],
    queryFn: async () =>
      (await api.get('/notifications', { params: { page, page_size: 25 } })).data,
    keepPreviousData: true,
  })

  const { data: prefs } = useQuery({
    queryKey: ['notification-prefs'],
    queryFn: async () => (await api.get('/notifications/preferences')).data,
  })

  const markAll = useMutation({
    mutationFn: async () => (await api.post('/notifications/read-all')).data,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['notifications'] }),
  })

  return (
    <>
      <PageHeader
        title="Notifications"
        description="Signal, trade, risk and system events."
        actions={
          <button type="button" className="btn-ghost" onClick={() => markAll.mutate()}>
            <CheckCheck size={13} /> Mark all read
          </button>
        }
      />

      {prefs && (
        <Panel title="Delivery channels" className="mb-4">
          <div className="grid gap-3 sm:grid-cols-3">
            {Object.entries(prefs.channels).map(([channel, info]) => (
              <div key={channel} className="rounded-md bg-base-800 p-3">
                <div className="flex items-center justify-between">
                  <span className="text-sm capitalize">{channel.replace('_', ' ')}</span>
                  <Badge tone={info.available ? 'profit' : 'warn'}>
                    {info.available ? 'Available' : 'Not configured'}
                  </Badge>
                </div>
                {info.blocked_reason && (
                  <p className="mt-1.5 text-2xs leading-relaxed text-ink-faint">
                    {info.blocked_reason}
                  </p>
                )}
              </div>
            ))}
          </div>
        </Panel>
      )}

      <Panel bodyClass="p-0">
        <DataTable
          columns={[
            { key: 'event', header: 'Event', render: (r) => <StateBadge state={r.event} /> },
            { key: 'title', header: 'Title', render: (r) => <span className="font-medium">{r.title}</span> },
            { key: 'body', header: 'Detail', render: (r) => <span className="text-xs text-ink-muted">{r.body ?? '—'}</span> },
            {
              key: 'is_read',
              header: '',
              sortable: false,
              render: (r) => (!r.is_read ? <Badge tone="accent">New</Badge> : null),
            },
            {
              key: 'created_at',
              header: 'When',
              render: (r) => <span className="text-2xs text-ink-faint">{timeIST(r.created_at, { withDate: true })}</span>,
            },
          ]}
          rows={data?.items ?? []}
          loading={isLoading}
          page={page}
          total={data?.total}
          pageSize={25}
          onPageChange={setPage}
          searchable={false}
          emptyTitle="No notifications"
          emptyDescription="Events appear here as signals are generated and trades are taken."
        />
      </Panel>
    </>
  )
}

/* ------------------------------------------------------------------ Broker */

export function Broker() {
  const queryClient = useQueryClient()
  const [notice, setNotice] = useState('')

  const { data, isLoading } = useQuery({
    queryKey: ['broker-status'],
    queryFn: async () => (await api.get('/broker/status')).data,
  })

  const connect = useMutation({
    mutationFn: async () => (await api.post('/broker/connect')).data,
    onSuccess: () => {
      setNotice('Connected.')
      queryClient.invalidateQueries({ queryKey: ['broker-status'] })
    },
    onError: (err) => setNotice(errorMessage(err)),
  })

  if (isLoading) return <Loading />

  const md = data.market_data

  return (
    <>
      <PageHeader
        title="Broker Connections"
        description="Market data and execution are separate adapters. Execution is always simulated in this build."
      />

      {notice && (
        <p className="mb-3 rounded-md border border-base-600 bg-base-800 px-3 py-2 text-xs text-ink-muted">
          {notice}
        </p>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel
          title={`Market data — ${md.broker}`}
          actions={
            <button
              type="button"
              className="btn-ghost"
              onClick={() => connect.mutate()}
              disabled={connect.isPending}
            >
              <Plug size={13} /> Test connection
            </button>
          }
        >
          <div className="flex flex-wrap gap-2">
            <Badge tone={md.connected ? 'profit' : 'warn'}>
              {md.connected ? 'Connected' : 'Not connected'}
            </Badge>
            <Badge tone={md.credentials_present ? 'profit' : 'warn'}>
              {md.credentials_present ? 'Credentials present' : 'No credentials'}
            </Badge>
          </div>
          <p className="mt-2.5 text-xs text-ink-muted">{md.message}</p>
          {md.blocked_reason && (
            <div className="mt-3 rounded-md border border-warn/25 bg-warn-soft px-3 py-2">
              <p className="text-2xs leading-relaxed text-warn">{md.blocked_reason}</p>
            </div>
          )}

          <div className="mt-4">
            <p className="label mb-1.5">Capabilities</p>
            <div className="grid grid-cols-2 gap-1.5">
              {Object.entries(md.capabilities).map(([key, value]) => (
                <div key={key} className="rounded bg-base-800 px-2 py-1">
                  <p className="text-[10px] text-ink-faint">{key.replace(/_/g, ' ')}</p>
                  <p className="tnum font-mono text-2xs">{String(value)}</p>
                </div>
              ))}
            </div>
          </div>
        </Panel>

        <Panel title="Execution adapter">
          <div className="flex flex-wrap gap-2">
            <Badge tone="warn">Paper</Badge>
            <Badge tone="profit">Simulated</Badge>
          </div>
          <p className="mt-2.5 text-xs leading-relaxed text-ink-muted">{data.execution.note}</p>
          <dl className="mt-4 space-y-1.5 text-2xs">
            {Object.entries(data.execution)
              .filter(([key]) => key !== 'note')
              .map(([key, value]) => (
                <div key={key} className="flex justify-between gap-2">
                  <dt className="text-ink-faint">{key.replace(/_/g, ' ')}</dt>
                  <dd className="font-mono">{String(value)}</dd>
                </div>
              ))}
          </dl>
        </Panel>
      </div>
    </>
  )
}

/* ------------------------------------------------------------------ System */

export function SystemMonitoring() {
  const { data, isLoading } = useQuery({
    queryKey: ['health'],
    queryFn: async () => (await api.get('/health')).data,
    refetchInterval: 15_000,
  })

  if (isLoading) return <Loading />

  return (
    <>
      <PageHeader title="System Monitoring" description="Service health and integration status." />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatTile
          label="Overall"
          value={data.status}
          tone={data.status === 'ok' ? 'profit' : 'loss'}
        />
        <StatTile
          label="PostgreSQL"
          value={data.dependencies.postgres.ok ? 'Up' : 'Down'}
          tone={data.dependencies.postgres.ok ? 'profit' : 'loss'}
          sub={data.dependencies.postgres.error ?? undefined}
        />
        <StatTile
          label="Redis"
          value={data.dependencies.redis.ok ? 'Up' : 'Down'}
          tone={data.dependencies.redis.ok ? 'profit' : 'loss'}
        />
        <StatTile label="Environment" value={data.environment} />
      </div>

      <Panel title="Execution safety" className="mt-4">
        <dl className="space-y-1.5 text-xs">
          {Object.entries(data.safety)
            .filter(([key]) => key !== 'note')
            .map(([key, value]) => (
              <div key={key} className="flex justify-between gap-3">
                <dt className="text-ink-faint">{key.replace(/_/g, ' ')}</dt>
                <dd className="font-mono">{String(value)}</dd>
              </div>
            ))}
        </dl>
        <p className="mt-3 rounded-md bg-base-800 px-3 py-2 text-2xs leading-relaxed text-ink-muted">
          {data.safety.note}
        </p>
      </Panel>

      <Panel title="Integrations" className="mt-4">
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="flex items-center justify-between rounded-md bg-base-800 px-3 py-2">
            <span className="text-sm">Broker credentials</span>
            <Badge tone={data.integrations.broker_credentials_present ? 'profit' : 'warn'}>
              {data.integrations.broker_credentials_present ? 'Present' : 'Missing'}
            </Badge>
          </div>
          <div className="flex items-center justify-between rounded-md bg-base-800 px-3 py-2">
            <span className="text-sm">AI research</span>
            <Badge tone={data.integrations.ai_enabled ? 'profit' : 'warn'}>
              {data.integrations.ai_enabled ? 'Enabled' : 'Disabled'}
            </Badge>
          </div>
        </div>
      </Panel>
    </>
  )
}

/* --------------------------------------------------------------- Audit log */

export function AuditLog() {
  const [page, setPage] = useState(1)
  const { data, isLoading } = useQuery({
    queryKey: ['audit', page],
    queryFn: async () => (await api.get('/audit-logs', { params: { page, page_size: 50 } })).data,
    keepPreviousData: true,
  })

  return (
    <>
      <PageHeader
        title="Audit Log"
        description="Append-only record of every configuration change, activation and trade action. These rows cannot be edited or deleted through the application."
      />
      <Panel bodyClass="p-0">
        <DataTable
          columns={[
            { key: 'action', header: 'Action', render: (r) => <code className="text-xs">{r.action}</code> },
            { key: 'entity_type', header: 'Entity', render: (r) => r.entity_type ?? '—' },
            { key: 'description', header: 'Detail', render: (r) => <span className="text-xs text-ink-muted">{r.description ?? '—'}</span> },
            {
              key: 'severity',
              header: 'Severity',
              render: (r) => (
                <Badge
                  tone={
                    r.severity === 'CRITICAL' ? 'loss' : r.severity === 'WARNING' ? 'warn' : 'neutral'
                  }
                >
                  {r.severity}
                </Badge>
              ),
            },
            {
              key: 'created_at',
              header: 'When',
              render: (r) => <span className="text-2xs text-ink-faint">{timeIST(r.created_at, { withDate: true })}</span>,
            },
          ]}
          rows={data?.items ?? []}
          loading={isLoading}
          page={page}
          total={data?.total}
          pageSize={50}
          onPageChange={setPage}
          searchable={false}
          exportName="audit-log"
          emptyTitle="No audit entries"
        />
      </Panel>
    </>
  )
}

/* ------------------------------------------------------------------- Users */

export function Users() {
  const { data: users, isLoading } = useQuery({
    queryKey: ['users'],
    queryFn: async () => (await api.get('/users')).data,
  })

  const { data: roles } = useQuery({
    queryKey: ['roles'],
    queryFn: async () => (await api.get('/roles')).data,
  })

  return (
    <>
      <PageHeader
        title="Users & Roles"
        description="Role-based access control. Permissions are data, not hardcoded checks — roles can be edited and new ones added."
      />

      <Panel title="Users" bodyClass="p-0">
        <DataTable
          columns={[
            { key: 'username', header: 'Username', render: (r) => <span className="font-medium">{r.username}</span> },
            { key: 'email', header: 'Email' },
            { key: 'full_name', header: 'Name', render: (r) => r.full_name ?? '—' },
            {
              key: 'roles',
              header: 'Roles',
              value: (r) => r.roles.map((x) => x.name).join(', '),
              render: (r) => (
                <span className="flex flex-wrap gap-1">
                  {r.roles.map((role) => (
                    <Badge key={role.id} tone="accent">
                      {role.name}
                    </Badge>
                  ))}
                </span>
              ),
            },
            {
              key: 'is_active',
              header: 'Status',
              render: (r) => (
                <Badge tone={r.is_active ? 'profit' : 'neutral'}>
                  {r.is_active ? 'Active' : 'Disabled'}
                </Badge>
              ),
            },
            {
              key: 'last_login_at',
              header: 'Last sign-in',
              render: (r) => (
                <span className="text-2xs text-ink-faint">
                  {r.last_login_at ? timeIST(r.last_login_at, { withDate: true }) : 'Never'}
                </span>
              ),
            },
          ]}
          rows={users ?? []}
          loading={isLoading}
          exportName="users"
        />
      </Panel>

      <Panel title="Roles and permissions" className="mt-4">
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {(roles ?? []).map((role) => (
            <div key={role.id} className="rounded-md bg-base-800 p-3">
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium">{role.name}</span>
                <Badge tone="neutral">{role.user_count} users</Badge>
              </div>
              <p className="mt-1 text-2xs leading-relaxed text-ink-faint">{role.description}</p>
              <details className="mt-2">
                <summary className="cursor-pointer text-2xs text-ink-faint">
                  {role.permissions.length} permissions
                </summary>
                <div className="mt-1.5 flex flex-wrap gap-1">
                  {role.permissions.map((p) => (
                    <code key={p} className="rounded bg-base-750 px-1.5 py-0.5 text-[10px]">
                      {p}
                    </code>
                  ))}
                </div>
              </details>
            </div>
          ))}
        </div>
      </Panel>
    </>
  )
}

/* ----------------------------------------------------------- Simple pages */

export function FnoModule() {
  return (
    <>
      <PageHeader
        title="F&O Trading"
        description="Options trading for NIFTY, BANK NIFTY and SENSEX."
      />
      <BlockedFeature
        title="The F&O module is scheduled for Phase 9"
        reason={
          'Options strategies need an option chain, open interest, implied volatility and ' +
          'Greeks — none of which exist for cash equity instruments, and none of which this ' +
          'build has a data feed for. The database schema already carries expiry, strike and ' +
          'option-type columns, and the module has its own independent activation switch, so ' +
          'the engine can be added without reworking the platform. Nothing here is stubbed ' +
          'out with equity data pretending to be options data.'
        }
        docs="docs/DEVELOPMENT_ROADMAP.md"
      />
    </>
  )
}

export function Reports() {
  const { data } = useQuery({
    queryKey: ['dashboard'],
    queryFn: async () => (await api.get('/dashboard')).data,
  })

  return (
    <>
      <PageHeader
        title="Reports"
        description="Exportable summaries. Every table in the platform also exports to CSV from its own toolbar."
      />
      {data && (
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <StatTile label="Closed trades" value={data.trades.total} />
          <StatTile label="Win rate" value={percent(data.trades.win_rate)} />
          <StatTile
            label="Net P&L"
            value={signed(data.pnl.all_time_realised, money)}
            tone={data.pnl.all_time_realised >= 0 ? 'profit' : 'loss'}
          />
          <StatTile label="Charges paid" value={money(data.capital.total_charges_paid)} tone="warn" />
        </div>
      )}
      <Panel title="Available reports" className="mt-4">
        <ul className="space-y-2 text-sm">
          {[
            ['Trade history', '/equity/history'],
            ['Backtest results', '/backtesting/history'],
            ['Risk breaches', '/risk'],
            ['Data quality', '/data/quality'],
            ['Audit log', '/audit'],
          ].map(([label, to]) => (
            <li key={to}>
              <Link to={to} className="text-accent hover:underline">
                {label}
              </Link>
              <span className="ml-2 text-2xs text-ink-faint">— export as CSV from that page</span>
            </li>
          ))}
        </ul>
      </Panel>
    </>
  )
}

export function StrategyCombinations() {
  const { data, isLoading } = useQuery({
    queryKey: ['combinations'],
    queryFn: async () => (await api.get('/strategy-combinations')).data,
  })

  return (
    <>
      <PageHeader
        title="Strategy Combinations"
        description="Require several strategies to agree before a trade is taken. More confirmations is not automatically better — test each combination out of sample."
      />
      {isLoading ? (
        <Loading />
      ) : !data?.length ? (
        <Panel>
          <EmptyState
            title="No combinations yet"
            description="Create at least two strategy configurations first, then combine them with AND, OR, weighted or minimum-confirmation logic."
          />
        </Panel>
      ) : (
        <div className="grid gap-3 md:grid-cols-2">
          {data.map((c) => (
            <Panel key={c.id} title={c.name} subtitle={c.description}>
              <div className="flex flex-wrap gap-1">
                <Badge tone="accent">{c.logic}</Badge>
                <Badge tone="neutral">{c.timeframe}</Badge>
                <Badge tone="neutral">entry ≥ {number(c.entry_threshold, 2)}</Badge>
                {c.logic === 'MIN_CONFIRMATIONS' && (
                  <Badge tone="neutral">min {c.min_confirmations}</Badge>
                )}
              </div>
              <ul className="mt-3 space-y-1.5">
                {c.legs.map((leg) => (
                  <li
                    key={leg.id}
                    className="flex items-center justify-between rounded bg-base-800 px-2.5 py-1.5"
                  >
                    <span className="text-xs">{leg.strategy ?? leg.strategy_config_id}</span>
                    <span className="flex gap-1">
                      {leg.role && <Badge tone="neutral">{leg.role}</Badge>}
                      {leg.is_mandatory && <Badge tone="warn">Mandatory</Badge>}
                      <Badge tone="neutral">w {number(leg.weight, 1)}</Badge>
                    </span>
                  </li>
                ))}
              </ul>
            </Panel>
          ))}
        </div>
      )}
    </>
  )
}

export function Settings() {
  const { data } = useQuery({
    queryKey: ['safety'],
    queryFn: async () => (await api.get('/safety')).data,
  })

  return (
    <>
      <PageHeader
        title="Settings"
        description="Configuration lives in environment variables, not in the database — so nothing here can switch live execution on."
      />
      <Panel title="Execution safety" className="mb-4">
        {data && (
          <>
            <dl className="space-y-1.5 text-xs">
              {Object.entries(data)
                .filter(([key]) => key !== 'note')
                .map(([key, value]) => (
                  <div key={key} className="flex justify-between gap-3">
                    <dt className="text-ink-faint">{key.replace(/_/g, ' ')}</dt>
                    <dd className="font-mono">{String(value)}</dd>
                  </div>
                ))}
            </dl>
            <p className="mt-3 rounded-md border border-warn/25 bg-warn-soft px-3 py-2 text-2xs leading-relaxed text-warn">
              {data.note}
            </p>
          </>
        )}
      </Panel>
      <Panel title="Where settings live">
        <p className="text-xs leading-relaxed text-ink-muted">
          Database, Redis, broker credentials, the Anthropic key, notification channels and all
          trading defaults are read from <code className="text-accent">.env</code>. Copy{' '}
          <code className="text-accent">.env.example</code>, fill it in, and restart the backend.
          Secrets are never returned by the API and never written to the database.
        </p>
      </Panel>
    </>
  )
}
