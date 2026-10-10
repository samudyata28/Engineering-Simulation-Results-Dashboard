import { describe, expect, it } from 'vitest'
import { num, signed, statusLabel, yMax } from './format'

describe('format', () => {
  it('formats numbers and missing values', () => {
    expect(num(19.94)).toBe('19.9')
    expect(num(null)).toBe('—')
  })
  it('signs deltas with a proper minus', () => {
    expect(signed(2.1)).toBe('+2.1')
    expect(signed(-4.9)).toBe('−4.9')
    expect(signed(0)).toBe('±0.0')
  })
  it('labels marginal passes distinctly', () => {
    expect(statusLabel('pass', true)).toBe('Pass · marginal')
    expect(statusLabel('incomplete')).toBe('Inconclusive')
  })
  it('keeps the limit line inside the chart', () => {
    expect(yMax([2, 3], 15)).toBeGreaterThanOrEqual(15 * 1.15)
    expect(yMax([22], 15)).toBeGreaterThan(22)
  })
})
