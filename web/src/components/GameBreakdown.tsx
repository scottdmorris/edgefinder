import { useEffect, useState } from 'react'
import { api, type GameBreakdownData, type GameScoring, type Market } from '../lib/api'

const point = (n: number) => n.toFixed(1)
const signed = (n: number) => `${n < 0 ? '−' : n > 0 ? '+' : ''}${point(Math.abs(n))}`

function spread(away: string, home: string, margin: number | null) {
  if (margin === null) return '—'
  if (Number(point(margin)) === 0) return 'Pick’em'
  return `${margin > 0 ? home : away} −${point(Math.abs(margin))}`
}

function Scoring({ team, score, window }: { team: string; score: GameScoring; window: number }) {
  const rows = [
    [`Recent scoring (up to ${window} games)`, point(score.recent)],
    ['Listed player adjustments', signed(score.adjustment)],
    ...(score.baseline_floor ? [['Baseline adjustment', signed(score.baseline_floor)]] : []),
  ]
  return <div className="min-w-0 rounded-2xl border border-line bg-ink p-3">
    <h4 className="mb-1 font-black text-text">{team}</h4>
    <dl className="space-y-1 text-xs text-muted">
      {rows.map(([label, value]) => <div key={label} className="flex justify-between gap-2">
        <dt>{label}</dt><dd className="font-semibold tabular-nums text-text">{value}</dd>
      </div>)}
    </dl>
    {score.players.length > 0 && <ul aria-label={`${team} biggest player adjustments`} className="mt-2 space-y-1 border-t border-line pt-2 text-xs">
      {score.players.map(({ name, change }) => <li key={name} className="flex justify-between gap-2">
        <span>{name}</span><b className="tabular-nums text-accent">{signed(change)}</b>
      </li>)}
    </ul>}
    <p className="mt-2 text-xs text-muted">{score.coverage} listed player{score.coverage === 1 ? '' : 's'}</p>
  </div>
}

function Comparison({ data }: { data: GameBreakdownData }) {
  const { away, home, market, teams, recent_window, home_margin, home_margin_gap: gap } = data
  const book = market?.book === 'draftkings' ? 'DraftKings' : 'FanDuel'
  const recentMargin = teams ? teams[home].recent - teams[away].recent : 0
  const playerSwing = teams ? teams[home].adjustment - teams[away].adjustment : 0
  return <div className="rise space-y-3">
    <table className="w-full text-left text-sm tabular-nums">
      <thead className="text-xs text-muted"><tr>
        <th scope="col" className="pb-2">Score</th>
        <th scope="col" className="pb-2 text-right">{away}</th>
        <th scope="col" className="pb-2 text-right">{home}</th>
        <th scope="col" className="pb-2 text-right">Spread</th>
      </tr></thead>
      <tbody className="divide-y divide-line border-t border-line">
        <tr>
          <th scope="row" className="py-2 pr-2 font-semibold">Our projection</th>
          <td className="text-right font-black text-accent">{teams ? point(teams[away].projected) : '—'}</td>
          <td className="text-right font-black text-accent">{teams ? point(teams[home].projected) : '—'}</td>
          <td className="whitespace-nowrap pl-2 text-right font-black text-accent">{spread(away, home, home_margin)}</td>
        </tr>
        <tr>
          <th scope="row" className="py-2 pr-2 font-semibold">{market ? `${book} implied score` : 'Market'}</th>
          <td className="text-right">{market?.away_score == null ? '—' : point(market.away_score)}</td>
          <td className="text-right">{market?.home_score == null ? '—' : point(market.home_score)}</td>
          <td className="whitespace-nowrap pl-2 text-right">{spread(away, home, market ? -market.home_spread : null)}</td>
        </tr>
      </tbody>
    </table>
    {gap !== null && <p className="rounded-lg border-l-2 border-accent bg-accent/10 px-3 py-2 text-sm font-semibold">
      {Number(point(gap)) === 0 ? `Our projected margin matches ${book} at this precision.`
        : `Our projected margin is ${point(Math.abs(gap))} points more favorable to ${gap > 0 ? home : away} than ${book}.`}
    </p>}
    <p className="text-xs text-muted">{market
      ? `${book} pregame snapshot · ${new Date(market.as_of).toLocaleString([], { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit', timeZoneName: 'short' })}.`
      : 'No pregame spread archived for this matchup.'}
      {market?.total != null && ' Implied scores use the spread and game total.'}
      {market && market.total == null && ' Game total unavailable.'}
    </p>
    {teams ? <div>
      <h3 className="font-bold">What moves our score</h3>
      <p className="mb-2 mt-1 text-xs text-muted">
        {data.model} replaces each listed player’s usual scoring with his projection. The rest of the team keeps its share of recent scoring.
      </p>
      <p className="mb-2 text-sm">
        Recent scoring {Number(point(recentMargin)) === 0 ? 'puts the teams even'
          : `favors ${recentMargin > 0 ? home : away} by ${point(Math.abs(recentMargin))}`}.
        {' '}Listed player projections {Number(point(playerSwing)) === 0 ? 'leave that margin unchanged'
          : `shift the margin ${point(Math.abs(playerSwing))} points toward ${playerSwing > 0 ? home : away}`}.
      </p>
      <div className="grid gap-2 sm:grid-cols-2">
        {[away, home].map((team) => <Scoring key={team} team={team} score={teams[team]} window={recent_window} />)}
      </div>
      {[away, home].some((team) => teams[team].baseline_floor > 0) &&
        <p className="mt-2 text-xs text-muted">The baseline adjustment keeps unlisted players’ points at zero or higher.</p>}
    </div> : <p className="text-sm text-muted">Pregame scoring history is unavailable for this matchup.</p>}
  </div>
}

export function GameBreakdown({ market: { date, book, model }, game }: { market: Market; game: string }) {
  const [result, setResult] = useState<GameBreakdownData | 'error' | null>(null)
  const [retry, setRetry] = useState(0)
  useEffect(() => {
    let active = true
    void api.gameBreakdown({ date, book, model }, game).then(
      (data) => { if (active) setResult(data) },
      () => { if (active) setResult('error') },
    )
    return () => { active = false }
  }, [date, book, model, game, retry])

  return <section aria-label="Game breakdown" className="mt-4 rounded-3xl border border-line bg-linear-to-br from-accent/10 via-raised to-raised p-3.5 sm:p-5">
    <h2 className="mb-3 text-lg font-black">Game breakdown</h2>
    {result === 'error' ? <p className="text-sm text-muted">Couldn’t load the breakdown. <button type="button"
      className="min-h-9 font-semibold text-accent underline" onClick={() => { setResult(null); setRetry(retry + 1) }}>Retry</button></p>
      : result ? <Comparison data={result} /> : <p role="status" className="text-sm text-muted">Loading projections…</p>}
  </section>
}
