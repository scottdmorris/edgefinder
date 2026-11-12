// @vitest-environment jsdom
import { act, cleanup, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, expect, it } from 'vitest'
import { savedSlip, slipForDate, useSlip } from './slip'
import type { Leg } from './api'

beforeEach(() => localStorage.clear())
afterEach(cleanup)
const leg = { id: 12, player: 'Example', player_id: 7, stat: 'points', odds: 110, chance_pct: 52, bet: '20+ points' } as Leg
const market = '2026-11-11|kalshi|ewma-v1'

it('preserves original selections and estimates after quotes disappear, across reloads', () => {
  const hook = renderHook(({ board }) => useSlip(market, board), { initialProps: { board: new Map([[12, leg]]) } })
  act(() => hook.result.current.toggle(12))
  act(() => hook.result.current.rememberEstimate({ legs: 1, stake: 10, to_win: 11 }, [12]))
  hook.rerender({ board: new Map() })
  expect(hook.result.current.legs).toEqual([])
  expect(hook.result.current.unavailable).toEqual([{ id: 12, leg }])
  expect(savedSlip()?.estimate?.price.to_win).toBe(11)
  hook.unmount()
  const restored = renderHook(() => useSlip(market, new Map<number, Leg>()))
  expect(restored.result.current.unavailable[0].leg?.player).toBe('Example')
  act(() => restored.result.current.toggle(12))
  expect(restored.result.current.unavailable).toEqual([])
})

it('restores each market and replaces changed quotes for the same player and stat', () => {
  const board = new Map([[12, leg], [13, { ...leg, id: 13, odds: 120 }]])
  const hook = renderHook(({ key }) => useSlip(key, board), { initialProps: { key: market } })
  act(() => hook.result.current.toggle(12))
  hook.rerender({ key: '2026-11-11|fanduel|ewma-v1' })
  expect(hook.result.current.legs).toEqual([])
  hook.rerender({ key: market })
  expect(hook.result.current.legs).toEqual([12])
  act(() => hook.result.current.toggle(13))
  expect(hook.result.current.legs).toEqual([13])
})

it('keeps the slip Live is tracking when another market is only looked at', () => {
  const board = new Map([[12, leg]])
  const hook = renderHook(({ key }) => useSlip(key, board), { initialProps: { key: market } })
  act(() => hook.result.current.toggle(12))
  hook.rerender({ key: '2026-11-11|kalshi|minutes-v1' })
  expect(savedSlip()?.legs).toEqual([12])
  act(() => hook.result.current.toggle(12))
  expect(savedSlip()?.market.model).toBe('minutes-v1')
})

it('keeps a selection whose price moved and reports the move', () => {
  const hook = renderHook(({ board }) => useSlip(market, board), { initialProps: { board: new Map([[12, leg]]) } })
  act(() => hook.result.current.toggle(12))
  hook.rerender({ board: new Map([[12, { ...leg, odds: 125 }]]) })
  expect(hook.result.current.legs).toEqual([12])
  expect(hook.result.current.moved).toEqual([{ id: 12, player: 'Example', was: 110, now: 125 }])
})

it('finds the slip built for a game day, as it was when added', () => {
  const hook = renderHook(() => useSlip(market, new Map([[12, leg]])))
  act(() => hook.result.current.toggle(12))
  expect(slipForDate('2026-11-11')?.legs.map((l) => l.player)).toEqual(['Example'])
  expect(slipForDate('2026-11-10')).toBeNull()
})
