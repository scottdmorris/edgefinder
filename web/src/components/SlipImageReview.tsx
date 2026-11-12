import { useEffect, useRef, useState } from 'react'
import { api, type Leg, type Market, type SlipMatches, type SlipReviewResult } from '../lib/api'
import { american } from '../lib/ladder'

type Props = { market: Market; legs: Map<number, Leg>; onApply: (ids: number[]) => void }
export function SlipImageReview(props: Props) {
  return <Panel key={`${props.market.date}|${props.market.book}|${props.market.model}`} {...props} />
}

function Panel({ market, legs, onApply }: Props) {
  const [files, setFiles] = useState<File[]>([])
  const [text, setText] = useState('')
  const [matches, setMatches] = useState<SlipMatches | null>(null)
  const [ids, setIds] = useState<number[]>([])
  const [confirmed, setConfirmed] = useState(false)
  const [review, setReview] = useState<SlipReviewResult | null>(null)
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const [search, setSearch] = useState('')
  const [manual, setManual] = useState('')
  const epoch = useRef(0)
  useEffect(() => () => { epoch.current += 1 }, [])
  function reset() { epoch.current += 1; setBusy(''); setReview(null); setConfirmed(false); setError('') }
  async function work(label: string, fn: () => Promise<void>) {
    setBusy(label); setError('')
    try { await fn() } catch (e) { setError(e instanceof Error ? e.message : 'Request failed.') }
    finally { setBusy('') }
  }
  function select(next: number[]) { reset(); setIds([...new Set(next)]) }
  const choices = [...legs.values()].filter((l) => search && `${l.player} ${l.bet}`.toLowerCase().includes(search.toLowerCase())).slice(0, 50)
  const current = ids.every((id) => legs.has(id))
  const buttonClass = 'min-h-11 rounded-lg border border-line px-3 text-sm font-semibold disabled:opacity-40'
  return <details className="mt-4 border-y border-line py-3">
    <summary className="cursor-pointer text-sm font-semibold">Review a slip from photos <span className="ml-2 text-xs font-normal text-muted">Local · No API key</span></summary>
    <div className="mt-4 space-y-3">
      <p className="text-xs text-muted">Upload up to 5 PNG, JPG or WebP images. Maximum 8 MB each, 20 MB total. Images are read on this computer and discarded after extraction.</p>
      <input aria-label="Slip images" type="file" accept="image/png,image/jpeg,image/webp" multiple disabled={!!busy}
        onChange={(e) => { reset(); setFiles(Array.from(e.target.files ?? [])); setText(''); setMatches(null); setIds([]) }} className="block max-w-full text-sm" />
      <button type="button" className={buttonClass} disabled={!files.length || !!busy} onClick={() => {
        if (files.length > 5 || files.some((f) => f.size > 8 * 1024 * 1024) || files.reduce((n, f) => n + f.size, 0) > 20 * 1024 * 1024) { setError('Choose at most 5 images, 8 MB each and 20 MB total.'); return }
        const ticket = ++epoch.current
        void work('Reading images…', async () => {
          const result = await api.readSlip(files)
          if (ticket !== epoch.current) return
          setText(result.images.map((image, i) => `Image ${i + 1}\n${image.text}`).join('\n\n'))
          setMatches(null); setIds([]); setConfirmed(false); setReview(null)
          if (result.images.some((image) => image.low_confidence || !image.lines)) setError('Some text was unclear or unreadable. Correct it below before matching.')
        })
      }}>Read images</button>
      <label className="block text-xs font-semibold">Extracted text · edit or paste
        <textarea value={text} maxLength={25000} rows={6} disabled={!!busy} onChange={(e) => { reset(); setText(e.target.value); setMatches(null); setIds([]) }}
          className="mt-1 w-full rounded-lg border border-line bg-ink p-3 text-sm font-normal" />
      </label>
      <button type="button" className={buttonClass} disabled={!text.trim() || !!busy} onClick={() => {
        const ticket = ++epoch.current
        void work('Matching lines…', async () => {
          const result = await api.matchSlip(market, text)
          if (ticket !== epoch.current) return
          setMatches(result); setReview(null); setConfirmed(false)
          setIds([...new Set(result.matches.flatMap((m) => m.candidate_ids.length === 1 ? m.candidate_ids : []))])
        })
      }}>Find matching legs</button>
      {matches && <div className="space-y-2 text-xs text-muted">
        <p>{matches.note}</p>
        {!matches.matches.length && <p>No players matched. Correct the text or select lines below.</p>}
        {matches.matches.map((m, i) => <div key={i} className="border-l-2 border-line pl-3"><b className="text-text">{m.player} · {m.status}</b><p>{m.text}</p></div>)}
      </div>}
      {(matches || text) && <>
        <div className="border-t border-line pt-3">
          <label className="text-xs">Add or correct a leg
            <input type="search" value={search} disabled={!!busy} onChange={(e) => { setSearch(e.target.value); setManual('') }} placeholder="Search player or prop" className="mt-1 block min-h-10 w-full rounded-lg bg-raised px-3 text-sm" />
          </label>
          {search && <div className="mt-2 flex gap-2">
            <select aria-label="Recorded prop" disabled={!!busy} value={manual} onChange={(e) => setManual(e.target.value)} className="min-h-11 min-w-0 flex-1 rounded-lg border border-line bg-ink text-sm">
              <option value="">Choose a recorded line</option>{choices.map((l) => <option key={l.id} value={l.id}>{l.player} · {l.bet} · {american(l.odds)}</option>)}
            </select>
            <button type="button" className={buttonClass} disabled={!manual || !!busy || ids.length >= 12} onClick={() => select([...ids, Number(manual)])}>Add</button>
          </div>}
        </div>
        <div className="divide-y divide-line">{ids.map((id) => <div key={id} className="flex items-center justify-between gap-2 py-2 text-sm">
          <span>{legs.get(id)?.player ?? 'Unavailable quote'} · {legs.get(id)?.bet} <span className="text-muted">{legs.has(id) ? american(legs.get(id)!.odds) : ''}</span></span>
          <button type="button" disabled={!!busy} className="min-h-11 px-2 text-muted" onClick={() => select(ids.filter((i) => i !== id))} aria-label={`Remove reviewed ${legs.get(id)?.player ?? 'leg'}`}>×</button>
        </div>)}</div>
        {!current && <p role="alert" className="text-xs text-warn">Quotes changed. Match the text again.</p>}
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={confirmed} disabled={!!busy} onChange={(e) => { setConfirmed(e.target.checked); setReview(null) }} />I checked every selected player, stat, side and line against my slip.</label>
        <button type="button" className={buttonClass} disabled={!confirmed || !ids.length || ids.length > 12 || !current || !!busy} onClick={() => {
          const ticket = ++epoch.current
          void work('Reviewing with Python…', async () => { const result = await api.reviewSlip(market, ids, true); if (ticket === epoch.current) setReview(result) })
        }}>Review confirmed slip</button>
      </>}
      {busy && <p role="status" className="text-sm text-muted">{busy}</p>}
      {error && <p role="alert" className="text-sm text-warn">{error}</p>}
      {review && current && <div className="space-y-3 border-t border-line pt-3">
        <p className="font-semibold">{review.chance_pct}% estimated chance · {review.ev_pct}% estimated EV</p>
        {review.legs.map((leg) => <div key={leg.id} className="text-sm"><b>{leg.player} · {leg.assessment}</b>
          <p className="text-xs text-muted">{leg.bet} · Projection {leg.projection ?? '–'} · {leg.chance_pct}% chance · {leg.ev_pct}% EV</p>
          <p className="mt-1 text-xs text-muted">{leg.reason}{leg.without_chance_pct !== null && ` Without this leg: ${leg.without_chance_pct}% chance.`}</p>
          <button type="button" className="min-h-9 text-xs text-accent" onClick={() => select(ids.filter((id) => id !== leg.id))}>Remove from reviewed slip</button>
        </div>)}
        <p className="text-sm font-semibold">Possible additions from other games</p>
        {!review.additions.length && <p className="text-xs text-muted">No qualifying additions on this board.</p>}
        {review.additions.map((leg) => <div key={leg.id} className="text-xs"><b>{leg.player} · {leg.bet}</b><p className="text-muted">{leg.ev_pct}% estimated EV · With this leg: {leg.with_chance_pct}% slip chance</p>
          <button type="button" className="min-h-9 text-accent" onClick={() => select([...ids, leg.id])}>Add and re-review</button></div>)}
        <details className="text-xs text-muted"><summary className="cursor-pointer">Review assumptions</summary>{review.notes.map((note) => <p key={note} className="mt-1">{note}</p>)}</details>
        <button type="button" className={buttonClass} onClick={() => onApply(ids)}>Use reviewed slip</button>
      </div>}
    </div>
  </details>
}
