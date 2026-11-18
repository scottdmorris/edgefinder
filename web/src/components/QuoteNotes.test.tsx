// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, expect, it } from 'vitest'
import type { BookComparison, QuoteQuality } from '../lib/api'
import { comparisonWord } from '../lib/quoteWords'
import { QuoteNotes } from './QuoteNotes'

afterEach(cleanup)

const quality: QuoteQuality = {
  eligible: false, warnings: ['Price not checked in the last 90 minutes'], history_games: 20, recent_hit_pct: 65,
  historical_low: 12, historical_high: 41, price_at: '2026-11-15T22:00:16Z', price_age_minutes: 200,
  injuries: 'Injury status is not verified by these history checks',
}
const draftkings: BookComparison = { book: 'DraftKings', line: 23.5, odds: -104, fetched_at: '2026-11-15T22:00:16Z',
  stale: false, same_line: false, better_payout: false }

it('fits the history, the range and the other book on one short line', () => {
  render(<QuoteNotes quality={quality} comparisons={[draftkings]} side="Over" />)
  expect(screen.getByText('65%')).toBeTruthy()
  expect(screen.getByText('usually 12–41')).toBeTruthy()
  expect(screen.getByText(/Over 23.5 -104/)).toBeTruthy()
  expect(screen.getByText('· other number')).toBeTruthy()
})

it('flags a quote left out of suggestions and keeps the reasons behind a toggle', () => {
  const { container } = render(<QuoteNotes quality={quality} comparisons={[]} side="Over" />)
  expect(screen.getByText('Not suggested · why')).toBeTruthy()
  const details = container.querySelector('details')!
  expect(details.open).toBe(false)
  expect(details.textContent).toContain('Price not checked in the last 90 minutes')
  expect(details.textContent).toContain('Injury status is not verified')
})

it('calls a quote with no problems plain details, and shows nothing with no data', () => {
  render(<QuoteNotes quality={{ ...quality, warnings: [], eligible: true }} comparisons={[]} side="Over" />)
  expect(screen.getByText('Details')).toBeTruthy()
  cleanup()
  const { container } = render(<QuoteNotes quality={null} comparisons={[]} side="Over" />)
  expect(container.textContent).toBe('')
})

it('describes the other price in a word or two', () => {
  expect(comparisonWord({ ...draftkings, same_line: true, better_payout: true }).text).toBe('pays more there')
  expect(comparisonWord({ ...draftkings, same_line: true }).text).toBe('same or less there')
  expect(comparisonWord({ ...draftkings, stale: true }).text).toBe('old price')
})
