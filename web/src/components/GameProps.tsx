// One game's betting options, laid out like a sportsbook's game page: the matchup on top, a tab
// per stat, then each team's players. Where a stat has both, "Over / Under" lines and "X+"
// ladders (10+, 15+, 20+) are two markets to switch between.
import { useState } from 'react'
import type { BoardGame, Leg } from '../lib/api'
import { american, ladderRows } from '../lib/ladder'
import { sidePrice, tipTime, type SidePrice } from './GameCards'
import { PropRow, STATS } from './PropsBrowser'
import { Empty, Photo, Pills } from './ui'

const STAT_ORDER = Object.keys(STATS)
type Market = 'lines' | 'ladder'

const isRung = (leg: Leg) => leg.side.endsWith('+')
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
function LadderRow({ player, label, selected, toggle }: {
  player: LadderPlayer; label: string; selected: number[]; toggle: (id: number) => void
}) {
  return <div className="px-3 py-2">
    <div className="flex items-center gap-2">
      <Photo src={player.photo} size={32} />
      <div className="min-w-0">
        <div className="text-sm font-bold leading-tight">{player.name}</div>
        <div className="text-xs tabular-nums text-muted"><Average average={player.average} /></div>
      </div>
    </div>
    <div className="no-scrollbar mt-2 flex gap-1.5 overflow-x-auto pb-0.5">
      {player.rungs.map((leg) => {
        const on = selected.includes(leg.id)
        return <button key={leg.id} type="button" aria-pressed={on} onClick={() => toggle(leg.id)}
          aria-label={`At least ${player.name} ${rung(leg)}+ ${label}`}
          className={`flex h-12 w-[4.25rem] shrink-0 flex-col items-center justify-center rounded-lg border leading-tight ${on ? 'border-button bg-button text-button-text' : 'border-line bg-raised-2 hover:border-line-strong'}`}>
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
  const market: Market = fellBack ? 'lines' : chosenMarket   // a stat not chosen opens on its lines, like a tap
  const label = STATS[stat] ?? stat
  const statLegs = legs.filter((l) => l.stat === stat)
  // Kalshi lists only ladders, shown as Yes/No rows; a sportsbook can list both markets
  const lineLegs = kalshi ? statLegs : statLegs.filter((l) => !isRung(l))
  const rungLegs = kalshi ? [] : statLegs.filter(isRung)
  const both = lineLegs.length > 0 && rungLegs.length > 0
  const shown: Market = rungLegs.length && (market === 'ladder' || !lineLegs.length) ? 'ladder' : 'lines'

  const teamOf = new Map(legs.map((l) => [l.player_id, l.team ?? null]))
  const sides = [game.away, game.home].filter((t): t is string => !!t)
  const sideOf = (id: number) => {   // a team that is neither side (a late trade) goes last
    const team = teamOf.get(id)
    return team && sides.includes(team) ? team : null
  }
  const logos: Record<string, string | undefined> = { [game.away ?? '']: game.away_logo, [game.home ?? '']: game.home_logo }
  const prices: Record<string, SidePrice | null> = {
    [game.away ?? '']: sidePrice(game.moneyline, 'away'), [game.home ?? '']: sidePrice(game.moneyline, 'home') }
  const bookName = game.moneyline?.book === 'draftkings' ? 'DraftKings' : 'FanDuel'
  const lineRows = ladderRows(lineLegs)
  const ladder = ladderPlayers(rungLegs)
  const groups = [...sides, null].map((team) => ({
    team,
    rows: lineRows.filter((r) => sideOf(r.player_id) === team),
    rungs: ladder.filter((p) => sideOf(p.id) === team),
  })).filter((g) => (shown === 'lines' ? g.rows.length : g.rungs.length))

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
        <div className="text-xs text-muted">{tipTime(game.tip)}{game.moneyline ? ` · win chances from the ${bookName} moneyline, vig removed` : ''}</div>
      </div>
    </div>

    <div className="mt-3 space-y-2">
      <Pills value={stat} onChange={(s) => { setStat(s); setMarket('lines') }}
        options={stats.map((s) => ({ id: s, label: STATS[s] }))} />
      {both && <Pills value={shown} onChange={setMarket}
        options={[{ id: 'lines', label: 'Over / Under' }, { id: 'ladder', label: `${label} X+` }]} />}
    </div>

    {groups.length === 0 ? <div className="mt-3"><Empty title="No props for this game yet" hint="Lines appear after the next snapshot." /></div>
      : groups.map(({ team, rows, rungs }) => (
        <section key={team ?? 'other'} aria-label={`${team ?? 'Other'} props`} className="mt-4">
          <h3 className="mb-2 flex items-center gap-2 text-sm font-black">
            {team && logos[team] && <img src={logos[team]} alt="" className="size-6" />}{team ?? 'Other players'}
            {team && prices[team] && <span className="text-xs font-bold tabular-nums text-muted">
              {prices[team]?.odds} · {prices[team]?.pct} to win</span>}
          </h3>
          <div className="divide-y divide-line overflow-hidden rounded-2xl border border-line bg-raised">
            {shown === 'lines'
              ? rows.map((row) => <PropRow key={row.key} row={row} slip={selected} toggle={toggle} kalshi={kalshi} inGame />)
              : rungs.map((p) => <LadderRow key={p.id} player={p} label={label} selected={selected} toggle={toggle} />)}
          </div>
        </section>
      ))}
  </section>
}
