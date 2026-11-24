// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import type { BoardGame, Leg } from '../lib/api'
import { GameCards } from './GameCards'
import { GameProps } from './GameProps'

afterEach(cleanup)
const game: BoardGame = { game: 'Memphis Grizzlies @ Charlotte Hornets', short: 'MEM @ CHA',
  tip: '2026-11-24T00:00:00Z', away: 'MEM', home: 'CHA', away_logo: '', home_logo: '', players: 2 }
const base = { photo: '', game: game.game, game_short: game.short, stat_label: 'Points', odds: -110,
  market_pct: 52, model_pct: 55, chance_pct: 53, average: null } as const
const leg = (id: number, player: string, player_id: number, team: string, stat: string, side: string, line: number) =>
  ({ ...base, id, player, player_id, team, stat, side, line, bet: `${side} ${line} ${stat}` }) as Leg
const legs = [
  leg(1, 'Coby White', 1, 'CHA', 'points', 'Over', 17.5), leg(2, 'Coby White', 1, 'CHA', 'points', 'Under', 17.5),
  leg(3, 'Coby White', 1, 'CHA', 'threes', 'Over', 1.5), leg(4, 'Coby White', 1, 'CHA', 'threes', 'Under', 1.5),
  leg(5, 'Ja Morant', 2, 'MEM', 'points', 'Over', 24.5), leg(6, 'Ja Morant', 2, 'MEM', 'points', 'Under', 24.5),
]

it('lists games as cards in the order given, with a choice for every game', () => {
  const choose = vi.fn()
  const other = { ...game, game: 'Bulls @ Knicks', short: 'CHI @ NYK', away: 'CHI', home: 'NYK', players: 9 }
  render(<GameCards games={[game, other]} value="__all__" all="__all__" onChange={choose} />)
  const cards = screen.getAllByRole('button')
  expect(cards.map((c) => c.getAttribute('aria-label') ?? c.textContent)).toEqual([
    'All games', expect.stringMatching(/^MEM @ CHA, .+, 2 players$/), expect.stringMatching(/^CHI @ NYK, .+, 9 players$/)])
  expect(cards[0].getAttribute('aria-pressed')).toBe('true')
  fireEvent.click(cards[2])
  expect(choose).toHaveBeenCalledWith('Bulls @ Knicks')
})

it("groups a game's players under their team, away side first, one line each until opened", () => {
  render(<GameProps game={game} legs={legs} selected={[]} toggle={vi.fn()} kalshi={false} />)
  const [away, home] = screen.getAllByRole('region', { name: /^[A-Z]{3} props$/ })
  expect(away.getAttribute('aria-label')).toBe('MEM props')
  expect(within(away).getByText('Ja Morant')).toBeTruthy()
  const white = within(home).getByRole('button', { name: /Coby White/ })
  expect(white.getAttribute('aria-expanded')).toBe('false')
  expect(white.textContent).toContain('PTS 17.5')
  expect(white.textContent).toContain('3PM 1.5')
  expect(screen.queryByRole('button', { name: 'Over Coby White 17.5 Points' })).toBeNull()
  fireEvent.click(white)
  expect(within(home).getByRole('button', { name: 'Over Coby White 17.5 Points' })).toBeTruthy()
  expect(within(home).getByRole('button', { name: 'Over Coby White 1.5 3PM' })).toBeTruthy()
})

it('opens a player who is already on the slip', () => {
  render(<GameProps game={game} legs={legs} selected={[3]} toggle={vi.fn()} kalshi={false} />)
  expect(screen.getByRole('button', { name: 'Over Coby White 1.5 3PM' }).getAttribute('aria-pressed')).toBe('true')
})

it('narrows by stat and by player name, and adds a bet from the game view', () => {
  const toggle = vi.fn()
  render(<GameProps game={game} legs={legs} selected={[]} toggle={toggle} kalshi={false} />)
  fireEvent.click(screen.getByRole('radio', { name: '3PM' }))
  expect(screen.queryByText('Ja Morant')).toBeNull()
  expect(screen.queryByRole('button', { name: 'Over Coby White 17.5 Points' })).toBeNull()
  fireEvent.click(screen.getByRole('radio', { name: 'All' }))
  fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'morant' } })
  expect(screen.queryByText('Coby White')).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: 'Under Ja Morant 24.5 Points' }))
  expect(toggle).toHaveBeenCalledWith(6)
})

const priced: BoardGame = { ...game, moneyline: { book: 'fanduel', away_odds: 128, home_odds: -150,
  away_pct: 42.2, home_pct: 57.8, as_of: '2026-11-23T23:00:00+00:00' } }

it("shows each side's moneyline and no-vig win chance on its game card", () => {
  render(<GameCards games={[priced]} value="__all__" all="__all__" onChange={vi.fn()} />)
  const card = screen.getByRole('button', { name: /^MEM @ CHA/ })
  expect(card.getAttribute('aria-label')).toMatch(/MEM \+128 42% to win, CHA -150 58% to win/)
  expect(card.textContent).toContain('+128')
  expect(card.textContent).toContain('58%')
})

it('leaves the odds off a card whose game has no moneyline yet', () => {
  render(<GameCards games={[game]} value="__all__" all="__all__" onChange={vi.fn()} />)
  const card = screen.getByRole('button', { name: /^MEM @ CHA/ })
  expect(card.getAttribute('aria-label')).not.toMatch(/to win/)
  expect(card.textContent).not.toMatch(/%/)
})

it("puts each team's moneyline and win chance beside its heading in the game view", () => {
  render(<GameProps game={priced} legs={legs} selected={[]} toggle={vi.fn()} kalshi={false} />)
  const [away, home] = screen.getAllByRole('region', { name: /^[A-Z]{3} props$/ })
  expect(within(away).getByRole('heading').textContent).toMatch(/MEM.*\+128.*42%/)
  expect(within(home).getByRole('heading').textContent).toMatch(/CHA.*-150.*58%/)
  expect(screen.getByText(/FanDuel moneyline, vig removed/)).toBeTruthy()
})
