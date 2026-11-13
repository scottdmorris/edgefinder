// One suggested slip, front and centre: its legs, the chance they all hit, and what it pays.
// The style switch changes how safe it is; "Another" steps through the other suggestions.
import { useState } from 'react'
import type { Idea, Leg } from '../lib/api'
import { american, money } from '../lib/ladder'
import { Photo } from './ui'

const EXAMPLE_STAKE = 10

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
          <div className="text-xs text-muted">{sameGame ? 'Same game' : 'One leg per game'}{ideas && ideas.length > 1 && ` · ${(at % ideas.length) + 1} of ${ideas.length}`}</div>
        </div>
        <div className="flex gap-1 rounded-full border border-line p-1" role="radiogroup" aria-label="Style">
          {styles.map((name) => (
            <button key={name} type="button" role="radio" aria-checked={name === style} onClick={() => onStyle(name)}
              className={`min-h-9 rounded-full px-3 text-xs font-bold transition-colors ${name === style ? 'bg-button text-button-text' : 'text-muted hover:text-text'}`}>
              {name}
            </button>
          ))}
        </div>
      </div>

      {ideas === null && <div className="mt-3 h-32 animate-pulse rounded-2xl bg-raised-2" />}
      {ideas?.length === 0 && <p className="mt-4 text-sm text-muted">Nothing fits this style here. Try a bigger-payout style or another game.</p>}
      {idea && (
        <div key={idea.legs.join(',')} className="rise">
          <div className="mt-3 divide-y divide-line">
            {idea.legs.map((id) => {
              const leg = legs.get(id)
              if (!leg) return null
              return (
                <div key={id} className="flex items-center gap-3 py-2">
                  <Photo src={leg.photo} size={40} />
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-sm font-bold">{leg.player} <span className="font-semibold text-muted">· {leg.bet}</span></div>
                    <div className="truncate text-xs text-muted">{leg.game_short}{leg.average?.season != null && ` · averages ${leg.average.season}`}</div>
                  </div>
                  <div className="shrink-0 rounded-full border border-line px-2.5 py-1 text-xs font-bold tabular-nums">{american(leg.odds)}</div>
                </div>
              )
            })}
          </div>
          <div className="mt-3 flex flex-wrap items-end justify-between gap-3">
            <div className="flex gap-6">
              <Figure value={`${idea.chance_pct.toFixed(0)}%`} label="to hit" />
              <Figure value={money(idea.pays * EXAMPLE_STAKE)} label={`back on $${EXAMPLE_STAKE}, before fees`} />
            </div>
            <div className="flex gap-2">
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
