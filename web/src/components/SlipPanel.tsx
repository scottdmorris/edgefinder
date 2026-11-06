import { useEffect, useState } from 'react'
import { api, type Leg, type Market, type SlipPrice } from '../lib/api'
import { american, money } from '../lib/ladder'
import { Photo } from './ui'

// The slip. On a wide screen it sits beside the props and stays in view; on a phone it is a bar
// along the bottom that opens into a sheet. Its numbers come from the API (the same maths as the
// Python builder, correlations included).
export function SlipPanel({ market, legs, legsById, onRemove, onClear }: {
  market: Market
  legs: number[]
  legsById: Map<number, Leg>
  onRemove: (id: number) => void
  onClear: () => void
}) {
  const [stake, setStake] = useState(10)
  const [priced, setPrice] = useState<SlipPrice | null>(null)
  const [failed, setError] = useState<string | null>(null)
  const [sheet, setSheet] = useState(false)

  useEffect(() => {
    if (!legs.length) return
    let live = true
    const timer = setTimeout(() => {
      api.slip(market, legs, stake).then((p) => { if (live) { setPrice(p); setError(null) } })
        .catch((e: Error) => live && setError(e.message))
    }, 150)
    return () => { live = false; clearTimeout(timer) }
  }, [market.date, market.book, market.model, legs.join(','), stake]) // eslint-disable-line react-hooks/exhaustive-deps

  // an empty slip shows nothing priced, whatever the last answer was
  const price = legs.length ? priced : null
  const error = legs.length ? failed : null

  const body = (
    <div>
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-lg font-extrabold">Your slip</h2>
        {legs.length > 0 && <button type="button" onClick={onClear} className="text-xs font-semibold text-muted hover:text-text">Clear</button>}
      </div>
      {legs.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-line px-5 py-8 text-center">
          <div className="font-bold">Your slip is empty</div>
          <div className="mt-1 text-sm text-muted">Tap Yes or No on any prop, or use an idea.</div>
        </div>
      ) : (
        <>
          <div className="space-y-2">
            {legs.map((id) => {
              const leg = legsById.get(id)!
              return (
                <div key={id} className="rise flex items-center gap-3 rounded-2xl border border-line bg-raised p-2.5">
                  <Photo src={leg.photo} size={40} />
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-sm font-bold">{leg.player}</div>
                    <div className="truncate text-xs text-muted">{leg.bet} · {leg.game_short}</div>
                  </div>
                  <span className="text-sm font-bold">{american(leg.odds)}</span>
                  <button type="button" aria-label={`Remove ${leg.player}`} onClick={() => onRemove(id)}
                    className="grid size-9 place-items-center rounded-full text-muted hover:bg-raised-2 hover:text-text">✕</button>
                </div>
              )
            })}
          </div>

          <label className="mt-4 block text-xs font-semibold uppercase tracking-wider text-muted" htmlFor="stake">Stake</label>
          <div className="mt-1.5 flex items-center rounded-full border border-line bg-raised px-4">
            <span className="text-muted">$</span>
            <input id="stake" type="number" inputMode="decimal" min={0} step={1} value={stake}
              onChange={(e) => setStake(Math.max(0, Number(e.target.value) || 0))}
              className="min-h-11 w-full bg-transparent px-2 font-bold outline-none" />
          </div>

          {error && <div className="mt-3 rounded-xl border border-bad/50 px-3 py-2 text-sm text-bad">{error}</div>}
          {price && !error && (
            <div className="mt-4 rounded-2xl border border-line bg-raised p-4">
              <div className="text-[11px] font-semibold uppercase tracking-wider text-muted">{legs.length === 1 ? 'Single bet' : `${legs.length}-leg parlay`}</div>
              <div className="mt-1 text-3xl font-black">To win {money(price.to_win)}</div>
              <div className="mt-3 grid grid-cols-2 gap-3 text-sm">
                <Fact label="Chance it hits" value={`${price.chance_pct?.toFixed(1)}% (${price.one_in})`} />
                <Fact label="Total return" value={money(price.total_return)} />
                <Fact label="Fair price" value={price.fair_american !== undefined ? american(price.fair_american) : '–'} />
                <Fact label="Average result" value={money(price.expected)} good={(price.expected ?? 0) > 0} />
              </div>
              <p className="mt-3 text-xs leading-relaxed text-muted">{price.verdict}</p>
            </div>
          )}
        </>
      )}
    </div>
  )

  return (
    <>
      <aside className="hidden lg:block">
        <div className="sticky top-4">{body}</div>
      </aside>

      {/* phones and tablets: a bar along the bottom that opens into a sheet */}
      <div className="lg:hidden">
        {legs.length > 0 && !sheet && (
          <button type="button" onClick={() => setSheet(true)}
            className="fixed inset-x-3 bottom-3 z-40 flex min-h-14 items-center justify-between rounded-full bg-button px-5 font-bold text-button-text shadow-2xl">
            <span>{legs.length} {legs.length === 1 ? 'bet' : 'bets'}</span>
            <span>{price?.to_win !== undefined ? `To win ${money(price.to_win)}` : 'Open slip'}</span>
          </button>
        )}
        {sheet && (
          <div className="fixed inset-0 z-50 flex items-end bg-black/60" onClick={() => setSheet(false)}>
            <div className="max-h-[85vh] w-full overflow-y-auto rounded-t-3xl border-t border-line bg-ink p-5 pb-8"
              onClick={(e) => e.stopPropagation()}>
              <div className="mx-auto mb-4 h-1.5 w-10 rounded-full bg-line" />
              {body}
              <button type="button" onClick={() => setSheet(false)}
                className="mt-4 min-h-11 w-full rounded-full border border-line font-semibold">Keep browsing</button>
            </div>
          </div>
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
