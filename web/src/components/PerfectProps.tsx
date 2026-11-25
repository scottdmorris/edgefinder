// Perfect Props: lines a player has cleared in every game this season, as one bold card, and the
// last finished day's list as a grid of hits and misses. Their prices come first on purpose: a
// streak everyone can see is priced in, so these are short favourites, not bargains.
import { useEffect, useState } from 'react'
import { api, type Leg, type Market, type PerfectProp, type PerfectProps as Data } from '../lib/api'
import { american } from '../lib/ladder'
import { BookBadge } from './BookBadge'
import { Photo } from './ui'

const STAKE = 10

function dayName(date: string): string {
  return new Date(`${date}T12:00:00`).toLocaleDateString([], { weekday: 'short', month: 'short', day: 'numeric' })
}

/** What $10 on a price wins, to show how little a heavy favourite pays. */
function wins(odds: number): string {
  const profit = odds > 0 ? (STAKE * odds) / 100 : (STAKE * 100) / -odds
  return `$${profit.toFixed(2)}`
}

function PropCard({ prop, leg, on, toggle, book }: {
  prop: PerfectProp; leg?: Leg; on: boolean; toggle: (id: number) => void; book: string
}) {
  const addable = !!leg && !prop.started
  return <div className="flex items-center gap-2 px-3 py-2">
    <Photo src={prop.photo} size={34} />
    <div className="min-w-0 flex-1">
      <div className="truncate text-sm font-bold">{prop.player}</div>
      <div className="flex flex-wrap items-center gap-x-1.5 text-xs text-muted">
        <span className="text-text">{prop.bet}</span>
        <span className="rounded bg-good/15 px-1 font-bold tabular-nums text-good">{prop.games}/{prop.games}</span>
        {prop.book !== book && <BookBadge book={prop.book} />}
        {prop.started && <span className="font-bold text-warn">started</span>}
      </div>
    </div>
    <div className="text-right">
      {addable
        ? <button type="button" aria-pressed={on} onClick={() => toggle(prop.leg_id)}
          aria-label={`Add ${prop.player} ${prop.bet} at ${american(prop.odds)}`}
          className={`min-h-10 min-w-16 rounded-lg border px-2 text-sm font-black tabular-nums ${on ? 'border-button bg-button text-button-text' : 'border-line bg-raised-2 text-accent hover:border-line-strong'}`}>
          {american(prop.odds)}</button>
        : <div className="text-sm font-black tabular-nums text-muted">{american(prop.odds)}</div>}
      <div className="mt-0.5 text-[10px] text-muted">${STAKE} wins {wins(prop.odds)}</div>
    </div>
  </div>
}

function Recap({ recap }: { recap: NonNullable<Data['recap']> }) {
  const perfect = recap.hit === recap.total
  return <div className="border-t border-line px-3 py-3">
    <div className="flex items-baseline justify-between">
      <div className="text-[11px] font-black uppercase tracking-wider text-muted">{dayName(recap.date)}’s perfect props</div>
      <div className="text-2xl font-black tabular-nums">
        <span className={perfect ? 'text-good' : 'text-warn'}>{recap.hit}</span> <span className="text-base text-muted">of</span> {recap.total}
      </div>
    </div>
    <div className="mt-2 grid grid-cols-3 gap-1 sm:grid-cols-5" role="list" aria-label="How each did">
      {recap.props.map((p) => <div key={`${p.player_id}-${p.stat}`} role="listitem"
        aria-label={`${p.player} ${p.bet}: ${p.hit ? 'hit' : 'missed'} with ${p.actual}`}
        className={`rounded-md border px-1.5 py-1 text-[10px] leading-tight ${p.hit ? 'border-good/50 bg-good/10' : 'border-bad/50 bg-bad/10'}`}>
        <div className="flex justify-between gap-1 font-bold"><span className="truncate">{p.player.split(' ').slice(-1)[0]}</span>
          <span className={p.hit ? 'text-good' : 'text-bad'}>{p.hit ? '✓' : '✗'}</span></div>
        <div className="truncate text-muted">{p.bet.replace(/^Over /, '')} · {p.actual}</div>
      </div>)}
    </div>
  </div>
}

export function PerfectProps({ market, legsById, selected, toggle }: {
  market: Market; legsById: Map<number, Leg>; selected: number[]; toggle: (id: number) => void
}) {
  const [data, setData] = useState<Data | null>(null)
  const [all, setAll] = useState(false)
  const key = `${market.date}|${market.book}|${market.model}`
  useEffect(() => {
    let live = true
    api.perfect(market).then((d) => live && setData(d)).catch(() => live && setData(null))
    return () => { live = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key])
  if (!data || (!data.props.length && !data.recap)) return null
  const shown = all ? data.props : data.props.slice(0, 6)
  return <section aria-label="Perfect props" className="mt-8 overflow-hidden rounded-3xl border border-line bg-raised">
    <div className="bg-gradient-to-br from-good/15 via-transparent to-transparent px-4 pb-3 pt-4">
      <div className="flex items-start justify-between gap-2">
        <div>
          <h2 className="text-2xl font-black uppercase italic tracking-tight">Perfect props</h2>
          <div className="text-[11px] font-bold uppercase tracking-wider text-muted">{dayName(data.date)} · hit in every game this season</div>
        </div>
        {data.props.length > 0 && <span className="rounded-full bg-good/15 px-2 py-1 text-[11px] font-black text-good">{data.props.length} today</span>}
      </div>
      <p className="mt-2 text-xs text-muted">
        A streak everyone can see is priced in, so these are heavy favourites: the price shows what ${STAKE} wins.
        Not picks, and a streak ends sometime.
      </p>
    </div>
    {data.props.length > 0
      ? <div className="divide-y divide-line border-t border-line">
        {shown.map((p) => <PropCard key={`${p.player_id}-${p.stat}`} prop={p} book={data.book}
          leg={p.book === data.book ? legsById.get(p.leg_id) : undefined} on={selected.includes(p.leg_id)} toggle={toggle} />)}
      </div>
      : data.recap?.date !== data.date   // a finished day shows only how its list did
        && <p className="border-t border-line px-4 py-3 text-sm text-muted">No line on today’s board has been cleared in every game.</p>}
    {data.props.length > 6 && <button type="button" onClick={() => setAll((v) => !v)}
      className="min-h-10 w-full border-t border-line text-sm font-semibold text-accent">{all ? 'Show fewer' : `Show all ${data.props.length}`}</button>}
    {data.recap && <Recap recap={data.recap} />}
  </section>
}
