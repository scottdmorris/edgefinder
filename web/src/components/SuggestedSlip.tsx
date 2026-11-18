// One suggested slip, front and centre: its legs, the chance they all hit, and what it pays.
// The style switch changes how safe it is; "Another" steps through the other suggestions.
import { useState } from 'react'
import type { Idea, Leg } from '../lib/api'
import { american, money } from '../lib/ladder'
import { Photo, Pills } from './ui'

const EXAMPLE_STAKE = 10
const LONG_SHOT = 'Long shot'

/** What each style is, said once under the switch. */
const STYLE_NOTES: Record<string, string> = {
  'Higher hit rate': 'Higher hit rate uses at most two legs and seeks a 60%+ model estimate. That is a target to test, not a proven win rate.',
  [LONG_SHOT]: 'Long shot stacks 8 to 10 of the likeliest legs worth betting, at most two players a game, for a big payout. Every leg adds the book’s cut again: on last season’s markets slips like this lost money at real prices. It is tracked on paper in the Record tab. Kalshi usually has enough legs; FanDuel and DraftKings rarely do.',
}

export function SuggestedSlip({ ideas, legs, sameGame, styles, style, onStyle, inUse, onUse }: {
  /** null while the suggestions load */
  ideas: Idea[] | null
  legs: Map<number, Leg>
  sameGame: boolean
  styles: string[]
  style: string
  onStyle: (style: string) => void
  /** the legs on the slip now, to show when this suggestion is already the slip */
  inUse: number[]
  onUse: (legs: number[]) => void
}) {
  const [at, setAt] = useState(0)
  const idea = ideas?.length ? ideas[at % ideas.length] : null
  const using = idea !== null && idea.legs.length === inUse.length && idea.legs.every((id) => inUse.includes(id))
  return (
    <section className="mt-5 rounded-3xl border-2 border-accent/50 bg-raised p-4" aria-label="Suggested slip">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-lg font-extrabold">Suggested slip</h2>
          <div className="text-xs text-muted">{sameGame ? 'Same game' : style === LONG_SHOT ? 'Up to two players a game' : 'One leg per game'}{ideas && ideas.length > 1 && ` · ${(at % ideas.length) + 1} of ${ideas.length}`}</div>
        </div>
        <div className="min-w-0 max-w-full">
          <Pills label="Betting style" options={styles.map((name) => ({ id: name, label: name }))}
            value={style} onChange={onStyle} />
        </div>
      </div>

      {ideas === null && <div className="mt-3 h-32 animate-pulse rounded-2xl bg-raised-2" />}
      {ideas?.length === 0 && <p className="mt-4 text-sm text-muted">{style === LONG_SHOT && sameGame
        ? 'Long shot needs legs from several games; clear the game filter to see one.'
        : 'No qualifying slip right now. Passing is part of this style; do not add legs just to get a suggestion.'}</p>}
      {STYLE_NOTES[style] && <p className="mt-2 text-xs text-muted">{STYLE_NOTES[style]}</p>}
      {idea && (
        <div key={idea.legs.join(',')} className="rise">
          <p className="mt-2 text-xs text-muted">
            Break-even hit rate: {(idea.break_even_pct ?? 100 / idea.pays).toFixed(1)}% at this payout.
            {' '}{idea.price_basis ?? 'Simulated payout from recorded leg prices'}; an actual sportsbook parlay quote may differ.
            {' '}{idea.tracked_id ? `Recorded for paper grading: ${idea.tracked_id.slice(0, 8)}` : 'Not recorded as a pregame offer'}
          </p>
          <div className="mt-3 divide-y divide-line">
            {idea.legs.map((id) => {
              const leg = legs.get(id)
              if (!leg) return null
              return (
                <div key={id} className="flex items-center gap-3 py-2">
                  <Photo src={leg.photo} size={40} />
                  <div className="min-w-0 flex-1 [overflow-wrap:anywhere]">
                    <div className="text-sm font-bold">{leg.player} <span className="font-semibold text-muted">· {leg.bet}</span></div>
                    <div className="text-xs text-muted">{leg.game_short}{leg.average?.season != null && ` · averages ${leg.average.season}`}</div>
                  </div>
                  <div className="shrink-0 rounded-full border border-line px-2.5 py-1 text-xs font-bold tabular-nums">{american(leg.odds)}</div>
                </div>
              )
            })}
          </div>
          <div className="mt-3 flex flex-wrap items-end justify-between gap-3">
            <div className="flex flex-wrap gap-6">
              <Figure value={`${idea.chance_pct.toFixed(idea.chance_pct < 10 ? 1 : 0)}%`} label="estimated to hit" />
              <Figure value={money(idea.pays * EXAMPLE_STAKE)} label={`back on $${EXAMPLE_STAKE}, before fees`} />
            </div>
            <div className="flex flex-wrap gap-2">
              {ideas!.length > 1 && <button type="button" onClick={() => setAt((n) => n + 1)}
                className="min-h-11 rounded-full border border-line px-4 text-sm font-semibold hover:border-line-strong">Another</button>}
              <button type="button" aria-pressed={using} onClick={() => onUse(idea.legs)}
                className={`min-h-11 rounded-full px-5 text-sm font-bold ${using ? 'border border-line text-muted' : 'bg-button text-button-text'}`}>
                {using ? '✓ On your slip' : 'Use this slip'}
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  )
}

function Figure({ value, label }: { value: string; label: string }) {
  return (
    <div>
      <div className="text-2xl font-black tabular-nums">{value}</div>
      <div className="text-[11px] text-muted">{label}</div>
    </div>
  )
}
