// Fetch something now and again every `ms`, pausing while the tab is hidden (a phone in a pocket
// shouldn't keep hitting the API). A failed refresh keeps the last good data and reports the error.
import { useEffect, useRef, useState } from 'react'

type Loaded<T> = { key: string; data: T | null; error: string | null; receivedAt: number | null }

export function usePoll<T>(load: () => Promise<T>, ms: number, key: string) {
  const [loaded, setLoaded] = useState<Loaded<T>>({ key, data: null, error: null, receivedAt: null })
  const loader = useRef(load)
  useEffect(() => { loader.current = load })

  useEffect(() => {
    let live = true
    let timer: number | undefined
    let pending = false
    const tick = async () => {
      window.clearTimeout(timer)
      if (document.hidden || pending) return
      pending = true
      try {
        const data = await loader.current()
        if (live) setLoaded({ key, data, error: null, receivedAt: Date.now() })
      } catch (e) {
        if (live) setLoaded((old) => ({ key, data: old.key === key ? old.data : null,
          receivedAt: old.key === key ? old.receivedAt : null, error: (e as Error).message }))
      }
      pending = false
      if (live) timer = window.setTimeout(tick, ms)
    }
    const onVisible = () => { if (!document.hidden) void tick() }
    void tick()
    document.addEventListener('visibilitychange', onVisible)
    return () => { live = false; window.clearTimeout(timer); document.removeEventListener('visibilitychange', onVisible) }
  }, [ms, key])

  // data fetched for an earlier key (another game, another slip) is never shown for this one
  return loaded.key === key ? { data: loaded.data, error: loaded.error, receivedAt: loaded.receivedAt }
    : { data: null, error: null, receivedAt: null }
}

/** The value before it last changed (undefined until it has changed once), for spotting what is
 *  new since the last refresh: a score that went up, plays or shots that just arrived. */
export function usePrevious<T>(value: T): T | undefined {
  const [state, setState] = useState<{ current: T; previous?: T }>({ current: value })
  if (!Object.is(state.current, value)) {
    setState({ current: value, previous: state.current })
    return state.current
  }
  return state.previous
}
