import type { Classification, Status } from './api'

export const num = (v: number | null | undefined, digits = 1): string =>
  v === null || v === undefined || Number.isNaN(v) ? '—' : v.toFixed(digits)

export const signed = (v: number | null | undefined, digits = 1): string =>
  v === null || v === undefined ? '—' : (v > 0 ? '+' : v < 0 ? '−' : '±') + Math.abs(v).toFixed(digits)

export const statusLabel = (s: Status, marginal = false): string =>
  ({ pass: marginal ? 'Pass · marginal' : 'Pass', fail: 'Fail', incomplete: 'Inconclusive', not_assessable: 'Not assessable' })[s]

export const statusIcon = (s: Status, marginal = false): string =>
  ({ pass: marginal ? '!' : '✓', fail: '✕', incomplete: '?', not_assessable: '–' })[s]

export const statusClass = (s: Status, marginal = false): string =>
  s === 'pass' && marginal ? 'marginal' : s

export const changeLabel = (c: Classification | null): string =>
  c === 'improved' ? '▼ improved' : c === 'degraded' ? '▲ degraded' : c === 'unchanged' ? '= unchanged' : '—'

export const changeClass = (c: Classification | null): string => c ?? 'unknown'

export const when = (iso: string): string => new Date(iso).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })

/** Chart y-axis max: room for the limit line and the tallest curve. */
export function yMax(peaks: number[], limit: number): number {
  const top = Math.max(limit * 1.15, ...peaks.map((p) => p * 1.12))
  const step = top > 40 ? 10 : 5
  return Math.ceil(top / step) * step
}
