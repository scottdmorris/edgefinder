// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { MyPlayers, Overview } from './Live'
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

it('dims the trailing team in the score strip', () => {
  render(<Overview games={games} chosen={null} onChoose={vi.fn()} legs={[]} />)
  const card = screen.getByRole('button', { name: 'MIL at BOS' })
  const row = (text: string) => [...card.querySelectorAll('div')].find((d) => d.textContent === text)!
  expect(row('MIL8').className).toContain('text-muted')
  expect(row('BOS10').className).not.toContain('text-muted')
})

it('puts slip players under the score with progress and any warning', () => {
  const leg = { id: 1, game_id: '1', player: 'Example Player', bet: '25+ points', photo: '', status: 'Alive', have: 22,
    target: 25, progress: 0.88, detail: '', game: '', alert: 'Off the floor for the last 11 minutes of game time. May be hurt or benched' } as TrackedLeg
  render(<MyPlayers legs={[leg, { ...leg, id: 2, player: 'Other Player', alert: '', status: 'Hit', have: 25, progress: 1 }]} />)
  expect(screen.getByText('Your players in this game')).toBeTruthy()
  expect(screen.getByText(/Off the floor for the last 11 minutes/)).toBeTruthy()
  expect(screen.getByText('Hit')).toBeTruthy()
})

it('shows no slip section for a game with none of your players', () => {
  render(<MyPlayers legs={[]} />)
  expect(screen.queryByText('Your players in this game')).toBeNull()
})
