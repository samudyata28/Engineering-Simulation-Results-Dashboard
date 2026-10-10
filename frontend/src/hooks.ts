import { useCallback, useEffect, useRef, useState } from 'react'

export interface Async<T> { data: T | null; error: string | null; loading: boolean; reload: () => void }

/** Minimal data hook: re-fetches when deps change, ignores stale responses. */
export function useAsync<T>(fn: () => Promise<T>, deps: unknown[]): Async<T> {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [tick, setTick] = useState(0)
  const seq = useRef(0)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const fnRef = useCallback(fn, deps)
  useEffect(() => {
    const id = ++seq.current
    setLoading(true)
    fnRef().then(
      (d) => { if (id === seq.current) { setData(d); setError(null); setLoading(false) } },
      (e: Error) => { if (id === seq.current) { setError(e.message); setLoading(false) } },
    )
  }, [fnRef, tick])
  return { data, error, loading, reload: () => setTick((t) => t + 1) }
}
