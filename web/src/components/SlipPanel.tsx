import { useEffect, useId, useLayoutEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { api, type Leg, type Market, type SlipPrice } from '../lib/api'
import { american, money } from '../lib/ladder'
import { Photo } from './ui'

// The slip. On a wide screen it sits beside the props and stays in view; on a phone it is a bar
// along the bottom that opens into a sheet. Its numbers come from the API (the same maths as the
// Python builder, correlations included).
export function SlipPanel({ market, legs, legsById, onRemove, onClear, onPriced, revision = 0 }: {
  market: Market
  legs: number[]
  legsById: Map<number, Leg>
  onRemove: (id: number) => void
  onClear: () => void
  onPriced?: (price: SlipPrice, ids: number[]) => void
  revision?: number
}) {
  const [stake, setStake] = useState(10)
  const [priced, setPrice] = useState<{ key: string; value: SlipPrice } | null>(null)
  const [failed, setError] = useState<{ key: string; message: string } | null>(null)
  const [sheet, setSheet] = useState(false)
  const fieldId = useId()
  const dialogRef = useRef<HTMLDialogElement>(null)
  const openerRef = useRef<HTMLButtonElement>(null)
  const closeRef = useRef<HTMLButtonElement>(null)

  const quoteKey = JSON.stringify([market.date, market.book, market.model, revision, legs.map(id => {
    const leg = legsById.get(id)
    return [id, leg?.odds, leg?.model_pct, leg?.market_pct, leg?.chance_pct]
  }), stake])

  useLayoutEffect(() => {
    if (!sheet) return
    const dialog = dialogRef.current!
    const opener = openerRef.current
    const overflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    // showModal supplies top-layer rendering, background inertness and native focus containment.
    dialog.showModal()
    closeRef.current?.focus()
    const desktop = window.matchMedia('(min-width: 1024px)')
    const closeOnDesktop = () => { if (desktop.matches) setSheet(false) }
    desktop.addEventListener('change', closeOnDesktop)
    closeOnDesktop()
    return () => {
      desktop.removeEventListener('change', closeOnDesktop)
      dialog.close()
      document.body.style.overflow = overflow
      opener?.focus()
    }
  }, [sheet])

  useEffect(() => {
    if (!legs.length) return
    let live = true
    const timer = setTimeout(() => {
      api.slip(market, legs, stake).then((p) => { if (live) { setPrice({ key: quoteKey, value: p }); setError(null); onPriced?.(p, legs) } })
        .catch((e: Error) => live && setError({ key: quoteKey, message: e.message }))
    }, 150)
    return () => { live = false; clearTimeout(timer) }
  }, [quoteKey, onPriced]) // eslint-disable-line react-hooks/exhaustive-deps

  // an empty slip shows nothing priced, whatever the last answer was
  const price = legs.length && priced?.key === quoteKey ? priced.value : null
  const error = legs.length && failed?.key === quoteKey ? failed.message : null

  const body = (surface: 'desktop' | 'mobile') => (
    <div>
      <div className="mb-3 flex items-center justify-between">
        <h2 id={`${fieldId}-${surface}-title`} className="text-lg font-extrabold">Your slip</h2>
        {legs.length > 0 && <button type="button" onClick={onClear} className="text-xs font-semibold text-muted hover:text-text">Clear</button>}
      </div>
      {legs.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-line px-5 py-8 text-center">
          <div className="font-bold">Your slip is empty</div>
          <div className="mt-1 text-sm text-muted">Choose a player's line and tap a price.</div>
        </div>
      ) : (
        <>
          <div className="divide-y divide-line border-y border-line">
            {legs.map((id) => {
              const leg = legsById.get(id)!
              return (
                <div key={id} className="flex items-center gap-2 py-3">
                  <Photo src={leg.photo} size={30} />
                  <div className="min-w-0 flex-1">
                    <div className="break-words text-sm font-bold">{leg.player}</div>
                    <div className="break-words text-xs text-muted">{leg.bet} · {leg.game_short}</div>
                  </div>
                  <span className="shrink-0 text-sm font-bold">{american(leg.odds)}</span>
                  <button type="button" aria-label={`Remove ${leg.player}`} onClick={() => onRemove(id)}
                    className="grid size-9 shrink-0 place-items-center rounded-full text-muted hover:bg-raised-2 hover:text-text">✕</button>
                </div>
              )
            })}
          </div>

          <label className="mt-4 block text-xs font-semibold uppercase tracking-wider text-muted" htmlFor={`${fieldId}-${surface}-stake`}>Stake</label>
          <div className="mt-1.5 flex items-center rounded-full border border-line bg-raised px-4">
            <span className="text-muted">$</span>
            <input id={`${fieldId}-${surface}-stake`} type="number" inputMode="decimal" min={0} step={1} value={stake}
              onChange={(e) => setStake(Math.max(0, Number(e.target.value) || 0))}
              className="min-h-11 w-full bg-transparent px-2 font-bold outline-none" />
          </div>

          {!price && !error && <p role="status" className="mt-3 text-sm text-muted">Recalculating estimate…</p>}
          {error && <div className="mt-3 rounded-xl border border-bad/50 px-3 py-2 text-sm text-bad">{error}</div>}
          {price && !error && (
            <div className="mt-4 border-t border-line py-4">
              <div className="text-[11px] font-semibold uppercase tracking-wider text-muted">{legs.length === 1 ? 'Single bet' : `${legs.length}-leg parlay`}</div>
              <div className="mt-1 text-xl font-bold">Estimated profit {money(price.to_win)}</div>
              <div className="mt-3 grid grid-cols-2 gap-3 text-sm">
                <Fact label="Estimated chance all hit" value={`${price.chance_pct?.toFixed(1)}% (${price.one_in})`} />
                <Fact label="Total return" value={money(price.total_return)} />
              </div>
              <p className="mt-3 text-xs text-muted">Recorded-price estimate · Before fees</p>
              <details className="mt-2 text-xs text-muted"><summary className="cursor-pointer py-1">Calculation details</summary>
                <div className="mt-2 grid grid-cols-2 gap-3">
                  <Fact label="Fair price" value={price.fair_american !== undefined ? american(price.fair_american) : '–'} />
                  <Fact label="Expected result before fees" value={money(price.expected)} good={(price.expected ?? 0) > 0} />
                </div>
                <p className="mt-3">Illustration using multiplied individual prices, not a quoted combined payout. Same-game pricing can differ. {market.book === 'kalshi' ? 'Kalshi trading fees are excluded.' : 'Check the actual combined quote.'} Expected result is a model estimate, not a promised return.</p>
              </details>
            </div>
          )}
        </>
      )}
    </div>
  )

  return (
    <>
      <aside className="hidden lg:block">
        <div className="sticky top-4">{body('desktop')}</div>
      </aside>

      {/* phones and tablets: a bar along the bottom that opens into a sheet */}
      <div className="lg:hidden">
        <button ref={openerRef} type="button" aria-haspopup="dialog" aria-expanded={sheet} onClick={() => setSheet(true)}
            style={{ display: legs.length === 0 && !sheet ? 'none' : undefined, bottom: 'max(0.75rem, env(safe-area-inset-bottom))' }}
            className="fixed inset-x-3 z-40 flex min-h-14 items-center justify-between rounded-full bg-button px-5 font-bold text-button-text shadow-2xl">
            <span>{legs.length} {legs.length === 1 ? 'bet' : 'bets'}</span>
            <span>{!error && price?.to_win !== undefined ? `Est. profit ${money(price.to_win)}` : 'Open slip'}</span>
          </button>
        {sheet && createPortal(
          <dialog ref={dialogRef} aria-labelledby={`${fieldId}-mobile-title`}
            onCancel={(event) => { event.preventDefault(); setSheet(false) }}
            onClose={() => setSheet(false)}
            onKeyDown={(event) => {
              if (event.key !== 'Tab') return
              const controls = [...event.currentTarget.querySelectorAll<HTMLElement>(
                'button:not(:disabled), input:not(:disabled), select:not(:disabled), a[href], summary, [tabindex="0"]',
              )].filter((element) => element.getClientRects().length > 0)
              const first = controls[0], last = controls.at(-1)
              if (!first) { event.preventDefault(); return }
              if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus() }
              else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() }
            }}
            onClick={(event) => { if (event.target === event.currentTarget) setSheet(false) }}
            className="fixed inset-x-0 bottom-0 top-auto m-0 max-h-[85dvh] w-full max-w-none overflow-y-auto rounded-t-3xl border-t border-line bg-ink text-text backdrop:bg-black/60">
            <div className="p-5" style={{ paddingBottom: 'max(2rem, env(safe-area-inset-bottom))' }}>
              <div className="mx-auto mb-4 h-1.5 w-10 rounded-full bg-line" />
              {body('mobile')}
              <button ref={closeRef} type="button" onClick={() => setSheet(false)}
                className="mt-4 min-h-11 w-full rounded-full border border-line font-semibold">Keep browsing</button>
            </div>
          </dialog>, document.body
        )}
      </div>
    </>
  )
}

function Fact({ label, value, good }: { label: string; value: string; good?: boolean }) {
  return (
    <div>
      <div className="text-[11px] text-muted">{label}</div>
      <div className={`font-bold ${good ? 'text-good' : ''}`}>{value}</div>
    </div>
  )
}
