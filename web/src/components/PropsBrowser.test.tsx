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

it("shows the under side's chances when the under is selected and exposes pressed state", () => {
  const toggle = vi.fn()
  render(<PropsBrowser legs={[over, under]} selected={[2]} toggle={toggle} kalshi={false} />)
  expect(screen.getByText('48%')).toBeTruthy()
  expect(screen.getByText('model 40%')).toBeTruthy()
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
  expect(screen.getByRole('button', { name: 'Yes Nikola Jokić 10+ Points' }).getAttribute('aria-pressed')).toBe('true')
  expect(screen.getByText('90%')).toBeTruthy()
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

it('changes an alternate line without selecting it until its price is clicked', () => {
  const toggle = vi.fn()
  const alt = { ...over, id: 9, side: '10+', line: 9.5 }
  render(<PropsBrowser legs={[over, under, alt]} selected={[]} toggle={toggle} kalshi={false} />)
  fireEvent.click(screen.getByRole('button', { name: '10+' }))
  expect(toggle).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: 'At least Nikola Jokić 10+ Points' }))
  expect(toggle).toHaveBeenCalledWith(9)
})
