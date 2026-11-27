// A live game on the court stage: the real score, clock and latest play, every shot at its real
// spot (the newest flies to the rim when it arrives), and the ten on the floor with their lines.
// NBA's feed has no player tracking, so players are listed, not placed on the court.
import { useEffect, useState } from 'react'
import type { BoxRow, GameDetail } from '../lib/api'
import { CourtStage, type ShotMark } from './CourtStage'

type Detail = NonNullable<GameDetail['detail']>
const SHOTS_SHOWN = 40

function onCourt(detail: Detail, team: string): BoxRow[] {
  const groups = detail.box[team]
  if (!groups) return []
  return [...groups.starters, ...groups.bench].filter((row) => row.on_court)
}

export function LiveCourt({ game }: { game: GameDetail & { detail: Detail } }) {
  const { detail } = game
  const latest = detail.plays[0]
  const sideOf = (team: string): 'away' | 'home' => (team === game.away.team ? 'away' : 'home')
  const shots: ShotMark[] = detail.shots.slice(-SHOTS_SHOWN)
    .map((s) => ({ key: s.n, x: s.x, y: s.y, made: s.made, team: sideOf(s.team), three: s.three }))
  // the newest shot flies in once, when it is new since the last refresh
  const newest = shots.at(-1)
  const key = newest?.key ?? null
  const [seen, setSeen] = useState(key)
  const [flying, setFlying] = useState<ShotMark | null>(null)
  if (seen !== key) {
    setSeen(key)
    setFlying(seen !== null && newest ? newest : null)
  }
  useEffect(() => {
    if (!flying) return
    const timer = setTimeout(() => setFlying(null), 1500)
    return () => clearTimeout(timer)
  }, [flying])
  const final = game.state === 'final'
  return <CourtStage
    away={{ code: game.away.team, logo: game.away.logo, color: game.away.color, score: game.away.score }}
    home={{ code: game.home.team, logo: game.home.logo, color: game.home.color, score: game.home.score }}
    period={final ? 'Final' : latest?.period ?? ''} clock={final ? '' : latest?.clock ?? ''}
    ticker={latest?.text} tickerTeam={latest?.team ? sideOf(latest.team) : null}
    shots={flying ? shots.filter((s) => s.key !== flying.key) : shots} flying={flying}
    badge={final ? 'Final' : game.state === 'live' ? '● Live' : undefined} scoreboard={false}>
    {!final && <div className="grid grid-cols-2 gap-px border-t border-white/10 bg-white/10 text-[11px]">
      {[game.away, game.home].map((side) => <div key={side.team} className="bg-[#070a10] px-2 py-1.5">
        <div className="mb-0.5 text-[9px] font-black uppercase tracking-wider" style={{ color: side.color }}>{side.team} on the floor</div>
        {onCourt(detail, side.team).map((row) => <div key={row.id} className="flex items-center justify-between gap-1 py-0.5">
          <span className="truncate">{row.Player.split(' ').slice(-1)[0]}</span>
          <span className="shrink-0 tabular-nums text-muted"><b className="text-text">{row.Pts}</b> p · {row.Reb} r · {row.Ast} a</span>
        </div>)}
      </div>)}
    </div>}
  </CourtStage>
}
