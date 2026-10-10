import { useState } from 'react'
import { BrowserRouter, NavLink, Route, Routes } from 'react-router-dom'
import { api } from './api'
import { useAsync } from './hooks'
import { Demands } from './pages/Demands'
import { Overview } from './pages/Overview'
import { ProjectPage } from './pages/ProjectPage'

export default function App() {
  const [syncTick, setSyncTick] = useState(0)
  const [syncing, setSyncing] = useState(false)
  const [syncMsg, setSyncMsg] = useState<string | null>(null)
  const criteria = useAsync(() => api.criteria(), [])
  const c = criteria.data

  const sync = async () => {
    setSyncing(true); setSyncMsg(null)
    try {
      const r = await api.runImport()
      setSyncMsg(`${r.created} new · ${r.updated} changed · ${r.unchanged} unchanged${r.failed ? ` · ${r.failed} failed` : ''}`)
      setSyncTick((t) => t + 1)
    } catch (e) { setSyncMsg((e as Error).message) } finally { setSyncing(false) }
  }

  return (
    <BrowserRouter>
      <a className="skip" href="#main">Skip to content</a>
      <header className="topbar">
        <div className="brand">Simulation Review</div>
        <nav>
          <NavLink to="/" end>Overview</NavLink>
          <NavLink to="/demands">Demands</NavLink>
        </nav>
        <div className="criterion" title={c?.description}>
          Criterion: peak ≤ <b>{c?.limit ?? 15} {c?.unit ?? 'mm'}</b> for <b>{c?.range_min ?? 0}–{c?.range_max ?? 50} Hz</b>
        </div>
        <div className="sync">
          {syncMsg && <span className="muted small" role="status">{syncMsg}</span>}
          <button className="btn" onClick={sync} disabled={syncing}>{syncing ? 'Syncing…' : '⟳ Sync data'}</button>
        </div>
      </header>
      <main id="main">
        <Routes>
          <Route path="/" element={<Overview criteria={c} syncTick={syncTick} />} />
          <Route path="/projects/:name" element={<ProjectPage criteria={c} syncTick={syncTick} />} />
          <Route path="/demands" element={<Demands syncTick={syncTick} />} />
          <Route path="*" element={<div className="alert error">Page not found.</div>} />
        </Routes>
      </main>
      <footer className="foot">Data-review criterion only — not a complete engineering safety assessment.</footer>
    </BrowserRouter>
  )
}
