// Parlay: one suggested slip up front, quick adds beside it, then every prop. The day, price
// source, model and game sit in one summary row that opens into the full choices.
import { useEffect, useMemo, useState } from 'react'
import { api, type Board, type Idea, type Leg, type Market, type Picks } from '../lib/api'
import { american, money } from '../lib/ladder'
import { useSlip } from '../lib/slip'
import { Empty, Pills, Section } from '../components/ui'
import { BookBadge } from '../components/BookBadge'
import { SlipPanel } from '../components/SlipPanel'
import { PropsBrowser } from '../components/PropsBrowser'
import { GameCards } from '../components/GameCards'
import { GameProps, countPicks } from '../components/GameProps'
import { SlipImageReview } from '../components/SlipImageReview'
import { QuickAdds, type QuickAdd } from '../components/QuickAdds'
import { SuggestedSlip } from '../components/SuggestedSlip'

const ALL = '__all__'
const PICKS_SHOWN = 6
const GAPS_SHOWN = 6

function gameFromHash(): string {
  return new URLSearchParams(window.location.hash.split('?')[1] ?? '').get('game') ?? ALL
}

export function Parlay() {
  const [market, setMarket] = useState<Market>({})
  const [board, setBoard] = useState<Board | null>(null)
  const [boardRevision, setBoardRevision] = useState(0)
  const [error, setError] = useState<string | null>(null)
  // the chosen game lives in the address (#/parlay?game=...), so Back returns to the games list
  const [game, setGameState] = useState(gameFromHash)
  useEffect(() => {
    const sync = () => setGameState(gameFromHash())
    window.addEventListener('hashchange', sync)
    return () => window.removeEventListener('hashchange', sync)
  }, [])
  const setGame = (next: string) => {
    window.location.hash = next === ALL ? '/parlay' : `/parlay?game=${encodeURIComponent(next)}`
    setGameState(next)
    window.scrollTo({ top: 0 })                // a new page, like a sportsbook's game screen
  }
  const [style, setStyle] = useState('Higher hit rate')
  const [ideas, setIdeas] = useState<Idea[] | null>(null)
  const [refresh, setRefresh] = useState(0)
  const [loading, setLoading] = useState(false)
  const [loadedAt, setLoadedAt] = useState<string | null>(null)
  const [picks, setPicks] = useState<Picks['liked']>([])
  const [choosing, setChoosing] = useState(false)

  useEffect(() => {
    let live = true
    setLoading(true)
    api.board(market).then((b) => { if (live) { setBoard(b); setBoardRevision((n) => n + 1); setError(null); setLoadedAt(new Date().toLocaleTimeString()) } })
      .catch((e: Error) => live && setError(e.message))
      .finally(() => { if (live) setLoading(false) })
    return () => { live = false }
  }, [market, refresh])

  const chosen: Market = board ? { date: board.date, book: board.book, model: board.model } : {}
  const marketKey = board ? `${board.date}|${board.book}|${board.model}` : null
  const legsById = useMemo(() => new Map((board?.legs ?? []).map((l) => [l.id, l])), [board])
  const slip = useSlip(marketKey, legsById)
  // a game from an old link that is not on this day's board falls back to the games list
  const activeGame = board?.games.some((g) => g.game === game) ? game : ALL

  useEffect(() => {
    if (!board) return
    let live = true
    setIdeas(null)
    api.ideas(chosen, style, activeGame === ALL ? undefined : activeGame).then((i) => live && setIdeas(i))
      .catch(() => live && setIdeas([]))
    return () => { live = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [board, style, activeGame])

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

  const chosenGame = board.games.find((g) => g.game === activeGame)
  const shown = board.legs.filter((l) => !chosenGame || l.game === chosenGame.game)
  const gameShort = chosenGame?.short
  const otherBook = board.books.find((b) => b.id === 'kalshi' && b.id !== board.book)
    ?? board.books.find((b) => b.id !== board.book)
  const model = board.models.find((m) => m.id === board.model)
  const bookName = board.books.find((b) => b.id === board.book)?.name ?? board.book
  // games that have tipped off: their pregame prices are gone, so nothing in them is offered
  const startedShorts = new Set(board.games.filter((g) => g.started).map((g) => g.short))
  const startedGames = new Set(board.games.filter((g) => g.started).map((g) => g.game))
  const quick = quickAdds(board, picks, activeGame, gameShort, shown, bookName).filter((q) => !startedShorts.has(q.game))
  const games = [...board.games].sort((a, b) => Number(!!a.started) - Number(!!b.started))   // open games first
  const startedOnSlip = slip.legs.map((id) => legsById.get(id)).filter((l): l is Leg => !!l && startedGames.has(l.game))
  const picksByGame = Object.fromEntries(board.games.map((g) =>
    [g.game, countPicks(board.legs.filter((l) => l.game === g.game))]))

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

        {/* what is being shown, in one row; "Change" opens the full choices */}
        <div className="mt-3 flex flex-wrap items-center gap-1.5" aria-label="Showing">
          {[board.day_label, board.books.find((b) => b.id === board.book)?.name ?? board.book,
            `${model?.short ?? board.model}${model?.record ? ` ${model.record}` : ''}${model?.recommended ? ' ★' : ''}`].map((text, i) => (
            <button key={i} type="button" onClick={() => setChoosing(true)}
              className="min-h-9 rounded-full border border-line px-3 text-xs font-semibold hover:border-line-strong">{i === 1 ? <BookBadge book={board.book} /> : text}</button>
          ))}
          <button type="button" aria-expanded={choosing} onClick={() => setChoosing((open) => !open)}
            className="min-h-9 px-2 text-xs font-semibold text-muted underline hover:text-text">{choosing ? 'Done' : 'Change'}</button>
        </div>
        {choosing && (
          <div className="rise mt-3 space-y-4 rounded-2xl border border-line bg-raised p-4">
            <Pills label="Game day" value={board.date}
              options={board.days.map((d) => ({ id: d.date, label: d.label }))}
              onChange={(date) => { setMarket({ date }); setGame(ALL) }} />
            <Pills label="Prices" value={board.book} options={board.books.map((b) => ({ id: b.id, label: <BookBadge book={b.id} /> }))}
              onChange={(book) => setMarket({ date: board.date, book })} />
            <div>
              <Pills label="Model" value={board.model} onChange={(id) => setMarket({ ...chosen, model: id })}
                options={board.models.map((m) => ({ id: m.id, label: `${m.short}${m.record ? ` ${m.record}` : ''}${m.recommended ? ' ★' : ''}` }))} />
              {model && <p className="mt-2 text-xs text-muted">
                {model.name}.{' '}
                {board.models.some((m) => m.recommended)
                  ? `★ is the most accurate on graded lines so far (${board.models.find((m) => m.recommended)?.short}); none has beaten the sportsbook yet.`
                  : 'Too few graded lines to recommend one yet.'}
                {model.record && ` ${model.record} is its graded record on points picks.`}
              </p>}
            </div>
          </div>
        )}


        {slip.unavailable.length > 0 && <details className="my-4 rounded-2xl border border-warn/50 bg-warn/5 px-4 py-2">
          <summary className="min-h-9 cursor-pointer py-1 text-sm font-bold text-warn">
            {slip.unavailable.length} saved bet{slip.unavailable.length === 1 ? ' is' : 's are'} no longer on the board · Review
          </summary>
          <h2 className="sr-only">Review saved selections</h2>
          <p role="alert" className="mt-2 text-sm text-muted">These bets are no longer on the board. They stay here for review and are left out of the estimate.</p>
          {slip.unavailable.map(({ id, leg }) => <div key={id} className="mt-3 border-t border-line pt-3 text-sm">
            <div className="font-bold">{leg?.player ?? 'Saved selection'} · No longer on the board</div>
            {leg && <p className="mt-1 text-muted">{leg.bet} · {american(leg.odds)} · original slip chance {leg.chance_pct?.toFixed(1) ?? '–'}%</p>}
            <button type="button" onClick={() => slip.toggle(id)} className="mt-2 min-h-11 text-sm font-bold text-accent">Remove {leg?.player ?? 'selection'}</button>
          </div>)}
          {slip.estimate && <p className="mt-3 text-xs text-muted">Original illustration: stake {money(slip.estimate.price.stake)}, estimated profit {money(slip.estimate.price.to_win)}. Saved {new Date(slip.estimate.recordedAt).toLocaleString()}. This is not the current payout.</p>}
        </details>}

        {startedOnSlip.length > 0 && <p role="status" className="mt-4 text-xs text-warn">
          {startedOnSlip.map((l) => l.player).join(', ')} {startedOnSlip.length === 1 ? 'is' : 'are'} on your slip from a game that has started: those were pregame prices, which can no longer be bet.
        </p>}

        {slip.moved.length > 0 && <p className="mt-4 text-xs text-muted">
          Price moved since you added: {slip.moved.map((m) => `${m.player} ${american(m.was)} → ${american(m.now)}`).join(' · ')}. The slip uses the new price.
        </p>}

        {chosenGame ? (
          <div className="mt-6">
            <GameProps key={chosenGame.game} game={chosenGame} legs={shown} selected={slip.legs} toggle={slip.toggle}
              kalshi={board.book === 'kalshi'} onBack={() => setGame(ALL)} />
          </div>
        ) : (
          <>
            <Section title="Games" aside="Tap a game for its props">
              <GameCards games={games} value={game} onChange={setGame} layout="list" picks={picksByGame} />
            </Section>
            <Section title="Find a player" aside="Recorded prices, not live quotes">
              <PropsBrowser legs={shown} selected={slip.legs} toggle={slip.toggle} kalshi={board.book === 'kalshi'} searchOnly
                other={otherBook && { name: otherBook.name, go: () => setMarket({ date: board.date, book: otherBook.id }) }} />
            </Section>
          </>
        )}

        <SuggestedSlip key={`${marketKey}|${activeGame}|${style}`} ideas={ideas} legs={legsById} sameGame={!!chosenGame}
          started={!!chosenGame?.started}
          styles={board.styles} style={style} onStyle={setStyle} inUse={slip.legs} onUse={slip.set} />

        {quick.length > 0 && (
          <Section title="Quick adds" aside={<a href="#/picks" className="underline">every line and projection</a>}>
            <QuickAdds items={quick} selected={slip.legs} toggle={slip.toggle} />
          </Section>
        )}

        <SlipImageReview market={chosen} legs={legsById} onApply={slip.set} />
      </div>

      <SlipPanel market={chosen} legs={slip.legs} legsById={legsById} revision={boardRevision}
        onRemove={slip.toggle} onClear={slip.clear} onPriced={slip.rememberEstimate} />
    </div>
  )
}

// Model picks, price gaps and steady legs in one list, each saying which it is and why.
// Model picks are made on FanDuel's lines. Price sources offer different numbers, so on
// another source a pick can only be added when that source lists the very same bet.
function quickAdds(board: Board, picks: Picks['liked'], game: string, gameShort: string | undefined, shown: Leg[],
  bookName: string): QuickAdd[] {
  const everywhere = game === ALL
  const liked = picks.filter((p) => everywhere || p.game_short === gameShort).slice(0, PICKS_SHOWN).map((p): QuickAdd => {
    const leg = board.legs.find((l) => l.player_id === p.player_id && l.bet === p.bet)
    const source = board.book === 'fanduel' ? '' : 'FanDuel '
    return {
      key: `pick-${p.player_id}-${p.bet}`, kind: 'Model pick', player: p.player, photo: p.photo,
      bet: p.bet, odds: leg?.odds ?? p.odds, game: p.game_short,
      why: `${source}models project ${p.projects} · ${p.agree > 1 ? `${p.agree} models agree` : 'one model'}`,
      figure: `${source}${p.ev_pct > 0 ? '+' : ''}${p.ev_pct}%`, legId: leg?.id ?? null,
      missing: !leg ? `FanDuel price shown. ${bookName} doesn't offer this number.` : undefined,
    }
  })
  const gaps = board.gaps.filter((g) => everywhere || shown.some((l) => l.id === g.leg_id)).slice(0, GAPS_SHOWN).map((g): QuickAdd => ({
    key: `gap-${g.player_id}-${g.bet}`, kind: 'Price gap', player: g.player, photo: g.photo,
    bet: `${g.bet} points`, odds: g.odds, game: g.game_short,
    why: `${g.reference} ${g.reference_pct.toFixed(0)}%${g.estimated ? ' (est.)' : ''} vs ${g.price_pct.toFixed(0)}% here`,
    figure: `+${g.edge_pct.toFixed(1)} pp`, legId: g.leg_id,
  }))
  const steady = board.steady.filter((s) => everywhere || s.game === game).map((s): QuickAdd => ({
    key: `steady-${s.leg_id}`, kind: 'Steady', player: s.player, photo: s.photo,
    bet: s.bet, odds: s.odds, game: s.game_short,
    why: `Priced at ${s.price_pct.toFixed(0)}%, so no bargain`,
    figure: `${s.hits} of ${s.games}`, legId: s.leg_id,
  }))
  return [...liked, ...gaps, ...steady]
}

function Loading() {
  return (
    <div className="space-y-3">
      {[0, 1, 2].map((i) => <div key={i} className="h-24 animate-pulse rounded-2xl bg-raised" />)}
    </div>
  )
}
