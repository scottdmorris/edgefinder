import { useEffect, useMemo, useState } from 'react'
import { api, type Board, type Idea, type Leg, type Market, type Picks } from '../lib/api'
import { american, money } from '../lib/ladder'
import { useSlip } from '../lib/slip'
import { Empty, Photo, Pills, Section } from '../components/ui'
import { SlipPanel } from '../components/SlipPanel'
import { PropsBrowser } from '../components/PropsBrowser'
import { SlipImageReview } from '../components/SlipImageReview'

const ALL = '__all__'

export function Parlay() {
  const [market, setMarket] = useState<Market>({})
  const [board, setBoard] = useState<Board | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [game, setGame] = useState(ALL)
  const [style, setStyle] = useState('Balanced')
  const [ideas, setIdeas] = useState<Idea[] | null>(null)
  const [refresh, setRefresh] = useState(0)
  const [loading, setLoading] = useState(false)
  const [loadedAt, setLoadedAt] = useState<string | null>(null)
  const [picks, setPicks] = useState<Picks['liked']>([])

  useEffect(() => {
    let live = true
    setLoading(true)
    api.board(market).then((b) => { if (live) { setBoard(b); setError(null); setLoadedAt(new Date().toLocaleTimeString()) } })
      .catch((e: Error) => live && setError(e.message))
      .finally(() => { if (live) setLoading(false) })
    return () => { live = false }
  }, [market, refresh])

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
  }, [board, style, game])

  // what the models would bet on this day (FanDuel points lines); none recorded is not an error
  const day = board?.date
  useEffect(() => {
    if (!day) return
    let live = true
    api.picks(day).then((p) => live && setPicks(p.liked)).catch(() => live && setPicks([]))
    return () => { live = false }
  }, [day, refresh])

  if (error && !board) return <Empty title="Couldn't load the lines" hint={error} />
  if (!board) return <Loading />

  const shown = board.legs.filter((l) => game === ALL || l.game === game)
  const gaps = board.gaps.filter((g) => game === ALL || shown.some((l) => l.id === g.leg_id))
  const steady = board.steady.filter((s) => game === ALL || s.game === game)
  const gameShort = board.games.find((g) => g.game === game)?.short
  const liked = picks.filter((p) => game === ALL || p.game_short === gameShort).slice(0, 6)
  const otherBook = board.books.find((b) => b.id !== board.book)
  const model = board.models.find((m) => m.id === board.model)

  return (
    <div className="lg:grid lg:grid-cols-[minmax(0,1fr)_360px] lg:gap-8">
      <div className="min-w-0">
        <div className="flex items-baseline justify-between gap-3">
          <h1 className="text-3xl font-black tracking-tight">Build a parlay</h1>
          <button type="button" disabled={loading} onClick={() => setRefresh((n) => n + 1)}
            className="min-h-10 rounded-full border border-line px-4 text-xs font-semibold text-muted hover:border-line-strong hover:text-text">
            {loading ? 'Refreshing…' : `Refresh · ${loadedAt ?? ''}`}
          </button>
        </div>
        {error && <p role="alert" className="mt-2 text-sm text-warn">Refresh failed: {error}. Showing the previous board.</p>}

        <div className="mt-5">
          <Pills label="Game day" value={board.date}
            options={board.days.map((d) => ({ id: d.date, label: d.label }))}
            onChange={(date) => { setMarket({ date }); setGame(ALL) }} />
        </div>
        <div className="mt-4 flex flex-wrap gap-x-8 gap-y-4">
          <Pills label="Prices" value={board.book} options={board.books.map((b) => ({ id: b.id, label: b.name }))}
            onChange={(book) => setMarket({ date: board.date, book })} />
          <Pills label="Model" value={board.model} options={board.models.map((m) => ({ id: m.id, label: m.short }))}
            onChange={(model) => setMarket({ ...chosen, model })} />
        </div>
        {model && <p className="mt-2 text-xs text-muted">
          The model is how each player's chance is estimated. {model.name}. Prices and lines are the same whichever you pick.
        </p>}
        <div className="mt-5">
          <Pills label="Game" value={game} onChange={setGame}
            options={[{ id: ALL, label: 'All games' }, ...board.games.map((g) => ({ id: g.game, label: g.short }))]} />
        </div>

      {slip.unavailable.length > 0 && <section className="my-4 rounded-2xl border border-warn/50 bg-warn/5 p-4">
        <h2 className="font-bold text-warn">Review saved selections</h2>
        <p role="alert" className="mt-2 text-sm text-muted">These bets are no longer on the board. They stay here for review and are left out of the estimate.</p>
        {slip.unavailable.map(({ id, leg }) => <div key={id} className="mt-3 border-t border-line pt-3 text-sm">
          <div className="font-bold">{leg?.player ?? 'Saved selection'} · No longer on the board</div>
          {leg && <p className="mt-1 text-muted">{leg.bet} · {american(leg.odds)} · original slip chance {leg.chance_pct?.toFixed(1) ?? '–'}%</p>}
          <button type="button" onClick={() => slip.toggle(id)} className="mt-2 min-h-11 text-sm font-bold text-accent">Remove {leg?.player ?? 'selection'}</button>
        </div>)}
        {slip.estimate && <p className="mt-3 text-xs text-muted">Original illustration: stake {money(slip.estimate.price.stake)}, estimated profit {money(slip.estimate.price.to_win)}. Saved {new Date(slip.estimate.recordedAt).toLocaleString()}. This is not the current payout.</p>}
      </section>}

        {slip.moved.length > 0 && <p className="mt-4 text-xs text-muted">
          Price moved since you added: {slip.moved.map((m) => `${m.player} ${american(m.was)} → ${american(m.now)}`).join(' · ')}. The slip uses the new price.
        </p>}

        {liked.length > 0 && (
          <Section title="Model picks" aside={<a href="#/picks" className="underline">every line and projection</a>}>
            <div className="grid gap-2.5 sm:grid-cols-2">
              {liked.map((pick) => {
                const leg = board.book === 'fanduel'
                  ? board.legs.find((l) => l.player_id === pick.player_id && l.bet === pick.bet) : undefined
                const on = leg !== undefined && slip.legs.includes(leg.id)
                return (
                  <div key={`${pick.player_id}-${pick.bet}`} className="rise flex items-center gap-3 rounded-2xl border border-line bg-raised p-3">
                    <Photo src={pick.photo} />
                    <div className="min-w-0 flex-1">
                      <div className="truncate font-bold">{pick.player}</div>
                      <div className="text-xs text-muted">{pick.bet} · {american(pick.odds)} · {pick.game_short}</div>
                      <div className="text-xs text-muted">Projects {pick.projects} · {pick.agree > 1 ? `${pick.agree} models agree` : 'one model'}</div>
                    </div>
                    <div className="text-right">
                      <div className="text-sm font-black text-accent">{pick.ev_pct > 0 ? '+' : ''}{pick.ev_pct}%</div>
                      {leg && (
                        <button type="button" aria-pressed={on} onClick={() => slip.toggle(leg.id)}
                          className={`mt-1 min-h-9 rounded-full px-3 text-xs font-bold ${on ? 'bg-button text-button-text' : 'border border-line hover:border-line-strong'}`}>
                          {on ? '✓ Added' : 'Add'}
                        </button>
                      )}
                    </div>
                  </div>
                )
              })}
            </div>
            <p className="mt-2 text-xs text-muted">FanDuel points lines where a model sees at least 2% expected value. A test of the models, not a recommendation.</p>
          </Section>
        )}

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
                      <div className="text-sm font-black text-accent">+{gap.edge_pct.toFixed(1)} pp</div>
                      {gap.leg_id !== null && (
                        <button type="button" aria-pressed={on} onClick={() => slip.toggle(gap.leg_id!)}
                          className={`mt-1 min-h-9 rounded-full px-3 text-xs font-bold ${on ? 'bg-button text-button-text' : 'border border-line hover:border-line-strong'}`}>
                          {on ? '✓ Added' : 'Add'}
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

        {steady.length > 0 && (
          <Section title="Steady" aside="reached in 18+ of the last 20 games">
            <div className="grid gap-2.5 sm:grid-cols-2">
              {steady.map((item) => {
                const on = slip.legs.includes(item.leg_id)
                return (
                  <div key={item.leg_id} className="rise flex items-center gap-3 rounded-2xl border border-line bg-raised p-3">
                    <Photo src={item.photo} />
                    <div className="min-w-0 flex-1">
                      <div className="truncate font-bold">{item.player}</div>
                      <div className="text-xs text-muted">{item.bet} · {american(item.odds)} · {item.game_short}</div>
                      <div className="text-xs text-muted">Priced at {item.price_pct.toFixed(0)}%</div>
                    </div>
                    <div className="text-right">
                      <div className="text-sm font-black">{item.hits} of {item.games}</div>
                      <button type="button" aria-pressed={on} onClick={() => slip.toggle(item.leg_id)}
                        className={`mt-1 min-h-9 rounded-full px-3 text-xs font-bold ${on ? 'bg-button text-button-text' : 'border border-line hover:border-line-strong'}`}>
                        {on ? '✓ Added' : 'Add'}
                      </button>
                    </div>
                  </div>
                )
              })}
            </div>
            <p className="mt-2 text-xs text-muted">
              Consistent, not cheap: the price already knows. Last season these hit 87% of the time and cost 88 cents on the dollar.
            </p>
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

        <Section title="All props" aside="Recorded prices, not live quotes">
          <PropsBrowser legs={shown} selected={slip.legs} toggle={slip.toggle} kalshi={board.book === 'kalshi'}
            expanded={game !== ALL}
            other={otherBook && { name: otherBook.name, go: () => setMarket({ date: board.date, book: otherBook.id }) }} />
        </Section>

        <SlipImageReview market={chosen} legs={legsById} onApply={slip.set} />
      </div>

      <SlipPanel market={chosen} legs={slip.legs} legsById={legsById}
        onRemove={slip.toggle} onClear={slip.clear} onPriced={slip.rememberEstimate} />
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
        <div className="text-xs text-muted"><b className="text-text">{idea.chance_pct.toFixed(0)}%</b> to hit · <b className="text-text">${idea.pays.toFixed(2)}</b> illustrative return on $1, before fees</div>
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
