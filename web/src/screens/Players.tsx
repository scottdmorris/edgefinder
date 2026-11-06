// Players: search anyone, see how they're playing, and how often they've cleared a number.
// The hit rate and chart are worked out here from the games the API sends, so moving the line
// answers instantly.
import { useEffect, useMemo, useRef, useState } from 'react'
import { api, type PlayerGame, type PlayerOption, type PlayerProfile } from '../lib/api'
import { american } from '../lib/ladder'
import { Empty, Pills, Section, StatStrip } from '../components/ui'

const STATS = [
  { id: 'pts', label: 'Points' }, { id: 'reb', label: 'Rebounds' },
  { id: 'ast', label: 'Assists' }, { id: 'fg3m', label: '3-pointers' },
] as const
type Stat = (typeof STATS)[number]['id']
const CHART_GAMES = 15
const MATCHES_SHOWN = 8

/** "Dončić" and "doncic" are the same search. */
const plain = (text: string) => text.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase()

export function Players() {
  const [options, setOptions] = useState<PlayerOption[] | null>(null)
  const [chosen, setChosen] = useState<number | null>(() => {
    const id = Number(new URLSearchParams(window.location.hash.split('?')[1]).get('id'))
    return Number.isFinite(id) && id > 0 ? id : null
  })
  useEffect(() => { api.players().then(setOptions).catch(() => setOptions([])) }, [])

  const choose = (id: number) => {
    setChosen(id)
    window.history.replaceState(null, '', `#/players?id=${id}`)
  }

  return (
    <div>
      <h1 className="text-3xl font-black tracking-tight">Players</h1>
      <Search options={options} onChoose={choose} />
      {chosen ? <Profile key={chosen} id={chosen} /> : (
        <p className="mt-4 text-sm text-muted">Search any player to see their averages, recent games and how often they've cleared a number.</p>
      )}
    </div>
  )
}

function Search({ options, onChoose }: { options: PlayerOption[] | null; onChoose: (id: number) => void }) {
  const [query, setQuery] = useState('')
  const [active, setActive] = useState(0)
  const box = useRef<HTMLInputElement>(null)
  const matches = useMemo(() => {
    const q = plain(query.trim())
    if (!q || !options) return []
    const starts = options.filter((o) => plain(o.name).split(' ').some((w) => w.startsWith(q)) || plain(o.name).startsWith(q))
    const contains = options.filter((o) => !starts.includes(o) && plain(o.name).includes(q))
    return [...starts, ...contains].slice(0, MATCHES_SHOWN)
  }, [query, options])

  const pick = (o: PlayerOption) => { onChoose(o.id); setQuery(''); box.current?.blur() }
  return (
    <div className="relative mt-4">
      <input ref={box} type="search" value={query} placeholder={options ? 'Search any player…' : 'Loading players…'}
        aria-label="Search players" role="combobox" aria-expanded={matches.length > 0} aria-controls="player-matches"
        onChange={(e) => { setQuery(e.target.value); setActive(0) }}
        onKeyDown={(e) => {
          if (e.key === 'ArrowDown') { e.preventDefault(); setActive(Math.min(active + 1, matches.length - 1)) }
          if (e.key === 'ArrowUp') { e.preventDefault(); setActive(Math.max(active - 1, 0)) }
          if (e.key === 'Enter' && matches[active]) pick(matches[active])
          if (e.key === 'Escape') setQuery('')
        }}
        className="min-h-12 w-full rounded-full border border-line bg-raised px-5 font-semibold outline-none placeholder:text-muted focus:border-line-strong" />
      {matches.length > 0 && (
        <ul id="player-matches" role="listbox" className="absolute inset-x-0 top-14 z-30 overflow-hidden rounded-2xl border border-line bg-raised-2 shadow-2xl">
          {matches.map((o, i) => (
            <li key={o.id} role="option" aria-selected={i === active}>
              <button type="button" onMouseEnter={() => setActive(i)} onClick={() => pick(o)}
                className={`flex min-h-11 w-full items-center gap-3 px-4 text-left ${i === active ? 'bg-raised' : ''}`}>
                <img src={`https://cdn.nba.com/headshots/nba/latest/260x190/${o.id}.png`} alt="" className="h-8 w-10 object-contain object-bottom" />
                <span className="flex-1 font-semibold">{o.name}</span>
                <span className="text-xs text-muted">{o.team}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
      {options && query.trim() && matches.length === 0 && <p className="mt-2 text-sm text-muted">No player matches “{query}”.</p>}
    </div>
  )
}

function Profile({ id }: { id: number }) {
  const [player, setPlayer] = useState<PlayerProfile | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => { api.player(id).then(setPlayer).catch((e: Error) => setError(e.message)) }, [id])
  if (error) return <div className="mt-5"><Empty title="Couldn't load that player" hint={error} /></div>
  if (!player) return <div className="mt-5 h-40 animate-pulse rounded-3xl bg-raised" />
  const a = player.averages
  return (
    <div className="mt-5">
      <div className="rise relative overflow-hidden rounded-3xl border border-line"
        style={{ background: `linear-gradient(110deg, color-mix(in srgb, ${player.color} 30%, #000), #0b0c0e 70%)` }}>
        <img src={player.logo} alt="" className="absolute -right-6 -top-6 size-40 opacity-10" />
        <div className="relative flex items-end gap-4 px-5 pt-5">
          <img src={player.photo} alt="" className="h-28 w-36 shrink-0 object-contain object-bottom sm:h-36 sm:w-48" />
          <div className="pb-5">
            <div className="text-2xl font-black leading-tight sm:text-3xl">{player.name}</div>
            <div className="mt-1 flex items-center gap-1.5 text-sm text-muted">
              <img src={player.logo} alt="" className="size-5" /> {player.team} · {player.season} · {player.season_games} games
            </div>
          </div>
        </div>
      </div>
      <div className="mt-3">
        <StatStrip items={[
          { value: a.pts?.toFixed(1), label: 'points' }, { value: a.reb?.toFixed(1), label: 'rebounds' },
          { value: a.ast?.toFixed(1), label: 'assists' }, { value: a.fg3m?.toFixed(1), label: '3-pointers' },
        ]} />
      </div>
      {player.tonight && (
        <div className="mt-3 rounded-2xl border border-line bg-raised p-4 text-sm">
          <div className="font-bold">On the slate: {player.tonight.game}</div>
          <div className="mt-1 text-muted">
            Points line <b className="text-text">{player.tonight.line}</b> (over {american(player.tonight.over)}, under {american(player.tonight.under)}).
            Projected: {player.tonight.projections.map((p) => `${p.model} ${p.mean}`).join(' · ')}
          </div>
        </div>
      )}
      <HitRate player={player} />
      <Recent games={player.games} />
    </div>
  )
}

function HitRate({ player }: { player: PlayerProfile }) {
  const season = player.games.filter((g) => g.season === player.season)
  // a line near the season average to start with, for whichever stat is picked
  const nearAverage = (which: Stat) =>
    Math.floor(season.length ? season.reduce((s, g) => s + g[which], 0) / season.length : 0) + 0.5
  const [stat, setStat] = useState<Stat>('pts')
  const [line, setLine] = useState(() => nearAverage('pts'))
  const chooseStat = (which: Stat) => { setStat(which); setLine(nearAverage(which)) }

  const rate = (games: PlayerGame[]) => ({ over: games.filter((g) => g[stat] > line).length, games: games.length })
  const last10 = rate(player.games.slice(0, 10))
  const year = rate(season)
  const pct = (r: { over: number; games: number }) => (r.games ? Math.round((r.over / r.games) * 100) : 0)
  const chart = player.games.slice(0, CHART_GAMES).reverse()
  const top = Math.max(line + 2, ...chart.map((g) => g[stat]))
  const label = STATS.find((s) => s.id === stat)!.label.toLowerCase()

  return (
    <Section title="How often have they cleared it?">
      <Pills value={stat} onChange={chooseStat} options={STATS.map((s) => ({ id: s.id, label: s.label }))} />
      <div className="mt-4 flex flex-wrap items-center gap-3">
        <button type="button" aria-label="Lower the line" onClick={() => setLine(Math.max(0.5, line - 1))}
          className="grid size-11 place-items-center rounded-full border border-line text-xl font-bold hover:border-line-strong">−</button>
        <div className="min-w-24 text-center">
          <div className="text-3xl font-black tabular-nums">{line}</div>
          <div className="text-[11px] uppercase tracking-wider text-muted">{label} line</div>
        </div>
        <button type="button" aria-label="Raise the line" onClick={() => setLine(line + 1)}
          className="grid size-11 place-items-center rounded-full border border-line text-xl font-bold hover:border-line-strong">+</button>
        <div className="grid w-full grid-cols-2 gap-4 sm:ml-auto sm:w-auto sm:text-right">
          <div><div className="text-2xl font-black">{pct(last10)}%</div><div className="text-[11px] text-muted">{last10.over} of last {last10.games}</div></div>
          <div><div className="text-2xl font-black">{pct(year)}%</div><div className="text-[11px] text-muted">{year.over} of {year.games} this season</div></div>
        </div>
      </div>
      <div className="mt-4 rounded-2xl border border-line bg-raised p-3">
        <div className="relative flex h-44 items-end gap-1 pl-7">
          <div className="pointer-events-none absolute inset-x-0 border-t-2 border-dashed border-warn" style={{ bottom: `${(line / top) * 100}%` }}>
            <span className="absolute -top-2.5 left-0 rounded bg-ink px-1 text-[10px] font-bold text-warn">{line}</span>
          </div>
          {chart.map((g) => {
            const over = g[stat] > line
            return (
              <div key={g.date} className="flex h-full flex-1 flex-col justify-end" title={`${g.date} ${g.home ? 'vs' : '@'} ${g.opponent}: ${g[stat]}`}>
                <div className="text-center text-[10px] font-bold tabular-nums">{g[stat]}</div>
                <div className={`rounded-t transition-all duration-500 ${over ? 'bg-text' : 'bg-line-strong/60'}`} style={{ height: `${(g[stat] / top) * 100}%`, minHeight: 2 }} />
              </div>
            )
          })}
        </div>
        <div className="mt-1 flex gap-1 pl-7">
          {chart.map((g) => <div key={g.date} className="flex-1 truncate text-center text-[9px] text-muted">{g.home ? '' : '@'}{g.opponent}</div>)}
        </div>
      </div>
      <p className="mt-2 text-xs text-muted">Last {chart.length} games, oldest on the left. White bars cleared the line. Past games don't guarantee anything.</p>
    </Section>
  )
}

function Recent({ games }: { games: PlayerGame[] }) {
  return (
    <Section title="Recent games">
      <div className="overflow-x-auto rounded-2xl border border-line bg-raised">
        <table className="w-full text-sm tabular-nums">
          <thead><tr className="text-xs text-muted">
            {['Date', 'Opponent', '', 'Min', 'Pts', 'Reb', 'Ast', '3PM'].map((h, i) => (
              <th key={h || i} className={`px-3 py-2 font-semibold ${i < 3 ? 'text-left' : 'text-right'}`}>{h}</th>
            ))}
          </tr></thead>
          <tbody>
            {games.slice(0, 10).map((g) => (
              <tr key={g.date} className="border-t border-line">
                <td className="whitespace-nowrap px-3 py-2">{new Date(`${g.date}T12:00:00`).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}</td>
                <td className="whitespace-nowrap px-3 py-2">{g.home ? 'vs' : '@'} {g.opponent}</td>
                <td className={`px-3 py-2 font-bold ${g.result === 'W' ? 'text-good' : 'text-bad'}`}>{g.result}</td>
                <td className="px-3 py-2 text-right">{g.minutes}</td>
                <td className="px-3 py-2 text-right font-black">{g.pts}</td>
                <td className="px-3 py-2 text-right">{g.reb}</td>
                <td className="px-3 py-2 text-right">{g.ast}</td>
                <td className="px-3 py-2 text-right">{g.fg3m}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Section>
  )
}
