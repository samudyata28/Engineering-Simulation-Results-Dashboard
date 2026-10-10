import { useState } from 'react'
import { api, type Demand, type ResultSummary } from '../api'
import { num } from '../format'

export function NewDemandDialog({ project, projects, originRevision, originSummary, onClose, onCreated }: {
  project?: string; projects?: string[]; originRevision?: string; originSummary?: ResultSummary
  onClose: () => void; onCreated: (d: Demand) => void
}) {
  const [proj, setProj] = useState(project ?? projects?.[0] ?? '')
  const s = originSummary
  const [text, setText] = useState(
    s ? `Investigate and reduce the ${s.project} resonance: ${s.revision} peaks at ${num(s.peak_magnitude)} ${s.unit} near ${num(s.peak_frequency)} Hz, above the ${s.limit} ${s.unit} limit (${s.range_min}–${s.range_max} Hz).` : '',
  )
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const submit = async () => {
    setBusy(true); setErr(null)
    try { onCreated(await api.createDemand({ project: proj, description: text, origin_revision: originRevision ?? null })) }
    catch (e) { setErr((e as Error).message); setBusy(false) }
  }
  return (
    <div className="overlay" onClick={onClose}>
      <div className="dialog" role="dialog" aria-modal="true" aria-label="Create demand" onClick={(e) => e.stopPropagation()}>
        <h2>{originRevision ? 'Create demand from finding' : 'New manual demand'}</h2>
        {s && (
          <p className="origin-box">
            <b>Origin:</b> {s.project} {s.revision} — peak <b>{num(s.peak_magnitude)} {s.unit}</b> at {num(s.peak_frequency)} Hz vs limit {s.limit} {s.unit} ({s.range_min}–{s.range_max} Hz).
            This origin is recorded permanently.
          </p>
        )}
        {!project && (
          <label className="field">Project / component
            <select value={proj} onChange={(e) => setProj(e.target.value)}>{projects?.map((p) => <option key={p}>{p}</option>)}</select>
          </label>
        )}
        <label className="field">What should be investigated or changed?
          <textarea rows={4} value={text} onChange={(e) => setText(e.target.value)} autoFocus />
        </label>
        {err && <div className="alert error" role="alert">{err}</div>}
        <div className="dialog-actions">
          <button className="btn" onClick={onClose}>Cancel</button>
          <button className="btn primary" disabled={busy || text.trim().length < 3 || !proj} onClick={submit}>Create demand</button>
        </div>
      </div>
    </div>
  )
}
