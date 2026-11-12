// @vitest-environment jsdom
import { act, cleanup, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { SlipPanel } from './SlipPanel'
import { api, type Leg, type SlipPrice } from '../lib/api'

vi.mock('../lib/api', () => ({ api: { slip: vi.fn() } }))
const market = { date: '2026-11-12', book: 'kalshi', model: 'ewma-v1' }
const legsById = new Map([[123, { id: 123, player: 'Example', bet: '25+ points', game_short: 'A @ B', odds: -110, photo: '/player.png' } as Leg]])
const props = { market, legs: [123], legsById, onRemove: vi.fn(), onClear: vi.fn() }
beforeEach(() => { vi.useFakeTimers(); vi.mocked(api.slip).mockReset() })
afterEach(() => { cleanup(); vi.useRealTimers() })

it('hides a previous payout immediately when the selected quote changes', async () => {
  vi.mocked(api.slip).mockResolvedValueOnce({ legs: 1, to_win: 50, total_return: 60, chance_pct: 55, expected: 2 })
  const view = render(<SlipPanel {...props} />)
  await act(async () => { await vi.advanceTimersByTimeAsync(151) })
  expect(screen.queryAllByText(/Estimated profit \$50/).length).toBeGreaterThan(0)
  let resolve!: (p: SlipPrice) => void
  vi.mocked(api.slip).mockReturnValueOnce(new Promise(r => { resolve = r }))
  view.rerender(<SlipPanel {...props} market={{ ...market, model: 'minutes-v1' }} />)
  expect(screen.queryAllByText(/\$50/)).toHaveLength(0)
  expect(screen.queryAllByText(/Recalculating/).length).toBeGreaterThan(0)
  await act(async () => { await vi.advanceTimersByTimeAsync(151) })
  await act(async () => { resolve({ legs: 1, to_win: 20 }) })
  expect(screen.queryAllByText(/Estimated profit \$20/).length).toBeGreaterThan(0)
})

it('never shows an old mobile payout after a pricing failure', async () => {
  vi.mocked(api.slip).mockResolvedValueOnce({ legs: 1, to_win: 50 })
  const view = render(<SlipPanel {...props} />)
  await act(async () => { await vi.advanceTimersByTimeAsync(151) })
  vi.mocked(api.slip).mockRejectedValueOnce(new Error('Quote expired'))
  view.rerender(<SlipPanel {...props} market={{ ...market, model: 'minutes-v1' }} />)
  await act(async () => { await vi.advanceTimersByTimeAsync(151) })
  expect(screen.queryAllByText(/\$50/)).toHaveLength(0)
  expect(screen.getByText('Quote expired')).toBeTruthy()
  expect(screen.getByText('Open slip')).toBeTruthy()
})
