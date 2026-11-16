// The lower sections of a team page: tonight's lines, what the team allows, recent form,
// who's out, and the roster.
import type { PropStat, TeamProfile as Team, TeammateSplit } from '../lib/api'
import { american } from '../lib/ladder'
import { ordinal, STAT_LABELS } from '../lib/teamFormat'
import { Section } from '../components/ui'

const SOFT_RANKS = 10           // in the top third for what a defense gives up: a friendly matchup

type OnPlayer = (id: number) => void

export function Tonight({ team, onPlayer }: { team: Team; onPlayer: OnPlayer }) {
  if (!team.tonight.length) return null
  return (
    <Section title="Points lines on the slate" aside="FanDuel · projection from Shot profile">
      <div className="overflow-x-auto rounded-2xl border border-line bg-raised">
        <table className="w-full text-sm tabular-nums">
          <thead><tr className="text-xs text-muted">
            {['Player', 'Line', 'Odds (o/u)', 'Projects', 'vs line', 'Last 10'].map((h, i) => (
              <th key={h} className={`px-3 py-2 font-semibold ${i === 0 ? 'text-left' : 'text-right'}`}>{h}</th>
            ))}
          </tr></thead>
          <tbody>
            {team.tonight.map((p) => (
              <tr key={p.id} className="border-t border-line">
                <td className="px-3 py-2"><button type="button" onClick={() => onPlayer(p.id)} className="font-semibold hover:underline">{p.name}</button></td>
                <td className="px-3 py-2 text-right font-black">{p.line}</td>
                <td className="whitespace-nowrap px-3 py-2 text-right text-muted">{american(p.over)} / {american(p.under)}</td>
                <td className="px-3 py-2 text-right">{p.projection ?? '–'}</td>
                <td className={`px-3 py-2 text-right font-bold ${p.edge == null ? 'text-muted' : p.edge > 0 ? 'text-good' : 'text-bad'}`}>
                  {p.edge == null ? '–' : `${p.edge > 0 ? '+' : ''}${p.edge}`}
                </td>
                <td className="px-3 py-2">
                  <div className="ml-auto flex w-24 items-center justify-end gap-2">
                    <div className="h-1.5 flex-1 rounded-full bg-line">
                      <div className="h-full rounded-full bg-text" style={{ width: `${p.games ? (p.cleared / p.games) * 100 : 0}%` }} />
                    </div>
                    <span className="w-9 text-right text-xs">{p.cleared}/{p.games}</span>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-2 text-xs text-muted">"vs line" is the projection minus the line. Last 10 is how many of his last 10 games went over it. Neither is a pick on its own.</p>
    </Section>
  )
}

export function Allowed({ team }: { team: Team }) {
  const of = team.teams_in_league
  const tougher = of - SOFT_RANKS + 1
  return (
    <Section title="What opponents put up against them" aside="per game, all opposing players">
      <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-4">
        {(Object.keys(STAT_LABELS) as PropStat[]).map((stat) => {
          const { value, rank } = team.allowed[stat]
          const tone = rank <= SOFT_RANKS ? 'text-good' : rank >= tougher ? 'text-bad' : 'text-muted'
          const word = rank <= SOFT_RANKS ? 'soft' : rank >= tougher ? 'tough' : 'average'
          return (
            <div key={stat} className="rounded-2xl border border-line bg-raised px-4 py-3">
              <div className="text-2xl font-black tabular-nums">{value}</div>
              <div className="text-[11px] font-semibold uppercase tracking-wider text-muted">{STAT_LABELS[stat]} allowed</div>
              <div className={`mt-1 text-xs font-semibold ${tone}`}>{ordinal(rank)} most · {word}</div>
            </div>
          )
        })}
      </div>
      <p className="mt-2 text-xs text-muted">Soft means opposing players tend to clear their numbers against this team; tough means the opposite.</p>
    </Section>
  )
}

export function Form({ team }: { team: Team }) {
  const games = [...team.results].reverse()
  if (!games.length) return null
  const margins = games.map((g) => { const [a, b] = g.score.split('-').map(Number); return a - b })
  const top = Math.max(10, ...margins.map(Math.abs))
  return (
    <Section title="Form" aside={`last ${games.length} games, oldest first`}>
      <div className="rounded-2xl border border-line bg-raised p-3">
        <div className="flex h-36 items-stretch gap-1">
          {games.map((g, i) => {
            const m = margins[i]
            const height = `${(Math.abs(m) / top) * 50}%`
            return (
              <div key={g.date} className="relative flex flex-1 flex-col" title={`${g.date} ${g.home ? 'vs' : '@'} ${g.opponent}: ${g.result} ${g.score}`}>
                <div className="flex flex-1 flex-col justify-end">{m > 0 && <div className="rounded-t bg-good" style={{ height: '100%', maxHeight: height, minHeight: 2 }} />}</div>
                <div className="h-px bg-line-strong" />
                <div className="flex flex-1 flex-col justify-start">{m <= 0 && <div className="rounded-b bg-bad" style={{ height: '100%', maxHeight: height, minHeight: 2 }} />}</div>
              </div>
            )
          })}
        </div>
        <div className="mt-1 flex gap-1">
          {games.map((g, i) => (
            <div key={g.date} className="flex-1 truncate text-center text-[9px] leading-tight text-muted">
              {g.home ? '' : '@'}{g.opponent}<br /><span className={margins[i] > 0 ? 'text-good' : 'text-bad'}>{margins[i] > 0 ? '+' : ''}{margins[i]}</span>
            </div>
          ))}
        </div>
      </div>
    </Section>
  )
}

function Split({ row, onPlayer }: { row: TeammateSplit; onPlayer: OnPlayer }) {
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

export function Absences({ team, onPlayer }: { team: Team; onPlayer: OnPlayer }) {
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
          ) : <p className="mt-1 text-xs text-muted">Fewer than 3 games without him this season, too few to compare.</p>}
        </div>
      ))}
      {others.length > 0 && <p className="text-sm text-muted">{others.map((i) => `${i.name} (${i.status.toLowerCase()})`).join(' · ')}</p>}
    </Section>
  )
}

export function Roster({ team, onPlayer }: { team: Team; onPlayer: OnPlayer }) {
  return (
    <Section title="Roster" aside="per game this season">
      <div className="overflow-x-auto rounded-2xl border border-line bg-raised">
        <table className="w-full text-sm tabular-nums">
          <thead><tr className="text-xs text-muted">
            {['Player', 'G', 'Min', 'Last 5', 'Pts', 'Reb', 'Ast', '3PM'].map((h, i) => (
              <th key={h} className={`px-3 py-2 font-semibold ${i === 0 ? 'text-left' : 'text-right'}`}>{h}</th>
            ))}
          </tr></thead>
          <tbody>
            {team.roster.map((p) => {
              const trend = p.last5_min - p.minutes
              return (
                <tr key={p.id} className="border-t border-line">
                  <td className="whitespace-nowrap px-3 py-2">
                    <button type="button" onClick={() => onPlayer(p.id)} className="font-semibold hover:underline">{p.name}</button>
                    {p.status && <span className="ml-2 rounded bg-bad/15 px-1.5 py-0.5 text-[10px] font-bold text-bad">{p.status}</span>}
                  </td>
                  <td className="px-3 py-2 text-right">{p.games}</td>
                  <td className="px-3 py-2 text-right">{p.minutes}</td>
                  <td className={`px-3 py-2 text-right ${Math.abs(trend) < 2 ? 'text-muted' : trend > 0 ? 'text-good' : 'text-bad'}`}>
                    {p.last5_min}{Math.abs(trend) >= 2 && (trend > 0 ? ' ▲' : ' ▼')}
                  </td>
                  <td className="px-3 py-2 text-right font-black">{p.pts}</td>
                  <td className="px-3 py-2 text-right">{p.reb}</td>
                  <td className="px-3 py-2 text-right">{p.ast}</td>
                  <td className="px-3 py-2 text-right">{p.fg3m}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      <p className="mt-2 text-xs text-muted">Last 5 is his minutes over his last five games; an arrow marks a change of two minutes or more, often a role change books are slow to price.</p>
    </Section>
  )
}
