// Watch a simulated game: the most typical of the runs, played back possession by possession on
// the court stage. Ten dots take their spots each trip down the floor, the shooter rises at his
// spot, the ball flies to the rim, and the score, clock, win chance, ticker and box score follow.
import { useEffect, useMemo, useRef, useState } from 'react'
import type { SimEvent, SimWatch } from '../lib/api'
import { CourtStage, type Dot, type ShotMark, type Side } from './CourtStage'
import { Pills } from './ui'

const SPEEDS = [1, 2, 4, 8]
// how long each kind of event stays on screen at 1x, in milliseconds
const HOLD: Record<SimEvent['kind'], number> = {
  start: 1400, period: 1600, final: 0, make: 1500, miss: 1300, free_throws: 1200,
  rebound: 650, turnover: 900, steal: 1000,
}
const SHOTS_SHOWN = 14
// where the offence stands, in feet from its baseline and from the middle: corners, wings, top
const SPOTS: [number, number][] = [[3, -21], [3, 21], [17, -16], [17, 16], [26, 0]]

type Box = Record<number, { pts: number; reb: number; ast: number }>

function initials(name: string): string {
  if (name.endsWith(' bench')) return 'BN'
  const parts = name.replace(/\./g, '').split(' ').filter(Boolean)
  return ((parts[0]?.[0] ?? '') + (parts[parts.length - 1]?.[0] ?? '')).toUpperCase()
}

/** Feet from a basket to court percent. */
function place(depth: number, side: number, right: boolean): { x: number; y: number } {
  const x = (Math.max(depth, 0.5) / 94) * 100
  return { x: right ? 100 - x : x, y: ((25 + side) / 50) * 100 }
}

/** A small fixed wobble per player and possession, so formations don't look stamped. */
function wobble(id: number, n: number): number {
  const v = Math.sin(id * 12.9898 + n * 78.233) * 43758.5453
  return (v - Math.floor(v) - 0.5) * 5
}

function ballTeam(event: SimEvent, away: string, home: string): string {
  if (event.kind === 'steal' || event.kind === 'rebound') return event.team
  if (event.kind === 'make' || event.kind === 'free_throws' || event.kind === 'turnover') {
    return event.team === away ? home : away         // the other side brings it up next
  }
  return event.team || away
}

function attacksRight(team: string, period: number, home: string): boolean {
  return (team === home) === (period <= 2)            // home attacks right in the first half
}

function dotsFor(event: SimEvent, n: number, watch: SimWatch, away: string, home: string): Dot[] {
  const names = new Map(watch.roster.map((p) => [p.id, p.name]))
  const shooting = event.kind === 'make' || event.kind === 'miss' || event.kind === 'free_throws'
  const offense = shooting ? event.team : ballTeam(event, away, home)
  const right = event.x != null ? event.x > 50 : attacksRight(offense, event.period, home)
  const out: Dot[] = []
  for (const team of [away, home]) {
    const ids = event.on?.[team] ?? []
    const onOffense = team === offense
    ids.forEach((id, i) => {
      const [depth, side] = SPOTS[i % SPOTS.length]
      let spot = onOffense
        ? place(depth + wobble(id, n), side + wobble(id + 7, n), right)
        : place(depth * 0.62 + 2 + wobble(id, n) * 0.5, side * 0.8 + wobble(id + 3, n) * 0.5, right)
      if (id === event.player && event.x != null && event.y != null) spot = { x: event.x, y: event.y }
      if (id === event.player && event.kind === 'free_throws') spot = place(15, 0, right)
      if (id === event.player && event.kind === 'rebound') spot = place(6 + wobble(id, n) * 0.4, wobble(id, n), right)
      out.push({ id, team: team === away ? 'away' : 'home', label: initials(names.get(id) ?? ''),
        x: spot.x, y: spot.y, hot: id === event.player })
    })
  }
  return out
}

function boxUpTo(events: SimEvent[], index: number): Box {
  const box: Box = {}
  const row = (id: number) => (box[id] ??= { pts: 0, reb: 0, ast: 0 })
  for (const e of events.slice(0, index + 1)) {
    if (e.player == null) continue
    if (e.kind === 'make' || e.kind === 'free_throws') row(e.player).pts += e.points ?? 0
    if (e.kind === 'rebound') row(e.player).reb += 1
    if (e.kind === 'make' && e.assist != null) row(e.assist).ast += 1
  }
  return box
}

function WinLine({ events, index, onSeek, away, home }: {
  events: SimEvent[]; index: number; onSeek: (i: number) => void; away: Side; home: Side
}) {
  const end = Math.max(events[events.length - 1]?.t ?? 2880, 2880)
  const points = events.map((e) => `${(e.t / end) * 300},${(1 - e.home_win / 100) * 40}`).join(' ')
  const at = events[index]
  return <svg viewBox="0 0 300 40" className="h-10 w-full cursor-pointer" preserveAspectRatio="none"
    role="slider" aria-label="Game timeline" aria-valuemin={0} aria-valuemax={events.length - 1} aria-valuenow={index}
    onClick={(e) => {
      const box = e.currentTarget.getBoundingClientRect()
      const t = ((e.clientX - box.left) / box.width) * end
      onSeek(Math.max(0, events.findIndex((ev) => ev.t >= t)))
    }}>
    <rect width="300" height="20" fill={home.color} opacity="0.08" />
    <rect y="20" width="300" height="20" fill={away.color} opacity="0.08" />
    <line x1="0" x2="300" y1="20" y2="20" stroke="rgba(255,255,255,0.2)" strokeDasharray="2 3" />
    <polyline points={points} fill="none" stroke="var(--color-text)" strokeWidth="1.2" vectorEffect="non-scaling-stroke" />
    {at && <line x1={(at.t / end) * 300} x2={(at.t / end) * 300} y1="0" y2="40" stroke="var(--color-good)" strokeWidth="2" vectorEffect="non-scaling-stroke" />}
  </svg>
}

export function GameWatch({ watch, away, home, runs }: { watch: SimWatch; away: Side; home: Side; runs: number }) {
  const events = watch.events
  const [index, setIndex] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [speed, setSpeed] = useState(2)
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const event = events[index]
  const done = index >= events.length - 1

  useEffect(() => {
    if (!playing || done) { if (done) setPlaying(false); return }
    timer.current = setTimeout(() => setIndex((i) => Math.min(i + 1, events.length - 1)), HOLD[event.kind] / speed)
    return () => { if (timer.current) clearTimeout(timer.current) }
  }, [playing, index, speed, done, event, events.length])

  const box = useMemo(() => boxUpTo(events, index), [events, index])
  const shots = useMemo(() => events.slice(0, index + 1)
    .map((e, i) => ({ e, i })).filter(({ e }) => (e.kind === 'make' || e.kind === 'miss') && e.x != null)
    .slice(-SHOTS_SHOWN)
    .map(({ e, i }): ShotMark => ({ key: i, x: e.x!, y: e.y!, made: e.kind === 'make',
      team: e.team === away.code ? 'away' : 'home', three: e.three })), [events, index, away.code])
  const flying = (event.kind === 'make' || event.kind === 'miss') && event.x != null
    ? { key: index, x: event.x, y: event.y!, made: event.kind === 'make', team: event.team === away.code ? 'away' as const : 'home' as const }
    : null
  const dots = useMemo(() => dotsFor(event, index, watch, away.code, home.code), [event, index, watch, away.code, home.code])
  const periodName = event.period <= 4 ? `Q${event.period}` : `OT${event.period - 4}`
  const names = new Map(watch.roster.map((p) => [p.id, p]))

  return <div>
    <CourtStage
      away={{ ...away, score: event.away }} home={{ ...home, score: event.home }}
      period={event.kind === 'final' ? 'Final' : periodName} clock={event.kind === 'final' ? '' : event.clock}
      homeWin={event.home_win} ticker={event.text}
      tickerTeam={event.team === away.code ? 'away' : event.team === home.code ? 'home' : null}
      dots={dots} shots={shots} flying={flying}
      badge={`Simulation · typical of ${runs.toLocaleString()}`}>
      {index === 0 && !playing && <div className="flex justify-center pb-3">
        <button type="button" onClick={() => setPlaying(true)}
          className="min-h-11 rounded-full bg-good px-5 text-sm font-black text-[#05070b] shadow-lg">▶ Watch the game</button>
      </div>}
      {/* who is on the floor, with their line so far */}
      <div className="grid grid-cols-2 gap-px border-t border-white/10 bg-white/10 text-[11px]">
        {[away, home].map((side) => <div key={side.code} className="bg-[#070a10] px-2 py-1.5">
          {(event.on?.[side.code] ?? []).map((id) => {
            const p = names.get(id)
            const line = box[id] ?? { pts: 0, reb: 0, ast: 0 }
            return <div key={id} className={`flex items-center justify-between gap-1 py-0.5 ${id === event.player ? 'text-good' : ''}`}>
              <span className="flex min-w-0 items-center gap-1.5">
                <span className="grid size-4 shrink-0 place-items-center rounded-full text-[8px] font-black text-[#05070b]" style={{ background: side.color }}>
                  {initials(p?.name ?? '')}</span>
                <span className="truncate">{p?.name.split(' ').slice(-1)[0] ?? ''}</span>
              </span>
              <span className="shrink-0 tabular-nums text-muted"><b className="text-text">{line.pts}</b> p · {line.reb} r · {line.ast} a</span>
            </div>
          })}
        </div>)}
      </div>
    </CourtStage>
    <div className="mt-2 flex flex-wrap items-center gap-2">
      <button type="button" onClick={() => (done ? (setIndex(0), setPlaying(true)) : setPlaying((p) => !p))}
        className="min-h-10 min-w-24 rounded-full bg-button px-4 text-sm font-black text-button-text">
        {playing ? '❚❚ Pause' : done ? '↺ Replay' : '▶ Play'}</button>
      <Pills label="Speed" value={String(speed)} onChange={(v) => setSpeed(Number(v))}
        options={SPEEDS.map((s) => ({ id: String(s), label: `${s}×` }))} />
      <button type="button" onClick={() => { setPlaying(false); setIndex(events.length - 1) }}
        className="min-h-10 px-2 text-xs font-semibold text-muted underline hover:text-text">Skip to the end</button>
    </div>
    <div className="mt-1">
      <WinLine events={events} index={index} away={away} home={home} onSeek={(i) => setIndex(i)} />
      <div className="flex justify-between text-[10px] text-muted"><span>Tip-off</span><span>{home.code} win chance over the game</span><span>Final</span></div>
    </div>
  </div>
}
