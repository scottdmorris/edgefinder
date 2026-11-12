// Live: every game at a glance, your slip bet by bet, and the chosen game in full.
// Everything refreshes every 10 seconds from NBA's own live feed while the page is open.
import { useState } from 'react'
import { api, type GameCard, type Side, type Tracked, type TrackedLeg } from '../lib/api'
import { shortStatus } from '../lib/format'
import { usePoll, usePrevious } from '../lib/poll'
import { savedSlip } from '../lib/slip'
import { Empty, Photo } from '../components/ui'
import { GameCenter } from '../components/GameCenter'
import { Freshness } from '../components/Freshness'

const REFRESH_MS = 10_000

export function Live() {
  const games = usePoll(api.live, REFRESH_MS, 'games')
  const [chosen, setChosen] = useState<string | null>(null)
  const slip = savedSlip()
  const slipKey = slip ? `${slip.market.date}|${slip.market.book}|${slip.market.model}|${slip.legs.join(',')}` : 'none'
  const tracked = usePoll<Tracked | null>(
    () => (slip ? api.track(slip.market, slip.legs) : Promise.resolve(null)), REFRESH_MS, slipKey)
  const list = games.data ?? []
  const id = chosen && list.some((g) => g.id === chosen) ? chosen : list[0]?.id ?? null

  if (games.error && !games.data) return <Empty title="NBA's live feed isn't answering" hint={`${games.error}. It tries again on its own.`} />
  if (!games.data) return <Loading />
  if (!list.length) return <Empty title="No NBA games on the board right now" hint="Tonight's games show up here once NBA posts the day's schedule." />

  return (
    <div>
      <div className="flex items-baseline justify-between gap-3">
        <h1 className="text-3xl font-black tracking-tight">Live</h1>
        <Freshness receivedAt={games.receivedAt} error={games.error} label="Board received" />
      </div>
      {games.error && <p role="alert" className="mt-3 text-sm text-warn">Showing the last successful board. {games.error}</p>}
      <Overview games={list} chosen={id} onChoose={setChosen} legs={tracked.error ? [] : tracked.data?.legs ?? []} />
      <SlipTracker slip={slip} tracked={tracked} />
      {id && <Game key={id} id={id} card={list.find((g) => g.id === id)!} />}
    </div>
  )
}

export function Overview({ games, chosen, onChoose, legs }: {
  games: GameCard[]; chosen: string | null; onChoose: (id: string) => void; legs: TrackedLeg[]
}) {
  return (
    <div className="no-scrollbar -mx-4 mt-4 flex gap-2 overflow-x-auto px-4 pb-1 sm:mx-0 sm:px-0" aria-label="Games">
      {games.map((g) => {
        const on = g.id === chosen
        const mine = legs.filter((leg) => leg.game_id === g.id).length
        return (
          <button key={g.id} type="button" aria-pressed={on} aria-label={`${g.away.team} at ${g.home.team}`} onClick={() => onChoose(g.id)}
            className={`min-w-[150px] shrink-0 rounded-2xl border px-3 py-2 text-left transition-colors ${on ? 'border-line-strong bg-raised-2' : 'border-line hover:border-line-strong'}`}>
            <div className="flex items-center justify-between gap-2 text-[11px] font-semibold text-muted">
              <span className="flex items-center gap-1">
                {g.state === 'live' && <span className="live-dot size-1.5 rounded-full bg-bad" />}
                {g.state === 'final' ? 'Final' : shortStatus(g.status)}
              </span>
              {mine > 0 && <span className="rounded-full bg-accent/15 px-1.5 text-accent">{mine} on slip</span>}
            </div>
            {[g.away, g.home].map((side) => (
              <div key={side.team} className="mt-0.5 flex items-center gap-1.5 text-sm">
                <img src={side.logo} alt="" className="size-4" />
                <span className="flex-1 font-bold">{side.team}</span>
                {g.state !== 'upcoming' && <span className="font-black tabular-nums">{side.score}</span>}
              </div>
            ))}
            {g.state === 'live' && g.detail_available === false && <div className="mt-0.5 text-[11px] text-warn">Score only for now</div>}
          </button>
        )
      })}
    </div>
  )
}

function Game({ id, card }: { id: string; card: GameCard }) {
  // details only matter once a game is on; a finished one is fetched once and kept
  const started = card.state !== 'upcoming'
  const detail = usePoll(() => api.game(id), card.state === 'live' ? REFRESH_MS : 3_600_000, `${id}:${started}`)
  const shown = detail.data ?? { ...card, detail: null }
  return (
    <div className="mt-5">
      <Hero game={{ ...shown, ...card }} />
      {card.state === 'live' && <div className="mt-2"><Freshness receivedAt={detail.data?.detail_received_at} error={detail.error} label="Game details received" /></div>}
      {started && (detail.error || (detail.data && !detail.data.detail)) && <p role="alert" className="mt-2 text-sm text-warn">{detail.error ?? 'NBA game details are temporarily unavailable'}. {shown.detail ? 'Showing previous game details.' : 'Retrying automatically.'}</p>}
      {!started && <p className="mt-3 text-sm text-muted">Tips off at {card.status}. Shots, plays and the box score appear once the game starts.</p>}
      {started && !detail.data && !detail.error && <div className="mt-5 h-64 animate-pulse rounded-2xl bg-raised" />}
      {started && detail.error && !detail.data && <p className="mt-3 text-sm text-warn">{detail.error}. Trying again…</p>}
      {shown.detail && shown.detail.foul_trouble.length > 0 && (
        <p className="mt-3 text-sm text-warn">
          Foul trouble: {shown.detail.foul_trouble.map((f) => `${f.name.split(' ').slice(-1)[0]} ${f.fouls} (${f.team})`).join(', ')}
        </p>
      )}
      {shown.detail && <GameCenter game={{ ...shown, detail: shown.detail }} />}
    </div>
  )
}

function Hero({ game }: { game: GameCard }) {
  const live = game.state === 'live'
  const started = game.state !== 'upcoming'
  return (
    <div className="relative overflow-hidden rounded-3xl border border-line px-4 py-5 sm:px-6"
      style={{ background: `linear-gradient(110deg, color-mix(in srgb, ${game.away.color} 22%, #000) 0%, #0b0c0e 45%, #0b0c0e 55%, color-mix(in srgb, ${game.home.color} 22%, #000) 100%)` }}>
      <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-2 sm:gap-4">
        <TeamSide side={game.away} started={started} gameId={game.id} />
        <div className={`flex items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 py-1 text-xs font-bold ${live ? 'bg-bad/15 text-bad' : 'bg-raised text-muted'}`}>
          {live && <span className="live-dot size-1.5 rounded-full bg-bad" />}
          {game.state === 'final' ? 'Final' : shortStatus(game.status)}
        </div>
        <TeamSide side={game.home} started={started} gameId={game.id} right />
      </div>
      {started && (
        <div className="mt-3 grid grid-cols-2 gap-2 border-t border-white/10 pt-3">
          <Notes side={game.away} />
          <Notes side={game.home} right />
        </div>
      )}
    </div>
  )
}

function TeamSide({ side, started, gameId, right }: { side: Side; started: boolean; gameId: string; right?: boolean }) {
  const before = usePrevious(`${gameId}:${side.score}`)
  const scored = before !== undefined && before.startsWith(`${gameId}:`) && Number(before.split(':')[1]) < side.score
  return (
    <div className={`flex min-w-0 items-center gap-2 sm:gap-3 ${right ? 'flex-row-reverse text-right' : ''}`}>
      <img src={side.logo} alt="" className="size-10 shrink-0 sm:size-16" />
      <div className="min-w-0">
        <div className="text-sm font-bold" style={{ color: side.color }}>{side.team}</div>
        {started && <div key={side.score} className={`text-3xl font-black tabular-nums sm:text-5xl ${scored ? 'score-pop' : ''}`}>{side.score}</div>}
      </div>
    </div>
  )
}

function Notes({ side, right }: { side: Side; right?: boolean }) {
  return (
    <div className={`flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-muted ${right ? 'justify-end' : ''}`}>
      <span aria-label={`${side.timeouts} timeouts left`} title="Timeouts left" className="flex gap-0.5">
        {Array.from({ length: 7 }, (_, i) => <span key={i} className={`h-1 w-2 rounded-full ${i < side.timeouts ? 'bg-text' : 'bg-line'}`} />)}
      </span>
      {side.fouls !== null && <span>{side.fouls} fouls</span>}
      {side.bonus && <span className="font-bold text-warn">Bonus</span>}
    </div>
  )
}

const BADGE: Record<string, string> = {
  Hit: 'bg-good/15 text-good', Alive: 'bg-button/10 text-text', Missed: 'bg-bad/15 text-bad',
  'Not started': 'bg-raised-2 text-muted', "Didn't play": 'bg-raised-2 text-muted',
}

function SlipTracker({ slip, tracked }: {
  slip: ReturnType<typeof savedSlip>
  tracked: { data: Tracked | null; error: string | null; receivedAt: number | null }
}) {
  const previous = usePrevious(tracked.data)
  if (!slip) return null
  const before = new Map(previous?.legs.map((l) => [l.id, l.status]) ?? [])
  const data = tracked.data
  return (
    <section className="mt-6">
      <div className="mb-2 flex items-center justify-between">
        <h2 className="text-lg font-extrabold">Your slip</h2>
        {data && <span className={`rounded-full px-3 py-1 text-xs font-bold ${BADGE[data.status] ?? ''}`}>{data.status}</span>}
      </div>
      {data?.legs.some((leg) => leg.alert) && <div role="alert" className="mb-2 rounded-2xl border border-warn/50 bg-warn/10 px-4 py-3 text-sm text-warn">
        {data.legs.filter((leg) => leg.alert).map((leg) => <p key={leg.id}><b>{leg.player}</b>: {leg.alert}.</p>)}
      </div>}
      {tracked.error && <p role="alert" className="text-sm text-warn">{tracked.error}{data ? ". Displayed progress is from the last successful update." : ""}</p>}
      {data && <Freshness receivedAt={tracked.receivedAt} error={tracked.error} label="Slip progress received" />}
      {tracked.error && <div className="mt-3 space-y-2 rounded-2xl border border-warn/40 p-4">
        <p className="text-sm text-muted">Saved selections for {slip.market.date}. Results cannot be verified from the current feed.</p>
        {slip.legs.map((id) => {
          const leg = slip.snapshots[id]
          return <p key={id} className="text-sm">{leg ? `${leg.player} · ${leg.bet}` : 'Saved selection'} <span className="text-warn">· Needs review</span></p>
        })}
        <a href="#/parlay" className="inline-block min-h-11 py-2 text-sm font-bold text-accent">Review the saved slip →</a>
      </div>}
      {!data && !tracked.error && <div className="h-20 animate-pulse rounded-2xl bg-raised" />}
      {data && data.legs.every((leg) => leg.game === 'no live game') && (
        <div className="rounded-2xl border border-dashed border-line px-4 py-4 text-sm text-muted">
          This slip is for {new Date(`${slip.market.date}T12:00:00`).toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' })}, and
          none of its games are on NBA's board today. <a href="#/parlay" className="font-semibold text-text underline">Build one for tonight</a>.
        </div>
      )}
      {data && !data.legs.every((leg) => leg.game === 'no live game') && (
        <div className="space-y-2">
          {data.legs.map((leg) => {
            const flipped = before.has(leg.id) && before.get(leg.id) !== leg.status
            return (
              <div key={leg.id} className={`rounded-2xl border bg-raised p-3 ${leg.alert ? 'border-warn/60' : 'border-line'} ${flipped ? 'flash' : ''}`}>
                <div className="flex items-center gap-3">
                  <Photo src={leg.photo} size={40} />
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-sm font-bold">{leg.player} <span className="font-semibold text-muted">· {leg.bet}</span></div>
                    <div className="truncate text-xs text-muted">{leg.game_state === 'final' ? 'Final · ' : leg.game_state === 'upcoming' ? 'Pending · ' : ''}{leg.status === "Didn't play" ? 'Void · ' : ''}{leg.detail} · {leg.game}</div>
                  </div>
                  <span className={`shrink-0 rounded-full px-2.5 py-1 text-xs font-bold ${BADGE[leg.status] ?? ''}`}>{leg.status}</span>
                </div>
                {leg.have !== null && (
                  <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-line">
                    <div className={`h-full rounded-full transition-all duration-700 ${leg.status === 'Missed' ? 'bg-bad' : leg.status === 'Hit' ? 'bg-good' : 'bg-text'}`}
                      style={{ width: `${Math.round(leg.progress * 100)}%` }} />
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
      <p className="mt-2 text-xs text-muted">The slip built on the Parlay screen in this browser. Change it there.</p>
    </section>
  )
}

function Loading() {
  return (
    <div className="space-y-3">
      <div className="h-20 animate-pulse rounded-2xl bg-raised" />
      <div className="h-40 animate-pulse rounded-3xl bg-raised" />
    </div>
  )
}
