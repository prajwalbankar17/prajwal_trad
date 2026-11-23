import { describe, expect, it } from 'vitest'
import { money, number, percent, pnlClass, signed } from '../lib/format'

describe('money', () => {
  it('formats with Indian grouping', () => {
    // 10 lakh groups as 10,00,000 — not 1,000,000.
    expect(money(1000000)).toContain('10,00,000')
  })

  it('returns an em dash for missing values', () => {
    expect(money(null)).toBe('—')
    expect(money(undefined)).toBe('—')
    expect(money('not a number')).toBe('—')
  })

  it('compacts large values when asked', () => {
    expect(money(1000000, { compact: true })).not.toContain('10,00,000')
  })
})

describe('percent and number', () => {
  it('formats to the requested precision', () => {
    expect(percent(12.3456)).toBe('12.35%')
    expect(percent(12.3456, 1)).toBe('12.3%')
    expect(number(1234.5)).toBe('1,234.50')
  })

  it('handles missing values', () => {
    expect(percent(null)).toBe('—')
    expect(number(undefined)).toBe('—')
  })
})

describe('signed', () => {
  it('prefixes a plus only for gains', () => {
    expect(signed(100, (v) => String(v))).toBe('+100')
    expect(signed(-100, (v) => String(v))).toBe('-100')
    expect(signed(0, (v) => String(v))).toBe('0')
  })
})

describe('pnlClass', () => {
  it('treats zero as neutral rather than green', () => {
    expect(pnlClass(0)).toBe('text-ink-muted')
    expect(pnlClass(1)).toBe('text-profit')
    expect(pnlClass(-1)).toBe('text-loss')
  })
})
