import { useEffect, useState } from 'react'
import { api, type Leg, type PropHistory } from '../lib/api'
import type { Step } from '../lib/ladder'
import { QuoteNotes } from './QuoteNotes'

const WINDOWS = [['last5', 'Last 5'], ['last10', 'Last 10'], ['last20', 'Last 20'], ['season', 'Season']] as const

function breakEven(odds: number) {
  return odds > 0 ? 10000 / (odds + 100) : odds < 0 ? 100 * -odds / (100 - odds) : null
}

export function PropEvidence({ step, initialUnder, kalshi, lineLabel }: {
  step: Step; initialUnder: boolean; kalshi: boolean; lineLabel: string
}) {
  const [under, setUnder] = useState(initialUnder)
  const [history, setHistory] = useState<PropHistory | null>(null)
  const [error, setError] = useState(false)
  const [retry, setRetry] = useState(0)
  const { player_id, game_date, stat, line } = step.yes
  const leg = under && step.no ? step.no : step.yes
  const sideLabel = (leg: Leg, no: boolean) => leg.side.endsWith('+') ? lineLabel
    : kalshi ? `${no ? 'No' : 'Yes'} ${lineLabel}` : `${leg.side} ${lineLabel}`

  useEffect(() => {
    if (!game_date) return
    let active = true
    void api.propHistory(player_id, game_date, stat, line).then(
      (result) => { if (active) setHistory(result) },
      () => { if (active) setError(true) },
    )
    return () => { active = false }
  }, [player_id, game_date, stat, line, retry])

  const even = breakEven(leg.odds)
  const hasHistory = history && history.last20.over + history.last20.under + history.last20.pushes > 0
  return <div className="rise space-y-2">
    {step.no ? <div role="group" aria-label="Side to inspect" className="flex flex-wrap gap-1.5">
      {[step.yes, step.no].map((side, index) => <button key={side.id} type="button"
        aria-pressed={leg.id === side.id} onClick={() => setUnder(index === 1)}
        className={`min-h-9 rounded-full px-3 font-semibold ${leg.id === side.id ? 'bg-button text-button-text' : 'border border-line text-text'}`}>
        {sideLabel(side, index === 1)}
      </button>)}
    </div> : <p className="font-semibold text-text">{sideLabel(leg, false)}</p>}
    <dl className="grid grid-cols-2 gap-1.5">
      <div className="rounded-xl bg-ink p-2.5">
        <dt>Model chance</dt>
        <dd className="text-lg font-black tabular-nums text-accent">{leg.model_pct == null ? '—' : `${leg.model_pct.toFixed(1)}%`}</dd>
      </div>
      <div className="rounded-xl bg-ink p-2.5">
        <dt>Break-even</dt>
        <dd className="text-lg font-black tabular-nums text-warn">{even == null ? '—' : `${even.toFixed(1)}%`}</dd>
      </div>
    </dl>
    <div className="flex flex-wrap gap-x-3">
      {leg.market_pct != null && <span>Market estimate <b className="text-text">{leg.market_pct.toFixed(1)}%</b></span>}
      {kalshi && <span>Break-even at the quoted price, before fees.</span>}
    </div>
    <div aria-live="polite">
      {hasHistory ? <dl aria-label="Historical hit rates" className="grid grid-cols-2 gap-1.5 sm:grid-cols-4">
        {WINDOWS.map(([key, name]) => {
          const counts = history[key]
          const hits = under ? counts.under : counts.over
          const graded = counts.over + counts.under
          return <div key={key} className="rounded-xl border border-line p-2.5">
            <dt>{name}</dt>
            <dd className="font-bold tabular-nums text-text">{graded ? `${Math.round(hits / graded * 100)}%` : '—'}</dd>
            <dd>{graded ? `${hits}/${graded} hit` : 'No graded games'}{counts.pushes > 0 && ` · ${counts.pushes} push${counts.pushes === 1 ? '' : 'es'}`}</dd>
          </div>
        })}
      </dl> : !game_date || history ? <p>No prior games available for this line.</p>
        : error ? <p>Couldn’t load game history. <button type="button" className="min-h-8 font-semibold text-accent underline"
          onClick={() => { setError(false); setRetry(retry + 1) }}>Retry</button></p>
          : <p>Loading game history…</p>}
    </div>
    {hasHistory && <p>Regular-season games before this slate. Recent windows can span seasons. Pushes are excluded from hit rates.</p>}
    <QuoteNotes quality={leg.quality} comparisons={leg.comparisons} side={leg.side} showRecentHit={false} />
  </div>
}
