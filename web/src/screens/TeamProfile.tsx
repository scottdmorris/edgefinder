// A team on the Players screen: record, where it ranks, tonight's lines, who is out and what
// his teammates did without him, the roster and recent results.
import { useEffect, useState } from 'react'
import { api, type TeamProfile as Team, type TeammateSplit } from '../lib/api'
import { american } from '../lib/ladder'
import { Empty, Section, StatStrip } from '../components/ui'

interface TeamProfileProps {
  code: string
  onPlayer: (id: number) => void
}

export function TeamProfile({ code, onPlayer }: TeamProfileProps) {
  const [team, setTeam] = useState<Team | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => { api.team(code).then(setTeam).catch((e: Error) => setError(e.message)) }, [code])
  if (error) return <div className="mt-5"><Empty title="Couldn't load that team" hint={error} /></div>
  if (!team) return <div className="mt-5 h-40 animate-pulse rounded-3xl bg-raised" />
  return <TeamView team={team} onPlayer={onPlayer} />
}

/** "3rd of 30" */
const ordinal = (n: number) => {
  const tail = n % 100 >= 11 && n % 100 <= 13 ? 'th' : ({ 1: 'st', 2: 'nd', 3: 'rd' } as Record<number, string>)[n % 10] ?? 'th'
  return `${n}${tail}`
}

export function TeamView({ team, onPlayer }: { team: Team; onPlayer: (id: number) => void }) {
  const r = team.record
  return (
    <div className="mt-5">
      <div className="rise relative overflow-hidden rounded-3xl border border-line px-5 py-5"
        style={{ background: `linear-gradient(110deg, color-mix(in srgb, ${team.color} 30%, #000), #0b0c0e 70%)` }}>
        <img src={team.logo} alt="" className="absolute -right-6 -top-6 size-40 opacity-10" />
        <div className="relative flex items-center gap-4">
          <img src={team.logo} alt="" className="size-16 shrink-0" />
          <div>
            <div className="text-2xl font-black leading-tight sm:text-3xl">{team.name}</div>
            <div className="mt-1 text-sm text-muted">
              {team.season} · {r.wins}-{r.losses} · home {r.home} · away {r.away} · last 10 {r.last10}{r.streak && ` · ${r.streak}`}
            </div>
          </div>
        </div>
      </div>
      <Ranks team={team} />
      <Tonight team={team} onPlayer={onPlayer} />
      <Absences team={team} onPlayer={onPlayer} />
      <Roster team={team} onPlayer={onPlayer} />
      <Results team={team} />
    </div>
  )
}

function Ranks({ team }: { team: Team }) {
  const g = team.ratings
  const of = team.teams_in_league
  return (
    <div className="mt-3">
      <StatStrip items={[
        { value: g.ppg?.toFixed(1), label: `points · ${ordinal(g.ppg_rank)}` },
        { value: g.opp_ppg?.toFixed(1), label: `allowed · ${ordinal(g.opp_ppg_rank)}` },
        { value: ordinal(g.ortg_rank), label: `offense of ${of}` },
        { value: ordinal(g.drtg_rank), label: `defense of ${of}` },
      ]} />
      <p className="mt-2 text-xs text-muted">
        Offense and defense rank points per possession, which strips out how fast a team plays.
        Pace: {ordinal(g.pace_rank)} fastest. Net {g.net > 0 ? '+' : ''}{g.net?.toFixed(1)} per 100 possessions ({ordinal(g.net_rank)}).
        Possessions are estimated from box scores.
      </p>
    </div>
  )
}

function Tonight({ team, onPlayer }: { team: Team; onPlayer: (id: number) => void }) {
  if (!team.tonight.length) return null
  return (
    <Section title="On the latest slate" aside={team.tonight[0].game}>
      <div className="overflow-hidden rounded-2xl border border-line bg-raised">
        {team.tonight.map((p) => (
          <button key={p.id} type="button" onClick={() => onPlayer(p.id)}
            className="flex min-h-11 w-full items-center gap-3 border-t border-line px-4 py-2 text-left text-sm first:border-t-0 hover:bg-raised-2">
            <span className="flex-1 font-semibold">{p.name}</span>
            <span className="tabular-nums">points <b>{p.line}</b> <span className="text-muted">o {american(p.over)} · u {american(p.under)}</span></span>
            {p.projection != null && <span className="w-24 text-right tabular-nums text-muted">projects {p.projection}</span>}
          </button>
        ))}
      </div>
    </Section>
  )
}

function Split({ row, onPlayer }: { row: TeammateSplit; onPlayer: (id: number) => void }) {
  const change = row.pts_without - row.pts_with
  return (
    <button type="button" onClick={() => onPlayer(row.id)}
      className="flex min-h-11 w-full items-center gap-3 border-t border-line px-4 py-2 text-left text-sm first:border-t-0 hover:bg-raised-2">
      <img src={row.photo} alt="" className="h-8 w-10 object-contain object-bottom" />
      <span className="flex-1 font-semibold">{row.name}</span>
      <span className="tabular-nums text-muted">{row.pts_with} → <b className="text-text">{row.pts_without}</b> pts</span>
      <span className={`w-14 text-right font-bold tabular-nums ${change >= 0 ? 'text-good' : 'text-bad'}`}>{change >= 0 ? '+' : ''}{change.toFixed(1)}</span>
      <span className="hidden w-28 text-right text-xs text-muted sm:block">{row.min_with} → {row.min_without} min</span>
    </button>
  )
}

function Absences({ team, onPlayer }: { team: Team; onPlayer: (id: number) => void }) {
  const others = team.injuries.filter((i) => !team.absences.some((a) => a.name === i.name))
  return (
    <Section title="Who's out" aside={team.injury_report ? 'ESPN injury report' : 'Injury report unavailable'}>
      {!team.injury_report && <p className="text-sm text-muted">The injury report couldn't be read right now.</p>}
      {team.injury_report && !team.injuries.length && <p className="text-sm text-muted">Nobody listed.</p>}
      {team.absences.map((a) => (
        <div key={a.id} className="mb-3">
          <div className="text-sm"><b>{a.name}</b> <span className="font-bold text-bad">{a.status}</span>{a.detail && <span className="text-muted"> · {a.detail}</span>}</div>
          {a.teammates.length ? (
            <div className="mt-2 overflow-hidden rounded-2xl border border-line bg-raised">
              <div className="px-4 py-2 text-xs text-muted">Teammates' points with him ({a.with_games} games) → without him ({a.without_games} games)</div>
              {a.teammates.map((t) => <Split key={t.id} row={t} onPlayer={onPlayer} />)}
            </div>
          ) : <p className="mt-1 text-xs text-muted">Not enough games without him this season to compare.</p>}
        </div>
      ))}
      {others.length > 0 && (
        <p className="text-sm text-muted">{others.map((i) => `${i.name} (${i.status.toLowerCase()})`).join(' · ')}</p>
      )}
    </Section>
  )
}

function Roster({ team, onPlayer }: { team: Team; onPlayer: (id: number) => void }) {
  return (
    <Section title="Roster" aside="per game this season">
      <div className="overflow-x-auto rounded-2xl border border-line bg-raised">
        <table className="w-full text-sm tabular-nums">
          <thead><tr className="text-xs text-muted">
            {['Player', 'G', 'Min', 'Pts', 'Reb', 'Ast', '3PM'].map((h, i) => (
              <th key={h} className={`px-3 py-2 font-semibold ${i === 0 ? 'text-left' : 'text-right'}`}>{h}</th>
            ))}
          </tr></thead>
          <tbody>
            {team.roster.map((p) => (
              <tr key={p.id} className="border-t border-line">
                <td className="px-3 py-2"><button type="button" onClick={() => onPlayer(p.id)} className="font-semibold hover:underline">{p.name}</button></td>
                <td className="px-3 py-2 text-right">{p.games}</td>
                <td className="px-3 py-2 text-right">{p.minutes}</td>
                <td className="px-3 py-2 text-right font-black">{p.pts}</td>
                <td className="px-3 py-2 text-right">{p.reb}</td>
                <td className="px-3 py-2 text-right">{p.ast}</td>
                <td className="px-3 py-2 text-right">{p.fg3m}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Section>
  )
}

function Results({ team }: { team: Team }) {
  return (
    <Section title="Recent results">
      <div className="overflow-hidden rounded-2xl border border-line bg-raised">
        {team.results.map((g) => (
          <div key={g.date} className="flex min-h-10 items-center gap-3 border-t border-line px-4 text-sm first:border-t-0">
            <span className="w-16 text-muted">{new Date(`${g.date}T12:00:00`).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}</span>
            <span className="flex-1">{g.home ? 'vs' : '@'} {g.opponent}</span>
            <span className={`font-bold ${g.result === 'W' ? 'text-good' : 'text-bad'}`}>{g.result}</span>
            <span className="w-20 text-right tabular-nums">{g.score}</span>
          </div>
        ))}
      </div>
    </Section>
  )
}
