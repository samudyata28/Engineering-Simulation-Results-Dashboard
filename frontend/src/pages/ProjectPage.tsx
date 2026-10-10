import { useMemo, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { Bar, BarChart, CartesianGrid, Cell, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api, type Criteria, type Demand, type ResultSummary } from '../api'
import { DeltaChart, ResponseChart, type Series } from '../components/ResponseChart'
import { ChangeTag, ErrorBox, Loading, Stat, StatusBadge, Warnings } from '../components/ui'
import { useAsync } from '../hooks'
import { num, signed, when, yMax } from '../format'
import { NewDemandDialog } from '../components/NewDemandDialog'


export function ProjectPage({ criteria, syncTick }: { criteria: Criteria | null; syncTick: number }) {
  const { name = '' } = useParams()
  const [sp, setSp] = useSearchParams()
  const tab = sp.get('tab') ?? 'response'
  const projects = useAsync(() => api.projects(), [syncTick])
  const project = projects.data?.find((p) => p.name === name)
  const revNames = project?.revisions.map((r) => r.name) ?? []
  const rev = sp.get('rev') && revNames.includes(sp.get('rev')!) ? sp.get('rev')! : revNames[revNames.length - 1]

  const setParams = (patch: Record<string, string | null>) => {
    const next = new URLSearchParams(sp)
    for (const [k, v] of Object.entries(patch)) v === null ? next.delete(k) : next.set(k, v)
    setSp(next, { replace: true })
  }

  if (projects.loading && !projects.data) return <Loading what="project" />
  if (projects.error) return <ErrorBox message={projects.error} onRetry={projects.reload} />
  if (!project) return <div className="alert error">Unknown project “{name}”. <Link to="/">Back to overview</Link></div>
  if (!rev) return <div className="alert warn">{name} has no imported revisions yet.</div>

  return (
    <div className="stack">
      <header className="proj-head">
        {project.image_url && <img src={project.image_url} alt={`${project.name} component`} className="thumb" />}
        <div>
          <div className="crumbs"><Link to="/">Overview</Link> / Project</div>
          <h1>{project.name}</h1>
          <div className="muted small">Component <b>{project.name}</b> · {project.revisions.length} revision(s) · latest <b>{project.latest_revision}</b></div>
        </div>
        <div className="rev-pills" role="tablist" aria-label="Revisions">
          {project.revisions.map((r) => (
            <button key={r.name} role="tab" aria-selected={r.name === rev && tab === 'response'}
              className={`pill ${r.name === rev ? 'active' : ''}`} onClick={() => setParams({ rev: r.name, tab: 'response' })}>
              <span className={`dot ${r.status === 'pass' && r.marginal ? 'marginal' : r.status}`} />
              {r.name}<small>{num(r.peak_magnitude)} mm</small>
            </button>
          ))}
        </div>
      </header>

      <nav className="tabs" aria-label="Views">
        {[['response', 'Response'], ['compare', 'Compare revisions'], ['history', 'History & trace']].map(([k, label]) => (
          <button key={k} className={tab === k ? 'active' : ''} onClick={() => setParams({ tab: k })}>{label}</button>
        ))}
      </nav>

      {tab === 'response' && <ResponseTab project={name} rev={rev} syncTick={syncTick} />}
      {tab === 'compare' && <CompareTab project={name} revs={revNames} sp={sp} setParams={setParams} syncTick={syncTick} criteria={criteria} />}
      {tab === 'history' && <HistoryTab project={name} syncTick={syncTick} />}
    </div>
  )
}

/* ------------------------------------------------------------------ response */
function ResponseTab({ project, rev, syncTick }: { project: string; rev: string; syncTick: number }) {
  const { data, error, loading, reload } = useAsync(() => api.revision(project, rev), [project, rev, syncTick])
  const demands = useAsync(() => api.demands({ project }), [project, syncTick])
  const [zoom, setZoom] = useState(false)
  const [dialog, setDialog] = useState(false)
  const nav = useNavigate()
  if (loading && !data) return <Loading what="response" />
  if (error) return <ErrorBox message={error} onRetry={reload} />
  if (!data) return null
  const s = data.summary
  const existing = demands.data?.find((d) => d.origin.revision === s.revision && d.status !== 'Resolved')
  const series: Series[] = [{
    id: 'r', label: s.revision, color: '#2f6fdb', samples: data.samples,
    peak: s.peak_magnitude !== null && s.peak_frequency !== null ? { frequency: s.peak_frequency, magnitude: s.peak_magnitude } : null,
  }]
  const tone = s.status === 'pass' && s.marginal ? 'marginal' : s.status

  return (
    <div className="stack">
      <div className={`verdict ${tone}`}>
        <StatusBadge status={s.status} marginal={s.marginal} />
        <p>{s.explanation}</p>
      </div>

      <div className="stats">
        <Stat label={`Peak in ${s.range_min}–${s.range_max} Hz`} value={<>{num(s.peak_magnitude)} <span className="unit">{s.unit}</span></>} sub={`at ${num(s.peak_frequency)} Hz`} tone={tone} />
        <Stat label="Limit" value={<>{num(s.limit, 0)} <span className="unit">{s.unit}</span></>} sub={`for ${s.range_min}–${s.range_max} Hz (inclusive)`} />
        <Stat label="Margin to limit" value={<>{signed(s.margin)} <span className="unit">{s.unit}</span></>} sub={s.margin === null ? '' : s.margin >= 0 ? 'below limit' : 'above limit'} tone={tone} />
        <Stat label="Overall peak (all frequencies)" value={<>{num(s.overall_peak_magnitude)} <span className="unit">{s.unit}</span></>} sub={`at ${num(s.overall_peak_frequency)} Hz · not assessed beyond ${s.range_max} Hz`} />
      </div>

      <section className="card">
        <div className="card-head">
          <h2>{project} · {s.revision} — frequency response</h2>
          <label className="toggle"><input type="checkbox" checked={zoom} onChange={(e) => setZoom(e.target.checked)} /> Zoom to assessed range</label>
        </div>
        <ResponseChart series={series} limit={s.limit} unit={s.unit} rangeMin={s.range_min} rangeMax={s.range_max} zoomToRange={zoom} />
        <Warnings r={s} />
      </section>

      <section className="card">
        <div className="card-head">
          <h2>Follow-up</h2>
        </div>
        {s.status === 'fail' ? (
          existing ? (
            <p>Demand <Link to={`/demands?focus=${existing.id}`}>#{existing.id}</Link> already tracks this finding ({existing.status}).</p>
          ) : (
            <>
              <p className="muted">This revision exceeds the limit. Create a demand to track the investigation; it will stay linked to {project} across all later revisions.</p>
              <button className="btn primary" onClick={() => setDialog(true)}>Create demand from this finding</button>
            </>
          )
        ) : (
          <p className="muted">No failed finding on this revision. A demand can still be raised manually from the <Link to="/demands">Demands</Link> page.</p>
        )}
        {demands.data && demands.data.length > 0 && (
          <p className="small">Demands on {project}: {demands.data.map((d) => <Link key={d.id} to={`/demands?focus=${d.id}`} className="chip">#{d.id} {d.status}</Link>)}</p>
        )}
      </section>
      {dialog && <NewDemandDialog project={project} originRevision={s.revision} originSummary={s} onClose={() => setDialog(false)} onCreated={(d: Demand) => nav(`/demands?focus=${d.id}`)} />}

      <SamplesTable s={s} samples={data.samples} />
      <Provenance s={s} />
    </div>
  )
}

function SamplesTable({ s, samples }: { s: ResultSummary; samples: { frequency: number; magnitude: number; in_range: boolean }[] }) {
  return (
    <details className="card">
      <summary>Samples ({s.sample_count}) — {s.samples_in_range} within the assessed range</summary>
      <div className="table-wrap narrow">
        <table>
          <thead><tr><th>Frequency [Hz]</th><th>Magnitude [{s.unit}]</th><th>Assessed?</th><th>vs limit</th></tr></thead>
          <tbody>
            {samples.map((p) => (
              <tr key={p.frequency} className={p.frequency === s.peak_frequency && p.in_range ? 'peak-row' : ''}>
                <td>{p.frequency}</td><td>{p.magnitude}</td>
                <td>{p.in_range ? 'Yes' : <span className="muted">No (&gt; {s.range_max} Hz)</span>}</td>
                <td>{p.in_range ? (p.magnitude > s.limit ? <span className="bad">over by {(p.magnitude - s.limit).toFixed(1)}</span> : 'ok') : '—'}{p.frequency === s.peak_frequency && p.in_range ? ' · peak' : ''}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  )
}

function Provenance({ s }: { s: ResultSummary }) {
  return (
    <p className="muted small prov">
      Source <code>{s.source_path}</code> · imported {when(s.imported_at)} · data version {s.data_version} · sha256 <code>{s.file_hash.slice(0, 10)}…</code> · {s.project} / {s.revision} / result #{s.id}
    </p>
  )
}

/* ------------------------------------------------------------------ compare */
function CompareTab({ project, revs, sp, setParams, syncTick, criteria }: {
  project: string; revs: string[]; sp: URLSearchParams; setParams: (p: Record<string, string | null>) => void; syncTick: number; criteria: Criteria | null
}) {
  const base = revs.includes(sp.get('base') ?? '') ? sp.get('base')! : revs[0]
  const target = revs.includes(sp.get('target') ?? '') ? sp.get('target')! : revs[revs.length - 1]
  const [zoom, setZoom] = useState(false)
  const { data, error, loading, reload } = useAsync(() => api.compare(project, base, target), [project, base, target, syncTick])

  const series: Series[] = useMemo(() => data ? [
    { id: 'a', label: `${data.base.revision} (base)`, color: '#6b7280', samples: data.base_samples, dashed: true,
      peak: data.base.peak_frequency !== null ? { frequency: data.base.peak_frequency, magnitude: data.base.peak_magnitude! } : null },
    { id: 'b', label: `${data.target.revision} (target)`, color: '#2f6fdb', samples: data.target_samples,
      peak: data.target.peak_frequency !== null ? { frequency: data.target.peak_frequency, magnitude: data.target.peak_magnitude! } : null },
  ] : [], [data])

  if (revs.length < 2) return <div className="alert warn">Only one revision exists for {project}; there is nothing to compare yet.</div>
  return (
    <div className="stack">
      <div className="card compare-pick">
        <label>Base <select value={base} onChange={(e) => setParams({ base: e.target.value })}>{revs.map((r) => <option key={r}>{r}</option>)}</select></label>
        <button className="btn sm" title="Swap" onClick={() => setParams({ base: target, target: base })}>⇄</button>
        <label>Target <select value={target} onChange={(e) => setParams({ target: e.target.value })}>{revs.map((r) => <option key={r}>{r}</option>)}</select></label>
        <span className="muted small">Comparing <b>{project}</b>: {base} → {target}</span>
      </div>
      {base === target && <div className="alert warn">Base and target are the same revision; choose two different revisions to see changes.</div>}
      {loading && !data && <Loading what="comparison" />}
      {error && <ErrorBox message={error} onRetry={reload} />}
      {data && (
        <>
          <div className={`verdict ${data.overall}`}>
            <ChangeTag c={data.overall} />
            <p>{data.verdict}</p>
          </div>
          <section className="card">
            <div className="card-head">
              <h2>Overlaid frequency response</h2>
              <label className="toggle"><input type="checkbox" checked={zoom} onChange={(e) => setZoom(e.target.checked)} /> Zoom to assessed range</label>
            </div>
            <ResponseChart series={series} limit={data.base.limit} unit={data.base.unit} rangeMin={data.base.range_min} rangeMax={data.base.range_max} zoomToRange={zoom} />
          </section>

          <section className="card">
            <h2>Metric changes</h2>
            <div className="table-wrap">
              <table>
                <thead><tr><th>Metric</th><th>{data.base.revision}</th><th>{data.target.revision}</th><th>Change</th><th></th></tr></thead>
                <tbody>
                  <tr><th scope="row">Assessment ({criteria?.limit ?? 15} {data.base.unit}, ≤ {data.base.range_max} Hz)</th>
                    <td><StatusBadge status={data.base.status} marginal={data.base.marginal} small /></td>
                    <td><StatusBadge status={data.target.status} marginal={data.target.marginal} small /></td>
                    <td colSpan={2}>{data.status_change}</td></tr>
                  {data.changes.map((c) => (
                    <tr key={c.metric}>
                      <th scope="row">{c.metric}</th>
                      <td>{num(c.base)} {c.unit}</td><td>{num(c.target)} {c.unit}</td>
                      <td>{signed(c.delta)} {c.unit}{c.delta_pct !== null && c.unit !== 'Hz' && !c.metric.startsWith('Margin') ? ` (${signed(c.delta_pct)}%)` : ''}</td>
                      <td>{c.classification ? <ChangeTag c={c.classification} /> : ''}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="muted small">▼ lower magnitude = improved. Changes of ≤ {criteria?.change_tolerance ?? 0.05} {data.base.unit} are reported as unchanged (CSV resolution is 0.1 {data.base.unit}).</p>
            {data.notes.length > 0 && <ul className="notes">{data.notes.map((n, i) => <li key={i} className="info"><span className="tag">Note</span> {n}</li>)}</ul>}
          </section>

          <section className="card">
            <h2>Difference curve (target − base)</h2>
            <p className="muted small">{data.delta_curve_note}
              {data.largest_in_range_change && <> Largest in-range change: <b>{signed(data.largest_in_range_change.delta, 2)} {data.base.unit}</b> at {num(data.largest_in_range_change.frequency)} Hz.</>}
            </p>
            <DeltaChart points={data.delta_curve} unit={data.base.unit} rangeMax={data.base.range_max} zoomToRange={zoom} />
          </section>
        </>
      )}
    </div>
  )
}

/* ------------------------------------------------------------------ history */
function HistoryTab({ project, syncTick }: { project: string; syncTick: number }) {
  const { data, error, loading, reload } = useAsync(() => api.history(project), [project, syncTick])
  const demands = useAsync(() => api.demands({ project }), [project, syncTick])
  if (loading && !data) return <Loading what="history" />
  if (error) return <ErrorBox message={error} onRetry={reload} />
  if (!data) return null
  const first = data.steps[0]?.summary
  const rows = data.steps.map((s) => ({ rev: s.summary.revision, peak: s.summary.peak_magnitude ?? 0, status: s.summary.status, marginal: s.summary.marginal }))
  const top = Math.max(5, Math.ceil(yMax(rows.map((r) => r.peak), first?.limit ?? 15) / 5) * 5)
  const colorOf = (r: { status: string; marginal: boolean }) => r.status === 'fail' ? 'var(--fail)' : r.marginal ? 'var(--marginal)' : r.status === 'pass' ? 'var(--pass)' : 'var(--muted)'
  return (
    <div className="stack">
      <div className={`verdict ${data.trend}`}><ChangeTag c={data.trend as never} /><p>{data.trend_text}</p></div>
      <section className="card">
        <h2>In-range peak by revision</h2>
        <div className="chart" role="img" aria-label="Peak magnitude per revision versus limit">
          <ResponsiveContainer width="100%" height={230}>
            <BarChart data={rows} margin={{ top: 16, right: 24, bottom: 8, left: 8 }}>
              <CartesianGrid stroke="var(--grid)" vertical={false} />
              <XAxis dataKey="rev" tick={{ fill: 'var(--muted)', fontSize: 12 }} />
              <YAxis domain={[0, top]} ticks={Array.from({ length: top / 5 + 1 }, (_, i) => i * 5)} width={52} tick={{ fill: 'var(--muted)', fontSize: 12 }}
                label={{ value: `Peak [${first?.unit ?? 'mm'}]`, angle: -90, position: 'insideLeft', fill: 'var(--muted)', fontSize: 12 }} />
              <Tooltip formatter={(v) => [`${v} ${first?.unit}`, 'In-range peak']} />
              <Bar dataKey="peak" maxBarSize={110} isAnimationActive={false} label={{ position: 'top', fill: 'var(--text)', fontSize: 12 }}>
                {rows.map((r) => <Cell key={r.rev} fill={colorOf(r)} />)}
              </Bar>
              <ReferenceLine y={first?.limit} stroke="var(--fail)" strokeDasharray="6 4" strokeWidth={2} label={{ value: `Limit ${first?.limit} ${first?.unit}`, position: 'insideTopLeft', fill: 'var(--fail)', fontSize: 12, fontWeight: 600 }} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </section>

      <section className="card">
        <h2>Revision-by-revision trace</h2>
        <div className="table-wrap">
          <table>
            <thead><tr><th>Revision</th><th>Result</th><th>Peak</th><th>Frequency</th><th>Margin</th><th>vs previous</th><th>vs {first?.revision}</th><th>Actions</th></tr></thead>
            <tbody>
              {data.steps.map((st, i) => {
                const s = st.summary
                const prev = data.steps[i - 1]
                return (
                  <tr key={s.revision}>
                    <th scope="row">{s.revision}</th>
                    <td><StatusBadge status={s.status} marginal={s.marginal} small /></td>
                    <td>{num(s.peak_magnitude)} {s.unit}</td><td>{num(s.peak_frequency)} Hz</td><td>{signed(s.margin)} {s.unit}</td>
                    <td>{st.vs_previous ? <><ChangeTag c={st.vs_previous.classification} /> <span className="muted">{signed(st.vs_previous.delta)}</span></> : <span className="muted">baseline</span>}</td>
                    <td>{i === 0 ? <span className="muted">—</span> : <><ChangeTag c={(st.vs_first ?? st.vs_previous)!.classification} /> <span className="muted">{signed((st.vs_first ?? st.vs_previous)!.delta)}</span></>}</td>
                    <td className="actions">
                      <Link to={`?tab=response&rev=${encodeURIComponent(s.revision)}`}>Open</Link>
                      {prev && <Link to={`?tab=compare&base=${encodeURIComponent(prev.summary.revision)}&target=${encodeURIComponent(s.revision)}`}>Compare to {prev.summary.revision}</Link>}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </section>

      <section className="card">
        <h2>Linked demands</h2>
        {demands.data && demands.data.length ? (
          <ul className="next">{demands.data.map((d) => (
            <li key={d.id}><Link to={`/demands?focus=${d.id}`}>#{d.id}</Link> <span className={`status-pill ${d.status.replace(' ', '')}`}>{d.status}</span> — {d.description}
              {d.needs_review && <span className="flag review"> latest result passes — review for resolution</span>}</li>
          ))}</ul>
        ) : <p className="muted">No demands yet for {project}.</p>}
      </section>
    </div>
  )
}
