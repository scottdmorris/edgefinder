// Turning the flat list of legs into what the screen shows: one row per player and stat, with
// the "at least" steps (10+ 15+ 20+) like Kalshi lists them. Mirrors the Python side's
// nba_parlay.ladder().
import type { Leg } from './api'

export type Step = { threshold: number; yes: Leg; no: Leg | null }
export type Row = { key: string; player: string; player_id: number; photo: string; game: string;
  game_short: string; stat: string; average: Leg['average']; steps: Step[] }

export function thresholdOf(leg: Leg): number {
  return leg.side.endsWith('+') ? parseInt(leg.side, 10) : Math.floor(leg.line) + 1
}

export function ladderRows(legs: Leg[]): Row[] {
  const rows = new Map<string, Row>()
  for (const leg of legs) {
    const key = `${leg.player_id}|${leg.stat}|${leg.game}`
    if (!rows.has(key)) {
      rows.set(key, { key, player: leg.player, player_id: leg.player_id, photo: leg.photo,
        game: leg.game, game_short: leg.game_short, stat: leg.stat, average: leg.average, steps: [] })
    }
  }
  for (const row of rows.values()) {
    const mine = legs.filter((l) => `${l.player_id}|${l.stat}|${l.game}` === row.key)
    const steps = new Map<number, Step>()
    for (const over of mine.filter((l) => l.side === 'Over')) {
      const under = mine.find((l) => l.side === 'Under' && l.line === over.line) ?? null
      steps.set(thresholdOf(over), { threshold: thresholdOf(over), yes: over, no: under })
    }
    for (const plus of mine.filter((l) => l.side.endsWith('+'))) {
      const t = thresholdOf(plus)
      if (!steps.has(t)) steps.set(t, { threshold: t, yes: plus, no: null })
    }
    row.steps = [...steps.values()].sort((a, b) => a.threshold - b.threshold)
  }
  // the biggest names first: the highest line a player is priced at
  return [...rows.values()].filter((r) => r.steps.length)
    .sort((a, b) => b.steps[b.steps.length - 1].threshold - a.steps[a.steps.length - 1].threshold)
}

// The step to show first: the one closest to a coin flip by the market's chance.
export function defaultStep(row: Row): Step {
  return row.steps.reduce((best, step) =>
    Math.abs((step.yes.market_pct ?? 50) - 50) < Math.abs((best.yes.market_pct ?? 50) - 50) ? step : best)
}

export function american(odds: number): string {
  return odds > 0 ? `+${odds}` : `${odds}`
}

export function money(amount: number | undefined): string {
  if (amount === undefined) return '–'
  const sign = amount < 0 ? '-' : ''
  return `${sign}$${Math.abs(amount).toFixed(2)}`
}
