// How a quote's comparison with the other sportsbook reads, in a word or two.
import type { BookComparison } from './api'

export function comparisonWord(other: BookComparison): { text: string; tone: string } {
  if (other.stale) return { text: 'old price', tone: 'text-muted' }
  if (!other.same_line) return { text: 'other number', tone: 'text-muted' }
  return other.better_payout ? { text: 'pays more there', tone: 'text-warn' } : { text: 'same or less there', tone: 'text-muted' }
}
