import { useState } from 'react'
import type { MissMetrics, MissReportRow } from '../lib/api'
import { BookBadge } from './BookBadge'
import { Empty, Section } from './ui'

const STAT_NAMES: Record<string, string> = {
  points: 'Points', rebounds: 'Rebounds', assists: 'Assists', threes: '3-pointers',
}
const BOOK_NAMES: Record<string, string> = { fanduel: 'FanDuel', draftkings: 'DraftKings', kalshi: 'Kalshi' }
const pct = (value: number | null) => value === null ? '—' : `${value.toFixed(1)}%`
const signed = (value: number | null, suffix = '', digits = 1) =>
  value === null ? '—' : `${value > 0 ? '+' : ''}${value.toFixed(digits)}${suffix}`
const tone = (value: number | null) => value === null || value === 0 ? '' : value > 0 ? 'text-good' : 'text-bad'

function Breakdown({ title, groups }: { title: string; groups: [string, MissMetrics][] }) {
  if (!groups.length) return null
  return <div className="min-w-0 rounded-2xl border border-line bg-raised px-3 py-2">
    <table className="w-full table-fixed text-left text-xs tabular-nums">
      <caption className="pb-2 pt-1 text-left text-sm font-bold">{title}</caption>
      <thead className="text-muted"><tr>
        <th scope="col" className="w-[32%] pb-2">Group</th>
        <th scope="col" className="pb-2 text-right">Picks</th>
        <th scope="col" className="pb-2 text-right">Hit</th>
        <th scope="col" className="pb-2 text-right">Even</th>
        <th scope="col" className="pb-2 text-right">ROI</th>
      </tr></thead>
      <tbody>{groups.map(([label, row]) => <tr key={label} className="border-t border-line">
        <th scope="row" className="py-2 pr-1 font-medium capitalize">{label}</th>
        <td className="text-right">{row.n}</td>
        <td className="text-right">{pct(row.win_pct)}</td>
        <td className="text-right">{pct(row.break_even_pct)}</td>
        <td className={`text-right font-semibold ${tone(row.roi_pct)}`}>{signed(row.roi_pct, '%')}</td>
      </tr>)}</tbody>
    </table>
  </div>
}

export function MissReport({ rows }: { rows: MissReportRow[] }) {
  const [bookChoice, setBook] = useState('fanduel')
  const [statChoice, setStat] = useState('points')
  const [modelChoice, setModel] = useState('')
  const books = [...new Set(rows.map((row) => row.book))]
  const book = books.includes(bookChoice) ? bookChoice : books[0]
  const stats = [...new Set(rows.filter((row) => row.book === book).map((row) => row.stat))]
  const stat = stats.includes(statChoice) ? statChoice : stats[0]
  const models = rows.filter((row) => row.book === book && row.stat === stat)
  const selected = models.find((row) => row.model === modelChoice) ?? models[0]
  const options = (values: string[], names: Record<string, string>) =>
    values.map((id) => <option key={id} value={id}>{names[id] ?? id}</option>)
  const selectClass = 'block min-h-11 w-full rounded-lg border border-line bg-ink px-2 text-sm font-semibold text-text'
  const statsCards = selected ? [
    { name: 'Graded picks', value: selected.n.toLocaleString(), color: '' },
    { name: 'Hit rate', value: pct(selected.win_pct), color: '' },
    { name: 'Break-even rate', value: pct(selected.break_even_pct), color: '' },
    { name: 'Flat-unit ROI', value: signed(selected.roi_pct, '%'), color: tone(selected.roi_pct) },
  ] : []
  return <Section title="What the misses say">
    {!selected ? <Empty title="No graded picks yet" hint="The breakdown appears when the settle job grades picks." /> :
      <div className="overflow-hidden rounded-3xl border border-line bg-raised">
        <div className="border-b border-line bg-linear-to-br from-accent/10 to-transparent px-4 py-4 sm:px-6">
          <div className="flex flex-wrap items-center gap-2 text-sm font-semibold">
            <BookBadge book={book} />
            <span>{STAT_NAMES[stat] ?? stat} · {selected.model_name}</span>
          </div>
          <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3">
            <label className="min-w-0 text-xs font-semibold text-muted">Book
              <select className={selectClass} value={book} onChange={(event) => setBook(event.target.value)}>
                {options(books, BOOK_NAMES)}
              </select>
            </label>
            <label className="min-w-0 text-xs font-semibold text-muted">Stat
              <select className={selectClass} value={stat} onChange={(event) => setStat(event.target.value)}>
                {options(stats, STAT_NAMES)}
              </select>
            </label>
            <label className="col-span-2 min-w-0 text-xs font-semibold text-muted sm:col-span-1">Model
              <select className={selectClass} value={selected.model} onChange={(event) => setModel(event.target.value)}>
                {models.map((row) => <option key={row.model} value={row.model}>{row.model_name}</option>)}
              </select>
            </label>
          </div>
        </div>
        <div key={`${book}:${stat}:${selected.model}`} className="miss-reveal space-y-4 px-4 py-4 sm:px-6">
          <dl className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            {statsCards.map(({ name, value, color }) => <div key={name} className="rounded-xl bg-ink px-3 py-2.5">
              <dt className="text-xs font-semibold text-muted">{name}</dt>
              <dd className={`mt-0.5 text-2xl font-black tabular-nums ${color}`}>{value}</dd>
            </div>)}
          </dl>
          <div>
            <div className="relative h-2 rounded-full bg-line" aria-hidden="true">
              <div className="h-full rounded-full bg-accent" style={{ width: `${selected.win_pct}%` }} />
              {selected.break_even_pct !== null && <span className="absolute -top-1 h-4 w-0.5 bg-warn"
                style={{ left: `${selected.break_even_pct}%` }} />}
            </div>
            <p className="mt-2 text-xs text-muted">
              Blue is hit rate. Gold marks the break-even rate at the recorded prices, assuming an equal hit chance across picks.
              {' '}Return is {signed(selected.units, ' units', 2)} at one unit per pick, before fees.
            </p>
          </div>
          <div className="grid min-w-0 gap-2 lg:grid-cols-2">
            <Breakdown title="Over and under" groups={Object.entries(selected.sides)} />
            <Breakdown title="By price" groups={Object.entries(selected.prices)} />
          </div>
          <div className="border-t border-line pt-3 text-sm">
            <p>Actual minus projection on graded picks <strong>{signed(selected.miss, '', 2)}</strong></p>
            <p className="mt-1 text-xs text-muted">
              {selected.disagreement
                ? `Across ${selected.disagreement.n.toLocaleString()} settled lines, ${signed(100 * selected.disagreement.share, '%', 0)} of the projection’s difference from the line showed up in the result (approx. ±${Math.round(100 * selected.disagreement.plus_minus)} percentage points).`
                : 'The projection comparison needs at least 30 distinct settled lines with usable observations.'}
            </p>
          </div>
        </div>
      </div>}
  </Section>
}
