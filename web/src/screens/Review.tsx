// Last night: a graded game day in one place. How each model did, how your own slip did and
// which leg sank it, and the misses worth a second look.
import { useEffect, useState } from 'react'
import { api, type GradedSlip, type Review as ReviewData, type ReviewPick } from '../lib/api'
import { american } from '../lib/ladder'
import { slipForDate, type DatedSlip } from '../lib/slip'
import { Empty, Photo, Pills, Section } from '../components/ui'

const DAYS_SHOWN = 7
const BADGE: Record<string, string> = {
  Hit: 'bg-good/15 text-good', Missed: 'bg-bad/15 text-bad',
  "Didn't play": 'bg-raised-2 text-muted', 'Not graded yet': 'bg-raised-2 text-muted',
}
const units = (u: number | null) => (u == null ? '–' : `${u > 0 ? '+' : ''}${u.toFixed(2)}`)
const tone = (u: number | null) => ((u ?? 0) > 0 ? 'text-good' : (u ?? 0) < 0 ? 'text-bad' : '')

export function Review() {
  const [date, setDate] = useState<string | undefined>()
  const [data, setData] = useState<ReviewData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [everyPick, setEveryPick] = useState(false)

  useEffect(() => {
    let live = true
    api.review(date).then((d) => { if (live) { setData(d); setError(null) } })
      .catch((e: Error) => live && setError(e.message))
    return () => { live = false }
  }, [date])

  if (error) return <Empty title="Nothing graded yet" hint="Picks are graded the morning after the games. Check back then." />
  if (!data) return <div className="space-y-3">{[0, 1, 2].map((i) => <div key={i} className="h-24 animate-pulse rounded-2xl bg-raised" />)}</div>

  const hits = data.picks.filter((p) => p.status === 'Hit').length
  const misses = data.picks.filter((p) => p.status === 'Missed').length
  return (
    <div>
      <h1 className="text-3xl font-black tracking-tight">Last night</h1>
      <p className="mt-1 text-sm text-muted">
        {data.label}: {hits} of {hits + misses} model picks hit{data.pending > 0 && `, ${data.pending} not graded yet`}.
      </p>
      <div className="mt-4">
        <Pills label="Game day" value={data.date} onChange={setDate}
          options={data.days.slice(0, DAYS_SHOWN).map((d) => ({ id: d.date, label: d.label }))} />
      </div>

      <YourSlip key={data.date} date={data.date} />

      <Section title="How each model did" aside="FanDuel points picks, in units">
        <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-4">
          {data.models.map((m) => (
            <div key={m.id} className="rounded-2xl border border-line bg-raised px-4 py-3">
              <div className="text-xs font-semibold text-muted">{m.short}</div>
              <div className="text-2xl font-black">{m.record}</div>
              <div className={`text-xs font-bold ${tone(m.units)}`}>{units(m.units)} units</div>
            </div>
          ))}
        </div>
        <p className="mt-2 text-xs text-muted">
          One night says little about a model. The Record screen has every night together.
          {data.kalshi && ` Kalshi picks, all stats: ${data.kalshi.record} (${units(data.kalshi.units)} units).`}
        </p>
      </Section>

      {data.misses.length > 0 && (
        <Section title="Misses worth a second look" aside="furthest from the projection">
          <div className="grid gap-2.5 sm:grid-cols-2">{data.misses.map((p) => <PickCard key={`${p.player_id}${p.bet}`} pick={p} />)}</div>
          <p className="mt-2 text-xs text-muted">A big miss usually means news the model did not have: an injury, a short night, a blowout.</p>
        </Section>
      )}

      <Section title="Every pick" aside={`${data.picks.length} bets`}>
        <div className="grid gap-2.5 sm:grid-cols-2">
          {(everyPick ? data.picks : data.picks.slice(0, 6)).map((p) => <PickCard key={`${p.player_id}${p.bet}`} pick={p} />)}
        </div>
        {!everyPick && data.picks.length > 6 && <button type="button" onClick={() => setEveryPick(true)}
          className="mt-3 min-h-11 w-full rounded-full border border-line text-sm font-semibold hover:border-line-strong">Show all {data.picks.length} picks</button>}
      </Section>
    </div>
  )
}

function PickCard({ pick }: { pick: ReviewPick }) {
  return (
    <div className="flex items-center gap-3 rounded-2xl border border-line bg-raised p-3">
      <Photo src={pick.photo} />
      <div className="min-w-0 flex-1">
        <div className="truncate font-bold">{pick.player}</div>
        <div className="text-xs text-muted">{pick.bet}{pick.odds !== null && ` · ${american(pick.odds)}`} · {pick.game_short}</div>
        <div className="text-xs text-muted">
          Projected {pick.projects ?? '–'}{pick.actual !== null && `, scored ${pick.actual}`} · {pick.models.join(', ')}
        </div>
        {pick.note && <div className="text-xs text-warn">{pick.note}</div>}
      </div>
      <span className={`shrink-0 rounded-full px-2.5 py-1 text-xs font-bold ${BADGE[pick.status] ?? ''}`}>{pick.status}</span>
    </div>
  )
}

// The slip built in this browser for that game day, graded against the box scores.
function YourSlip({ date }: { date: string }) {
  const [slip] = useState<DatedSlip | null>(() => slipForDate(date))
  const [graded, setGraded] = useState<GradedSlip | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!slip) return
    let live = true
    api.gradeSlip(date, slip.legs.map((l) => ({ player_id: l.player_id, stat: l.stat, side: l.side, line: l.line })))
      .then((g) => live && setGraded(g)).catch((e: Error) => live && setError(e.message))
    return () => { live = false }
  }, [date, slip])

  if (!slip) return (
    <Section title="Your slip">
      <div className="rounded-2xl border border-dashed border-line px-4 py-4 text-sm text-muted">
        No slip was built in this browser for this game day. Slips from the Parlay screen show up here once the games are graded.
      </div>
    </Section>
  )
  const sank = graded?.legs.findIndex((leg) => leg.status === 'Missed') ?? -1
  return (
    <Section title="Your slip" aside={graded && (
      <span className={`rounded-full px-3 py-1 font-bold ${BADGE[graded.status] ?? ''}`}>
        {graded.status}{graded.status !== 'Not graded yet' && ` · ${graded.hit} of ${graded.legs.length} hit`}
      </span>)}>
      {error && <p role="alert" className="text-sm text-warn">Could not grade this slip: {error}</p>}
      <div className="space-y-2">
        {slip.legs.map((leg, i) => {
          const result = graded?.legs[i]
          return (
            <div key={leg.id} className={`flex items-center gap-3 rounded-2xl border bg-raised p-3 ${i === sank ? 'border-bad/60' : 'border-line'}`}>
              <Photo src={leg.photo} size={40} />
              <div className="min-w-0 flex-1">
                <div className="truncate text-sm font-bold">{leg.player} <span className="font-semibold text-muted">· {leg.bet}</span></div>
                <div className="text-xs text-muted">
                  {result?.actual != null ? `Finished with ${result.actual}` : 'No result yet'}
                  {leg.chance_pct != null && ` · you added it at a ${leg.chance_pct.toFixed(0)}% chance`}
                </div>
                {result?.note && <div className="text-xs text-warn">{result.note}</div>}
                {i === sank && <div className="text-xs font-bold text-bad">This leg sank the slip{graded && graded.missed > 1 ? ` (${graded.missed} legs missed)` : ''}.</div>}
              </div>
              {result && <span className={`shrink-0 rounded-full px-2.5 py-1 text-xs font-bold ${BADGE[result.status] ?? ''}`}>{result.status}</span>}
            </div>
          )
        })}
      </div>
    </Section>
  )
}
