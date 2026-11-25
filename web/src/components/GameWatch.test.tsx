// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import type { GameDetail, SimEvent, SimWatch } from '../lib/api'
import { GameWatch } from './GameWatch'
import { LiveCourt } from './LiveCourt'

beforeEach(() => vi.useFakeTimers())
afterEach(() => { cleanup(); vi.useRealTimers() })

const on = { BOS: [1, 2, 3, 4, 5], WAS: [6, 7, 8, 9, 10] }
const ev = (e: Partial<SimEvent>): SimEvent => ({ t: 0, period: 1, clock: '12:00', kind: 'start', team: '', text: 'Tip-off',
  away: 0, home: 0, on, home_win: 40, ...e })
const watch: SimWatch = {
  periods: 4,
  roster: [...on.BOS, ...on.WAS].map((id) => ({ id, name: id === 1 ? 'Jayson Tatum' : `Player ${id}`,
    team: id <= 5 ? 'BOS' : 'WAS', starter: true, photo: '' })),
  events: [
    ev({}),
    ev({ t: 15, clock: '11:45', kind: 'make', team: 'BOS', text: 'Jayson Tatum 26-foot three', player: 1, points: 3,
      x: 20, y: 40, three: true, away: 3, home_win: 35 }),
    ev({ t: 30, clock: '11:30', kind: 'miss', team: 'WAS', text: 'Player 6 misses 12-foot jumper', player: 6, x: 85, y: 50, away: 3 }),
    ev({ t: 2880, period: 4, clock: '0:00', kind: 'final', text: 'Final: BOS 110, WAS 104', away: 110, home: 104, home_win: 0 }),
  ],
}
const side = (code: string) => ({ code, color: '#fff', score: 0 })

it('plays the game event by event: score, ticker and the shooter’s line follow', () => {
  render(<GameWatch watch={watch} runs={2000} away={side('BOS')} home={side('WAS')} />)
  expect(screen.getByRole('img', { name: 'Tip-off' })).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: '▶ Watch the game' }))
  act(() => { vi.advanceTimersByTime(1000) })
  expect(screen.getByRole('img', { name: 'Jayson Tatum 26-foot three' })).toBeTruthy()   // the court and its ticker
  expect(screen.getAllByText('3').length).toBeGreaterThanOrEqual(2)     // the scoreboard and Tatum's line
  fireEvent.click(screen.getByRole('button', { name: '❚❚ Pause' }))
  fireEvent.click(screen.getByRole('button', { name: 'Skip to the end' }))
  expect(screen.getByRole('img', { name: 'Final: BOS 110, WAS 104' })).toBeTruthy()
  expect(screen.getByRole('button', { name: '↺ Replay' })).toBeTruthy()
})

it('shows the win chance at the moment being watched', () => {
  render(<GameWatch watch={watch} runs={2000} away={side('BOS')} home={side('WAS')} />)
  expect(screen.getByLabelText('Win chance: BOS 60%, WAS 40%')).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'Skip to the end' }))
  expect(screen.getByLabelText('Win chance: BOS 100%, WAS 0%')).toBeTruthy()
})

const live = {
  id: '1', state: 'live', status: 'Q3 5:21',
  away: { team: 'DET', logo: '', color: '#c8102e', score: 70, timeouts: 3, bonus: false, fouls: 2 },
  home: { team: 'ORL', logo: '', color: '#0077c0', score: 66, timeouts: 3, bonus: false, fouls: 2 },
  detail: { quarters: { columns: [], rows: [] }, compare: [], leaders: [], foul_trouble: [],
    shots: [{ n: 1, team: 'DET', x: 10, y: 50, made: true, three: false, period: 3, period_label: 'Q3', text: '' },
      { n: 2, team: 'ORL', x: 90, y: 40, made: false, three: true, period: 3, period_label: 'Q3', text: '' }],
    plays: [{ order: 9, period: 'Q3', clock: '5:21', team: 'DET', text: 'Cunningham driving layup', score: '' }],
    box: { DET: { starters: [{ id: 1, photo: '', on_court: true, Player: 'Cade Cunningham', Min: 20, Pts: 18, Reb: 4, Ast: 7,
      FG: '', '3PT': '', FT: '', Stl: 0, Blk: 0, TO: 1, PF: 1, '+/-': '' }], bench: [] }, ORL: { starters: [], bench: [] } } },
} as unknown as GameDetail & { detail: NonNullable<GameDetail['detail']> }

it('puts a live game’s real shots and latest play on the court, with who is on the floor', () => {
  const { container } = render(<LiveCourt game={live} />)
  expect(screen.getByText('Cunningham driving layup')).toBeTruthy()
  expect(screen.getByText('Cunningham')).toBeTruthy()
  expect(container.querySelectorAll('circle[stroke="white"]').length).toBeGreaterThanOrEqual(1)   // the make
  expect(screen.queryByText('70')).toBeNull()                       // the page's own header shows the score
})
