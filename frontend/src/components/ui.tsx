import type { ReactNode } from 'react'
import type { Classification, ResultSummary, Status } from '../api'
import { changeClass, changeLabel, statusClass, statusIcon, statusLabel } from '../format'

export function StatusBadge({ status, marginal = false, small = false }: { status: Status; marginal?: boolean; small?: boolean }) {
  return (
    <span className={`badge ${statusClass(status, marginal)} ${small ? 'sm' : ''}`}>
      <span aria-hidden className="ico">{statusIcon(status, marginal)}</span>
      {statusLabel(status, marginal)}
    </span>
  )
}

export function ChangeTag({ c }: { c: Classification | null }) {
  return <span className={`change ${changeClass(c)}`}>{changeLabel(c)}</span>
}

export function Loading({ what = 'data' }: { what?: string }) {
  return <div className="state">Loading {what}…</div>
}

export function ErrorBox({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="alert error" role="alert">
      <strong>Something went wrong.</strong> {message}
      {onRetry && <button className="btn sm" onClick={onRetry}>Retry</button>}
    </div>
  )
}

export function Stat({ label, value, sub, tone }: { label: string; value: ReactNode; sub?: ReactNode; tone?: string }) {
  return (
    <div className={`stat ${tone ?? ''}`}>
      <div className="stat-label">{label}</div>
      <div className="stat-value">{value}</div>
      {sub && <div className="stat-sub">{sub}</div>}
    </div>
  )
}

export function Warnings({ r }: { r: ResultSummary }) {
  const items = r.warnings
  return (
    <>
      {r.sync_state !== 'ok' && (
        <div className="alert warn" role="alert">
          <strong>{r.sync_state === 'stale_error' ? 'Data may be out of date.' : 'Source file missing.'}</strong> {r.sync_message}
        </div>
      )}
      {items.length > 0 && (
        <ul className="notes">
          {items.map((w, i) => (
            <li key={i} className={w.severity}><span className="tag">{w.severity === 'warning' ? 'Caution' : 'Note'}</span> {w.message}</li>
          ))}
        </ul>
      )}
    </>
  )
}
