// "We simulated this game 5,000 times": a court-side scoreboard with each team's win chance and
// typical score, the spread of margins, and one typical game's box score. Display only: it adds up
// the model's projections, it doesn't add knowledge they don't have.
import { useEffect, useState } from 'react'
import { api, type BoardGame, type Market, type Simulation } from '../lib/api'
import { sidePrice } from './GameCards'
import { GameWatch } from './GameWatch'

const AWAY = 'var(--color-accent)'
const HOME = 'var(--color-good)'
const BOX_STATS = [['points', 'PTS'], ['rebounds', 'REB'], ['assists', 'AST'], ['threes', '3PM']] as const

/** A full court seen from above, both ends painted in their team's colour. */
function Court() {
  const line = { fill: 'none', stroke: 'rgba(255,255,255,0.35)', strokeWidth: 2 }
  return <svg viewBox="0 0 940 500" aria-hidden className="absolute inset-0 size-full" preserveAspectRatio="xMidYMid slice">
    <defs>
      <linearGradient id="wood" x1="0" x2="1" y1="0" y2="1">
        <stop offset="0" stopColor="#6b4526" /><stop offset="1" stopColor="#3d2614" />
      </linearGradient>
      <radialGradient id="dim" cx="0.5" cy="0.5" r="0.7">
        <stop offset="0" stopColor="rgba(7,10,16,0.35)" /><stop offset="1" stopColor="rgba(7,10,16,0.88)" />
      </radialGradient>
    </defs>
    <rect width="940" height="500" fill="url(#wood)" />
    <rect x="20" y="20" width="900" height="460" {...line} />
    <rect x="20" y="170" width="190" height="160" fill={AWAY} fillOpacity="0.45" {...{ stroke: line.stroke, strokeWidth: 2 }} />
    <rect x="730" y="170" width="190" height="160" fill={HOME} fillOpacity="0.45" {...{ stroke: line.stroke, strokeWidth: 2 }} />
    <path d="M20 50 H160 A220 220 0 0 1 160 450 H20" {...line} />
    <path d="M920 50 H780 A220 220 0 0 0 780 450 H920" {...line} />
    <circle cx="210" cy="250" r="60" {...line} /><circle cx="730" cy="250" r="60" {...line} />
    <line x1="470" y1="20" x2="470" y2="480" {...line} />
    <circle cx="470" cy="250" r="62" {...line} />
    <rect width="940" height="500" fill="url(#dim)" />
  </svg>
}

function Side({ code, logo, pct, score, colour, market, align }: {
  code: string; logo?: string; pct: number; score: number; colour: string; market?: string; align: 'left' | 'right'
}) {
  return <div className={`flex flex-col ${align === 'right' ? 'items-end text-right' : 'items-start'}`}>
    <div className={`flex items-center gap-2 ${align === 'right' ? 'flex-row-reverse' : ''}`}>
      {logo && <img src={logo} alt="" className="size-9 drop-shadow sm:size-11" />}
      <span className="text-lg font-black tracking-wide sm:text-xl">{code}</span>
    </div>
    <div className="mt-1 text-4xl font-black tabular-nums sm:text-5xl" style={{ color: colour }}>{Math.round(pct)}%</div>
    <div className="text-[11px] font-semibold uppercase tracking-wider text-muted">to win · scores ~{score}</div>
    {market && <div className="mt-0.5 text-[11px] text-muted">market {market}</div>}
  </div>
}

/** How often each margin came up: away wins to the left, home wins to the right. */
function MarginChart({ sim }: { sim: Simulation }) {
  const top = Math.max(...sim.margin_chart.map((b) => b.pct), 1)
  return <div>
    <div className="flex h-20 items-end gap-0.5" role="img"
      aria-label={`Final margins: ${sim.home} by ${sim.margin.median} in the middle run, from ${sim.margin.low} to ${sim.margin.high} in 8 of 10`}>
      {sim.margin_chart.map((bar) => <div key={bar.from} title={`${bar.from} to ${bar.to}: ${bar.pct}%`}
        className="flex-1 rounded-t-sm" style={{ height: `${(bar.pct / top) * 100}%`, minHeight: bar.pct ? 2 : 0,
          background: bar.to <= 0 ? AWAY : bar.from >= 0 ? HOME : 'var(--color-muted)', opacity: 0.85 }} />)}
    </div>
    <div className="mt-1 flex justify-between text-[10px] font-semibold uppercase tracking-wider text-muted">
      <span>{sim.away} by 30+</span><span>even</span><span>{sim.home} by 30+</span>
    </div>
  </div>
}

function BoxScore({ sim }: { sim: Simulation }) {
  return <div className="grid gap-3 sm:grid-cols-2">
    {[sim.away, sim.home].map((team) => {
      const rows = sim.typical.box.filter((r) => r.team === team)
      return <table key={team} className="w-full text-xs tabular-nums">
        <caption className="mb-1 text-left text-[11px] font-black uppercase tracking-wider"
          style={{ color: team === sim.away ? AWAY : HOME }}>{team} · {sim.typical.score[team]}</caption>
        <thead><tr className="text-muted">
          <th className="py-1 text-left font-semibold">Player</th>
          {BOX_STATS.map(([, label]) => <th key={label} className="w-9 text-right font-semibold">{label}</th>)}
        </tr></thead>
        <tbody className="divide-y divide-line">
          {rows.map((r) => <tr key={r.player_id}>
            <td className="truncate py-1 pr-2">{r.player}</td>
            {BOX_STATS.map(([key]) => <td key={key} className="text-right">{r[key] ?? '–'}</td>)}
          </tr>)}
          <tr className="text-muted"><td className="py-1">Rest of the team</td>
            <td className="text-right">{sim.typical.rest[team]}</td><td colSpan={3} /></tr>
        </tbody>
      </table>
    })}
  </div>
}

export function GameSim({ market, game }: { market: Market; game: BoardGame }) {
  const [sim, setSim] = useState<Simulation | null>(null)
  const [failed, setFailed] = useState(false)
  const [showBox, setShowBox] = useState(false)
  const [request, setRequest] = useState<{ key: string } | null>(null)
  const key = `${market.date}|${market.book}|${market.model}|${game.game}`
  const requested = request?.key === key
  useEffect(() => {
    if (!requested) return
    let live = true
    setSim(null); setFailed(false)
    api.simulate(market, game.game).then((s) => live && setSim(s)).catch(() => live && setFailed(true))
    return () => { live = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, request, requested])
  if (!requested || failed) return (
    <section aria-label="Game simulation" className="mt-4 rounded-3xl border border-line bg-raised p-4">
      {requested && failed && <p role="alert" className="mb-2 text-sm text-warn">The simulation couldn’t load.</p>}
      <button type="button" className="min-h-11 font-bold text-accent"
        onClick={() => { setFailed(false); setSim(null); setShowBox(false); setRequest({ key }) }}>
        {requested && failed ? 'Retry simulation' : 'Run game simulation'}
      </button>
    </section>
  )
  const awayTeam = sim?.teams[sim.away]
  const homeTeam = sim?.teams[sim.home]
  const prices = [sidePrice(game.moneyline, 'away'), sidePrice(game.moneyline, 'home')]
  return <section aria-label="Game simulation" className="mt-4 overflow-hidden rounded-3xl border border-line bg-raised">
    {sim?.watch && <div className="p-2 sm:p-3">
      <GameWatch watch={sim.watch} runs={sim.runs}
        away={{ code: sim.away, logo: game.away_logo, color: AWAY, score: 0 }}
        home={{ code: sim.home, logo: game.home_logo, color: HOME, score: 0 }} />
    </div>}
    <div className={`relative px-4 pb-5 pt-4 sm:px-6 ${sim?.watch ? 'border-t border-line' : ''}`}>
      {!sim?.watch && <Court />}
      <div className="relative">
        <p className="text-center text-[11px] font-black uppercase tracking-[0.2em] text-good">
          {sim ? `We simulated this game ${sim.runs.toLocaleString()} times` : <span role="status">Simulating game…</span>}</p>
        {!sim || !awayTeam || !homeTeam ? <div className="mx-auto mt-4 h-28 max-w-md animate-pulse rounded-2xl bg-raised-2/60" />
          : <>
            <div className="mt-3 flex items-start justify-between gap-3">
              <Side code={sim.away} logo={game.away_logo} pct={awayTeam.win_pct} score={awayTeam.median}
                colour={AWAY} market={prices[0]?.pct} align="left" />
              <div className="pt-6 text-center">
                <div className="text-[10px] font-semibold uppercase tracking-wider text-muted">typical final</div>
                <div className="whitespace-nowrap text-lg font-black tabular-nums sm:text-2xl">{sim.typical.score[sim.away]}–{sim.typical.score[sim.home]}</div>
              </div>
              <Side code={sim.home} logo={game.home_logo} pct={homeTeam.win_pct} score={homeTeam.median}
                colour={HOME} market={prices[1]?.pct} align="right" />
            </div>
            <div className="mt-3 flex h-2 overflow-hidden rounded-full" aria-hidden>
              <div style={{ width: `${awayTeam.win_pct}%`, background: AWAY }} />
              <div style={{ width: `${homeTeam.win_pct}%`, background: HOME }} />
            </div>
          </>}
      </div>
    </div>
    {sim && <div className="space-y-4 border-t border-line px-4 py-4 sm:px-6">
      <div className="grid grid-cols-2 gap-3 text-center">
        <div className="rounded-2xl bg-raised-2 py-2">
          <div className="text-[10px] font-semibold uppercase tracking-wider text-muted">Total points</div>
          <div className="text-lg font-black tabular-nums">{sim.total.median}</div>
          <div className="text-[11px] text-muted">{sim.total.low}–{sim.total.high} in 8 of 10</div>
        </div>
        <div className="rounded-2xl bg-raised-2 py-2">
          <div className="text-[10px] font-semibold uppercase tracking-wider text-muted">Margin</div>
          <div className="text-lg font-black tabular-nums">{sim.margin.median === 0 ? 'Even'
            : `${sim.margin.median > 0 ? sim.home : sim.away} by ${Math.abs(sim.margin.median)}`}</div>
          <div className="text-[11px] text-muted">{sim.away} by {Math.max(-sim.margin.low, 0)} to {sim.home} by {Math.max(sim.margin.high, 0)}</div>
        </div>
      </div>
      <MarginChart sim={sim} />
      <div>
        <button type="button" aria-expanded={showBox} onClick={() => setShowBox((v) => !v)}
          className="min-h-9 text-sm font-bold text-accent">{showBox ? 'Hide' : 'Show'} a typical game’s box score</button>
        {showBox && <div className="mt-2"><BoxScore sim={sim} /></div>}
      </div>
      <p className="text-[11px] leading-relaxed text-muted">
        {sim.watch
          ? <>Each run plays the game possession by possession from how these players shoot, pass, rebound and turn it over this season,
            with each team’s shooting tuned so its average score meets {sim.model_short}’s projections. The game above is the run closest
            to the middle of all of them; its player spots are drawn from typical positions, not tracking data.</>
          : <>Each run draws every player’s stats around {sim.model_short}’s projections with the spread the props are priced on,
            and team scores with a real game’s swing.</>}
        {' '}It adds up the projections; it knows nothing they don’t, and it isn’t a pick.
        {prices[0] && ' “Market” is the moneyline’s chance with the book’s margin removed.'}
      </p>
    </div>}
  </section>
}
