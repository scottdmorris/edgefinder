// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, it } from 'vitest'
import type { EvLine, EvLines as EvData } from '../lib/api'
import { EvLines } from './EvLines'

afterEach(cleanup)

const line = (i: number, game = 'MIA @ PHI'): EvLine => ({
  player: `Player ${i}`, photo: null, game_short: game, stat: 'points', bet: 'Over 18.5 points',
  book: 'fanduel', book_name: 'FanDuel', odds: 120, fair_odds: 100, fair_pct: 50, edge_pct: 10,
  books: 4, fetched_at: null,
})
const data = (lines: EvLine[], graded = 0): EvData => ({
  date: '2026-11-25', min_edge_pct: 3, min_books: 3, flagged: lines.length, books: 20, lines,
  record: { logged: 5, graded, record: graded ? '3-2' : '0-0', units: 0.4, roi_pct: 8, clv_novig_n: 0, avg_clv_novig_pct: null },
})

it('shows the book, line, price, fair price and edge, framed as a paper test', () => {
  render(<EvLines data={data([line(1)])} />)
  expect(screen.getByText('Player 1 · Over 18.5 points')).toBeTruthy()
  expect(screen.getByText(/FanDuel \+120 vs fair \+100 \(50%, 4 books\)/)).toBeTruthy()
  expect(screen.getByText('+10.0%')).toBeTruthy()
  expect(screen.getByText(/A paper test, not advice: 5 logged, none graded yet/)).toBeTruthy()
  expect(screen.queryByRole('button', { name: /add/i })).toBeNull()
})

it('keeps the list short until asked and filters to the chosen game', () => {
  const lines = [...Array.from({ length: 8 }, (_, i) => line(i)), line(9, 'CHI @ CHA')]
  render(<EvLines data={data(lines, 5)} />)
  expect(screen.getAllByRole('listitem')).toHaveLength(6)
  fireEvent.click(screen.getByText('Show all 9'))
  expect(screen.getAllByRole('listitem')).toHaveLength(9)
  expect(screen.getByText(/3-2, \+0.40 units on 5 graded/)).toBeTruthy()
  cleanup()
  render(<EvLines data={data(lines)} game="CHI @ CHA" />)
  expect(screen.getAllByRole('listitem')).toHaveLength(1)
  cleanup()
  const { container } = render(<EvLines data={data(lines)} game="BOS @ NYK" />)
  expect(container.textContent).toBe('')
})
