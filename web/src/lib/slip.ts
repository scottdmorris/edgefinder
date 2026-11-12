// One saved slip per market. Quote snapshots remain reviewable when a board changes.
import { useCallback, useEffect, useRef, useState } from 'react'
import type { Leg, SlipPrice } from './api'

const KEY = 'bk-slip-v2'
const marketKey = (market: string) => `${KEY}:${market}`
export type SavedEstimate = { price: SlipPrice; recordedAt: number }
type Slip = { market: string | null; legs: number[]; snapshots: Record<number, Leg>; estimate?: SavedEstimate }

function read(market: string | null): Slip {
  const empty = { market, legs: [], snapshots: {} }
  if (!market) return empty
  try {
    const stored = JSON.parse(localStorage.getItem(marketKey(market)) ?? localStorage.getItem(KEY) ?? 'null') as Slip | null
    return stored && stored.market === market && Array.isArray(stored.legs)
      ? { ...stored, snapshots: stored.snapshots ?? {} } : empty
  } catch { return empty }
}

/** Active slip for Live; per-market slips stay available when switching back in Parlay. */
export function savedSlip() {
  try {
    const stored = JSON.parse(localStorage.getItem(KEY) ?? 'null') as Slip | null
    if (!stored?.market || !Array.isArray(stored.legs) || !stored.legs.length) return null
    const [date, book, model] = stored.market.split('|')
    return { market: { date, book, model }, legs: stored.legs, snapshots: stored.snapshots ?? {}, estimate: stored.estimate }
  } catch { return null }
}

export function useSlip(market: string | null, legsById: Map<number, Leg>) {
  const [slip, setSlip] = useState<Slip>(() => read(market))
  if (slip.market !== market) setSlip(read(market))
  // Live tracks the slip you last changed, not whichever market you last looked at
  const touched = useRef<string | null>(null)

  useEffect(() => {
    if (!slip.market) return
    try {
      const stored = JSON.stringify(slip)
      localStorage.setItem(marketKey(slip.market), stored)
      const active = savedSlip()
      const mine = active && `${active.market.date}|${active.market.book}|${active.market.model}` === slip.market
      if (touched.current === slip.market || mine || !active) localStorage.setItem(KEY, stored)
    } catch { /* Storage blocked or full: keep this session usable. */ }
  }, [slip])

  const toggle = useCallback((id: number) => {
    touched.current = market
    setSlip((current) => {
      if (current.legs.includes(id)) return { ...current, estimate: undefined, legs: current.legs.filter((other) => other !== id) }
      const leg = legsById.get(id)
      if (!leg) return current
      const sameBet = (other: number) => {
        const existing = legsById.get(other) ?? current.snapshots[other]
        return existing?.player_id === leg.player_id && existing?.stat === leg.stat
      }
      return { ...current, estimate: undefined,
        legs: [...current.legs.filter((other) => !sameBet(other)), id],
        snapshots: { ...current.snapshots, [id]: leg } }
    })
  }, [legsById, market])

  const set = useCallback((legs: number[]) => { touched.current = market; setSlip((current) => ({
    ...current, legs, estimate: undefined,
    snapshots: Object.fromEntries(legs.flatMap((id) => {
      const leg = legsById.get(id) ?? current.snapshots[id]
      return leg ? [[id, leg]] : []
    })),
  })) }, [legsById, market])
  const clear = useCallback(() => set([]), [set])
  const rememberEstimate = useCallback((price: SlipPrice, ids: number[]) => {
    setSlip((current) => current.estimate || current.legs.join(',') !== ids.join(',') ? current
      : { ...current, estimate: { price, recordedAt: Date.now() } })
  }, [])
  const ids = slip.market === market ? slip.legs : []
  const legs = ids.filter((id) => legsById.has(id))
  const unavailable = ids.filter((id) => !legsById.has(id)).map((id) => ({ id, leg: slip.snapshots[id] }))
  // the same bet at a different price than when it was added
  const moved = legs.flatMap((id) => {
    const was = slip.snapshots[id]?.odds, now = legsById.get(id)!
    return was !== undefined && was !== now.odds ? [{ id, player: now.player, was, now: now.odds }] : []
  })
  return { legs, toggle, set, clear, unavailable, moved, estimate: slip.estimate, rememberEstimate }
}
