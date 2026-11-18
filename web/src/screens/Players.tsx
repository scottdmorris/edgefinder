// Players: search any player or team. A player shows how they're playing and how often they've
// cleared a number (worked out here from the games the API sends, so moving the line answers
// instantly); a team shows its record, ranks, who's out and the roster (TeamProfile).
import { useEffect, useId, useMemo, useRef, useState } from 'react'
import { api, type PlayerGame, type PlayerOption, type PlayerProfile, type TeamOption } from '../lib/api'
import { american } from '../lib/ladder'
import { Empty, Section, StatStrip } from '../components/ui'
import { chosenFromHash, findMatches, type Chosen, type Match } from '../lib/search'
import { TeamProfile } from './TeamProfile'

const STATS = [
  { id: 'pts', label: 'Points' }, { id: 'reb', label: 'Rebounds' },
  { id: 'ast', label: 'Assists' }, { id: 'fg3m', label: '3-pointers' },
] as const
type Stat = (typeof STATS)[number]['id']
const CHART_GAMES = 15

// Each catalog can fail and recover without hiding the other catalog or the profile.
function useCatalog<T>(load: () => Promise<T[]>) {
  const [data, setData] = useState<T[] | null>(null)
  const [error, setError] = useState(false)
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    let current = true
    load().then((next) => { if (current) setData(next) })
      .catch(() => { if (current) setError(true) })
    return () => { current = false }
  }, [load, attempt])
  return { data, error, retry: () => { setError(false); setAttempt((n) => n + 1) } }
}

export function Players() {
  const players = useCatalog(api.players)
  const teams = useCatalog(api.teams)
  const [chosen, setChosen] = useState<Chosen | null>(() => chosenFromHash(window.location.hash))
  useEffect(() => {
    const sync = () => setChosen(chosenFromHash(window.location.hash))
    window.addEventListener('hashchange', sync)
    return () => window.removeEventListener('hashchange', sync)
  }, [])

  const choose = (next: Chosen) => {
    setChosen(next)
    window.scrollTo({ top: 0 })
    window.location.hash = next.kind === 'team' ? `/players?team=${next.code}` : `/players?id=${next.id}`
  }

  return (
    <div>
      <h1 className="text-3xl font-black tracking-tight">Players & teams</h1>
      {[{ name: 'players', catalog: players }, { name: 'teams', catalog: teams }].map(({ name, catalog }) => catalog.error && (
        <div key={name} role="alert" className="mt-3 rounded-2xl border border-warn/40 p-3 text-sm">
          Couldn't load {name}. Other available results are still searchable.{' '}
          <button type="button" onClick={catalog.retry} className="min-h-11 px-2 font-bold underline">Retry {name}</button>
        </div>
      ))}
      <Search options={players.data} teams={teams.data ?? []} complete={players.data !== null && teams.data !== null && !players.error && !teams.error} onChoose={choose} />
      {chosen?.kind === 'player' && <Profile key={chosen.id} id={chosen.id} onTeam={(code) => choose({ kind: 'team', code })} />}
      {chosen?.kind === 'team' && <TeamProfile key={chosen.code} code={chosen.code} onPlayer={(id) => choose({ kind: 'player', id })} />}
      {!chosen && (
        <p className="mt-4 text-sm text-muted">Search any player for their averages, recent games and how often they've cleared a number, or any team for its record, ranks, who's out and how teammates do without them.</p>
      )}
    </div>
  )
}

interface SearchProps {
  options: PlayerOption[] | null
  teams: TeamOption[]
  complete: boolean
  onChoose: (chosen: Chosen) => void
}

function Search({ options, teams, complete, onChoose }: SearchProps) {
  const [query, setQuery] = useState('')
  const [active, setActive] = useState(0)
  const listId = useId()
  const box = useRef<HTMLInputElement>(null)
  const matches = useMemo(() => findMatches(query, options ?? [], teams), [query, options, teams])

  const activeIndex = Math.min(active, Math.max(0, matches.length - 1))
  useEffect(() => {
    if (matches.length) document.getElementById(`${listId}-${activeIndex}`)?.scrollIntoView?.({ block: 'nearest' })
  }, [listId, activeIndex, matches.length])
  const pick = (m: Match) => {
    onChoose(m.kind === 'team' ? { kind: 'team', code: m.option.code } : { kind: 'player', id: m.option.id })
    setQuery('')
    box.current?.blur()
  }
  return (
    <div className="relative mt-4">
      <input ref={box} type="search" value={query} placeholder="Search any player or team…"
        aria-label="Search players and teams" role="combobox" aria-expanded={matches.length > 0} aria-controls={matches.length ? listId : undefined} aria-autocomplete="list"
        aria-activedescendant={matches.length ? `${listId}-${activeIndex}` : undefined}
        onChange={(e) => { setQuery(e.target.value); setActive(0) }}
        onKeyDown={(e) => {
          if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
            e.preventDefault()
            if (matches.length) setActive((activeIndex + (e.key === 'ArrowDown' ? 1 : -1) + matches.length) % matches.length)
          }
          if (e.key === 'Home' && matches.length) { e.preventDefault(); setActive(0) }
          if (e.key === 'End' && matches.length) { e.preventDefault(); setActive(matches.length - 1) }
          if (e.key === 'Enter' && matches[activeIndex]) { e.preventDefault(); pick(matches[activeIndex]) }
          if (e.key === 'Escape' || e.key === 'Tab') setQuery('')
        }}
        className="min-h-12 w-full rounded-full border border-line bg-raised px-5 font-semibold outline-none placeholder:text-muted focus:border-line-strong" />
      {matches.length > 0 && (
        <ul id={listId} role="listbox" aria-label="Players and teams" className="absolute inset-x-0 top-14 z-30 max-h-[45dvh] overflow-y-auto rounded-2xl border border-line bg-raised-2 shadow-2xl">
          {matches.map((m, i) => (
            <li key={m.kind === 'team' ? `team-${m.option.code}` : m.option.id} id={`${listId}-${i}`} role="option" aria-selected={i === activeIndex}>
              <button type="button" tabIndex={-1} onMouseDown={(e) => e.preventDefault()} onMouseEnter={() => setActive(i)} onClick={() => pick(m)}
                className={`flex min-h-11 w-full items-center gap-3 px-4 text-left ${i === activeIndex ? 'bg-raised' : ''}`}>
                {m.kind === 'team' ? (
                  <img src={m.option.logo} alt="" className="h-8 w-10 object-contain" />
                ) : (
                  <img src={`https://cdn.nba.com/headshots/nba/latest/260x190/${m.option.id}.png`} alt="" className="h-8 w-10 object-contain object-bottom" />
                )}
                <span className="flex-1 font-semibold">{m.option.name}</span>
                <span className="text-xs text-muted">{m.kind === 'team' ? 'Team' : m.option.team}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
      {complete && query.trim() && matches.length === 0 && <p className="mt-2 text-sm text-muted">Nothing matches “{query}”.</p>}
    </div>
  )
}

function Profile({ id, onTeam }: { id: number; onTeam: (code: string) => void }) {
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
        <div className="relative flex items-end gap-2 px-3 pt-3 sm:gap-4 sm:px-5 sm:pt-5">
          <img src={player.photo} alt="" className="h-20 w-20 shrink-0 object-contain object-bottom sm:h-36 sm:w-48" />
          <div className="min-w-0 flex-1 pb-3 sm:pb-5">
            <div className="break-words text-2xl font-black leading-tight sm:text-3xl">{player.name}</div>
            <div className="mt-1 flex flex-wrap items-center gap-x-1.5 gap-y-1 text-sm text-muted">
              <img src={player.logo} alt="" className="size-5" />
              <button type="button" onClick={() => onTeam(player.team)} className="font-semibold text-text hover:underline">{player.team}</button>
              <span>{player.season}</span><span>· {player.season_games} games</span>
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
  const [selectedDate, setSelectedDate] = useState<string | null>(null)
  const detailId = useId()
  const [line, setLine] = useState(() => nearAverage('pts'))
  const chooseStat = (which: Stat) => { setStat(which); setLine(nearAverage(which)) }

  const rate = (games: PlayerGame[]) => ({ over: games.filter((g) => g[stat] > line).length, games: games.length })
  const last10 = rate(player.games.slice(0, 10))
  const year = rate(season)
  const pct = (r: { over: number; games: number }) => (r.games ? Math.round((r.over / r.games) * 100) : 0)
  const chart = player.games.slice(0, CHART_GAMES).reverse()
  const top = Math.max(line + 2, ...chart.map((g) => g[stat]))
  const label = STATS.find((s) => s.id === stat)!.label.toLowerCase()

  const selected = chart.find((g) => g.date === selectedDate) ?? chart.at(-1)
  const describe = (g: PlayerGame) => `${g.date} ${g.home ? 'vs' : '@'} ${g.opponent}: ${g[stat]} ${label}; line ${line}; ${g[stat] > line ? 'cleared' : 'did not clear'}`

  return (
    <Section title="How often have they cleared it?">
      <div role="radiogroup" aria-label="Player statistic" className="flex flex-wrap gap-1.5">
        {STATS.map((s, i) => (
          <button key={s.id} type="button" role="radio" aria-checked={stat === s.id} tabIndex={stat === s.id ? 0 : -1}
            onClick={() => chooseStat(s.id)}
            onKeyDown={(e) => {
              let next = i
              if (e.key === 'ArrowRight' || e.key === 'ArrowDown') next = (i + 1) % STATS.length
              else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') next = (i + STATS.length - 1) % STATS.length
              else if (e.key === 'Home') next = 0
              else if (e.key === 'End') next = STATS.length - 1
              else return
              e.preventDefault()
              chooseStat(STATS[next].id)
              ;(e.currentTarget.parentElement?.children[next] as HTMLButtonElement | undefined)?.focus()
            }}
            className={`min-h-10 rounded-full border px-4 text-sm font-semibold ${stat === s.id ? 'border-button bg-button text-button-text' : 'border-line text-text'}`}>
            {s.label}
          </button>
        ))}
      </div>
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
              <button key={g.date} type="button" aria-label={describe(g)} aria-describedby={detailId}
                onClick={() => setSelectedDate(g.date)} onFocus={() => setSelectedDate(g.date)}
                className="flex h-full min-w-0 flex-1 flex-col justify-end rounded focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-text">
                <div className="w-full text-center text-[10px] font-bold tabular-nums">{g[stat]}</div>
                <div className={`w-full rounded-t transition-all duration-500 ${over ? 'bg-text' : 'bg-line-strong/60'}`} style={{ height: `${(g[stat] / top) * 100}%`, minHeight: 2 }} />
              </button>
            )
          })}
        </div>
        <div className="mt-1 flex gap-1 pl-7">
          {chart.map((g) => <div key={g.date} className="flex-1 truncate text-center text-[9px] text-muted">{g.home ? '' : '@'}{g.opponent}</div>)}
        </div>
      </div>
      <p id={detailId} role="status" className="mt-3 text-sm">{selected ? describe(selected) : 'No recent games available.'}</p>
      <details className="mt-3">
        <summary className="cursor-pointer py-2 font-semibold">View all chart data</summary>
        <div role="region" aria-label="Player chart data" tabIndex={0} className="overflow-x-auto rounded border border-line focus-visible:outline-2">
          <table className="w-full text-left text-sm tabular-nums">
            <caption className="py-2">Last {chart.length} games · {label} · line {line}</caption>
            <thead><tr>{['Date', 'Opponent', 'Value', 'Line', 'Cleared'].map((h) => <th key={h} scope="col" className="px-3 py-2">{h}</th>)}</tr></thead>
            <tbody>{chart.map((g) => <tr key={g.date}>
              <td className="whitespace-nowrap px-3 py-2">{g.date}</td><td className="whitespace-nowrap px-3 py-2">{g.home ? 'vs' : '@'} {g.opponent}</td>
              <td className="px-3 py-2">{g[stat]}</td><td className="px-3 py-2">{line}</td><td className="px-3 py-2">{g[stat] > line ? 'Yes' : 'No'}</td>
            </tr>)}</tbody>
          </table>
        </div>
      </details>
      <p className="mt-2 text-xs text-muted">Last {chart.length} games, oldest on the left. White bars cleared the line. Past games don't guarantee anything.</p>
    </Section>
  )
}

function Recent({ games }: { games: PlayerGame[] }) {
  return (
    <Section title="Recent games">
      <div role="region" aria-label="Recent player games" tabIndex={0} className="overflow-x-auto rounded-2xl border border-line bg-raised focus-visible:outline-2">
        <table aria-label="Recent player games" className="w-full text-sm tabular-nums">
          <thead><tr className="text-xs text-muted">
            {['Date', 'Opponent', 'Result', 'Min', 'Pts', 'Reb', 'Ast', '3PM'].map((h, i) => (
              <th key={h} scope="col" className={`px-3 py-2 font-semibold ${i < 3 ? 'text-left' : 'text-right'}`}>{h}</th>
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
