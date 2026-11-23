import clsx from 'clsx'
import { AlertTriangle, Inbox, Loader2, ShieldCheck } from 'lucide-react'

export function Panel({ title, subtitle, actions, children, className, bodyClass }) {
  return (
    <section className={clsx('panel', className)}>
      {(title || actions) && (
        <header className="panel-header">
          <div className="min-w-0">
            {title && <h2 className="text-sm font-semibold text-ink truncate">{title}</h2>}
            {subtitle && <p className="text-2xs text-ink-faint mt-0.5">{subtitle}</p>}
          </div>
          {actions && <div className="flex items-center gap-2 shrink-0">{actions}</div>}
        </header>
      )}
      <div className={clsx('p-4', bodyClass)}>{children}</div>
    </section>
  )
}

export function StatTile({ label, value, sub, tone = 'neutral', icon: Icon, hint }) {
  const tones = {
    neutral: 'text-ink',
    profit: 'text-profit',
    loss: 'text-loss',
    warn: 'text-warn',
    accent: 'text-accent',
  }
  return (
    <div className="panel p-4" title={hint}>
      <div className="flex items-start justify-between gap-2">
        <span className="label">{label}</span>
        {Icon && <Icon size={14} className="text-ink-faint shrink-0" />}
      </div>
      <p className={clsx('mt-2 text-xl font-semibold tnum truncate', tones[tone])}>{value}</p>
      {sub && <p className="mt-1 text-2xs text-ink-faint truncate">{sub}</p>}
    </div>
  )
}

const BADGE_TONES = {
  neutral: 'bg-base-700 text-ink-muted',
  accent: 'bg-accent-soft text-accent',
  profit: 'bg-profit-soft text-profit',
  loss: 'bg-loss-soft text-loss',
  warn: 'bg-warn-soft text-warn',
}

export function Badge({ tone = 'neutral', children, className }) {
  return <span className={clsx('badge', BADGE_TONES[tone], className)}>{children}</span>
}

/** Maps a backend state string to a badge tone, in one place. */
export function StateBadge({ state }) {
  const map = {
    VALIDATED: 'profit',
    PAPER_EXECUTED: 'accent',
    GENERATED: 'neutral',
    PENDING: 'neutral',
    REJECTED: 'loss',
    CANCELLED: 'loss',
    EXPIRED: 'warn',
    OPEN: 'accent',
    CLOSED: 'neutral',
    PARTIALLY_CLOSED: 'warn',
    COMPLETED: 'profit',
    RUNNING: 'accent',
    QUEUED: 'neutral',
    PAUSED: 'warn',
    FAILED: 'loss',
    TARGET_HIT: 'profit',
    STOP_LOSS_HIT: 'loss',
    SESSION_END: 'neutral',
    BUY: 'profit',
    SELL: 'loss',
  }
  if (!state) return <span className="text-ink-faint">—</span>
  return <Badge tone={map[state] ?? 'neutral'}>{String(state).replace(/_/g, ' ')}</Badge>
}

export function Loading({ label = 'Loading…', className }) {
  return (
    <div className={clsx('flex items-center justify-center gap-2 py-10 text-ink-faint', className)}>
      <Loader2 size={16} className="animate-spin" />
      <span className="text-sm">{label}</span>
    </div>
  )
}

export function EmptyState({ title, description, action, icon: Icon = Inbox }) {
  return (
    <div className="flex flex-col items-center justify-center py-12 text-center px-4">
      <Icon size={28} className="text-ink-faint mb-3" />
      <p className="text-sm font-medium text-ink">{title}</p>
      {description && (
        <p className="mt-1 text-xs text-ink-faint max-w-md leading-relaxed">{description}</p>
      )}
      {action && <div className="mt-4">{action}</div>}
    </div>
  )
}

export function ErrorState({ title = 'Could not load this', message, onRetry, details }) {
  return (
    <div className="flex flex-col items-center justify-center py-10 text-center px-4">
      <AlertTriangle size={26} className="text-loss mb-3" />
      <p className="text-sm font-medium text-ink">{title}</p>
      {message && <p className="mt-1 text-xs text-ink-muted max-w-lg">{message}</p>}
      {details && (
        <pre className="mt-3 max-w-lg overflow-auto rounded bg-base-800 p-2 text-left text-2xs text-ink-faint">
          {JSON.stringify(details, null, 2)}
        </pre>
      )}
      {onRetry && (
        <button type="button" className="btn-ghost mt-4" onClick={onRetry}>
          Try again
        </button>
      )}
    </div>
  )
}

/**
 * Shown on every screen that displays money. The platform must never let a
 * simulated figure be mistaken for a real one.
 */
export function PaperTradingBanner({ compact = false }) {
  if (compact) {
    return (
      <Badge tone="warn" className="gap-1">
        <ShieldCheck size={10} /> Paper
      </Badge>
    )
  }
  return (
    <div className="flex items-start gap-2 rounded-md border border-warn/25 bg-warn-soft px-3 py-2">
      <ShieldCheck size={14} className="text-warn mt-0.5 shrink-0" />
      <p className="text-2xs leading-relaxed text-warn">
        <strong className="font-semibold">Paper trading only.</strong> Every figure here is
        simulated and net of modelled brokerage, taxes and slippage. Live order execution is
        disabled in this build and cannot be enabled from the interface.
      </p>
    </div>
  )
}

export function Toggle({ checked, onChange, label, disabled, hint }) {
  return (
    <label
      className={clsx(
        'flex items-center gap-2 select-none',
        disabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer',
      )}
      title={hint}
    >
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        aria-label={label}
        disabled={disabled}
        onClick={() => !disabled && onChange(!checked)}
        className={clsx(
          'relative h-5 w-9 shrink-0 rounded-full transition-colors',
          checked ? 'bg-accent' : 'bg-base-600',
        )}
      >
        <span
          className={clsx(
            'absolute top-0.5 h-4 w-4 rounded-full bg-white transition-transform',
            checked ? 'translate-x-4' : 'translate-x-0.5',
          )}
        />
      </button>
      {label && <span className="text-sm text-ink-muted">{label}</span>}
    </label>
  )
}

export function PageHeader({ title, description, actions, children }) {
  return (
    <div className="mb-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-lg font-semibold text-ink">{title}</h1>
          {description && (
            <p className="mt-1 text-xs text-ink-faint max-w-3xl leading-relaxed">{description}</p>
          )}
        </div>
        {actions && <div className="flex items-center gap-2 shrink-0">{actions}</div>}
      </div>
      {children && <div className="mt-3">{children}</div>}
    </div>
  )
}

/** Blocks a feature that needs a credential or subscription we do not have. */
export function BlockedFeature({ title, reason, docs }) {
  return (
    <div className="panel p-5">
      <div className="flex items-start gap-3">
        <AlertTriangle size={18} className="text-warn mt-0.5 shrink-0" />
        <div>
          <p className="text-sm font-medium text-ink">{title}</p>
          <p className="mt-1.5 text-xs text-ink-muted leading-relaxed max-w-2xl">{reason}</p>
          {docs && (
            <p className="mt-2 text-2xs text-ink-faint">
              See <code className="text-accent">{docs}</code> for setup instructions.
            </p>
          )}
        </div>
      </div>
    </div>
  )
}
