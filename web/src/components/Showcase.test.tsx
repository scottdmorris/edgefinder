// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { api, type BoardGame, type Leg, type PerfectProps as Data, type Simulation } from '../lib/api'
import { GameSim } from './GameSim'
import { PerfectProps } from './PerfectProps'

afterEach(() => { cleanup(); vi.restoreAllMocks() })

const game: BoardGame = { game: 'Boston Celtics @ Washington Wizards', short: 'BOS @ WAS', away: 'BOS', home: 'WAS',
  moneyline: { book: 'fanduel', away_odds: -450, home_odds: 350, away_pct: 79.1, home_pct: 20.9, as_of: '' } }
const sim: Simulation = {
  game: game.game, away: 'BOS', home: 'WAS', model: 'context-v2', model_short: 'Shot profile', runs: 5000,
  teams: { BOS: { win_pct: 60.1, median: 108, average: 107.8 }, WAS: { win_pct: 39.9, median: 104, average: 104.1 } },
  total: { low: 188, median: 212, high: 236 }, margin: { low: -21, median: -4, high: 13 },
  margin_chart: [{ from: -6, to: -3, pct: 60 }, { from: 0, to: 3, pct: 40 }],
  players: [],
  typical: { score: { BOS: 108, WAS: 104 }, rest: { BOS: 22, WAS: 1 },
    box: [{ player_id: 1, player: 'Jayson Tatum', team: 'BOS', points: 86, rebounds: 11, assists: 4, threes: 5 },
      { player_id: 2, player: 'Trae Young', team: 'WAS', points: 103, rebounds: 2, assists: 7, threes: 3 }] },
}

it("shows each side's simulated win chance beside the market's, the typical score and its box score", async () => {
  vi.spyOn(api, 'simulate').mockResolvedValue(sim)
  render(<GameSim market={{ date: '2026-11-24', book: 'fanduel' }} game={game} />)
  expect(await screen.findByText('60%')).toBeTruthy()
  expect(screen.getByText('40%')).toBeTruthy()
  expect(screen.getByText('market 79%')).toBeTruthy()
  expect(screen.getByText('108–104')).toBeTruthy()
  expect(screen.getByText('BOS by 4')).toBeTruthy()
  expect(screen.queryByText('Jayson Tatum')).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: /typical game’s box score/ }))
  expect(screen.getByText('Jayson Tatum')).toBeTruthy()
  expect(screen.getAllByText('Rest of the team')).toHaveLength(2)
})

it('stays out of the way when the simulation cannot be run', async () => {
  vi.spyOn(api, 'simulate').mockRejectedValue(new Error('no'))
  const { container } = render(<GameSim market={{}} game={game} />)
  await new Promise((r) => setTimeout(r, 0))
  expect(container.textContent).toBe('')
})

const prop = { leg_id: 7, player: 'Jalen Suggs', player_id: 3, game: 'X @ Y', event_id: 'e', stat: 'assists',
  bet: 'Over 1.5 assists', side: 'Over', line: 1.5, odds: -900, games: 8, book: 'fanduel', low: 2, photo: '' }
const data: Data = { date: '2026-11-25', book: 'fanduel', props: [prop, { ...prop, leg_id: 8, player_id: 4, player: 'P.J. Washington', book: 'kalshi', odds: -2400 }],
  recap: { date: '2026-11-24', hit: 11, total: 12, props: [{ ...prop, actual: 1, hit: false }] } }

it('lists perfect props with their streak and what $10 wins, adds one from this book, and grades the last day', async () => {
  vi.spyOn(api, 'perfect').mockResolvedValue(data)
  const toggle = vi.fn()
  render(<PerfectProps market={{}} legsById={new Map([[7, { id: 7 } as Leg]])} selected={[]} toggle={toggle} />)
  const add = await screen.findByRole('button', { name: 'Add Jalen Suggs Over 1.5 assists at -900' })
  expect(screen.getAllByText('8/8')).toHaveLength(2)
  expect(screen.getByText('$10 wins $1.11')).toBeTruthy()
  expect(screen.queryByRole('button', { name: /Add P.J. Washington/ })).toBeNull()   // another book's price
  fireEvent.click(add)
  expect(toggle).toHaveBeenCalledWith(7)
  expect(screen.getByRole('listitem', { name: 'Jalen Suggs Over 1.5 assists: missed with 1' })).toBeTruthy()
  expect(screen.getByText(/perfect props$/i, { selector: 'div' })).toBeTruthy()
})

it('shows only how a finished day went when the chosen day is over', async () => {
  vi.spyOn(api, 'perfect').mockResolvedValue({ ...data, props: [], recap: { ...data.recap!, date: data.date } })
  render(<PerfectProps market={{}} legsById={new Map()} selected={[]} toggle={vi.fn()} />)
  expect(await screen.findByRole('list', { name: 'How each did' })).toBeTruthy()
  expect(screen.queryByText(/No line on today/)).toBeNull()
})
