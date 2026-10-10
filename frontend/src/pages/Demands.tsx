import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api, DEMAND_STATUSES, type Demand, type DemandStatus } from '../api'
import { NewDemandDialog } from '../components/NewDemandDialog'
import { ChangeTag, ErrorBox, Loading, StatusBadge } from '../components/ui'
import { useAsync } from '../hooks'
import { num, signed, when } from '../format'

const enc = encodeURIComponent

export function Demands({ syncTick }: { syncTick: number }) {
  const [sp, setSp] = useSearchParams()
  const f = { status: sp.get('status') ?? '', project: sp.get('project') ?? '', latest_status: sp.get('latest') ?? '', q: sp.get('q') ?? '' }
  const focus = Number(sp.get('focus')) || null
  const [dialog, setDialog] = useState(false)
  const [open, setOpen] = useState<number | null>(focus)
  const [reviewOnly, setReviewOnly] = useState(false)
  const projects = useAsync(() => api.projects(), [syncTick])
  const { data, error, loading, reload } = useAsync(() => api.demands(f), [f.status, f.project, f.latest_status, f.q, syncTick])
  useEffect(() => { if (focus) setOpen(focus) }, [focus])

  const set = (k: string, v: string) => { const n = new URLSearchParams(sp); v ? n.set(k, v) : n.delete(k); n.delete('focus'); setSp(n, { replace: true }) }
  const rows = (data ?? []).filter((d) => !reviewOnly || d.needs_review)
  const filtered = !!(f.status || f.project || f.latest_status || f.q || reviewOnly)

  return (
    <div className="stack">
      <section className="row-between">
        <div>
          <h1>Engineering demands</h1>
          <p className="lede">Follow-up items tracked against a component across all of its revisions. A later passing result never resolves a demand automatically — that is an engineering decision.</p>
        </div>
        <button className="btn primary" onClick={() => setDialog(true)}>+ New manual demand</button>
      </section>

      <div className="card filters">
        <label>Status<select value={f.status} onChange={(e) => set('status', e.target.value)}><option value="">All</option>{DEMAND_STATUSES.map((s) => <option key={s}>{s}</option>)}</select></label>
        <label>Project<select value={f.project} onChange={(e) => set('project', e.target.value)}><option value="">All</option>{projects.data?.map((p) => <option key={p.name}>{p.name}</option>)}</select></label>
        <label>Latest result<select value={f.latest_status} onChange={(e) => set('latest', e.target.value)}>
          <option value="">Any</option><option value="fail">Fail</option><option value="pass">Pass</option><option value="incomplete">Inconclusive</option></select></label>
        <label className="grow">Search<input type="search" placeholder="Description or project…" value={f.q} onChange={(e) => set('q', e.target.value)} /></label>
        <label className="toggle"><input type="checkbox" checked={reviewOnly} onChange={(e) => setReviewOnly(e.target.checked)} /> Needs review</label>
        {filtered && <button className="btn sm" onClick={() => { setSp({}); setReviewOnly(false) }}>Clear</button>}
      </div>

      {loading && !data && <Loading what="demands" />}
      {error && <ErrorBox message={error} onRetry={reload} />}
      {data && (
        <div className="card flush">
          <div className="table-wrap">
            <table className="demands">
              <thead><tr><th>#</th><th>Component / project</th><th>Demand</th><th>Status</th><th>Origin</th><th>Result per revision</th><th>Latest</th></tr></thead>
              <tbody>
                {rows.length === 0 && <tr><td colSpan={7} className="empty">{filtered ? 'No demands match these filters.' : 'No demands yet. Create one from a failed result, or add a manual demand.'}</td></tr>}
                {rows.map((d) => (
                  <DemandRow key={d.id} d={d} open={open === d.id} onToggle={() => setOpen(open === d.id ? null : d.id)} onChanged={reload} />
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
      {dialog && <NewDemandDialog projects={projects.data?.map((p) => p.name)} onClose={() => setDialog(false)} onCreated={(d) => { setDialog(false); setOpen(d.id); reload() }} />}
    </div>
  )
}

function DemandRow({ d, open, onToggle, onChanged }: { d: Demand; open: boolean; onToggle: () => void; onChanged: () => void }) {
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const o = d.origin
  const changeStatus = async (status: DemandStatus) => {
    setBusy(true); setErr(null)
    try { await api.updateDemand(d.id, { status }); onChanged() } catch (e) { setErr((e as Error).message) } finally { setBusy(false) }
  }
  return (
    <>
      <tr className={open ? 'open' : ''} id={`demand-${d.id}`}>
        <td><button className="link" onClick={onToggle} aria-expanded={open} aria-label={`Toggle details for demand ${d.id}`}>{open ? '▾' : '▸'} {d.id}</button></td>
        <td><Link to={`/projects/${enc(d.project)}`}><b>{d.component}</b></Link><div className="muted small">{d.project}</div></td>
        <td className="desc">{d.description}
          {d.needs_review && <div className="flag review">Latest result ({d.latest?.revision}) passes — review whether this can be resolved.</div>}
          {d.regressed && <div className="flag regress">Marked Resolved, but the latest result ({d.latest?.revision}) fails again.</div>}
        </td>
        <td>
          <select className={`status-select ${d.status.replace(' ', '')}`} value={d.status} disabled={busy} onChange={(e) => changeStatus(e.target.value as DemandStatus)} aria-label={`Status of demand ${d.id}`}>
            {DEMAND_STATUSES.map((s) => <option key={s}>{s}</option>)}
          </select>
          {err && <div className="bad small">{err}</div>}
        </td>
        <td className="origin">
          {o.manual ? <span className="muted">Created manually</span> : (
            <>
              <Link to={`/projects/${enc(d.project)}?tab=response&rev=${enc(o.revision!)}`}><b>{o.revision}</b></Link>
              <div className="small">{o.metric?.replace('Peak displacement magnitude', 'Peak')}</div>
              <div className="small"><b>{num(o.value)} {o.unit}</b> @ {num(o.frequency)} Hz · limit {o.limit} {o.unit}</div>
            </>
          )}
        </td>
        <td>
          <div className="chips">
            {d.linked_results.map((r) => (
              <Link key={r.revision} className={`rchip ${r.status === 'pass' && r.marginal ? 'marginal' : r.status} ${r.is_origin ? 'origin' : ''}`}
                to={`/projects/${enc(d.project)}?tab=response&rev=${enc(r.revision)}`} title={`${r.revision}: ${r.status} — peak ${num(r.peak_magnitude)} ${r.unit} @ ${num(r.peak_frequency)} Hz`}>
                <span>{r.revision}{r.is_origin ? ' ★' : ''}</span><b>{num(r.peak_magnitude)}</b>
              </Link>
            ))}
          </div>
        </td>
        <td>{d.latest ? <><StatusBadge status={d.latest.status} marginal={d.latest.marginal} small /><div className="small muted">{d.latest.revision}: {num(d.latest.peak_magnitude)} {d.latest.unit}</div></> : '—'}</td>
      </tr>
      {open && <tr className="detail"><td colSpan={7}><DemandDetail d={d} onChanged={onChanged} /></td></tr>}
    </>
  )
}

function DemandDetail({ d, onChanged }: { d: Demand; onChanged: () => void }) {
  const [text, setText] = useState(d.description)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  useEffect(() => setText(d.description), [d.description])
  const first = d.linked_results[0]?.revision
  const latest = d.latest?.revision
  const save = async () => {
    setBusy(true); setErr(null)
    try { await api.updateDemand(d.id, { description: text }); onChanged() } catch (e) { setErr((e as Error).message) } finally { setBusy(false) }
  }
  const originRev = d.origin.revision ?? first
  return (
    <div className="detail-grid">
      <div>
        <h3>Edit description</h3>
        <textarea rows={3} value={text} onChange={(e) => setText(e.target.value)} />
        <div className="row">
          <button className="btn primary sm" disabled={busy || text.trim() === d.description || text.trim().length < 3} onClick={save}>Save description</button>
          {err && <span className="bad small">{err}</span>}
        </div>
        <h3>Trace</h3>
        <div className="row links">
          {originRev && <Link className="btn sm" to={`/projects/${enc(d.project)}?tab=response&rev=${enc(originRev)}`}>Origin result ({originRev})</Link>}
          {originRev && latest && originRev !== latest && <Link className="btn sm" to={`/projects/${enc(d.project)}?tab=compare&base=${enc(originRev)}&target=${enc(latest)}`}>Compare {originRev} → {latest}</Link>}
          <Link className="btn sm" to={`/projects/${enc(d.project)}?tab=history`}>Full history</Link>
        </div>
        {d.origin.drifted && <div className="alert warn small">The origin revision’s data was re-imported and now shows {num(d.origin.current_value)} {d.origin.unit}; the demand keeps the originally recorded {num(d.origin.value)} {d.origin.unit}.</div>}
      </div>
      <div>
        <h3>Result history for {d.component}</h3>
        <table className="mini">
          <thead><tr><th>Revision</th><th>Result</th><th>Peak</th><th>Freq.</th><th>Margin</th>{!d.origin.manual && <th>vs origin</th>}</tr></thead>
          <tbody>
            {d.linked_results.map((r, i, arr) => (
              <tr key={r.revision}>
                <th scope="row">{r.revision}{r.is_origin && ' ★ origin'}{i === arr.length - 1 && ' (latest)'}</th>
                <td><StatusBadge status={r.status} marginal={r.marginal} small /></td>
                <td>{num(r.peak_magnitude)} {r.unit}</td><td>{num(r.peak_frequency)} Hz</td><td>{signed(r.margin)}</td>
                {!d.origin.manual && <td>{r.is_origin ? '—' : <><ChangeTag c={r.change_vs_origin} /> <span className="muted">{signed(r.delta_vs_origin)}</span></>}</td>}
              </tr>
            ))}
          </tbody>
        </table>
        <h3>Activity</h3>
        <ul className="events">{[...d.events].reverse().map((e, i) => <li key={i}><span className="muted">{when(e.at)}</span> {e.detail}</li>)}</ul>
      </div>
    </div>
  )
}
