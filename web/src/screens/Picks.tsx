// Picks: what each model would bet on a FanDuel game day, and every points line with each model's
// projection beside FanDuel's own price. Paper only: these are tests of the models, not advice.
import { useEffect, useState } from 'react'
import { api, type Picks as PicksData } from '../lib/api'
import { american } from '../lib/ladder'
import { Empty, Photo, Pills, Section } from '../components/ui'

type Sort = 'gap' | 'game'

export function Picks() {
  const [date, setDate] = useState<string | undefined>()
  const [data, setData] = useState<PicksData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [sort, setSort] = useState<Sort>('gap')
  const [picksOnly, setPicksOnly] = useState(false)

  useEffect(() => {
    let live = true
    api.picks(date).then((d) => { if (live) { setData(d); setError(null) } }).catch((e: Error) => live && setError(e.message))
    return () => { live = false }
  }, [date])

  if (error) return <Empty title="No FanDuel lines yet" hint={error} />
  if (!data) return <div className="space-y-3">{[0, 1, 2].map((i) => <div key={i} className="h-24 animate-pulse rounded-2xl bg-raised" />)}</div>

  const short = (id: string) => data.models.find((m) => m.id === id)?.short ?? id
  let lines = picksOnly ? data.lines.filter((l) => l.models.some((m) => m.pick)) : data.lines
  lines = [...lines].sort(sort === 'gap'
    ? (a, b) => Math.abs(b.gap ?? 0) - Math.abs(a.gap ?? 0)
    : (a, b) => a.game_short.localeCompare(b.game_short) || a.player.localeCompare(b.player))

  return (
    <div>
      <h1 className="text-3xl font-black tracking-tight">Model picks</h1>
      <p className="mt-1 max-w-2xl text-sm text-muted">
        Paper only. The question is whether any model beats FanDuel's own odds over many bets, not whether one pick looks good.
      </p>
      <div className="mt-4">
        <Pills label="Game day" value={data.date} onChange={setDate} options={data.days.map((d) => ({ id: d.date, label: d.label }))} />
      </div>

      <Section title="Bets the models like" aside="FanDuel points lines">
        <div className="mb-3 rounded-2xl border border-warn/40 bg-warn/5 px-4 py-3 text-sm text-warn">
          Not proven yet: only a few nights are graded (see Record). A projection far from the line usually means the model is
          missing news, not that it found an edge.
        </div>
        {data.liked.length === 0 ? <Empty title="No model sees value on this day" /> : (
          <div className="grid gap-2.5 sm:grid-cols-2">
            {data.liked.map((p) => (
              <div key={`${p.player_id}${p.bet}`} className="rise flex items-center gap-3 rounded-2xl border border-line bg-raised p-3">
                <Photo src={p.photo} />
                <div className="min-w-0 flex-1">
                  <div className="truncate font-bold">{p.player}</div>
                  <div className="text-xs text-muted">{p.bet} · {p.game_short}</div>
                  <div className="text-xs text-muted">Projects {p.projects} · edge {p.ev_pct > 0 ? '+' : ''}{p.ev_pct}% · {p.agree > 1 ? `${p.agree} models agree` : 'one model'}</div>
                </div>
                <div className="rounded-full border border-line px-2.5 py-1 text-xs font-bold">{american(p.odds)}</div>
              </div>
            ))}
          </div>
        )}
      </Section>

      <Section title="Every line, with each projection" aside={`${lines.length} lines`}>
        <div className="flex flex-wrap items-end gap-4">
          <Pills label="Sort by" value={sort} onChange={setSort}
            options={[{ id: 'gap', label: 'Biggest gap' }, { id: 'game', label: 'Game' }]} />
          <label className="flex min-h-10 cursor-pointer items-center gap-2 text-sm font-semibold">
            <input type="checkbox" checked={picksOnly} onChange={(e) => setPicksOnly(e.target.checked)} className="size-4 accent-[var(--color-button)]" />
            Only lines a model picks
          </label>
        </div>
        <div className="mt-3 divide-y divide-line overflow-hidden rounded-2xl border border-line bg-raised">
          {lines.map((l) => (
            <div key={`${l.player}${l.line}`} className="px-4 py-3">
              <div className="flex items-center gap-3">
                {l.photo && <Photo src={l.photo} size={40} />}
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm font-bold">{l.player} <span className="font-semibold text-muted">· {l.line} pts</span></div>
                  <div className="text-xs text-muted">{l.game_short} · O {american(l.over)} / U {american(l.under)} · market {l.market_pct}% over</div>
                </div>
                <div className={`text-right text-lg font-black tabular-nums ${(l.gap ?? 0) > 0 ? 'text-good' : (l.gap ?? 0) < 0 ? 'text-bad' : ''}`}>
                  {(l.gap ?? 0) > 0 ? '+' : ''}{l.gap}
                  <div className="text-[10px] font-semibold text-muted">gap</div>
                </div>
              </div>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {l.models.filter((m) => m.proj !== null).map((m) => (
                  <span key={m.id} className={`rounded-full px-2.5 py-1 text-xs ${m.pick ? 'bg-button font-bold text-button-text' : 'border border-line text-muted'}`}>
                    {short(m.id)} {m.proj} · {m.pct}%{m.pick ? ` · ${m.pick}` : ''}
                  </span>
                ))}
              </div>
            </div>
          ))}
          {lines.length === 0 && <div className="px-4 py-6 text-center text-sm text-muted">No lines match.</div>}
        </div>
        <p className="mt-2 text-xs leading-relaxed text-muted">
          Gap is the newest model's projection minus the line. Each chip is a model's projection and its chance of the over;
          a filled chip is a pick, which means the model, blended 30/70 with FanDuel's price, sees at least 2% expected value.
          Treat a pick as a test of the model, not a recommendation.
        </p>
      </Section>
    </div>
  )
}
