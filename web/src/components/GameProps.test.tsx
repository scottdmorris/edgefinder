// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import type { BoardGame, Leg } from '../lib/api'
import { GameCards } from './GameCards'
import { GameProps } from './GameProps'

afterEach(cleanup)
const game: BoardGame = { game: 'Memphis Grizzlies @ Charlotte Hornets', short: 'MEM @ CHA',
  tip: '2026-11-24T00:00:00Z', away: 'MEM', home: 'CHA', away_logo: '', home_logo: '', players: 2 }
const base = { photo: '', game: game.game, game_short: game.short, stat_label: 'Points', odds: -110,
  market_pct: 52, model_pct: 55, chance_pct: 53, average: null } as const
const leg = (id: number, player: string, player_id: number, team: string, stat: string, side: string, line: number, odds = -110) =>
  ({ ...base, id, player, player_id, team, stat, side, line, odds, bet: `${side} ${line} ${stat}` }) as Leg
const legs = [
  leg(1, 'Coby White', 1, 'CHA', 'points', 'Over', 17.5), leg(2, 'Coby White', 1, 'CHA', 'points', 'Under', 17.5),
  leg(3, 'Coby White', 1, 'CHA', 'threes', 'Over', 1.5), leg(4, 'Coby White', 1, 'CHA', 'threes', 'Under', 1.5),
  leg(5, 'Ja Morant', 2, 'MEM', 'points', 'Over', 24.5), leg(6, 'Ja Morant', 2, 'MEM', 'points', 'Under', 24.5),
]
const rungs = [leg(7, 'Ja Morant', 2, 'MEM', 'points', '20+', 19.5, -250), leg(8, 'Ja Morant', 2, 'MEM', 'points', '30+', 29.5, 260),
  leg(9, 'Ja Morant', 2, 'MEM', 'points', '25+', 24.5, 110)]

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

it('lays the games out as a list to choose from, with no "All games" card', () => {
  render(<GameCards games={[game]} value="" onChange={vi.fn()} layout="list" />)
  expect(screen.queryByRole('button', { name: 'All games' })).toBeNull()
  expect(screen.getByRole('button', { name: /^MEM @ CHA/ })).toBeTruthy()
})

it("opens on the game's first stat with both teams in one list, biggest averages first, and a way back", () => {
  const back = vi.fn()
  const averaged = legs.map((l) => ({ ...l, average: l.player === 'Coby White' ? { season: 19.2, last10: 21 } : { season: 25.1, last10: 24 } }))
  render(<GameProps game={game} legs={averaged} selected={[]} toggle={vi.fn()} kalshi={false} onBack={back} />)
  expect(screen.getAllByRole('radio').map((r) => r.textContent)).toEqual(['Points', '3PM'])   // only stats it has
  expect(screen.queryByRole('region', { name: /^[A-Z]{3} props$/ })).toBeNull()             // no split by team
  const overs = screen.getAllByRole('button', { name: /^Over .* Points$/ })
  expect(overs.map((b) => b.getAttribute('aria-label'))).toEqual(['Over Ja Morant 24.5 Points', 'Over Coby White 17.5 Points'])
  expect(overs[0].textContent).toBe('O 24.5-110')
  expect(screen.getByText('MEM')).toBeTruthy()                         // each row names its team
  expect(screen.queryByRole('button', { name: 'Over Coby White 1.5 3PM' })).toBeNull()
  fireEvent.click(screen.getByRole('radio', { name: '3PM' }))
  expect(screen.getByRole('button', { name: 'Over Coby White 1.5 3PM' })).toBeTruthy()
  expect(screen.queryByText('Ja Morant')).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: '‹ All games' }))
  expect(back).toHaveBeenCalled()
})

it('switches a stat between its Over / Under lines and its X+ ladder, lowest rung first', () => {
  const toggle = vi.fn()
  render(<GameProps game={game} legs={[...legs, ...rungs]} selected={[9]} toggle={toggle} kalshi={false} />)
  expect(screen.queryByRole('button', { name: /^At least/ })).toBeNull()
  fireEvent.click(screen.getByRole('radio', { name: 'Points X+' }))
  const ladder = screen.getAllByRole('button', { name: /^At least Ja Morant/ })
  expect(ladder.map((b) => b.textContent)).toEqual(['20+-250', '25++110', '30++260'])
  expect(ladder[1].getAttribute('aria-pressed')).toBe('true')
  fireEvent.click(ladder[2])
  expect(toggle).toHaveBeenCalledWith(8)
  expect(screen.queryByText('Coby White')).toBeNull()                 // he has no ladder
})

it('falls back to the first stat when the chosen one is gone after a switch of book or day', () => {
  const props = { game, selected: [], toggle: vi.fn(), kalshi: false }
  const threesRung = leg(10, 'Coby White', 1, 'CHA', 'threes', '2+', 1.5, 120)
  const { rerender } = render(<GameProps {...props} legs={[...legs, ...rungs, threesRung]} />)
  fireEvent.click(screen.getByRole('radio', { name: '3PM' }))
  fireEvent.click(screen.getByRole('radio', { name: '3PM X+' }))
  rerender(<GameProps {...props} legs={[...legs, ...rungs].filter((l) => l.stat === 'points')} />)
  expect(screen.getByRole('radio', { name: 'Points' }).getAttribute('aria-checked')).toBe('true')
  expect(screen.getByRole('button', { name: 'Over Ja Morant 24.5 Points' })).toBeTruthy()   // its lines, not its ladder
})

it('offers no market switch when a stat has only one kind of line', () => {
  render(<GameProps game={game} legs={legs} selected={[]} toggle={vi.fn()} kalshi={false} />)
  expect(screen.queryByRole('radio', { name: 'Points X+' })).toBeNull()
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

it("shows both teams' moneylines and win chances under the matchup", () => {
  render(<GameProps game={priced} legs={legs} selected={[]} toggle={vi.fn()} kalshi={false} />)
  expect(screen.getByText('MEM', { selector: 'b' }).parentElement?.textContent).toMatch(/MEM \+128 · 42% to win/)
  expect(screen.getByText('CHA', { selector: 'b' }).parentElement?.textContent).toMatch(/CHA -150 · 58% to win/)
  expect(screen.getByTitle(/FanDuel moneyline, vig removed/)).toBeTruthy()
})

it("marks the model's tracked picks on their prices, counts them, and can show them alone", () => {
  const picked = legs.map((l) => (l.id === 6 ? { ...l, pick: true, projection: 21.3 } : l))
  render(<GameProps game={game} legs={[...picked, ...rungs.map((r) => (r.id === 9 ? { ...r, pick: true } : r))]}
    selected={[]} toggle={vi.fn()} kalshi={false} />)
  expect(screen.getByText(/2 model picks/)).toBeTruthy()
  expect(screen.getByRole('radio', { name: 'Points · ★2' })).toBeTruthy()
  expect(screen.getByRole('button', { name: 'Under Ja Morant 24.5 Points, model pick' })).toBeTruthy()
  expect(screen.getByText('★ Model pick: Under 24.5')).toBeTruthy()
  expect(screen.getByText('21.3')).toBeTruthy()                         // the model's number on the row
  fireEvent.click(screen.getByRole('checkbox', { name: 'Model picks only' }))
  expect(screen.queryByText('Coby White')).toBeNull()
  fireEvent.click(screen.getByRole('radio', { name: 'Points X+ · ★1' }))
  expect(screen.getByRole('button', { name: 'At least Ja Morant 25+ Points, model pick' })).toBeTruthy()
  expect(screen.getByText('★ Model pick: 25+')).toBeTruthy()
})

it('says so when the model made no picks in a game', () => {
  render(<GameProps game={game} legs={legs} selected={[]} toggle={vi.fn()} kalshi={false} />)
  expect(screen.getByText(/made no picks in this game/)).toBeTruthy()
  expect(screen.queryByRole('checkbox', { name: 'Model picks only' })).toBeNull()
})

it("counts each game's model picks on its card", () => {
  render(<GameCards games={[game]} value="" onChange={vi.fn()} layout="list" picks={{ [game.game]: 3 }} />)
  expect(screen.getByRole('button', { name: /3 model picks$/ }).textContent).toContain('★ 3 model picks')
})

it('counts several picked rungs of one ladder as one pick and shows their range', () => {
  const ladder = rungs.map((r) => ({ ...r, pick: r.id !== 7 }))      // 25+ and 30+
  render(<GameProps game={game} legs={[...legs, ...ladder]} selected={[]} toggle={vi.fn()} kalshi={false} />)
  expect(screen.getByText(/★ 1 model pick$/)).toBeTruthy()
  fireEvent.click(screen.getByRole('radio', { name: 'Points X+ · ★1' }))
  expect(screen.getByText('★ Model pick: 25+ to 30+')).toBeTruthy()
})
