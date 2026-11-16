// Small formatting helpers shared by the team page's sections.
import type { PropStat } from './api'

export const STAT_LABELS: Record<PropStat, string> = { pts: 'Points', reb: 'Rebounds', ast: 'Assists', fg3m: '3-pointers' }

/** "3rd" */
export function ordinal(n: number): string {
  const teen = n % 100 >= 11 && n % 100 <= 13
  const tail = teen ? 'th' : ({ 1: 'st', 2: 'nd', 3: 'rd' } as Record<number, string>)[n % 10] ?? 'th'
  return `${n}${tail}`
}
