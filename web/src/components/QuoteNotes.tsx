// The short line under each prop: how often it has hit, the usual range, the other sportsbook's
// price, and a flag when the quote is left out of suggestions. The reasons and timestamps sit
// behind "Why", so the list stays readable.
import type { ReactNode } from 'react'
import type { BookComparison, QuoteQuality } from '../lib/api'
import { american } from '../lib/ladder'
import { comparisonWord } from '../lib/quoteWords'
import { BookBadge } from './BookBadge'

interface QuoteNotesProps {
  quality?: QuoteQuality | null
  comparisons?: BookComparison[]
  side: string
  showRecentHit?: boolean
}

const when = (iso: string | null) => (iso ? new Date(iso).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }) : 'unknown')

export function QuoteNotes({ quality, comparisons = [], side, showRecentHit = true }: QuoteNotesProps) {
  if (!quality && comparisons.length === 0) return null
  const parts: ReactNode[] = []
  if (showRecentHit && quality?.recent_hit_pct != null) parts.push(<span key="hit">Hit <b className="text-text">{Math.round(quality.recent_hit_pct)}%</b> of last {quality.history_games}</span>)
  if (quality?.historical_low != null) parts.push(<span key="range">usually {quality.historical_low}–{quality.historical_high}</span>)
  for (const other of comparisons) {
    const word = comparisonWord(other)
    parts.push(<span key={other.book} className="inline-flex flex-wrap items-center gap-1">
      <BookBadge book={other.book} /> <span>{side} {other.line} {american(other.odds)}</span> <span className={word.tone}>· {word.text}</span>
    </span>)
  }
  const warnings = quality?.warnings ?? []
  return (
    <div className="basis-full text-xs text-muted">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        {parts.map((part, i) => <span key={i} className="inline-flex min-w-0 max-w-full items-center gap-2">{i > 0 && <span aria-hidden="true">·</span>}{part}</span>)}
        {quality && (
          <details className="group open:basis-full">
            <summary className="cursor-pointer list-none rounded-full border border-line px-2 py-0.5 hover:border-line-strong">
              {warnings.length ? <span className="text-warn">Not suggested · why</span> : 'Details'}
            </summary>
            <ul className="mt-1.5 list-disc space-y-0.5 pl-4">
              {warnings.map((w) => <li key={w} className="text-warn">{w}</li>)}
              <li>Price checked {when(quality.price_at)}</li>
              {comparisons.map((o) => <li key={o.book}>{o.book} price checked {when(o.fetched_at)}</li>)}
              <li>{quality.injuries}</li>
            </ul>
          </details>
        )}
      </div>
    </div>
  )
}
