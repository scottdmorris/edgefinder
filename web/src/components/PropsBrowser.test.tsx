// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import type { Leg } from '../lib/api'
import { PropsBrowser } from './PropsBrowser'

afterEach(cleanup)
const over = { id: 1, player: 'Nikola Jokić', player_id: 7, photo: '', game: 'DEN @ BOS', game_short: 'DEN @ BOS',
  stat: 'points', stat_label: 'Points', side: 'Over', line: 24.5, bet: 'Over 24.5 points', odds: -110,
  market_pct: 52, model_pct: 60, chance_pct: 54, average: null } as Leg
const under = { ...over, id: 2, side: 'Under', bet: 'Under 24.5 points', market_pct: 48, model_pct: 40, chance_pct: 46 }
const rebound = { ...over, id: 3, stat: 'rebounds', side: '10+', line: 9.5, bet: '10+ rebounds' }
const other = { ...over, id: 4, player: 'Jaylen Brown', player_id: 8 }
const details = (name = 'Details for Nikola Jokić Points') => fireEvent.click(screen.getByRole('button', { name }))

it('combines accent-insensitive search, stat and selected filters', () => {
  render(<PropsBrowser legs={[over, under, rebound, other]} selected={[3]} toggle={vi.fn()} kalshi={false} />)
  fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'jokic' } })
  expect(screen.queryByText('Jaylen Brown')).toBeNull()
  fireEvent.click(screen.getByRole('radio', { name: 'Rebounds' }))
  fireEvent.click(screen.getByRole('checkbox'))
  expect(screen.getByRole('button', { name: 'At least Nikola Jokić 10+ Rebounds' })).toBeTruthy()
  fireEvent.click(screen.getByRole('radio', { name: 'Points' }))
  expect(screen.getByText('No matching props')).toBeTruthy()
})

it('shows a prop like a sportsbook: the line and price on each button, the numbers behind it on request', () => {
  render(<PropsBrowser legs={[over, under]} selected={[]} toggle={vi.fn()} kalshi={false} />)
  expect(screen.getByRole('button', { name: 'Over Nikola Jokić 24.5 Points' }).textContent).toBe('O 24.5-110')
  expect(screen.getByRole('button', { name: 'Under Nikola Jokić 24.5 Points' }).textContent).toBe('U 24.5-110')
  expect(screen.queryByText(/Price implies/)).toBeNull()             // no percentages until asked
  details()
  expect(screen.getByText(/Price implies/).textContent).toBe('Price implies 52% · model 60%')
})

it("shows the under side's chances when the under is selected and exposes pressed state", () => {
  const toggle = vi.fn()
  render(<PropsBrowser legs={[over, under]} selected={[2]} toggle={toggle} kalshi={false} />)
  details()
  expect(screen.getByText(/Price implies/).textContent).toBe('Price implies 48% · model 40%')
  const button = screen.getByRole('button', { name: 'Under Nikola Jokić 24.5 Points' })
  expect(button.getAttribute('aria-pressed')).toBe('true')
  fireEvent.click(button)
  expect(toggle).toHaveBeenCalledWith(2)
})

it('brings a newly selected ladder step into view even when another step is the default', () => {
  const low = { ...over, id: 9, side: '10+', line: 9.5, market_pct: 90, chance_pct: 91 }
  const view = render(<PropsBrowser legs={[over, under, low]} selected={[]} toggle={vi.fn()} kalshi={true} />)
  expect(screen.getByRole('button', { name: 'Yes Nikola Jokić 25+ Points' })).toBeTruthy()
  view.rerender(<PropsBrowser legs={[over, under, low]} selected={[9]} toggle={vi.fn()} kalshi={true} />)
  const yes = screen.getByRole('button', { name: 'Yes Nikola Jokić 10+ Points' })
  expect(yes.getAttribute('aria-pressed')).toBe('true')
  expect(yes.textContent).toMatch(/^Yes 10\+\d+¢$/)
  details()
  expect(screen.getByText(/Price implies/).textContent).toContain('90%')
})

it('always offers all four stats and points to another source when one has no lines', () => {
  const three = { ...over, id: 5, stat: 'threes', line: 2.5, bet: 'Over 2.5 threes' }
  const go = vi.fn()
  render(<PropsBrowser legs={[over, under, rebound, three]} selected={[]} toggle={vi.fn()} kalshi={false} other={{ name: 'Kalshi', go }} />)
  expect(screen.getByRole('radio', { name: 'Points' }).getAttribute('aria-checked')).toBe('true')
  expect(screen.getAllByRole('radio').map((r) => r.textContent)).toEqual(['Points', 'Rebounds', 'Assists', '3PM'])
  fireEvent.click(screen.getByRole('radio', { name: '3PM' }))
  expect(screen.getByRole('button', { name: 'Over Nikola Jokić 2.5 3PM' })).toBeTruthy()
  expect(screen.queryByRole('button', { name: 'Over Nikola Jokić 24.5 Points' })).toBeNull()
  fireEvent.click(screen.getByRole('radio', { name: 'Assists' }))
  expect(screen.getByText('No Assists lines from this price source')).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'See Kalshi lines' }))
  expect(go).toHaveBeenCalled()
})

it('lists a few players until asked for all, and everyone once a game is chosen', () => {
  const many = Array.from({ length: 9 }, (_, i) => ({ ...over, id: 100 + i, player: `Player ${i}`, player_id: 100 + i }))
  const view = render(<PropsBrowser legs={many} selected={[]} toggle={vi.fn()} kalshi={false} />)
  expect(screen.getAllByText(/^Player \d/)).toHaveLength(6)
  fireEvent.click(screen.getByRole('button', { name: 'Show all 9 players' }))
  expect(screen.getAllByText(/^Player \d/)).toHaveLength(9)
  view.unmount()
  render(<PropsBrowser legs={many} selected={[]} toggle={vi.fn()} kalshi={false} expanded />)
  expect(screen.getAllByText(/^Player \d/)).toHaveLength(9)
})

it('changes to an alternate line from the details without selecting it until its price is clicked', () => {
  const toggle = vi.fn()
  const alt = { ...over, id: 9, side: '10+', line: 9.5 }
  render(<PropsBrowser legs={[over, under, alt]} selected={[]} toggle={toggle} kalshi={false} />)
  details()
  fireEvent.click(screen.getByRole('button', { name: '10+' }))
  expect(toggle).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: 'At least Nikola Jokić 10+ Points' }))
  expect(toggle).toHaveBeenCalledWith(9)
})

it("shows the player's season and last-10 average for the stat on each row", () => {
  render(<PropsBrowser legs={[{ ...over, average: { season: 26.4, last10: 29 } }, under]} selected={[]} toggle={vi.fn()} kalshi={false} />)
  expect(screen.getByText(/^avg/).textContent).toBe('avg 26.4 · L10 29.0')
})

it('keeps the other book and quote warnings in the details', () => {
  const compared = { ...over, comparisons: [{ book: 'DraftKings', line: 25.5, odds: 120,
    fetched_at: '2026-11-15T20:00:00Z', stale: false, same_line: false, better_payout: false }],
    quality: { eligible: false, warnings: ['Minutes have been unstable'], history_games: 20,
      recent_hit_pct: 65, historical_low: 10, historical_high: 30, price_at: '2026-11-15T20:00:00Z',
      price_age_minutes: 5, injuries: 'Injury status is not verified' } }
  render(<PropsBrowser legs={[compared, under]} selected={[]} toggle={vi.fn()} kalshi={false} />)
  expect(screen.queryByText('· other number')).toBeNull()
  details()
  expect(screen.getByText('· other number').parentElement?.textContent).toContain('DraftKings Over 25.5')
  expect(screen.queryByText(/pays more there/)).toBeNull()
  expect(screen.getByText(/Minutes have been unstable/)).toBeTruthy()
})
