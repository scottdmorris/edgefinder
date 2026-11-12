import { useEffect, useState } from 'react'

export function Freshness({ receivedAt, error, label = 'NBA feed received' }: {
  receivedAt?: string | number | null; error?: string | null; label?: string
}) {
  const [now, setNow] = useState(Date.now)
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [])
  const timestamp = typeof receivedAt === 'string' ? Date.parse(receivedAt) : receivedAt
  const seconds = timestamp == null || !Number.isFinite(timestamp) ? null
    : Math.max(0, Math.floor((now - timestamp) / 1000))
  const stale = seconds !== null && seconds > 30
  const age = seconds === null ? 'Waiting for data' : `${label} ${seconds < 60 ? `${seconds}s` : `${Math.floor(seconds / 60)}m ${seconds % 60}s`} ago`
  return (
    <span className={`text-xs ${error || stale ? 'text-warn' : 'text-muted'}`}>
      {age}{error ? ' · Connection failed; retrying' : stale ? ' · Stale data' : ''}
    </span>
  )
}
