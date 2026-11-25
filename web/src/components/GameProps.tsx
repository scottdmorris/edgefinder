// One game's betting options, laid out like a sportsbook's game page: the matchup on top, a tab
// per stat, then each team's players. Where a stat has both, "Over / Under" lines and "X+"
// ladders (10+, 15+, 20+) are two markets to switch between.
import { useState } from 'react'
import type { BoardGame, Leg } from '../lib/api'
import { american, ladderRows, type Row } from '../lib/ladder'
import { sidePrice, tipTime } from './GameCards'
import { PickStar, PropRow, STATS } from './PropsBrowser'
import { Empty, Photo, Pills } from './ui'

const STAT_ORDER = Object.keys(STATS)
type Market = 'lines' | 'ladder'

const isRung = (leg: Leg) => leg.side.endsWith('+')
const rowPicked = (row: Row) => row.steps.some((s) => s.yes.pick || s.no?.pick)
const picksText = (n: number) => (n ? ` · ★${n}` : '')

/** Highest season average first (then last 10, then the biggest line), like a sportsbook's list. */
function byAverage<T>(items: T[], average: (item: T) => Leg['average'], line: (item: T) => number): T[] {
  const score = (item: T) => {
    const a = average(item)
    return [a?.season ?? a?.last10 ?? -1, a?.last10 ?? -1, line(item)]
  }
  return [...items].sort((x, y) => {
    const [a, b] = [score(x), score(y)]
    return b[0] - a[0] || b[1] - a[1] || b[2] - a[2]
  })
}
/** Picks counted by prop, not by price: several picked rungs of one player's ladder are one pick. */
export const countPicks = (legs: Leg[]) =>
  new Set(legs.filter((l) => l.pick).map((l) => `${l.player_id}|${l.stat}|${isRung(l)}`)).size
const rung = (leg: Leg) => parseInt(leg.side, 10)

type LadderPlayer = { id: number; name: string; photo: string; average: Leg['average']; rungs: Leg[] }

function ladderPlayers(legs: Leg[]): LadderPlayer[] {
  const players = new Map<number, LadderPlayer>()
  for (const leg of legs) {
    const player = players.get(leg.player_id)
      ?? { id: leg.player_id, name: leg.player, photo: leg.photo, average: leg.average, rungs: [] }
    players.set(leg.player_id, { ...player, rungs: [...player.rungs, leg] })
  }
  // the biggest names first: the highest rung a player is offered
  return [...players.values()].map((p) => ({ ...p, rungs: [...p.rungs].sort((a, b) => rung(a) - rung(b)) }))
    .sort((a, b) => rung(b.rungs[b.rungs.length - 1]) - rung(a.rungs[a.rungs.length - 1]))
}

function Average({ average }: { average: Leg['average'] }) {
  if (!average || (average.season == null && average.last10 == null)) return null
  return <span>avg <b className="text-text">{average.season?.toFixed(1) ?? '–'}</b> · L10 <b className="text-text">{average.last10?.toFixed(1) ?? '–'}</b></span>
}

/** A player's "at least" rungs as a row of price buttons, like a sportsbook's alt-line market. */
function LadderRow({ player, label, selected, toggle, team, locked = false }: {
  player: LadderPlayer; label: string; selected: number[]; toggle: (id: number) => void; team?: string
  locked?: boolean
}) {
  const picks = player.rungs.filter((leg) => leg.pick)      // rungs come lowest first
  const projection = player.rungs[0]?.projection
  return <div className="px-3 py-2">
    <div className="flex items-center gap-2">
      <Photo src={player.photo} size={32} />
      <div className="min-w-0">
        <div className="text-sm font-bold leading-tight">{player.name}</div>
        {picks.length > 0 && <div className="text-xs font-bold text-good">
          ★ {picks[0].projection_model || 'Model'} pick: {rung(picks[0])}+{picks.length > 1 && ` to ${rung(picks[picks.length - 1])}+`}</div>}
        <div className="text-xs tabular-nums text-muted">
          {team && <span>{team} · </span>}<Average average={player.average} />
          {projection != null && <span>{player.average ? ' · ' : ''}proj <b className="text-text">{projection.toFixed(1)}</b></span>}
        </div>
      </div>
    </div>
    <div className="no-scrollbar mt-2 flex gap-1.5 overflow-x-auto pb-0.5 pt-1.5">
      {player.rungs.map((leg) => {
        const on = selected.includes(leg.id)
        return <button key={leg.id} type="button" aria-pressed={on} onClick={() => toggle(leg.id)} disabled={locked && !on}
          aria-label={`At least ${player.name} ${rung(leg)}+ ${label}${leg.pick ? ', model pick' : ''}`}
          className={`relative flex h-12 w-[4.25rem] shrink-0 disabled:cursor-not-allowed disabled:opacity-40 flex-col items-center justify-center rounded-lg border leading-tight ${on ? 'border-button bg-button text-button-text' : leg.pick ? 'border-good bg-raised-2' : 'border-line bg-raised-2 hover:border-line-strong'}`}>
          {leg.pick && <PickStar on={on} />}
          <span className={`text-[11px] font-semibold ${on ? '' : 'text-muted'}`}>{rung(leg)}+</span>
          <span className={`text-sm font-black tabular-nums ${on ? '' : 'text-accent'}`}>{american(leg.odds)}</span>
        </button>
      })}
    </div>
  </div>
}

export function GameProps({ game, legs, selected, toggle, kalshi, onBack }: {
  game: BoardGame; legs: Leg[]; selected: number[]; toggle: (id: number) => void; kalshi: boolean
  onBack?: () => void
}) {
  const stats = STAT_ORDER.filter((s) => legs.some((l) => l.stat === s))
  const [picked, setStat] = useState(stats[0] ?? 'points')
  // after a switch of book or day the picked stat may be gone from this game: fall back to its first
  const fellBack = !stats.includes(picked)
  const stat = fellBack ? stats[0] ?? picked : picked
  const [chosenMarket, setMarket] = useState<Market>('lines')
  const [picksOnly, setPicksOnly] = useState(false)
  const market: Market = fellBack ? 'lines' : chosenMarket   // a stat not chosen opens on its lines, like a tap
  const label = STATS[stat] ?? stat
  const statLegs = legs.filter((l) => l.stat === stat)
  // Kalshi lists only ladders, shown as Yes/No rows; a sportsbook can list both markets
  const lineLegs = kalshi ? statLegs : statLegs.filter((l) => !isRung(l))
  const rungLegs = kalshi ? [] : statLegs.filter(isRung)
  const both = lineLegs.length > 0 && rungLegs.length > 0
  const shown: Market = rungLegs.length && (market === 'ladder' || !lineLegs.length) ? 'ladder' : 'lines'

  const teamOf = new Map(legs.map((l) => [l.player_id, l.team ?? null]))
  const prices = [game.away, game.home].map((code, i) => ({ code, logo: i ? game.home_logo : game.away_logo,
    price: sidePrice(game.moneyline, i ? 'home' : 'away') }))
  const bookName = game.moneyline?.book === 'draftkings' ? 'DraftKings' : 'FanDuel'
  // one list like a sportsbook's: the biggest producers first (season average, then last 10),
  // and with "Model picks only" just the model's picks
  const lineRows = byAverage(ladderRows(lineLegs), (r) => r.average, (r) => r.steps[r.steps.length - 1].threshold)
    .filter((r) => !picksOnly || rowPicked(r))
  const ladder = byAverage(ladderPlayers(rungLegs), (p) => p.average, (p) => rung(p.rungs[p.rungs.length - 1]))
    .filter((p) => !picksOnly || p.rungs.some((l) => l.pick))
  const empty = shown === 'lines' ? !lineRows.length : !ladder.length
  const locked = !!game.started
  // when the prices on this page were recorded: they are snapshots, not live quotes
  const pricedAt = legs.map((l) => l.quality?.price_at).filter((t): t is string => !!t).sort().pop()
  const pickCount = countPicks
  const gamePicks = pickCount(legs)

  return <section aria-label={`${game.short} player props`}>
    <div className="flex items-center gap-3">
      {onBack && <button type="button" onClick={onBack}
        className="min-h-10 shrink-0 rounded-full border border-line px-3 text-sm font-semibold hover:border-line-strong">‹ All games</button>}
      <div className="min-w-0">
        <h2 className="flex items-center gap-1.5 text-lg font-black">
          {game.away_logo && <img src={game.away_logo} alt="" className="size-6" />}{game.away ?? game.short}
          <span className="text-muted">@</span>
          {game.home_logo && <img src={game.home_logo} alt="" className="size-6" />}{game.home}
        </h2>
        <div className="text-xs text-muted">{locked ? `Started ${tipTime(game.tip)}` : tipTime(game.tip)}
          {pricedAt && ` · prices recorded ${new Date(pricedAt).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}`}</div>
      </div>
    </div>
    {game.moneyline && <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted"
      title={`Win chances from the ${bookName} moneyline, vig removed`}>
      {prices.map(({ code, logo, price }) => price && <span key={code} className="flex items-center gap-1.5 tabular-nums">
        {logo && <img src={logo} alt="" className="size-4" />}<b className="text-text">{code}</b> {price.odds} · {price.pct} to win
      </span>)}
    </div>}
    {locked && <p role="status" className="mt-3 rounded-xl border border-warn/50 bg-warn/5 px-3 py-2 text-sm text-warn">
      This game has started. These were its pregame prices, which can no longer be bet, so they can't be added.
    </p>}
    <p className="mt-2 text-xs text-muted">
      {gamePicks
        ? <><b className="text-good">★ {gamePicks} model pick{gamePicks === 1 ? '' : 's'}</b> in this game, marked on their prices.</>
        : 'The model made no picks in this game: it rates these prices about right.'}
      {' '}Picks are paper bets the <a href="#/record" className="underline">record</a> tracks, not advice.
    </p>

    <div className="mt-3 space-y-2">
      <Pills value={stat} onChange={(s) => { setStat(s); setMarket('lines') }}
        options={stats.map((s) => ({ id: s, label: STATS[s] + picksText(pickCount(legs.filter((l) => l.stat === s))) }))} />
      <div className="flex flex-wrap items-center gap-2">
        {both && <Pills value={shown} onChange={setMarket}
          options={[{ id: 'lines', label: 'Over / Under' + picksText(pickCount(lineLegs)) },
            { id: 'ladder', label: `${label} X+` + picksText(pickCount(rungLegs)) }]} />}
        {gamePicks > 0 && <label className="flex min-h-10 cursor-pointer items-center gap-2 text-xs text-muted">
          <input type="checkbox" checked={picksOnly} onChange={(e) => setPicksOnly(e.target.checked)} className="size-4 accent-accent" />Model picks only
        </label>}
      </div>
    </div>

    {empty ? <div className="mt-3">{picksOnly
      ? <Empty title={`No model picks in ${shown === 'lines' ? label : `${label} X+`}`} hint="Untick “Model picks only” or try another tab." />
      : <Empty title="No props for this game yet" hint="Lines appear after the next snapshot." />}</div>
      : <>{shown === 'ladder' && !countPicks(rungLegs) && <p className="mt-3 text-xs text-muted">
        X+ picks aren't starred: on the rungs FanDuel offers, every model's X+ picks have lost money so far.</p>}
      <div className="mt-4 divide-y divide-line overflow-hidden rounded-2xl border border-line bg-raised">
        {shown === 'lines'
          ? lineRows.map((row) => <PropRow key={row.key} row={row} slip={selected} toggle={toggle} kalshi={kalshi}
            inGame team={teamOf.get(row.player_id) ?? undefined} locked={locked} />)
          : ladder.map((p) => <LadderRow key={p.id} player={p} label={label} selected={selected} toggle={toggle}
            team={teamOf.get(p.id) ?? undefined} locked={locked} />)}
      </div></>}
  </section>
}
