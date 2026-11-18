// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { Live } from './Live'

const mocks = vi.hoisted(() => ({ board: { data: [] as unknown[] | null, error: null as string | null, receivedAt: null } }))
vi.mock('../lib/live', () => ({ useLiveGames: () => mocks.board }))
vi.mock('../lib/poll', () => ({
  usePoll: () => ({ data: null, error: 'Tracking unavailable', receivedAt: null }),
  usePrevious: () => undefined,
}))
vi.mock('../lib/slip', () => ({ savedSlip: () => ({ market: { date: '2026-11-14' }, legs: [1],
  snapshots: { 1: { player: 'Saved Player', bet: 'Over 20.5 points' } } }) }))
afterEach(cleanup)
it.each([false, true])('keeps saved selections and recovery visible with unavailable scoreboard (%s)', (failed) => {
  mocks.board = { data: failed ? null : [], error: failed ? 'Feed down' : null, receivedAt: null }
  render(<Live />)
  expect(screen.getByRole('heading', { name: 'Live' })).toBeTruthy()
  expect(screen.getByText(/Saved Player/)).toBeTruthy()
  expect(screen.getByText(/Needs review/)).toBeTruthy()
  expect(screen.getByRole('link', { name: /Review the saved slip/ })).toBeTruthy()
})
