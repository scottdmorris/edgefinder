// The court stage: a tilted court with a scoreboard on top, the win-chance bar, a ticker of the
// latest play and, when known, ten player dots that slide into place. Shots fly to the rim and
// makes flash. One look for a simulated game and a live one.
import { useEffect, useId, useState, type ReactNode } from 'react'

const W = 940
const H = 500
const HOOP_X = 52.5
const HOOP_Y = 250

export type Side = { code: string; logo?: string; color: string; score: number }
export type Dot = { id: number; team: 'away' | 'home'; label: string; x: number; y: number; hot?: boolean }
export type ShotMark = { key: string | number; x: number; y: number; made: boolean; team: 'away' | 'home'; three?: boolean }

/** Court percent (x along the length, y across) to the SVG's units. */
export const toCourt = (x: number, y: number) => ({ cx: (x / 100) * W, cy: (y / 100) * H })

function Lines() {
  const line = { fill: 'none', stroke: 'rgba(255,255,255,0.55)', strokeWidth: 3 }
  const end = (mirror: boolean) => {
    const x = (v: number) => (mirror ? W - v : v)
    const s = mirror ? 0 : 1
    return <g>
      <rect x={mirror ? W - 190 : 0} y={170} width={190} height={160} {...line} />
      <circle cx={x(190)} cy={250} r={60} {...line} />
      <path d={`M${x(0)},30 L${x(140)},30 A237.5,237.5 0 0 ${s} ${x(140)},470 L${x(0)},470`} {...line} />
      <circle cx={x(HOOP_X)} cy={HOOP_Y} r={7.5} fill="none" stroke="#ff8a3d" strokeWidth={3} />
      <line x1={x(40)} x2={x(40)} y1={220} y2={280} stroke="rgba(255,255,255,0.8)" strokeWidth={4} />
    </g>
  }
  return <g>
    <rect x={0} y={0} width={W} height={H} {...line} />
    <line x1={W / 2} x2={W / 2} y1={0} y2={H} {...line} />
    <circle cx={W / 2} cy={250} r={60} {...line} />
    {end(false)}{end(true)}
  </g>
}

export function CourtStage({ away, home, period, clock, homeWin, ticker, tickerTeam, dots = [], shots = [],
  flying, badge, scoreboard = true, children }: {
  away: Side; home: Side; period: string; clock: string
  /** the home side's chance to win, 0-100; no bar when unknown */
  homeWin?: number | null
  ticker?: string; tickerTeam?: 'away' | 'home' | null
  dots?: Dot[]; shots?: ShotMark[]
  /** the shot in the air right now: it flies from its spot to the rim */
  flying?: ShotMark | null
  /** a small label over the court ("SIMULATION", "LIVE") */
  badge?: ReactNode
  /** off where the page already shows the score (the live game's sticky header) */
  scoreboard?: boolean
  children?: ReactNode
}) {
  const id = useId()
  const colour = (team: 'away' | 'home') => (team === 'away' ? away.color : home.color)
  return <div className="overflow-hidden rounded-3xl border border-line bg-[#05070b]">
    {/* scoreboard */}
    {scoreboard && <div className="relative flex items-center justify-between gap-2 bg-gradient-to-b from-[#121a26] to-[#0a0f17] px-3 py-2 sm:px-5">
      <Team side={away} />
      <div className="text-center">
        {badge && <div className="text-[9px] font-black uppercase tracking-[0.2em] text-good">{badge}</div>}
        <div className="text-sm font-black tabular-nums text-text sm:text-base">{period} <span className="text-muted">·</span> {clock}</div>
      </div>
      <Team side={home} right />
    </div>}
    {homeWin != null && <div className="flex h-1.5" aria-label={`Win chance: ${away.code} ${Math.round(100 - homeWin)}%, ${home.code} ${Math.round(homeWin)}%`}>
      <div className="transition-[width] duration-700" style={{ width: `${100 - homeWin}%`, background: away.color }} />
      <div className="flex-1" style={{ background: home.color }} />
    </div>}
    {homeWin != null && <div className="flex justify-between px-3 pt-1 text-[10px] font-bold tabular-nums text-muted sm:px-5">
      <span>{Math.round(100 - homeWin)}% to win</span><span>{Math.round(homeWin)}% to win</span>
    </div>}

    {/* the court, tilted like a broadcast camera */}
    <div className="relative px-2 pb-1 pt-2 [perspective:1100px] sm:px-6">
      <svg viewBox={`-20 -20 ${W + 40} ${H + 40}`} className="w-full origin-bottom [transform:rotateX(24deg)]" role="img"
        aria-label={ticker ?? 'Court'}>
        <defs>
          <linearGradient id={`${id}-wood`} x1="0" x2="1">
            <stop offset="0" stopColor="#8a5b31" /><stop offset="0.5" stopColor="#a8723f" /><stop offset="1" stopColor="#8a5b31" />
          </linearGradient>
          <pattern id={`${id}-boards`} width="940" height="18" patternUnits="userSpaceOnUse">
            <rect width="940" height="18" fill={`url(#${id}-wood)`} />
            <line x1="0" x2="940" y1="17.5" y2="17.5" stroke="rgba(0,0,0,0.12)" strokeWidth="1" />
          </pattern>
          <radialGradient id={`${id}-glow`}><stop offset="0" stopColor="white" stopOpacity="0.9" /><stop offset="1" stopColor="white" stopOpacity="0" /></radialGradient>
        </defs>
        <rect x={-20} y={-20} width={W + 40} height={H + 40} rx={18} fill="#2a1a0e" />
        <rect x={0} y={0} width={W} height={H} fill={`url(#${id}-boards)`} />
        <rect x={0} y={170} width={190} height={160} fill={away.color} opacity={0.75} />
        <rect x={W - 190} y={170} width={190} height={160} fill={home.color} opacity={0.75} />
        {home.logo && <image href={home.logo} x={W / 2 - 50} y={200} width={100} height={100} opacity={0.35} />}
        <Lines />
        {shots.map((s) => {
          const { cx, cy } = toCourt(s.x, s.y)
          return s.made
            ? <circle key={s.key} cx={cx} cy={cy} r={7} fill={colour(s.team)} stroke="white" strokeWidth={1.5} opacity={0.75} />
            : <g key={s.key} stroke={colour(s.team)} strokeWidth={3} opacity={0.6}>
              <line x1={cx - 6} x2={cx + 6} y1={cy - 6} y2={cy + 6} /><line x1={cx - 6} x2={cx + 6} y1={cy + 6} y2={cy - 6} /></g>
        })}
        {dots.map((d) => <g key={d.id} className="transition-transform duration-700 ease-out"
          style={{ transform: `translate(${toCourt(d.x, d.y).cx}px, ${toCourt(d.x, d.y).cy}px)` }}>
          {d.hot && <circle r={30} fill={`url(#${id}-glow)`} className="animate-pulse" />}
          <circle r={17} fill={colour(d.team)} stroke={d.hot ? 'white' : 'rgba(0,0,0,0.55)'} strokeWidth={d.hot ? 4 : 2} />
          <text textAnchor="middle" dy="5.5" fontSize="14" fontWeight="900" fill="#05070b">{d.label}</text>
        </g>)}
        {flying && <FlyingBall key={flying.key} shot={flying} />}
      </svg>
      {ticker && <div className="pointer-events-none absolute inset-x-0 bottom-3 flex justify-center px-3">
        <div key={ticker} className="rise flex max-w-full items-center gap-2 rounded-lg border border-white/10 bg-[#05070b]/90 px-3 py-1.5 text-xs font-bold shadow-lg sm:text-sm">
          {tickerTeam && <span className="rounded px-1.5 py-0.5 text-[10px] font-black text-[#05070b]" style={{ background: colour(tickerTeam) }}>
            {tickerTeam === 'away' ? away.code : home.code}</span>}
          <span className="truncate">{ticker}</span>
        </div>
      </div>}
    </div>
    {children}
  </div>
}

function Team({ side, right = false }: { side: Side; right?: boolean }) {
  const [pop, setPop] = useState(false)
  useEffect(() => { setPop(true); const t = setTimeout(() => setPop(false), 500); return () => clearTimeout(t) }, [side.score])
  return <div className={`flex items-center gap-2 ${right ? 'flex-row-reverse text-right' : ''}`}>
    {side.logo && <img src={side.logo} alt="" className="size-8 sm:size-10" />}
    <div>
      <div className="text-[11px] font-black tracking-wider" style={{ color: side.color }}>{side.code}</div>
      <div className={`text-2xl font-black tabular-nums leading-none sm:text-3xl ${pop ? 'score-pop' : ''}`}>{side.score}</div>
    </div>
  </div>
}

/** The ball's flight from the shot spot to the rim, and a flash when it drops. */
function FlyingBall({ shot }: { shot: ShotMark }) {
  const { cx, cy } = toCourt(shot.x, shot.y)
  const hoopX = shot.x > 50 ? W - HOOP_X : HOOP_X
  const [landed, setLanded] = useState(false)
  useEffect(() => { const t = setTimeout(() => setLanded(true), 30); return () => clearTimeout(t) }, [])
  return <g>
    <circle r={9} fill="#ff8a3d" stroke="#5a2a0a" strokeWidth={2}
      style={{ transform: `translate(${landed ? hoopX : cx}px, ${landed ? HOOP_Y : cy}px)`,
        transition: 'transform 650ms cubic-bezier(0.3, -0.4, 0.6, 1)' }} />
    {landed && shot.made && <circle cx={hoopX} cy={HOOP_Y} r={14} fill="none" stroke="white" strokeWidth={4} className="rim-flash" />}
  </g>
}
