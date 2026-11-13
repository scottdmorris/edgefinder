// One game in full: quarter scores, the shot chart, team stats side by side, leaders, the
// play-by-play and the box score. Plays and shots that arrived since the last refresh are marked.
import { useMemo, useState } from 'react'
import type { BoxRow, GameDetail, Play } from '../lib/api'
import { usePrevious } from '../lib/poll'
import { Court } from './Court'
import { Photo, Pills } from './ui'

type Detail = NonNullable<GameDetail['detail']>
const LATEST_PLAYS = 4
const TABS = [{ id: 'stats', label: 'Stats' }, { id: 'plays', label: 'Plays' }, { id: 'box', label: 'Box score' }]

/** `mine` are the players on your slip in this game: their plays stand out in the feed. */
export function GameCenter({ game, mine = [] }: { game: GameDetail & { detail: Detail }; mine?: string[] }) {
  const [tab, setTab] = useState('stats')
  // box-score plays name players by surname ("Banchero makes driving layup")
  const surnames = mine.map((name) => name.split(' ').slice(-1)[0]).filter((name) => name.length > 2)
  const colors = { [game.away.team]: game.away.color, [game.home.team]: game.home.color }
  return (
    <div className="mt-5">
      <Pills value={tab} onChange={setTab} options={TABS} />
      <div className="mt-4">
        {tab === 'stats' && <Stats game={game} colors={colors} surnames={surnames} onAllPlays={() => setTab('plays')} />}
        {tab === 'plays' && <Plays plays={game.detail.plays} colors={colors} gameId={game.id} surnames={surnames} />}
        {tab === 'box' && <Box game={game} />}
      </div>
    </div>
  )
}

function Stats({ game, colors, surnames, onAllPlays }: {
  game: GameDetail & { detail: Detail }; colors: Record<string, string>; surnames: string[]; onAllPlays: () => void
}) {
  const { detail } = game
  return (
    <div className="space-y-6">
      {game.state === 'live' && detail.plays.length > 0 && (
        <div>
          <div className="mb-2 flex items-baseline justify-between">
            <Heading>Latest plays</Heading>
            <button type="button" onClick={onAllPlays} className="text-xs font-semibold text-muted underline hover:text-text">All plays</button>
          </div>
          <Plays plays={detail.plays.slice(0, LATEST_PLAYS)} colors={colors} gameId={game.id} surnames={surnames} />
        </div>
      )}
      <Quarters detail={detail} colors={colors} />
      <Shots game={game} colors={colors} />
      {detail.compare.length > 0 && (
        <div>
          <Heading>Team stats</Heading>
          <div className="space-y-3 rounded-2xl border border-line bg-raised p-4">
            {detail.compare.map((row) => (
              <div key={row.label}>
                <div className="flex justify-between text-sm">
                  <b className={row.ahead === 'away' ? '' : 'text-muted'}>{row.away_text}</b>
                  <span className="text-xs text-muted">{row.label}</span>
                  <b className={row.ahead === 'home' ? '' : 'text-muted'}>{row.home_text}</b>
                </div>
                <div className="mt-1 flex h-1.5 gap-1 overflow-hidden rounded-full">
                  <div className="rounded-full transition-all duration-700" style={{ width: `${row.away_share * 100}%`, background: game.away.color, opacity: row.ahead === 'home' ? 0.4 : 1 }} />
                  <div className="flex-1 rounded-full transition-all duration-700" style={{ background: game.home.color, opacity: row.ahead === 'away' ? 0.4 : 1 }} />
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
      <div>
        <Heading>Leaders</Heading>
        <div className="grid gap-2 sm:grid-cols-2">
          {[game.away.team, game.home.team].map((team) => (
            <div key={team} className="rounded-2xl border border-line bg-raised p-2" style={{ borderTopColor: colors[team], borderTopWidth: 3 }}>
              {detail.leaders.filter((l) => l.team === team).map((l) => (
                <div key={l.stat} className="flex items-center gap-3 px-1.5 py-1.5">
                  <Photo src={l.photo} size={40} />
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-sm font-bold">{l.name}</div>
                    <div className="text-xs text-muted">{l.stat}</div>
                  </div>
                  <div className="text-xl font-black">{l.value}</div>
                </div>
              ))}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

function Quarters({ detail, colors }: { detail: Detail; colors: Record<string, string> }) {
  const { columns, rows } = detail.quarters
  return (
    <div className="overflow-x-auto rounded-2xl border border-line bg-raised">
      <table className="w-full text-sm tabular-nums">
        <thead>
          <tr className="text-xs text-muted">
            <th className="px-4 py-2 text-left font-semibold">Team</th>
            {columns.map((c) => <th key={c} className="px-2 py-2 text-right font-semibold">{c}</th>)}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.team} className="border-t border-line">
              <td className="px-4 py-2 font-bold"><span style={{ color: colors[row.team] }}>●</span> {row.team}</td>
              {row.values.map((v, i) => (
                <td key={i} className={`px-2 py-2 text-right ${i === row.values.length - 1 ? 'font-black' : ''}`}>{v}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function Shots({ game, colors }: { game: GameDetail & { detail: Detail }; colors: Record<string, string> }) {
  const [period, setPeriod] = useState('all')
  const shots = game.detail.shots
  const latest = shots.length ? shots[shots.length - 1].n : -1
  const previous = usePrevious(`${game.id}:${latest}`)
  const freshFrom = previous && previous.startsWith(`${game.id}:`) ? Number(previous.split(':')[1]) : null
  const periods = useMemo(() => [...new Map(shots.map((s) => [String(s.period), s.period_label])).entries()], [shots])
  const shown = period === 'all' ? shots : shots.filter((s) => String(s.period) === period)
  const line = (team: string) => {
    const mine = shown.filter((s) => s.team === team)
    return `${mine.filter((s) => s.made).length}-${mine.length}`
  }
  return (
    <div>
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <Heading>Shot chart</Heading>
        {periods.length > 1 && (
          <Pills value={period} onChange={setPeriod}
            options={[{ id: 'all', label: 'All' }, ...periods.map(([id, label]) => ({ id, label }))]} />
        )}
      </div>
      {shots.length === 0 ? <div className="text-sm text-muted">No shots with a location yet.</div> : (
        <>
          <div className="mb-1.5 flex items-center justify-between text-sm">
            <span>◀ <b style={{ color: game.away.color }}>{game.away.team}</b> {line(game.away.team)}</span>
            <span className="text-xs text-muted">● made · ✕ missed</span>
            <span><b style={{ color: game.home.color }}>{game.home.team}</b> {line(game.home.team)} ▶</span>
          </div>
          <Court shots={shown} colors={colors} homeColor={game.home.color} homeLogo={game.home.logo} freshFrom={freshFrom} />
        </>
      )}
    </div>
  )
}

function Plays({ plays, colors, gameId, surnames = [] }: {
  plays: Play[]; colors: Record<string, string>; gameId: string; surnames?: string[]
}) {
  const newest = plays.length ? plays[0].order : -1
  const previous = usePrevious(`${gameId}:${newest}`)
  const seen = previous && previous.startsWith(`${gameId}:`) ? Number(previous.split(':')[1]) : null
  if (!plays.length) return <div className="text-sm text-muted">No plays yet.</div>
  return (
    <ol className="divide-y divide-line overflow-hidden rounded-2xl border border-line bg-raised">
      {plays.map((p) => {
        const yours = surnames.some((name) => p.text.includes(name))
        return (
          <li key={p.order} className={`flex gap-3 px-4 py-2.5 ${yours ? 'bg-accent/10' : ''} ${seen !== null && p.order > seen ? 'ticker flash' : ''}`}
            style={{ boxShadow: p.team ? `inset 3px 0 0 ${colors[p.team] ?? 'transparent'}` : undefined }}>
            <span className="w-16 shrink-0 text-xs tabular-nums text-muted">{p.period} {p.clock}</span>
            <span className={`min-w-0 flex-1 text-sm ${yours ? 'font-semibold text-accent' : ''}`}>{p.text}</span>
            {p.score && <span className="shrink-0 text-xs font-bold tabular-nums text-muted">{p.score}</span>}
          </li>
        )
      })}
    </ol>
  )
}

const BOX_COLUMNS: (keyof BoxRow)[] = ['Min', 'Pts', 'Reb', 'Ast', 'FG', '3PT', 'FT', 'Stl', 'Blk', 'TO', 'PF', '+/-']

function Box({ game }: { game: GameDetail & { detail: Detail } }) {
  const [team, setTeam] = useState(game.away.team)
  const box = game.detail.box[team]
  return (
    <div>
      <Pills value={team} onChange={setTeam} options={[game.away.team, game.home.team].map((t) => ({ id: t, label: t }))} />
      {(['starters', 'bench'] as const).map((group) => box?.[group].length ? (
        <div key={group} className="mt-4">
          <Heading>{group === 'starters' ? 'Starters' : 'Bench'}</Heading>
          <div className="overflow-x-auto rounded-2xl border border-line bg-raised">
            <table className="w-full text-sm tabular-nums">
              <thead>
                <tr className="text-xs text-muted">
                  <th className="sticky left-0 bg-raised px-3 py-2 text-left font-semibold">Player</th>
                  {BOX_COLUMNS.map((c) => <th key={c} className="px-2 py-2 text-right font-semibold">{c}</th>)}
                </tr>
              </thead>
              <tbody>
                {box[group].map((row) => (
                  <tr key={row.id} className="border-t border-line">
                    <td className="sticky left-0 bg-raised px-3 py-1.5">
                      <div className="flex items-center gap-2 whitespace-nowrap font-semibold">
                        <Photo src={row.photo} size={30} />
                        {row.Player}
                        {row.on_court && <span className="live-dot size-1.5 rounded-full bg-good" title="On the court" />}
                      </div>
                    </td>
                    {BOX_COLUMNS.map((c) => (
                      <td key={c} className={`whitespace-nowrap px-2 py-1.5 text-right ${c === 'Pts' ? 'font-black' : ''} ${c === 'PF' && Number(row.PF) >= 4 ? 'text-warn' : ''}`}>{row[c]}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null)}
      <p className="mt-2 text-xs text-muted">A green dot marks players on the court right now; orange fouls are four or more.</p>
    </div>
  )
}

function Heading({ children }: { children: React.ReactNode }) {
  return <h3 className="mb-2 text-sm font-extrabold uppercase tracking-wider text-muted">{children}</h3>
}
