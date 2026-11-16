// A team on the Players screen. Built for someone about to bet a prop: tonight's matchup and
// lines first, then what the team gives up, its form, who's out (and what teammates did without
// them), and the roster. Sections live in TeamSections.
import { useEffect, useState } from 'react'
import { api, type MatchupSide, type PropStat, type TeamProfile as Team } from '../lib/api'
import { Empty, Section } from '../components/ui'
import { ordinal, STAT_LABELS } from '../lib/teamFormat'
import { Absences, Allowed, Form, Roster, Tonight } from './TeamSections'

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

export function TeamView({ team, onPlayer }: { team: Team; onPlayer: (id: number) => void }) {
  return (
    <div className="mt-5">
      <Header team={team} />
      <Matchup team={team} />
      <Tonight team={team} onPlayer={onPlayer} />
      <Allowed team={team} />
      <Absences team={team} onPlayer={onPlayer} />
      <Form team={team} />
      <Roster team={team} onPlayer={onPlayer} />
      <details className="mt-6 rounded-2xl border border-line bg-raised px-4 py-3">
        <summary className="min-h-8 cursor-pointer text-sm font-bold">Full team rankings</summary>
        <Ranks team={team} />
      </details>
    </div>
  )
}

function Chip({ label, value, tone }: { label: string; value: string; tone?: 'good' | 'bad' }) {
  const color = tone === 'good' ? 'text-good' : tone === 'bad' ? 'text-bad' : 'text-text'
  return (
    <span className="rounded-full border border-line bg-ink/40 px-3 py-1 text-xs">
      <span className="text-muted">{label} </span><b className={color}>{value}</b>
    </span>
  )
}

function Header({ team }: { team: Team }) {
  const r = team.record
  return (
    <div className="rise relative overflow-hidden rounded-3xl border border-line px-5 py-5"
      style={{ background: `linear-gradient(110deg, color-mix(in srgb, ${team.color} 30%, #0D1B2B), #111C2C 78%)` }}>
      <img src={team.logo} alt="" className="absolute -right-8 -top-8 size-48 opacity-10" />
      <div className="relative flex items-center gap-4">
        <img src={team.logo} alt="" className="size-16 shrink-0 sm:size-20" />
        <div className="min-w-0">
          <div className="text-2xl font-black leading-tight sm:text-3xl">{team.name}</div>
          <div className="mt-0.5 text-sm text-muted">{team.season}</div>
        </div>
        <div className="ml-auto text-right">
          <div className="text-3xl font-black tabular-nums sm:text-4xl">{r.wins}-{r.losses}</div>
          <div className="text-[11px] uppercase tracking-wider text-muted">record</div>
        </div>
      </div>
      <div className="relative mt-4 flex flex-wrap gap-2">
        <Chip label="Home" value={r.home} />
        <Chip label="Away" value={r.away} />
        <Chip label="Last 10" value={r.last10} />
        {r.streak && <Chip label="Streak" value={r.streak} tone={r.streak.startsWith('W') ? 'good' : 'bad'} />}
      </div>
    </div>
  )
}

/** A rank as a 0-1 bar where 1st is full. */
const strength = (rank: number, of: number) => Math.max(0.06, 1 - (rank - 1) / Math.max(of - 1, 1))

function RankBar({ label, rank, of, detail }: { label: string; rank: number; of: number; detail?: string }) {
  return (
    <div className="rounded-2xl border border-line bg-raised px-4 py-3">
      <div className="flex items-baseline justify-between gap-2">
        <div className="text-[11px] font-semibold uppercase tracking-wider text-muted">{label}</div>
        <div className="text-lg font-black tabular-nums">{ordinal(rank)}</div>
      </div>
      <div className="mt-2 h-1.5 rounded-full bg-line">
        <div className="h-full rounded-full bg-text" style={{ width: `${strength(rank, of) * 100}%` }} />
      </div>
      {detail && <div className="mt-1.5 text-xs text-muted">{detail}</div>}
    </div>
  )
}

function Ranks({ team }: { team: Team }) {
  const g = team.ratings
  const of = team.teams_in_league
  return (
    <>
      <div className="mt-3 grid grid-cols-2 gap-2.5 sm:grid-cols-4">
        <RankBar label="Scoring" rank={g.ppg_rank} of={of} detail={`${g.ppg?.toFixed(1)} a game`} />
        <RankBar label="Points allowed" rank={g.opp_ppg_rank} of={of} detail={`${g.opp_ppg?.toFixed(1)} a game`} />
        <RankBar label="Offense" rank={g.ortg_rank} of={of} detail="per possession" />
        <RankBar label="Defense" rank={g.drtg_rank} of={of} detail="per possession" />
      </div>
      <p className="mt-2 text-xs text-muted">
        Ranks out of {of}; 1st is best. Pace {ordinal(g.pace_rank)} fastest. Net {g.net > 0 ? '+' : ''}{g.net?.toFixed(1)} per
        100 possessions ({ordinal(g.net_rank)}). Possessions are estimated from box scores.
      </p>
    </>
  )
}

const tipTime = (iso: string) =>
  new Date(iso).toLocaleString('en-US', { weekday: 'short', hour: 'numeric', minute: '2-digit', timeZone: 'America/New_York' }) + ' ET'

const ROWS: { label: string; pick: (s: MatchupSide) => string; better: (s: MatchupSide) => number }[] = [
  { label: 'Record', pick: (s) => s.record, better: (s) => -s.net_rank },
  { label: 'Points a game', pick: (s) => s.ppg.toFixed(1), better: (s) => s.ppg },
  { label: 'Allowed a game', pick: (s) => s.opp_ppg.toFixed(1), better: (s) => -s.opp_ppg },
  { label: 'Offense', pick: (s) => ordinal(s.ortg_rank), better: (s) => -s.ortg_rank },
  { label: 'Defense', pick: (s) => ordinal(s.drtg_rank), better: (s) => -s.drtg_rank },
  { label: 'Pace', pick: (s) => ordinal(s.pace_rank), better: () => 0 },
]

function Matchup({ team }: { team: Team }) {
  const sides = team.matchup?.sides
  const next = team.next_game
  if (!sides || sides.length < 2 || !next) return null
  const [mine, theirs] = sides
  const stats = Object.keys(STAT_LABELS) as PropStat[]
  return (
    <Section title={`Next: ${next.home ? 'vs' : '@'} ${theirs.name}`} aside={tipTime(next.tip)}>
      <div className="overflow-hidden rounded-2xl border border-line bg-raised">
        <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-2 border-b border-line px-4 py-3">
          <div className="flex items-center gap-2"><img src={mine.logo} alt="" className="size-8" /><b>{mine.code}</b></div>
          <div className="text-xs text-muted">{next.home ? 'home' : 'away'}</div>
          <div className="flex items-center justify-end gap-2"><b>{theirs.code}</b><img src={theirs.logo} alt="" className="size-8" /></div>
        </div>
        {ROWS.map((row) => {
          const a = row.better(mine), b = row.better(theirs)
          return (
            <div key={row.label} className="grid grid-cols-[1fr_auto_1fr] items-center gap-2 border-t border-line px-4 py-2 text-sm tabular-nums first:border-t-0">
              <span className={a > b ? 'font-black' : 'text-muted'}>{row.pick(mine)}</span>
              <span className="text-center text-xs text-muted">{row.label}</span>
              <span className={`text-right ${b > a ? 'font-black' : 'text-muted'}`}>{row.pick(theirs)}</span>
            </div>
          )
        })}
      </div>
      <p className="mt-2 text-xs text-muted">
        {theirs.code} gives up {stats.map((s) => `${theirs.allowed[s].value} ${STAT_LABELS[s].toLowerCase()} (${ordinal(theirs.allowed[s].rank)} most)`).join(' · ')} a game.
      </p>
    </Section>
  )
}
