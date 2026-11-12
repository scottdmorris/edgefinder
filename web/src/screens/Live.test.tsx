// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { Overview } from './Live'
import type { GameCard, TrackedLeg } from '../lib/api'

afterEach(cleanup)
const side = (team: string, score: number) => ({ team, score, logo: '', color: '#fff', timeouts: 3, bonus: false, fouls: 0 })
const games: GameCard[] = [['MIL', 'BOS'], ['NYK', 'CHI'], ['DEN', 'LAL']].map(([away, home], i) => ({
  id: String(i), state: 'live', status: '1st Qtr 8:00', away: side(away, 8), home: side(home, 10), detail_available: i !== 2,
}))

it('shows every simultaneous game, marks the ones on the slip, and reports the chosen game', () => {
  const choose = vi.fn()
  render(<Overview games={games} chosen="0" onChoose={choose}
    legs={[{ id: 1, game_id: '1', player: 'Example', bet: '20+ points', detail: '8 points so far', status: 'Alive' } as TrackedLeg]} />)
  expect(screen.getAllByRole('button')).toHaveLength(3)
  expect(screen.getByRole('button', { name: 'MIL at BOS' }).getAttribute('aria-pressed')).toBe('true')
  expect(screen.getByText('1 on slip')).toBeTruthy()
  expect(screen.getByText('Score only for now')).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'DEN at LAL' }))
  expect(choose).toHaveBeenCalledWith('2')
})
