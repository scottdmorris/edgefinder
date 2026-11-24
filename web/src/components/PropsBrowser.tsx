import { useEffect, useRef, useState } from 'react'
import type { Leg } from '../lib/api'
import { american, defaultStep, ladderRows, type Row, type Step } from '../lib/ladder'
import { QuoteNotes } from './QuoteNotes'
import { Empty, Photo, Pills } from './ui'

export const STATS: Record<string, string> = { points: 'Points', rebounds: 'Rebounds', assists: 'Assists', threes: '3PM' }
const MODEL_AGREES = 2     // percentage points within which the model and the price are called level
const SHOWN = 6     // players listed before "Show all"; the biggest names come first
export const normalize = (text: string) => text.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().trim()

export function PropsBrowser({ legs, selected, toggle, kalshi, expanded = false, other, searchOnly = false }: {
  legs: Leg[]; selected: number[]; toggle: (id: number) => void; kalshi: boolean
  /** list everyone from the start (one game is chosen, so the list is already short) */
  expanded?: boolean
  /** another price source to offer when this one has no lines for the chosen stat */
  other?: { name: string; go: () => void }
  /** list nothing until a name is typed (or "On my slip" is ticked): a finder, not a list */
  searchOnly?: boolean
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
  const idle = searchOnly && query === '' && !onlySelected
  return <section aria-label="Player props">
    <div className="flex flex-wrap items-center gap-2">
      <Pills value={stat} onChange={setStat} options={Object.entries(STATS).map(([id, label]) => ({ id, label }))} />
      <input aria-label="Find a player" type="search" placeholder="Search players" value={query} onChange={(e) => setQuery(e.target.value)}
        className="min-h-10 min-w-40 flex-1 rounded-full border border-line bg-raised px-4 text-sm" />
      <label className="flex min-h-10 shrink-0 cursor-pointer items-center gap-2 text-xs text-muted">
        <input type="checkbox" checked={onlySelected} onChange={(e) => setOnlySelected(e.target.checked)} className="size-4 accent-accent" />On my slip
      </label>
    </div>
    {idle ? null : !hasLines ? <div className="mt-3 rounded-2xl border border-dashed border-line px-5 py-6 text-center">
      <div className="font-bold">No {STATS[stat]} lines from this price source</div>
      {other && <button type="button" onClick={other.go} className="mt-3 min-h-10 rounded-full bg-button px-4 text-sm font-bold text-button-text">See {other.name} lines</button>}
    </div> : rows.length === 0 ? <div className="mt-3"><Empty title="No matching props" hint="Try another game or player." /></div> : <>
      <p className="mt-3 text-xs text-muted">Tap a price to add it to your slip. ⓘ shows other lines and the numbers behind a prop.</p>
      <div className="mt-2 divide-y divide-line overflow-hidden rounded-2xl border border-line bg-raised">{(open ? rows : rows.slice(0, SHOWN)).map((row) => <PropRow key={row.key} row={row} slip={selected} toggle={toggle} kalshi={kalshi} />)}</div>
      {!open && rows.length > SHOWN && <button type="button" onClick={() => setAll(true)}
        className="mt-3 min-h-11 w-full rounded-full border border-line text-sm font-semibold hover:border-line-strong">Show all {rows.length} players</button>}
    </>}
  </section>
}

/** `compact` is for a row under its player's own heading: no photo, the stat named instead. */
export function PropRow({ row, slip, toggle, kalshi, compact = false, inGame = false }: {
  row: Row; slip: number[]; toggle: (id: number) => void; kalshi: boolean; compact?: boolean
  /** on a game's own page: the game is already named above, so it is left off the row */
  inGame?: boolean
}) {
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
  const [open, setOpen] = useState(false)
  // the other lines live in the details; keep the chosen one in the middle of their strip
  useEffect(() => {
    const box = strip.current
    const on = box?.querySelector<HTMLElement>('[data-on]')
    if (box && on) box.scrollLeft = on.offsetLeft - box.clientWidth / 2 + on.offsetWidth / 2
  }, [step.threshold, open])

  // a sportsbook price button: the bet on top, the price underneath
  const button = (leg: Leg, no = false) => {
    const on = slip.includes(leg.id)
    const plus = kalshi || leg.side.endsWith('+')
    const word = plus ? (no ? 'No' : 'Yes') : (no ? 'Under' : 'Over')
    const name = kalshi ? word : leg.side.endsWith('+') ? 'At least' : word
    const top = kalshi ? `${word} ${stepText(step)}` : plus ? stepText(step) : `${no ? 'U' : 'O'} ${leg.line}`
    const price = kalshi ? `${Math.round(100 / (leg.odds > 0 ? leg.odds / 100 + 1 : 100 / -leg.odds + 1))}¢` : american(leg.odds)
    return <button type="button" aria-pressed={on} aria-label={`${name} ${row.player} ${stepText(step)} ${label}`} onClick={() => toggle(leg.id)}
      className={`flex h-12 w-[4.25rem] shrink-0 sm:w-[5.25rem] flex-col items-center justify-center rounded-lg border leading-tight transition-colors ${on ? 'border-button bg-button text-button-text' : 'border-line bg-raised-2 hover:border-line-strong'}`}>
      <span className={`text-[11px] font-semibold ${on ? '' : 'text-muted'}`}>{top}</span>
      <span className={`text-sm font-black tabular-nums ${on ? '' : 'text-accent'}`}>{price}</span>
    </button>
  }

  // the model's view against the price: green when it rates this side higher, red when lower
  const lean = (compared.model_pct ?? 0) - (compared.market_pct ?? 0)
  const leanTone = compared.model_pct == null || Math.abs(lean) < MODEL_AGREES ? 'text-text' : lean > 0 ? 'text-good' : 'text-bad'
  const average = row.average && (row.average.season != null || row.average.last10 != null) ? row.average : null

  // like a sportsbook: who, their averages, two prices; everything else behind the details button
  return <div className="px-3 py-2">
    <div className="flex items-center gap-2 sm:gap-2.5">
      {!compact && <div className="hidden sm:block"><Photo src={row.photo} size={36} /></div>}
      <div className="min-w-0 flex-1">
        <div className="line-clamp-2 text-sm font-bold leading-tight">{compact ? label : row.player}</div>
        <div className="mt-0.5 text-xs leading-snug tabular-nums text-muted">
          {!compact && !inGame && <span>{row.game_short}{average ? ' · ' : ''}</span>}
          {average && <span>avg <b className="text-text">{average.season?.toFixed(1) ?? '–'}</b> · L10 <b className="text-text">{average.last10?.toFixed(1) ?? '–'}</b></span>}
        </div>
      </div>
      <div className="flex shrink-0 gap-1 sm:gap-1.5">{button(step.yes)}{step.no && button(step.no, true)}</div>
      <button type="button" aria-expanded={open} aria-label={`Details for ${row.player} ${label}`} onClick={() => setOpen((v) => !v)}
        className={`grid size-7 shrink-0 place-items-center sm:size-8 rounded-full text-sm ${open ? 'bg-raised-2 text-text' : 'text-muted hover:text-text'}`}>
        {open ? '✕' : 'ⓘ'}
      </button>
    </div>
    {open && <div className="mt-2 space-y-2 rounded-xl bg-raised-2/60 p-3 text-xs text-muted">
      {row.steps.length > 1 && <div>
        <div className="mb-1">Other lines</div>
        <div ref={strip} className="no-scrollbar -mx-1 flex gap-1 overflow-x-auto px-1">
          {row.steps.map((s) => {
            const on = s.threshold === step.threshold
            const picked = slip.includes(s.yes.id) || (s.no !== null && slip.includes(s.no.id))
            return <button key={s.threshold} type="button" data-on={on || undefined} aria-current={on || undefined}
              onClick={() => setChoice({ threshold: s.threshold, selection })}
              className={`min-h-8 shrink-0 rounded-full px-2.5 font-semibold tabular-nums ${on ? 'bg-button text-button-text' : picked ? 'text-accent ring-1 ring-line' : 'ring-1 ring-line hover:text-text'}`}>
              {stepText(s)}
            </button>
          })}
        </div>
      </div>}
      <div>
        Price implies <b className="text-text">{compared.market_pct?.toFixed(0) ?? '–'}%</b>
        {' · '}model <b className={leanTone}>{compared.model_pct?.toFixed(0) ?? '–'}%</b>
        {compared.projection != null && <> · projects <b className="text-text">{compared.projection.toFixed(1)}</b></>}
      </div>
      <QuoteNotes quality={compared.quality} comparisons={compared.comparisons} side={compared.side} />
      <div>Hit rates are past games, not forecasts. Injury news isn't checked.</div>
    </div>}
  </div>
}
