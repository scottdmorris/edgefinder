// Our record: every FanDuel pick as it was locked, how it turned out, and proof nothing was
// changed afterwards. It refuses to call a winner until there are enough graded lines to mean it.
import { useEffect, useMemo, useState } from 'react'
import { api, type ModelRecord, type RecordData } from '../lib/api'
import { american } from '../lib/ladder'
import { Empty, Pills, Section, StatStrip } from '../components/ui'

const SERIES = ['#eff3f4', '#8b98a5', '#f5b83d', '#00ba7c', '#1d9bf0']
const STAT_NAMES: Record<string, string> = { points: 'Points', rebounds: 'Rebounds', assists: 'Assists', threes: '3-pointers' }
const LOG_PAGE = 40

const units = (u: number | null | undefined) => (u == null ? '–' : `${u > 0 ? '+' : ''}${u.toFixed(2)}`)
const tone = (u: number | null | undefined) => (u == null || u === 0 ? '' : u > 0 ? 'text-good' : 'text-bad')
const when = (iso: string | null | undefined) =>
  iso ? new Date(iso).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit', timeZone: 'America/New_York' }) : '–'

export function Record() {
  const [data, setData] = useState<RecordData | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => { api.record().then(setData).catch((e: Error) => setError(e.message)) }, [])

  if (error) return <Empty title="Couldn't load the record" hint={error} />
  if (!data) return <div className="space-y-3">{[0, 1, 2].map((i) => <div key={i} className="h-24 animate-pulse rounded-2xl bg-raised" />)}</div>
  if (data.empty) return <Empty title="No picks yet" hint="They appear here as soon as the first lines are recorded." />

  const { integrity } = data
  return (
    <div>
      <h1 className="text-3xl font-black tracking-tight">Our record</h1>
      <p className="mt-1 max-w-2xl text-sm text-muted">
        Every pick is written down before the game and graded after it. Only the result is filled in later.
      </p>
      <div className="mt-5">
        <StatStrip items={[
          { value: integrity.picks, label: 'FanDuel picks locked' },
          { value: integrity.graded, label: 'graded so far' },
          { value: <span className={integrity.after_tip ? 'text-bad' : 'text-good'}>{integrity.after_tip}</span>, label: 'recorded after tip-off' },
          { value: data.chain.started ? <span className={data.chain.intact && data.chain.clean ? 'text-good' : 'text-bad'}>{data.chain.intact && data.chain.clean ? 'Intact' : 'Broken'}</span> : '–', label: 'tamper log' },
        ]} />
        {integrity.first_lock && (
          <p className="mt-2 text-xs text-muted">
            First locked {when(integrity.first_lock)} ET · most recent {when(integrity.last_lock)} ET.{' '}
            {integrity.after_tip ? 'Some picks were recorded after tip-off: ignore those.' : 'Every pick was recorded before its game started.'}
          </p>
        )}
      </div>

      <Models models={data.models} />
      <Profit running={data.running} models={data.models} />
      <ByBook data={data} />
      <Chain chain={data.chain} />
      <Clv data={data} />
      <Days days={data.days} models={data.models} />
      <Log log={data.log} models={data.models} />
    </div>
  )
}

function Models({ models }: { models: ModelRecord[] }) {
  const [chosen, setChosen] = useState(models[0]?.id ?? '')
  const model = models.find((m) => m.id === chosen) ?? models[0]
  if (!model) return null
  return (
    <Section title="How each model is doing" aside="FanDuel main lines, 1 unit a pick">
      <div className="grid gap-2.5 sm:grid-cols-2 lg:grid-cols-3">
        {models.map((m) => (
          <button key={m.id} type="button" onClick={() => setChosen(m.id)}
            className={`rise rounded-2xl border p-4 text-left transition-colors ${m.id === model.id ? 'border-line-strong bg-raised-2' : 'border-line bg-raised hover:border-line-strong'}`}>
            <div className="text-sm font-bold">{m.name}</div>
            <div className="mt-2 flex items-end justify-between">
              <div>
                <div className="text-2xl font-black">{m.record}</div>
                <div className="text-[11px] uppercase tracking-wider text-muted">record</div>
              </div>
              <div className="text-right">
                <div className={`text-2xl font-black ${tone(m.units)}`}>{units(m.units)}</div>
                <div className="text-[11px] uppercase tracking-wider text-muted">units · {m.roi_pct > 0 ? '+' : ''}{m.roi_pct.toFixed(0)}%</div>
              </div>
            </div>
          </button>
        ))}
      </div>
      <div className="mt-3 rounded-2xl border border-line bg-raised p-4">
        <div className="text-sm font-bold">{model.name}: is it better than FanDuel's own odds?</div>
        <p className="mt-1 text-sm text-muted">{model.verdict}</p>
        <Calibration model={model} />
      </div>
    </Section>
  )
}

function Calibration({ model }: { model: ModelRecord }) {
  if (!model.calibration.length) return <p className="mt-3 text-xs text-muted">Fills in once games have been graded.</p>
  const bars = [
    { key: 'model' as const, label: 'Model said', color: SERIES[0] },
    { key: 'market' as const, label: 'Market said', color: SERIES[1] },
    { key: 'actual' as const, label: 'Actually happened', color: SERIES[3] },
  ]
  return (
    <div className="mt-4">
      <div className="text-xs font-semibold text-muted">When it says 60%, does it happen 60% of the time?</div>
      <div className="mt-3 grid grid-flow-col gap-3" style={{ gridAutoColumns: 'minmax(0, 1fr)' }}>
        {model.calibration.map((bin) => (
          <div key={bin.bucket}>
            <div className="flex h-28 items-end justify-center gap-1 border-b border-line">
              {bars.map((b) => (
                <div key={b.key} title={`${b.label}: ${bin[b.key]?.toFixed(0)}%`}
                  className="w-full max-w-4 rounded-t transition-all duration-700"
                  style={{ height: `${bin[b.key] ?? 0}%`, background: b.color }} />
              ))}
            </div>
            <div className="mt-1 text-center text-[11px] font-semibold">{bin.bucket}</div>
            <div className="text-center text-[10px] text-muted">{bin.lines} lines</div>
          </div>
        ))}
      </div>
      <Legend items={bars.map((b) => ({ label: b.label, color: b.color }))} />
      <p className="mt-1 text-xs text-muted">Green should match white. Small groups swing a lot.</p>
    </div>
  )
}

function Profit({ running, models }: { running: RecordData['running']; models: ModelRecord[] }) {
  const days = useMemo(() => [...new Set(running.map((r) => r.day))].sort(), [running])
  const series = models.map((m, i) => ({ ...m, color: SERIES[i % SERIES.length], points: running.filter((r) => r.model === m.id) }))
    .filter((s) => s.points.length)
  if (!series.length) return null
  const values = running.map((r) => r.units)
  const top = Math.max(1, ...values)
  const bottom = Math.min(-1, ...values)
  const W = 600, H = 200, PAD = 28
  const x = (day: string) => PAD + (days.length === 1 ? (W - 2 * PAD) / 2 : (days.indexOf(day) / (days.length - 1)) * (W - 2 * PAD))
  const y = (u: number) => 10 + ((top - u) / (top - bottom)) * (H - 30)
  return (
    <Section title="Running profit" aside="units won, all graded FanDuel picks">
      <div className="rounded-2xl border border-line bg-raised p-3">
        <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="Running profit by model">
          <line x1={PAD} x2={W - PAD} y1={y(0)} y2={y(0)} stroke="#536471" strokeDasharray="4 4" />
          <text x={4} y={y(0) + 4} fontSize={10} fill="#71767b">0</text>
          <text x={4} y={y(top) + 4} fontSize={10} fill="#71767b">{top > 0 ? `+${top.toFixed(0)}` : ''}</text>
          <text x={4} y={y(bottom) + 4} fontSize={10} fill="#71767b">{bottom.toFixed(0)}</text>
          {days.map((d) => <text key={d} x={x(d)} y={H - 4} fontSize={10} fill="#71767b" textAnchor="middle">{d.slice(5)}</text>)}
          {series.map((s) => (
            <g key={s.id}>
              <polyline fill="none" stroke={s.color} strokeWidth={2.5} strokeLinejoin="round"
                points={s.points.map((p) => `${x(p.day)},${y(p.units)}`).join(' ')} />
              {s.points.map((p) => (
                <circle key={p.day} cx={x(p.day)} cy={y(p.units)} r={3.5} fill={s.color}>
                  <title>{`${s.name} · ${p.day} · ${units(p.units)}`}</title>
                </circle>
              ))}
            </g>
          ))}
        </svg>
        <Legend items={series.map((s) => ({ label: `${s.short} ${units(s.points[s.points.length - 1].units)}`, color: s.color }))} />
      </div>
    </Section>
  )
}

function ByBook({ data }: { data: RecordData }) {
  if (!data.by_book.length) return null
  return (
    <Section title="By price source and stat" aside="all models together">
      <div className="grid gap-2.5 sm:grid-cols-2">
        {data.by_book.map((book) => (
          <div key={book.book} className="rounded-2xl border border-line bg-raised p-4">
            <div className="font-bold">{book.name}</div>
            <table className="mt-2 w-full text-sm tabular-nums">
              <tbody>
                {book.stats.map((s) => (
                  <tr key={s.stat} className="border-t border-line">
                    <td className="py-1.5">{STAT_NAMES[s.stat] ?? s.stat}</td>
                    <td className="py-1.5 text-right font-semibold">{s.record}</td>
                    <td className={`py-1.5 text-right font-bold ${tone(s.units)}`}>{units(s.units)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ))}
      </div>
      <p className="mt-2 text-xs text-muted">
        Kalshi's ladders price every rung, and early Kalshi picks were mostly long shots far out on them. From Nov 6 a
        Kalshi pick also needs the model to give it at least 35% and to sit within 15 points of Kalshi's price, the same
        rule X+ picks use. Picks already locked stay as they were.
      </p>
      {data.alt.picks > 0 && <p className="mt-1 text-xs text-muted">X+ points picks: {data.alt.picks} locked, {data.alt.settled} graded, record {data.alt.record}.</p>}
    </Section>
  )
}

function Chain({ chain }: { chain: RecordData['chain'] }) {
  if (!chain.started) return null
  const ok = chain.intact && chain.clean
  const published = chain.published ?? []
  return (
    <Section title="Has anything been changed?" aside="SHA-256 hash chain">
      <div className="rounded-2xl border border-line bg-raised p-4">
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Fact label="Log" value={chain.intact ? 'Intact' : 'BROKEN'} className={chain.intact ? 'text-good' : 'text-bad'} />
          <Fact label="Rows matching the log" value={`${chain.matched} of ${chain.rows}`} className={chain.clean ? 'text-good' : 'text-bad'} />
          <Fact label="Entries" value={String(chain.entries)} />
          <Fact label="Latest fingerprint" value={chain.head?.slice(0, 10) ?? ''} mono />
        </div>
        <p className="mt-3 text-xs leading-relaxed text-muted">
          Every pick and result goes into an append-only log where each entry carries a fingerprint of the one before, so
          changing the past breaks everything after it. {chain.imported} entries were imported when the log began.{' '}
          {published.length === 0
            ? 'No fingerprint has been published yet, so until one is this proves nothing to an outsider.'
            : published.every((p) => p.ok)
              ? `${published.length} published fingerprint${published.length === 1 ? '' : 's'}, the latest from ${published[published.length - 1].date}, still match.`
              : 'A published fingerprint does NOT match this log.'}
        </p>
        {!ok && <p className="mt-2 text-sm font-bold text-bad">The record does not match its log. Do not trust the numbers on this page.</p>}
        {chain.problems?.map((p) => <p key={p} className="mt-1 text-xs text-warn">{p}</p>)}
      </div>
    </Section>
  )
}

function Clv({ data }: { data: RecordData }) {
  return (
    <Section title="Did the price move our way?" aside="closing-line value">
      {data.clv.length === 0 ? <p className="text-sm text-muted">Appears after the first graded picks with a closing price.</p> : (
        <div className="grid gap-2.5 sm:grid-cols-2">
          {data.clv.map((c) => (
            <div key={c.book} className="rounded-2xl border border-line bg-raised p-4">
              <div className="font-bold">{c.name}</div>
              <div className="mt-2 grid grid-cols-3 gap-2">
                <Fact label="Average move" value={`${c.avg_pct > 0 ? '+' : ''}${c.avg_pct.toFixed(1)}%`} />
                <Fact label="Beat the close" value={`${c.beat_pct.toFixed(0)}%`} className={c.beat_pct >= 50 ? 'text-good' : 'text-bad'} />
                <Fact label="Measured" value={String(c.measured)} />
              </div>
            </div>
          ))}
        </div>
      )}
      <p className="mt-2 text-xs text-muted">
        Compares the price we took with the price just before tip-off. A market that keeps moving our way shows up long
        before wins and losses can be trusted.
      </p>
      {data.gaps && (
        <p className="mt-1 text-xs text-muted">
          Price gaps (FanDuel vs Kalshi): {data.gaps.all.logged} logged, {data.gaps.all.record}, {units(data.gaps.all.units)} units.
        </p>
      )}
    </Section>
  )
}

function Days({ days, models }: { days: RecordData['days']; models: ModelRecord[] }) {
  if (!days.length) return null
  const name = (id: string) => models.find((m) => m.id === id)?.short ?? id
  return (
    <Section title="Day by day">
      <div className="overflow-x-auto rounded-2xl border border-line bg-raised">
        <table className="w-full text-sm tabular-nums">
          <thead><tr className="text-xs text-muted">
            <th className="px-4 py-2 text-left font-semibold">Game day</th><th className="px-2 py-2 text-left font-semibold">Model</th>
            <th className="px-2 py-2 text-right font-semibold">Picks</th><th className="px-2 py-2 text-right font-semibold">Record</th>
            <th className="px-4 py-2 text-right font-semibold">Units</th>
          </tr></thead>
          <tbody>
            {[...days].sort((a, b) => b.day.localeCompare(a.day) || a.model.localeCompare(b.model)).map((d) => (
              <tr key={`${d.day}${d.model}`} className="border-t border-line">
                <td className="px-4 py-2">{d.day}</td><td className="px-2 py-2">{name(d.model)}</td>
                <td className="px-2 py-2 text-right">{d.picks}</td><td className="px-2 py-2 text-right font-semibold">{d.record}</td>
                <td className={`px-4 py-2 text-right font-bold ${tone(d.units)}`}>{units(d.units)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Section>
  )
}

function Log({ log, models }: { log: RecordData['log']; models: ModelRecord[] }) {
  const [model, setModel] = useState('all')
  const [result, setResult] = useState('all')
  const [shown, setShown] = useState(LOG_PAGE)
  const name = (id: string) => models.find((m) => m.id === id)?.short ?? id
  const rows = log.filter((r) => (model === 'all' || r.model === model)
    && (result === 'all' || (result === 'pending' ? !r.result : r.result === result)))
  return (
    <Section title="Every pick, as locked" aside={`${rows.length} shown`}>
      <div className="flex flex-wrap gap-4">
        <Pills label="Model" value={model} onChange={(v) => { setModel(v); setShown(LOG_PAGE) }}
          options={[{ id: 'all', label: 'All' }, ...models.map((m) => ({ id: m.id, label: m.short }))]} />
        <Pills label="Result" value={result} onChange={(v) => { setResult(v); setShown(LOG_PAGE) }}
          options={[{ id: 'all', label: 'All' }, { id: 'win', label: 'Wins' }, { id: 'loss', label: 'Losses' }, { id: 'pending', label: 'Pending' }]} />
      </div>
      <div className="mt-3 divide-y divide-line overflow-hidden rounded-2xl border border-line bg-raised">
        {rows.slice(0, shown).map((r, i) => (
          <div key={i} className="flex items-center gap-3 px-4 py-2.5">
            <span className={`grid size-7 shrink-0 place-items-center rounded-full text-xs font-black ${r.result === 'win' ? 'bg-good/15 text-good' : r.result === 'loss' ? 'bg-bad/15 text-bad' : 'bg-raised-2 text-muted'}`}>
              {r.result === 'win' ? 'W' : r.result === 'loss' ? 'L' : '·'}
            </span>
            <div className="min-w-0 flex-1">
              <div className="truncate text-sm font-bold">{r.player} <span className="font-semibold text-muted">· {r.bet} {r.odds != null ? american(r.odds) : ''}</span></div>
              <div className="truncate text-xs text-muted">{r.day} · {name(r.model)} · locked {when(r.locked)} ET · {r.lead}</div>
            </div>
            <span className={`shrink-0 text-sm font-bold tabular-nums ${tone(r.units)}`}>{r.result ? units(r.units) : 'Pending'}</span>
          </div>
        ))}
        {rows.length === 0 && <div className="px-4 py-6 text-center text-sm text-muted">No picks match.</div>}
      </div>
      {rows.length > shown && (
        <button type="button" onClick={() => setShown(shown + LOG_PAGE)}
          className="mt-3 min-h-11 w-full rounded-full border border-line font-semibold hover:border-line-strong">
          Show {Math.min(LOG_PAGE, rows.length - shown)} more
        </button>
      )}
      <p className="mt-2 text-xs text-muted">Picks stay on this list win or lose. Players who don't play are graded void and don't count.</p>
    </Section>
  )
}

function Fact({ label, value, className = '', mono }: { label: string; value: string; className?: string; mono?: boolean }) {
  return (
    <div>
      <div className="text-[11px] text-muted">{label}</div>
      <div className={`font-bold ${mono ? 'font-mono text-sm' : ''} ${className}`}>{value}</div>
    </div>
  )
}

function Legend({ items }: { items: { label: string; color: string }[] }) {
  return (
    <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted">
      {items.map((i) => (
        <span key={i.label} className="flex items-center gap-1.5"><span className="size-2.5 rounded-sm" style={{ background: i.color }} />{i.label}</span>
      ))}
    </div>
  )
}
