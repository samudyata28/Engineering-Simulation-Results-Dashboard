import { api } from '../api'
import { useAsync } from '../hooks'
import { when } from '../format'

export function SyncPanel({ syncTick }: { syncTick: number }) {
  const { data: run } = useAsync(() => api.latestImport(), [syncTick])
  if (!run) return null
  const problems = run.issues
  return (
    <section className="card">
      <h2>Data import</h2>
      <p className="muted small">
        Last sync {when(run.finished_at ?? run.started_at)} ({run.trigger}) of <code>{run.input_dir}</code>: {run.files_found} files —{' '}
        {run.created} new, {run.updated} changed, {run.unchanged} unchanged, <b className={run.failed ? 'bad' : ''}>{run.failed} failed</b>
        {run.missing > 0 && <>, {run.missing} missing from disk</>}.
      </p>
      {problems.length > 0 ? (
        <ul className="notes">
          {problems.map((i, k) => (
            <li key={k} className={i.severity === 'error' ? 'error' : 'warning'}><span className="tag">{i.severity === 'error' ? 'Not imported' : 'Warning'}</span> <code>{i.path}</code> — {i.message}</li>
          ))}
        </ul>
      ) : <p className="small">All files imported cleanly.</p>}
    </section>
  )
}
