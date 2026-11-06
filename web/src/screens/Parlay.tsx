import { useEffect, useMemo, useRef, useState } from 'react'
import { api, type Board, type Idea, type Leg, type Market } from '../lib/api'
import { american, defaultStep, ladderRows, type Row } from '../lib/ladder'
import { useSlip } from '../lib/slip'
import { Empty, Photo, Pills, Section, StatStrip } from '../components/ui'
import { SlipPanel } from '../components/SlipPanel'

const STAT_ORDER = ['points', 'rebounds', 'assists', 'threes']
const STAT_NAMES: Record<string, string> = {
  points: 'Points', rebounds: 'Rebounds', assists: 'Assists', threes: '3-pointers',
}
const ALL = '__all__'

export function Parlay() {
  const [market, setMarket] = useState<Market>({})
  const [board, setBoard] = useState<Board | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [game, setGame] = useState(ALL)
  const [style, setStyle] = useState('Balanced')
  const [ideas, setIdeas] = useState<Idea[] | null>(null)
  const [open, setOpen] = useState<string>('points')

  useEffect(() => {
    let live = true
    api.board(market).then((b) => { if (live) { setBoard(b); setError(null) } })
      .catch((e: Error) => live && setError(e.message))
    return () => { live = false }
  }, [market])

  const chosen: Market = board ? { date: board.date, book: board.book, model: board.model } : {}
  const marketKey = board ? `${board.date}|${board.book}|${board.model}` : null
  const legsById = useMemo(() => new Map((board?.legs ?? []).map((l) => [l.id, l])), [board])
  const slip = useSlip(marketKey, legsById)

  useEffect(() => {
    if (!board) return
    let live = true
    setIdeas(null)
    api.ideas(chosen, style, game === ALL ? undefined : game).then((i) => live && setIdeas(i))
      .catch(() => live && setIdeas([]))
    return () => { live = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [marketKey, style, game])

  if (error) return <Empty title="Couldn't load the lines" hint={error} />
  if (!board) return <Loading />

  const shown = board.legs.filter((l) => game === ALL || l.game === game)
  const gaps = board.gaps.filter((g) => game === ALL || shown.some((l) => l.id === g.leg_id))
  const stats = STAT_ORDER.filter((s) => shown.some((l) => l.stat === s))

  return (
    <div className="lg:grid lg:grid-cols-[minmax(0,1fr)_360px] lg:gap-8">
      <div className="min-w-0">
        <h1 className="text-3xl font-black tracking-tight">Build a parlay</h1>

        <div className="mt-5 grid gap-4 sm:grid-cols-3">
          <Pills label="Game day" value={board.date}
            options={board.days.map((d) => ({ id: d.date, label: d.label }))}
            onChange={(date) => { setMarket({ date }); setGame(ALL) }} />
          <Pills label="Prices" value={board.book} options={board.books.map((b) => ({ id: b.id, label: b.name }))}
            onChange={(book) => setMarket({ date: board.date, book })} />
          <Pills label="Model" value={board.model} options={board.models.map((m) => ({ id: m.id, label: m.short }))}
            onChange={(model) => setMarket({ ...chosen, model })} />
        </div>

        <div className="mt-5">
          <StatStrip items={[
            { value: board.summary.games, label: 'games' },
            { value: board.summary.props, label: 'player props' },
            { value: board.summary.gaps, label: 'price gaps' },
            { value: board.books.find((b) => b.id === board.book)?.name, label: 'prices from' },
          ]} />
        </div>

        <div className="mt-5">
          <Pills label="Game" value={game} onChange={setGame}
            options={[{ id: ALL, label: 'All games' }, ...board.games.map((g) => ({ id: g.game, label: g.short }))]} />
        </div>

        {gaps.length > 0 && (
          <Section title="Where the prices disagree" aside={`vs ${board.book === 'fanduel' ? 'Kalshi' : 'FanDuel'}`}>
            <div className="grid gap-2.5 sm:grid-cols-2">
              {gaps.slice(0, 6).map((gap) => {
                const on = gap.leg_id !== null && slip.legs.includes(gap.leg_id)
                return (
                  <div key={`${gap.player_id}-${gap.bet}`} className="rise flex items-center gap-3 rounded-2xl border border-line bg-raised p-3">
                    <Photo src={gap.photo} />
                    <div className="min-w-0 flex-1">
                      <div className="truncate font-bold">{gap.player}</div>
                      <div className="text-xs text-muted">{gap.bet} pts · {american(gap.odds)} · {gap.game_short}</div>
                      <div className="text-xs text-muted">{gap.reference} {gap.reference_pct.toFixed(0)}%{gap.estimated ? ' (est.)' : ''} vs {gap.price_pct.toFixed(0)}%</div>
                    </div>
                    <div className="text-right">
                      <div className="text-sm font-black text-good">+{gap.edge_pct.toFixed(1)}%</div>
                      {gap.leg_id !== null && (
                        <button type="button" onClick={() => slip.toggle(gap.leg_id!)}
                          className={`mt-1 min-h-9 rounded-full px-3 text-xs font-bold ${on ? 'bg-button text-button-text' : 'border border-line hover:border-line-strong'}`}>
                          {on ? 'Added' : 'Add'}
                        </button>
                      )}
                    </div>
                  </div>
                )
              })}
            </div>
            <p className="mt-2 text-xs text-muted">The other market's view, not our model's. Prices are from the last snapshot.</p>
          </Section>
        )}

        <Section title="Ideas" aside={game === ALL ? 'one leg per game' : 'same game'}>
          <Pills value={style} onChange={setStyle} options={board.styles.map((s) => ({ id: s, label: s }))} />
          <div className="mt-3 grid gap-3 md:grid-cols-2">
            {ideas === null && <div className="text-sm text-muted">Finding slips…</div>}
            {ideas?.length === 0 && <Empty title="Nothing fits this style here" hint="Try a bigger-payout style or another game." />}
            {ideas?.map((idea, i) => (
              <IdeaCard key={i} idea={idea} legs={legsById} onAdd={() => slip.set(idea.legs)} />
            ))}
          </div>
        </Section>

        <Section title="All props" aside="Pick how many, then Yes or No">
          <div className="space-y-2">
            {stats.map((stat) => (
              <div key={stat} className="overflow-hidden rounded-2xl border border-line">
                <button type="button" onClick={() => setOpen(open === stat ? '' : stat)}
                  className="flex min-h-12 w-full items-center justify-between px-4 font-bold hover:bg-raised">
                  <span>Player {STAT_NAMES[stat]}</span>
                  <span className="text-muted">{open === stat ? '−' : '+'}</span>
                </button>
                {open === stat && (
                  <div className="divide-y divide-line border-t border-line">
                    {ladderRows(shown.filter((l) => l.stat === stat)).map((row) => (
                      <PropRow key={row.key} row={row} slip={slip.legs} toggle={slip.toggle} kalshi={board.book === 'kalshi'} />
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </Section>
      </div>

      <SlipPanel market={chosen} legs={slip.legs} legsById={legsById}
        onRemove={slip.toggle} onClear={slip.clear} />
    </div>
  )
}

function PropRow({ row, slip, toggle, kalshi }: { row: Row; slip: number[]; toggle: (id: number) => void; kalshi: boolean }) {
  const [threshold, setThreshold] = useState(() => defaultStep(row).threshold)
  const step = row.steps.find((s) => s.threshold === threshold) ?? defaultStep(row)
  const strip = useRef<HTMLDivElement>(null)
  // keep the chosen number in the middle of the strip (scrolls only the strip, never the page)
  useEffect(() => {
    const box = strip.current
    const on = box?.querySelector<HTMLElement>('[data-on]')
    if (box && on) box.scrollLeft = on.offsetLeft - box.clientWidth / 2 + on.offsetWidth / 2
  }, [step.threshold])
  const price = (leg: Leg) => (kalshi ? `${Math.round(100 / (leg.odds > 0 ? leg.odds / 100 + 1 : 100 / -leg.odds + 1))}¢` : american(leg.odds))
  const button = (leg: Leg, word: string) => {
    const on = slip.includes(leg.id)
    return (
      <button type="button" onClick={() => toggle(leg.id)}
        className={`min-h-11 flex-1 rounded-full px-3 text-sm font-bold transition-colors ${on ? 'bg-button text-button-text' : 'border border-line hover:border-line-strong'}`}>
        {on ? '✓ ' : ''}{word} {price(leg)}
      </button>
    )
  }
  return (
    <div className="px-4 py-3">
      <div className="flex items-center gap-3">
        <Photo src={row.photo} />
        <div className="min-w-0 flex-1">
          <div className="truncate font-bold">{row.player} <span className="font-semibold text-muted">· {step.threshold}+</span></div>
          <div className="text-xs text-muted">
            {row.game_short}{row.average?.season != null && ` · avg ${row.average.season} · last 10: ${row.average.last10}`}
          </div>
        </div>
        <div className="text-right">
          <div className="text-xl font-black">{step.yes.market_pct?.toFixed(0)}%</div>
          <div className="text-[11px] text-muted">model {step.yes.model_pct?.toFixed(0)}%</div>
        </div>
      </div>
      <div className="mt-2.5 space-y-2">
        {row.steps.length > 1 && (
          <div ref={strip} className="no-scrollbar -mx-1 flex snap-x gap-1 overflow-x-auto px-1">
            {row.steps.map((s) => (
              <button key={s.threshold} type="button" data-on={s.threshold === step.threshold || undefined}
                onClick={() => setThreshold(s.threshold)}
                className={`min-h-9 shrink-0 snap-center rounded-full px-3 text-xs font-semibold ${s.threshold === step.threshold ? 'bg-raised-2 text-text ring-1 ring-line-strong' : 'text-muted hover:text-text'}`}>
                {s.threshold}+
              </button>
            ))}
          </div>
        )}
        <div className="flex gap-2">
          {button(step.yes, 'Yes')}
          {step.no && button(step.no, 'No')}
        </div>
      </div>
    </div>
  )
}

function IdeaCard({ idea, legs, onAdd }: { idea: Idea; legs: Map<number, Leg>; onAdd: () => void }) {
  return (
    <div className="rise rounded-2xl border border-line bg-raised p-3">
      {idea.legs.map((id) => {
        const leg = legs.get(id)
        if (!leg) return null
        return (
          <div key={id} className="flex items-center gap-3 border-b border-line py-2 last:border-0">
            <Photo src={leg.photo} size={40} />
            <div className="min-w-0 flex-1">
              <div className="truncate text-sm font-bold">{leg.player}</div>
              <div className="text-xs text-muted">{leg.bet}{leg.average?.season != null && ` · avg ${leg.average.season}`}</div>
            </div>
            <div className="rounded-full border border-line px-2.5 py-1 text-xs font-bold">{american(leg.odds)}</div>
          </div>
        )
      })}
      <div className="mt-2 flex items-center justify-between gap-2">
        <div className="text-xs text-muted"><b className="text-text">{idea.chance_pct.toFixed(0)}%</b> to hit · <b className="text-text">${idea.pays.toFixed(2)}</b> back on $1</div>
        <button type="button" onClick={onAdd} className="min-h-9 rounded-full bg-button px-4 text-xs font-bold text-button-text">Use slip</button>
      </div>
    </div>
  )
}

function Loading() {
  return (
    <div className="space-y-3">
      {[0, 1, 2].map((i) => <div key={i} className="h-24 animate-pulse rounded-2xl bg-raised" />)}
    </div>
  )
}
