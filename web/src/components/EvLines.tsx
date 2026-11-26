// The +EV screen: lines one book prices above the other books' no-vig average, from the
// latest recorded snapshot. A paper experiment that is graded like everything else; it says
// where prices disagree, not what to bet, so it has no add buttons.
import { useState } from 'react'
import type { EvLines as EvData } from '../lib/api'
import { american } from '../lib/ladder'
import { Photo } from './ui'

const SHOWN = 6

export function EvLines({ data, game }: { data: EvData; game?: string }) {
  const [all, setAll] = useState(false)
  const lines = data.lines.filter((l) => !game || l.game_short === game)
  if (lines.length === 0) return null
  const shown = all ? lines : lines.slice(0, SHOWN)
  const r = data.record
  return (
    <div>
      <ul className="divide-y divide-line rounded-2xl border border-line bg-raised" aria-label="Lines priced above the other books' average">
        {shown.map((l) => (
          <li key={`${l.book}-${l.player}-${l.bet}`} className="flex items-center gap-3 px-3 py-2.5">
            {l.photo && <Photo src={l.photo} size={32} />}
            <div className="min-w-0 flex-1">
              <div className="truncate text-sm font-bold">{l.player} · {l.bet}</div>
              <div className="truncate text-xs text-muted">
                {l.game_short} · {l.book_name} {american(l.odds)} vs fair {american(l.fair_odds)} ({l.fair_pct.toFixed(0)}%, {l.books} books)
              </div>
            </div>
            <div className="text-right text-sm font-black tabular-nums text-good">+{l.edge_pct.toFixed(1)}%</div>
          </li>
        ))}
      </ul>
      {lines.length > SHOWN && (
        <button type="button" onClick={() => setAll((open) => !open)} className="mt-2 min-h-9 text-xs font-semibold text-muted underline hover:text-text">
          {all ? 'Show fewer' : `Show all ${lines.length}`}
        </button>
      )}
      <p className="mt-2 text-xs text-muted">
        Each price is compared with the other books' average on the same number once their margins are removed (at least {data.min_books} books);
        the figure is the expected return per $1 if that average is right. Recorded prices, not live quotes, and often gone at the book.
        A paper test, not advice: {r.graded > 0 ? `${r.record}, ${r.units >= 0 ? '+' : ''}${r.units.toFixed(2)} units on ${r.graded} graded so far.` : `${r.logged} logged, none graded yet.`}
      </p>
    </div>
  )
}
