// The slip: which legs are on it, kept in this browser between visits. One bet per player per
// stat (adding a second price for the same number replaces the first), like the Python builder.
// Each slip belongs to one market (day | price source | model): leg ids mean nothing elsewhere.
import { useCallback, useEffect, useState } from 'react'
import type { Leg } from './api'

const KEY = 'bk-slip'

type Slip = { market: string | null; legs: number[] }

function read(market: string | null): number[] {
  if (!market) return []
  try {
    const stored = JSON.parse(localStorage.getItem(KEY) ?? 'null') as Slip | null
    return stored && stored.market === market && Array.isArray(stored.legs) ? stored.legs : []
  } catch {
    return []
  }
}

/** The slip saved in this browser and the market it belongs to, for the Live screen to track. */
export function savedSlip(): { market: { date: string; book: string; model: string }; legs: number[] } | null {
  try {
    const stored = JSON.parse(localStorage.getItem(KEY) ?? 'null') as Slip | null
    if (!stored?.market || !Array.isArray(stored.legs) || !stored.legs.length) return null
    const [date, book, model] = stored.market.split('|')
    return { market: { date, book, model }, legs: stored.legs }
  } catch {
    return null
  }
}

/** `market` is null until the board has loaded; nothing is read or saved before then. */
export function useSlip(market: string | null, legsById: Map<number, Leg>) {
  const [slip, setSlip] = useState<Slip>(() => ({ market, legs: read(market) }))

  // a different market means different legs: load that market's slip (React's
  // "adjust state while rendering" pattern, so the old legs never pair with the new market)
  if (slip.market !== market) setSlip({ market, legs: read(market) })

  useEffect(() => {
    if (!slip.market) return
    try {
      localStorage.setItem(KEY, JSON.stringify(slip))
    } catch {
      /* private mode or storage blocked: the slip just won't survive a reload */
    }
  }, [slip])

  const toggle = useCallback((id: number) => {
    setSlip((current) => {
      if (current.legs.includes(id)) return { ...current, legs: current.legs.filter((x) => x !== id) }
      const leg = legsById.get(id)
      if (!leg) return current
      const sameBet = (other: number) => {
        const o = legsById.get(other)
        return o !== undefined && o.player_id === leg.player_id && o.stat === leg.stat
      }
      return { ...current, legs: [...current.legs.filter((x) => !sameBet(x)), id] }
    })
  }, [legsById])

  const set = useCallback((legs: number[]) => setSlip((current) => ({ ...current, legs })), [])
  const clear = useCallback(() => set([]), [set])
  const legs = slip.market === market ? slip.legs.filter((id) => legsById.has(id)) : []

  return { legs, toggle, set, clear }
}
