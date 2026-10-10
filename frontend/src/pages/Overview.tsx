import { Link } from 'react-router-dom'
import { api, type Criteria, type Project } from '../api'
import { ErrorBox, Loading, StatusBadge } from '../components/ui'
import { useAsync } from '../hooks'
import { num, signed } from '../format'
import { SyncPanel } from '../components/SyncPanel'

export function Overview({ criteria, syncTick }: { criteria: Criteria | null; syncTick: number }) {
  const { data, error, loading, reload } = useAsync(() => api.projects(), [syncTick])
  if (loading && !data) return <Loading what="projects" />
  if (error) return <ErrorBox message={error} onRetry={reload} />
  const projects = data ?? []
  const revs = [...new Set(projects.flatMap((p) => p.revisions.map((r) => r.name)))].sort((a, b) => a.localeCompare(b, undefined, { numeric: true }))
  const latest = projects.filter((p) => p.latest_status)
  const failing = latest.filter((p) => p.latest_status === 'fail')
  const needAttention = projects.filter((p) => p.latest_status !== 'pass' || p.open_demands > 0)

  return (
    <div className="stack">
      <section>
        <h1>Review overview</h1>
        {criteria && <p className="lede">{criteria.description}</p>}
      </section>

      {projects.length === 0 ? (
        <div className="alert warn">No projects have been imported yet. Add CSVs under <code>Inputs/&lt;revision&gt;/&lt;Project&gt;.csv</code> and press “Sync data”.</div>
      ) : (
        <>
          <div className="stats">
            <div className="stat"><div className="stat-label">Projects</div><div className="stat-value">{projects.length}</div><div className="stat-sub">{revs.length} revisions</div></div>
            <div className={`stat ${failing.length ? 'fail' : 'pass'}`}>
              <div className="stat-label">Failing in latest revision</div>
              <div className="stat-value">{failing.length} <span className="of">of {latest.length}</span></div>
              <div className="stat-sub">{failing.map((p) => p.name).join(', ') || 'none'}</div>
            </div>
            <div className="stat"><div className="stat-label">Open demands</div><div className="stat-value">{projects.reduce((n, p) => n + p.open_demands, 0)}</div>
              <div className="stat-sub"><Link to="/demands">View demands →</Link></div></div>
          </div>

          <section className="card">
            <h2>Peak magnitude by project and revision</h2>
            <p className="muted small">In-range peak (≤ {criteria?.range_max ?? 50} Hz) in {criteria?.unit ?? 'mm'}. Select a cell to open that revision.</p>
            <div className="table-wrap">
              <table className="matrix">
                <thead><tr><th>Project</th>{revs.map((r) => <th key={r}>{r}</th>)}<th>Peak trend</th><th>Demands</th></tr></thead>
                <tbody>
                  {projects.map((p) => <MatrixRow key={p.name} p={p} revs={revs} />)}
                </tbody>
              </table>
            </div>
          </section>

          {needAttention.length > 0 && (
            <section className="card">
              <h2>Where to look next</h2>
              <ul className="next">
                {needAttention.map((p) => (
                  <li key={p.name}>
                    <Link to={`/projects/${encodeURIComponent(p.name)}?tab=history`}><b>{p.name}</b></Link>{' '}
                    {p.latest_status === 'fail' && <>still fails in {p.latest_revision}. </>}
                    {p.latest_status === 'pass' && p.open_demands > 0 && <>passes in {p.latest_revision} but has {p.open_demands} unresolved demand(s) awaiting an engineering decision. </>}
                    {p.latest_status !== 'pass' && p.latest_status !== 'fail' && <>latest result is not assessable. </>}
                  </li>
                ))}
              </ul>
            </section>
          )}
        </>
      )}
      <SyncPanel syncTick={syncTick} />
    </div>
  )
}

const TOL = 0.05
function Trend({ p }: { p: Project }) {
  const pk = p.revisions.map((r) => r.peak_magnitude)
  if (pk.length < 2 || pk.includes(null)) return <span className="muted">—</span>
  const row = (label: string, a: number, b: number) => {
    const d = b - a
    const cls = d < -TOL ? 'improved' : d > TOL ? 'degraded' : 'unchanged'
    return <div className={`change ${cls}`}>{cls === 'improved' ? '▼' : cls === 'degraded' ? '▲' : '='} {signed(d)} mm <span className="muted">{label}</span></div>
  }
  const n = pk.length - 1
  return <>{row(`vs ${p.revisions[n - 1].name}`, pk[n - 1]!, pk[n]!)}{n > 1 && row(`vs ${p.revisions[0].name}`, pk[0]!, pk[n]!)}</>
}

function MatrixRow({ p, revs }: { p: Project; revs: string[] }) {
  return (
    <tr>
      <th scope="row"><Link to={`/projects/${encodeURIComponent(p.name)}`}>{p.name}</Link></th>
      {revs.map((rn) => {
        const r = p.revisions.find((x) => x.name === rn)
        if (!r) return <td key={rn} className="muted">—</td>
        return (
          <td key={rn}>
            <Link className={`cell ${r.status === 'pass' && r.marginal ? 'marginal' : r.status}`} to={`/projects/${encodeURIComponent(p.name)}?rev=${encodeURIComponent(rn)}`}>
              <span className="cell-num">{num(r.peak_magnitude)}</span>
              <StatusBadge status={r.status} marginal={r.marginal} small />
            </Link>
          </td>
        )
      })}
      <td><Trend p={p} /></td>
      <td>{p.open_demands ? <Link to={`/demands?project=${encodeURIComponent(p.name)}`}>{p.open_demands} open</Link> : <span className="muted">0</span>}</td>
    </tr>
  )
}
