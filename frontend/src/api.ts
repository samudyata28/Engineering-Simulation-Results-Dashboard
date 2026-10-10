export type Status = 'pass' | 'fail' | 'incomplete' | 'not_assessable'
export type DemandStatus = 'Open' | 'In Progress' | 'Resolved'
export const DEMAND_STATUSES: DemandStatus[] = ['Open', 'In Progress', 'Resolved']

export interface Warning { code: string; severity: 'info' | 'warning'; message: string }
export interface ResultSummary {
  id: number; project: string; revision: string; status: Status; marginal: boolean
  metric: string; unit: string; limit: number; range_min: number; range_max: number
  peak_magnitude: number | null; peak_frequency: number | null; margin: number | null
  samples_in_range: number; sample_count: number; freq_min: number; freq_max: number
  overall_peak_magnitude: number; overall_peak_frequency: number
  explanation: string; warnings: Warning[]
  sync_state: 'ok' | 'stale_error' | 'source_missing'; sync_message: string | null
  source_path: string; file_hash: string; data_version: number; imported_at: string; updated_at: string
}
export interface Sample { frequency: number; magnitude: number; in_range: boolean }
export interface RevisionResult { summary: ResultSummary; samples: Sample[] }
export interface Criteria {
  metric: string; unit: string; limit: number; range_min: number; range_max: number
  marginal_fraction: number; change_tolerance: number; description: string
}
export interface RevisionRef {
  name: string; status: Status; marginal: boolean; peak_magnitude: number | null
  peak_frequency: number | null; sync_state: string
}
export interface Project {
  name: string; image_url: string | null; revisions: RevisionRef[]
  latest_revision: string | null; latest_status: Status | null; trend: string; open_demands: number
}
export type Classification = 'improved' | 'degraded' | 'unchanged' | 'unknown'
export interface Change {
  metric: string; unit: string; base: number | null; target: number | null
  delta: number | null; delta_pct: number | null; classification: Classification | null
}
export interface DeltaPoint { frequency: number; base: number; target: number; delta: number }
export interface Comparison {
  project: string; base: ResultSummary; target: ResultSummary; changes: Change[]
  status_change: string; overall: Classification; verdict: string
  base_samples: Sample[]; target_samples: Sample[]; delta_curve: DeltaPoint[]; delta_curve_note: string
  largest_in_range_change: DeltaPoint | null; notes: string[]
}
export interface HistoryStep {
  summary: ResultSummary; vs_previous: Change | null; vs_first: Change | null; demand_ids: number[]
}
export interface History { project: string; steps: HistoryStep[]; trend: string; trend_text: string }
export interface ImportRun {
  id: number; trigger: string; started_at: string; finished_at: string | null; input_dir: string
  files_found: number; created: number; updated: number; unchanged: number; failed: number; missing: number
  issues: { path: string; severity: 'error' | 'warning'; message: string }[]
}
export interface LinkedResult {
  revision: string; is_origin: boolean; status: Status; marginal: boolean
  peak_magnitude: number | null; peak_frequency: number | null; margin: number | null
  limit: number; unit: string; delta_vs_origin: number | null; change_vs_origin: Classification | null
  sync_state: string
}
export interface Demand {
  id: number; project: string; component: string; description: string; status: DemandStatus
  created_at: string; updated_at: string
  origin: {
    manual: boolean; revision: string | null; metric: string | null; value: number | null
    frequency: number | null; limit: number | null; unit: string | null
    range_min: number | null; range_max: number | null; current_value: number | null; drifted: boolean
  }
  linked_results: LinkedResult[]; latest: LinkedResult | null
  needs_review: boolean; regressed: boolean
  events: { at: string; kind: string; detail: string }[]
}

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) { super(message); this.status = status }
}

async function req<T>(url: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(url, { headers: { 'Content-Type': 'application/json' }, ...init })
  } catch {
    throw new ApiError(0, 'Cannot reach the API. Is the backend running?')
  }
  if (!res.ok) {
    let msg = res.statusText
    try {
      const body = await res.json()
      const d = body.detail
      msg = typeof d === 'string' ? d : d?.message ?? JSON.stringify(d)
    } catch { /* keep statusText */ }
    throw new ApiError(res.status, msg)
  }
  return res.json() as Promise<T>
}

const e = encodeURIComponent
export const api = {
  criteria: () => req<Criteria>('/api/criteria'),
  projects: () => req<Project[]>('/api/projects'),
  revision: (p: string, r: string) => req<RevisionResult>(`/api/projects/${e(p)}/revisions/${e(r)}`),
  compare: (p: string, base: string, target: string) =>
    req<Comparison>(`/api/projects/${e(p)}/compare?base=${e(base)}&target=${e(target)}`),
  history: (p: string) => req<History>(`/api/projects/${e(p)}/history`),
  latestImport: () => req<ImportRun | null>('/api/import/latest'),
  runImport: () => req<ImportRun>('/api/import', { method: 'POST' }),
  demands: (params: Record<string, string>) => {
    const q = new URLSearchParams(Object.entries(params).filter(([, v]) => v)).toString()
    return req<Demand[]>(`/api/demands${q ? '?' + q : ''}`)
  },
  createDemand: (body: { project: string; description: string; origin_revision?: string | null }) =>
    req<Demand>('/api/demands', { method: 'POST', body: JSON.stringify(body) }),
  updateDemand: (id: number, body: { description?: string; status?: DemandStatus }) =>
    req<Demand>(`/api/demands/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
}
