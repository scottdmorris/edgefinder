// Single bets worth a look, in one sideways row: what a model likes, where the two price
// sources disagree, and legs a player nearly always reaches. Each card says which it is.
import { useState } from 'react'
import { american } from '../lib/ladder'
import { Photo, Pills } from './ui'

export type QuickAdd = {
  key: string
  kind: 'Model pick' | 'Price gap' | 'Steady'
  player: string
  photo: string
  bet: string
  odds: number
  game: string
  /** one line on why it is here */
  why: string
  /** the headline number for its kind: edge, gap, or games reached */
  figure: string
  /** the board leg it adds; null when this price source has no such leg */
  legId: number | null
  /** shown in place of the add button when there is no such leg here */
  missing?: string
}

const ALL = 'All'
const LABELS: Record<string, string> = { 'Model pick': 'Model picks', 'Price gap': 'Price gaps', Steady: 'Steady' }
const TONE: Record<QuickAdd['kind'], string> = {
  'Model pick': 'bg-accent/15 text-accent', 'Price gap': 'bg-good/15 text-good', Steady: 'bg-raised-2 text-muted',
}

export function QuickAdds({ items, selected, toggle }: { items: QuickAdd[]; selected: number[]; toggle: (id: number) => void }) {
  const [kind, setKind] = useState(ALL)
  const kinds = [...new Set(items.map((item) => item.kind))]
  // a kind that is no longer in the list (another game was chosen) falls back to everything
  const active = kinds.some((name) => name === kind) ? kind : ALL
  const shown = items.filter((item) => active === ALL || item.kind === active)
  return (
    <div>
      {kinds.length > 1 && <Pills value={active} onChange={setKind}
        options={[ALL, ...kinds].map((name) => ({ id: name, label: LABELS[name] ?? name }))} />}
      <div className="no-scrollbar -mx-4 mt-3 flex snap-x gap-2.5 overflow-x-auto px-4 pb-1 sm:mx-0 sm:px-0">
        {shown.map((item) => {
          const on = item.legId !== null && selected.includes(item.legId)
          return (
            <div key={item.key} className="flex w-64 shrink-0 snap-start flex-col rounded-2xl border border-line bg-raised p-3">
              <div className="flex items-center justify-between gap-2">
                <span className={`rounded-full px-2 py-0.5 text-[11px] font-bold ${TONE[item.kind]}`}>{item.kind}</span>
                <span className="text-sm font-black tabular-nums">{item.figure}</span>
              </div>
              <div className="mt-2 flex items-center gap-2.5">
                <Photo src={item.photo} size={36} />
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm font-bold">{item.player}</div>
                  <div className="truncate text-xs text-muted">{item.bet} · {american(item.odds)}</div>
                </div>
              </div>
              <div className="mt-1.5 flex-1 text-xs text-muted">{item.game} · {item.why}</div>
              {item.legId === null && item.missing && <div className="mt-2.5 text-xs text-warn">{item.missing}</div>}
              {item.legId !== null && (
                <button type="button" aria-pressed={on} aria-label={`${on ? 'Remove' : 'Add'} ${item.player} ${item.bet}`} onClick={() => toggle(item.legId!)}
                  className={`mt-2.5 min-h-9 rounded-full text-xs font-bold ${on ? 'bg-button text-button-text' : 'border border-line hover:border-line-strong'}`}>
                  {on ? '✓ Added' : 'Add to slip'}
                </button>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
