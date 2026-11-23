/** Indian number formatting (lakh/crore grouping) and P&L helpers. */

const inr = new Intl.NumberFormat('en-IN', {
  style: 'currency',
  currency: 'INR',
  maximumFractionDigits: 2,
})

const inrCompact = new Intl.NumberFormat('en-IN', {
  style: 'currency',
  currency: 'INR',
  notation: 'compact',
  maximumFractionDigits: 2,
})

export function money(value, { compact = false } = {}) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '—'
  return compact ? inrCompact.format(Number(value)) : inr.format(Number(value))
}

export function number(value, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '—'
  return Number(value).toLocaleString('en-IN', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })
}

export function percent(value, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '—'
  return `${Number(value).toFixed(digits)}%`
}

export function signed(value, formatter = money) {
  if (value === null || value === undefined) return '—'
  const n = Number(value)
  return `${n > 0 ? '+' : ''}${formatter(n)}`
}

/** Tailwind class for a P&L figure. Zero is neutral, not green. */
export function pnlClass(value) {
  const n = Number(value)
  if (!n) return 'text-ink-muted'
  return n > 0 ? 'text-profit' : 'text-loss'
}

export function timeIST(iso, { withDate = false } = {}) {
  if (!iso) return '—'
  const d = new Date(iso)
  const time = d.toLocaleTimeString('en-IN', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
    timeZone: 'Asia/Kolkata',
  })
  if (!withDate) return time
  const date = d.toLocaleDateString('en-IN', {
    day: '2-digit',
    month: 'short',
    timeZone: 'Asia/Kolkata',
  })
  return `${date} ${time}`
}

export function dateIST(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString('en-IN', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    timeZone: 'Asia/Kolkata',
  })
}
