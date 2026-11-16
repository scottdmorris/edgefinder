import { useCallback, useEffect, useRef, useSyncExternalStore } from 'react'
import { api, type GameCard } from './api'

type Snapshot = { data: GameCard[] | null; error: string | null; receivedAt: number | null }
type Subscriber = { ms: number }
type Session = {
  subscribers: Map<Subscriber, () => void>
  snapshot: Snapshot
  pending: boolean
  completedAt: number | null
  timer: number | undefined
  hidden: boolean
  onVisibility: () => void
}

const empty: Snapshot = { data: null, error: null, receivedAt: null }
let session: Session | null = null
const getSnapshot = () => session?.snapshot ?? empty
const getServerSnapshot = () => empty

function clearTimer(current: Session) {
  window.clearTimeout(current.timer)
  current.timer = undefined
}

function schedule(current: Session) {
  clearTimer(current)
  if (session !== current || current.pending || document.hidden) return
  const ms = Math.min(...Array.from(current.subscribers.keys(), (subscriber) => subscriber.ms))
  const elapsed = current.completedAt === null ? 0 : Date.now() - current.completedAt
  current.timer = window.setTimeout(() => { void refresh(current) }, Math.max(0, ms - elapsed))
}

async function refresh(current: Session) {
  clearTimer(current)
  if (session !== current || current.pending || document.hidden) return
  current.pending = true
  try {
    const data = await api.live()
    if (session !== current) return
    current.snapshot = { data, error: null, receivedAt: Date.now() }
  } catch (error) {
    if (session !== current) return
    current.snapshot = { ...current.snapshot, error: error instanceof Error ? error.message : String(error) }
  } finally {
    if (session === current) {
      current.pending = false
      current.completedAt = Date.now()
      current.subscribers.forEach((notify) => notify())
      schedule(current)
    }
  }
}

function subscribe(subscriber: Subscriber, notify: () => void) {
  const first = session === null
  const current: Session = session ?? {
    subscribers: new Map(), snapshot: empty, pending: false, completedAt: null,
    timer: undefined, hidden: document.hidden,
    onVisibility: () => {
      const wasHidden = current.hidden
      current.hidden = document.hidden
      if (current.hidden) clearTimer(current)
      else if (wasHidden) void refresh(current)
    },
  }
  session = current
  current.subscribers.set(subscriber, notify)
  if (first) {
    document.addEventListener('visibilitychange', current.onVisibility)
    void refresh(current)
  } else schedule(current)

  return () => {
    current.subscribers.delete(subscriber)
    if (current.subscribers.size) schedule(current)
    else {
      clearTimer(current)
      document.removeEventListener('visibilitychange', current.onVisibility)
      // An outstanding request belongs to this session and must never publish into the next one.
      session = null
    }
  }
}

/** One live board and request loop, using the fastest interval requested by mounted consumers. */
export function useLiveGames(ms: number) {
  const subscriber = useRef<Subscriber>({ ms })
  const listen = useCallback((notify: () => void) => subscribe(subscriber.current, notify), [])
  const snapshot = useSyncExternalStore(listen, getSnapshot, getServerSnapshot)
  useEffect(() => {
    subscriber.current.ms = ms
    if (session?.subscribers.has(subscriber.current)) schedule(session)
  }, [ms, subscriber])
  return snapshot
}
