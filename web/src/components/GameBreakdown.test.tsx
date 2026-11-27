// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { api, type GameBreakdownData } from '../lib/api'
import { GameBreakdown } from './GameBreakdown'

afterEach(() => { cleanup(); vi.restoreAllMocks() })

const data: GameBreakdownData = {
  away: 'BOS', home: 'WAS', model: 'Shot profile', recent_window: 15,
  teams: {
    BOS: { projected: 114, recent: 110, adjustment: 4, baseline_floor: 0, coverage: 3,
      players: [{ name: 'Jaylen Brown', change: 4 }] },
    WAS: { projected: 112, recent: 115, adjustment: -3, baseline_floor: 0, coverage: 4, players: [] },
  },
  market: { book: 'draftkings', home_spread: -3.5, total: 220.5, as_of: '2026-11-25T20:00:00Z',
    away_score: 108.5, home_score: 112 },
  home_margin: -2, home_margin_gap: -5.5,
}

it('shows model and market scores and explains which team the gap favors', async () => {
  vi.spyOn(api, 'gameBreakdown').mockResolvedValue(data)
  const simulate = vi.spyOn(api, 'simulate')
  render(<GameBreakdown market={{ book: 'fanduel' }} game="Boston Celtics @ Washington Wizards" />)
  expect(await screen.findByText('5.5 points more favorable to BOS', { exact: false })).toBeTruthy()
  expect(screen.getByText('BOS −2.0')).toBeTruthy()
  expect(screen.getByText('WAS −3.5')).toBeTruthy()
  expect(screen.getByText('DraftKings implied score')).toBeTruthy()
  expect(screen.getByText('shift the margin 7.0 points toward BOS', { exact: false })).toBeTruthy()
  expect(screen.getByText('Jaylen Brown')).toBeTruthy()
  expect(simulate).not.toHaveBeenCalled()
})

it('retries an unavailable request and still shows the model when no market line was archived', async () => {
  vi.spyOn(api, 'gameBreakdown').mockRejectedValueOnce(new Error('offline'))
    .mockResolvedValueOnce({ ...data, market: null, home_margin_gap: null })
  render(<GameBreakdown market={{}} game="Boston Celtics @ Washington Wizards" />)
  fireEvent.click(await screen.findByRole('button', { name: 'Retry' }))
  expect(await screen.findByText('No pregame spread archived for this matchup.')).toBeTruthy()
  expect(screen.getByText('BOS −2.0')).toBeTruthy()
})
