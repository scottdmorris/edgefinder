// One game's props the way a sportsbook shows them: each team in turn, each player once, with
// every stat he has a line for underneath. A stat filter and a name search narrow it down.
import { useState } from 'react'
import type { BoardGame, Leg } from '../lib/api'
import { defaultStep, ladderRows, type Row } from '../lib/ladder'
import { sidePrice, type SidePrice } from './GameCards'
import { PropRow, STATS, normalize } from './PropsBrowser'
import { Empty, Photo, Pills } from './ui'

const ALL_STATS = 'all'
const STAT_ORDER = Object.keys(STATS)

type Player = { id: number; name: string; photo: string; rows: Row[] }

function playersOf(rows: Row[]): Player[] {
  const players = new Map<number, Player>()
  for (const row of rows) {   // rows come biggest names first, so players keep that order
    const player = players.get(row.player_id) ?? { id: row.player_id, name: row.player, photo: row.photo, rows: [] }
    players.set(row.player_id, { ...player, rows: [...player.rows, row] })
  }
  return [...players.values()].map((p) => ({
    ...p, rows: [...p.rows].sort((a, b) => STAT_ORDER.indexOf(a.stat) - STAT_ORDER.indexOf(b.stat)) }))
}

const SHORT: Record<string, string> = { points: 'PTS', rebounds: 'REB', assists: 'AST', threes: '3PM' }

const onSlip = (row: Row, slip: number[]) =>
  row.steps.some((s) => slip.includes(s.yes.id) || (s.no !== null && slip.includes(s.no.id)))

/** A folded player's one line: the main number for each stat he has. */
function summary(player: Player): string {
  return player.rows.map((row) => {
    const step = defaultStep(row)
    const number = step.yes.side.endsWith('+') ? `${step.threshold}+` : step.yes.line
    return `${SHORT[row.stat] ?? row.stat} ${number}`
  }).join(' · ')
}

export function GameProps({ game, legs, selected, toggle, kalshi }: {
  game: BoardGame; legs: Leg[]; selected: number[]; toggle: (id: number) => void; kalshi: boolean
}) {
  const [stat, setStat] = useState(ALL_STATS)
  const [query, setQuery] = useState('')
  const [opened, setOpened] = useState<number[]>([])     // players tapped away from how they start
  // with every stat showing, players start folded to one line to keep the page short
  const folding = stat === ALL_STATS && query === ''
  const flip = (id: number) => setOpened((ids) => (ids.includes(id) ? ids.filter((x) => x !== id) : [...ids, id]))
  const teamOf = new Map(legs.map((l) => [l.player_id, l.team ?? null]))
  const rows = ladderRows(legs).filter((row) => (stat === ALL_STATS || row.stat === stat)
    && normalize(row.player).includes(normalize(query)))
  const sides = [game.away, game.home].filter((t): t is string => !!t)
  const logos: Record<string, string | undefined> = { [game.away ?? '']: game.away_logo, [game.home ?? '']: game.home_logo }
  const prices: Record<string, SidePrice | null> = {
    [game.away ?? '']: sidePrice(game.moneyline, 'away'), [game.home ?? '']: sidePrice(game.moneyline, 'home') }
  const bookName = game.moneyline?.book === 'draftkings' ? 'DraftKings' : 'FanDuel'
  // a player whose team is neither side (a trade the logs haven't caught up with) goes last
  const sideOf = (row: Row) => {
    const team = teamOf.get(row.player_id)
    return team && sides.includes(team) ? team : null
  }
  const groups = [...sides, null].map((team) => ({ team, players: playersOf(rows.filter((r) => sideOf(r) === team)) }))
    .filter((g) => g.players.length)

  return <section aria-label={`${game.short} player props`}>
    <div className="flex flex-wrap items-center gap-2">
      <Pills value={stat} onChange={setStat}
        options={[{ id: ALL_STATS, label: 'All' }, ...Object.entries(STATS).map(([id, label]) => ({ id, label }))]} />
      <input aria-label="Find a player in this game" type="search" placeholder="Search players" value={query}
        onChange={(e) => setQuery(e.target.value)} className="min-h-10 min-w-40 flex-1 rounded-full border border-line bg-raised px-4 text-sm" />
    </div>
    {game.moneyline && <p className="mt-2 text-xs text-muted">
      Win chances are the {bookName} moneyline, vig removed: the market’s view, not a model’s.</p>}
    {groups.length === 0 ? <div className="mt-3"><Empty title="No matching props" hint="Try another stat or player." /></div>
      : groups.map(({ team, players }) => (
        <section key={team ?? 'other'} aria-label={`${team ?? 'Other'} props`} className="mt-4">
          <h3 className="mb-2 flex items-center gap-2 text-sm font-black">
            {team && logos[team] && <img src={logos[team]} alt="" className="size-6" />}{team ?? 'Other players'}
            {team && prices[team] && <span className="text-xs font-bold tabular-nums text-muted">
              {prices[team]?.odds} · {prices[team]?.pct} to win</span>}
          </h3>
          <div className="space-y-1.5">
            {players.map((p) => {
              // folded players open with a tap; one already on the slip starts open instead
              const startsOpen = p.rows.some((r) => onSlip(r, selected))
              const shown = !folding || startsOpen !== opened.includes(p.id)
              return <div key={p.id} className="overflow-hidden rounded-2xl border border-line bg-raised">
                <button type="button" aria-expanded={shown} onClick={() => flip(p.id)}
                  className={`flex w-full items-center gap-2 px-3 pt-1.5 text-left hover:bg-raised-2 ${shown ? 'border-b border-line' : ''}`}>
                  <Photo src={p.photo} size={32} />
                  <span className="min-w-0 flex-1 pb-1.5">
                    <span className="block truncate font-bold">{p.name}</span>
                    {!shown && <span className="block truncate text-xs tabular-nums text-muted">{summary(p)}</span>}
                  </span>
                  <span aria-hidden className="pb-1.5 text-muted">{shown ? '–' : '+'}</span>
                </button>
                {shown && <div className="divide-y divide-line">
                  {p.rows.map((row) => <PropRow key={row.key} row={row} slip={selected} toggle={toggle} kalshi={kalshi} compact />)}
                </div>}
              </div>
            })}
          </div>
        </section>
      ))}
  </section>
}
