import { useEffect, useRef, useState } from 'react'
import type { Leg } from '../lib/api'
import { american, defaultStep, ladderRows, type Row, type Step } from '../lib/ladder'
import { Empty, Photo, Pills } from './ui'

const STATS: Record<string, string> = { points: 'Points', rebounds: 'Rebounds', assists: 'Assists', threes: '3PM' }
const MODEL_AGREES = 2     // percentage points within which the model and the price are called level
const SHOWN = 6     // players listed before "Show all"; the biggest names come first
const normalize = (text: string) => text.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().trim()

export function PropsBrowser({ legs, selected, toggle, kalshi, expanded = false, other }: {
  legs: Leg[]; selected: number[]; toggle: (id: number) => void; kalshi: boolean
  /** list everyone from the start (one game is chosen, so the list is already short) */
  expanded?: boolean
  /** another price source to offer when this one has no lines for the chosen stat */
  other?: { name: string; go: () => void }
}) {
  const [query, setQuery] = useState('')
  const [stat, setStat] = useState('points')
  const [onlySelected, setOnlySelected] = useState(false)
  const [all, setAll] = useState(false)
  const hasLines = legs.some((leg) => leg.stat === stat)
  const rows = ladderRows(legs).filter((row) => row.stat === stat
    && normalize(row.player).includes(normalize(query))
    && (!onlySelected || row.steps.some((step) => selected.includes(step.yes.id) || (step.no && selected.includes(step.no.id)))))
  const open = all || expanded || query !== '' || onlySelected
  return <section aria-label="Player props">
    <div className="flex flex-wrap items-center gap-2">
      <Pills value={stat} onChange={setStat} options={Object.entries(STATS).map(([id, label]) => ({ id, label }))} />
      <input aria-label="Find a player" type="search" placeholder="Search players" value={query} onChange={(e) => setQuery(e.target.value)}
        className="min-h-10 min-w-40 flex-1 rounded-full border border-line bg-raised px-4 text-sm" />
      <label className="flex min-h-10 shrink-0 cursor-pointer items-center gap-2 text-xs text-muted">
        <input type="checkbox" checked={onlySelected} onChange={(e) => setOnlySelected(e.target.checked)} className="size-4 accent-accent" />On my slip
      </label>
    </div>
    {!hasLines ? <div className="mt-3 rounded-2xl border border-dashed border-line px-5 py-6 text-center">
      <div className="font-bold">No {STATS[stat]} lines from this price source</div>
      {other && <button type="button" onClick={other.go} className="mt-3 min-h-10 rounded-full bg-button px-4 text-sm font-bold text-button-text">See {other.name} lines</button>}
    </div> : rows.length === 0 ? <div className="mt-3"><Empty title="No matching props" hint="Try another game or player." /></div> : <>
      <p className="mt-3 text-xs text-muted">
        {kalshi ? 'Tap a number to change the line, then Yes or No to add it.' : 'Tap a number to change the line, then Over or Under to add it.'} The
        big % is the chance the price implies; "model" is the chosen model's view, green when it rates the bet higher and red when lower.
      </p>
      <div className="mt-2 divide-y divide-line overflow-hidden rounded-2xl border border-line bg-raised">{(open ? rows : rows.slice(0, SHOWN)).map((row) => <PropRow key={row.key} row={row} slip={selected} toggle={toggle} kalshi={kalshi} />)}</div>
      {!open && rows.length > SHOWN && <button type="button" onClick={() => setAll(true)}
        className="mt-3 min-h-11 w-full rounded-full border border-line text-sm font-semibold hover:border-line-strong">Show all {rows.length} players</button>}
    </>}
  </section>
}

export function PropRow({ row, slip, toggle, kalshi }: { row: Row; slip: number[]; toggle: (id: number) => void; kalshi: boolean }) {
  const selected = row.steps.find((s) => slip.includes(s.yes.id) || (s.no && slip.includes(s.no.id)))
  const selection = selected ? `${selected.threshold}:${slip.includes(selected.yes.id) ? 'yes' : 'no'}` : ''
  // the step being looked at; a new selection (from an idea, say) brings its own step into view
  const [choice, setChoice] = useState({ threshold: (selected ?? defaultStep(row)).threshold, selection })
  const step = (choice.selection === selection ? row.steps.find((s) => s.threshold === choice.threshold) : selected) ?? defaultStep(row)
  const noSelected = step.no !== null && slip.includes(step.no.id)
  const compared = noSelected && step.no ? step.no : step.yes
  const label = STATS[row.stat] ?? row.stat
  const stepText = (s: Step) => (kalshi || s.yes.side.endsWith('+') ? `${s.threshold}+` : String(s.yes.line))

  const strip = useRef<HTMLDivElement>(null)
  // keep the chosen number in the middle of the strip (scrolls only the strip, never the page)
  useEffect(() => {
    const box = strip.current
    const on = box?.querySelector<HTMLElement>('[data-on]')
    if (box && on) box.scrollLeft = on.offsetLeft - box.clientWidth / 2 + on.offsetWidth / 2
  }, [step.threshold])

  const button = (leg: Leg, no = false) => {
    const on = slip.includes(leg.id)
    const plus = kalshi || leg.side.endsWith('+')
    const word = plus ? (no ? 'No' : 'Yes') : (no ? 'Under' : 'Over')
    const name = kalshi ? word : leg.side.endsWith('+') ? 'At least' : word
    const price = kalshi ? `${Math.round(100 / (leg.odds > 0 ? leg.odds / 100 + 1 : 100 / -leg.odds + 1))}¢` : american(leg.odds)
    return <button type="button" aria-pressed={on} aria-label={`${name} ${row.player} ${stepText(step)} ${label}`} onClick={() => toggle(leg.id)}
      className={`min-h-10 min-w-24 flex-1 rounded-full px-3 text-sm font-bold transition-colors sm:flex-none ${on ? 'bg-button text-button-text' : 'border border-line hover:border-line-strong'}`}>
      {on ? '✓ ' : ''}{word} <span className="tabular-nums">{price}</span>
    </button>
  }

  // the model's view against the price: green when it rates this side higher, red when lower
  const lean = (compared.model_pct ?? 0) - (compared.market_pct ?? 0)
  const leanTone = compared.model_pct == null || Math.abs(lean) < MODEL_AGREES ? 'text-muted' : lean > 0 ? 'text-good' : 'text-bad'

  // one line per player: who and what, the other numbers to step through, the chance, the prices
  return <div className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-2 px-3 py-2.5">
    <div className="hidden sm:block"><Photo src={row.photo} size={36} /></div>
    <div className="min-w-0 flex-1 basis-44">
      <div className="truncate text-sm font-bold">{row.player} <span className="font-semibold text-accent">{stepText(step)} {row.stat}</span></div>
      {row.steps.length > 1 ? (
        <div ref={strip} className="no-scrollbar -mx-1 flex gap-0.5 overflow-x-auto px-1">
          {row.steps.map((s) => {
            const on = s.threshold === step.threshold
            const picked = slip.includes(s.yes.id) || (s.no !== null && slip.includes(s.no.id))
            return <button key={s.threshold} type="button" data-on={on || undefined} aria-current={on || undefined}
              onClick={() => setChoice({ threshold: s.threshold, selection })}
              className={`min-h-8 shrink-0 rounded-full px-2 text-xs font-semibold tabular-nums ${on ? 'bg-raised-2 text-text ring-1 ring-line-strong' : picked ? 'text-accent' : 'text-muted hover:text-text'}`}>
              {stepText(s)}
            </button>
          })}
        </div>
      ) : <div className="truncate text-xs text-muted">{row.game_short}</div>}
    </div>
    <div className="w-20 shrink-0 text-center" title={`${row.game_short}${row.average?.season != null ? ` · averages ${row.average.season}` : ''}${compared.projection != null ? ` · projected ${compared.projection.toFixed(1)}` : ''} · blended ${compared.chance_pct?.toFixed(1) ?? '–'}%`}>
      <div className="text-xl font-black tabular-nums leading-tight">{compared.market_pct?.toFixed(0) ?? '–'}%</div>
      <div className={`text-[11px] font-semibold tabular-nums ${leanTone}`}>model {compared.model_pct?.toFixed(0) ?? '–'}%</div>
    </div>
    <div className="flex basis-full gap-1.5 sm:basis-auto">{button(step.yes)}{step.no && button(step.no, true)}</div>
  </div>
}
