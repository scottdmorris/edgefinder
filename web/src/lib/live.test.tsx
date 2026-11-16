// @vitest-environment jsdom
import { act, cleanup, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { api, type GameCard } from './api'
import { useLiveGames } from './live'

const board: GameCard[] = []
const laterBoard: GameCard[] = [{
  id: 'game', state: 'live', status: 'Q1',
  away: { team: 'BOS', logo: '', color: '', score: 10, timeouts: 3, bonus: false, fouls: 0 },
  home: { team: 'NYK', logo: '', color: '', score: 12, timeouts: 3, bonus: false, fouls: 0 },
}]

function deferred() {
  let resolve!: (data: GameCard[]) => void
  let reject!: (error: Error) => void
  const promise = new Promise<GameCard[]>((done, fail) => { resolve = done; reject = fail })
  return { promise, resolve, reject }
}

async function advance(ms = 0) {
  await act(async () => { await vi.advanceTimersByTimeAsync(ms) })
}

function visibility(hidden: boolean) {
  act(() => {
    vi.spyOn(document, 'hidden', 'get').mockReturnValue(hidden)
    document.dispatchEvent(new Event('visibilitychange'))
  })
}

beforeEach(() => {
  vi.useFakeTimers()
  vi.setSystemTime(new Date('2026-11-15T12:00:00Z'))
  vi.spyOn(document, 'hidden', 'get').mockReturnValue(false)
  vi.spyOn(api, 'live').mockResolvedValue(board)
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  vi.useRealTimers()
})

it('shares one pending request and one fastest timer between two subscribers', async () => {
  const pending = deferred()
  vi.mocked(api.live).mockReturnValueOnce(pending.promise)
  const header = renderHook(() => useLiveGames(60_000))
  const games = renderHook(() => useLiveGames(10_000))
  expect(api.live).toHaveBeenCalledTimes(1)
  expect(vi.getTimerCount()).toBe(0)
  await advance(90_000)
  expect(api.live).toHaveBeenCalledTimes(1)
  await act(async () => { pending.resolve(board) })
  expect(header.result.current).toBe(games.result.current)
  expect(header.result.current.receivedAt).toBe(Date.now())
  expect(vi.getTimerCount()).toBe(1)
  await advance(9_999)
  expect(api.live).toHaveBeenCalledTimes(1)
  await advance(1)
  expect(api.live).toHaveBeenCalledTimes(2)
  expect(vi.getTimerCount()).toBe(1)

  games.unmount()
  await advance(59_999)
  expect(api.live).toHaveBeenCalledTimes(2)
  await advance(1)
  expect(api.live).toHaveBeenCalledTimes(3)
  header.unmount()
  expect(vi.getTimerCount()).toBe(0)
})

it('joins a loaded board without refreshing and anchors cadence changes to the last attempt', async () => {
  const header = renderHook(({ ms }) => useLiveGames(ms), { initialProps: { ms: 60_000 } })
  await advance()
  const original = header.result.current
  await advance(5_000)
  const games = renderHook(() => useLiveGames(10_000))
  expect(games.result.current).toBe(original)
  expect(api.live).toHaveBeenCalledTimes(1)
  games.unmount()
  header.rerender({ ms: 10_000 })
  expect(api.live).toHaveBeenCalledTimes(1)
  expect(header.result.current).toBe(original)
  expect(vi.getTimerCount()).toBe(1)
  await advance(4_999)
  expect(api.live).toHaveBeenCalledTimes(1)
  await advance(1)
  expect(api.live).toHaveBeenCalledTimes(2)

  await advance(2_000)
  header.rerender({ ms: 60_000 })
  expect(api.live).toHaveBeenCalledTimes(2)
  await advance(57_999)
  expect(api.live).toHaveBeenCalledTimes(2)
  await advance(1)
  expect(api.live).toHaveBeenCalledTimes(3)
})

it('pauses hidden tabs and resumes once without overlapping a pending request', async () => {
  visibility(true)
  const hook = renderHook(() => useLiveGames(10_000))
  await advance(60_000)
  expect(api.live).not.toHaveBeenCalled()
  expect(vi.getTimerCount()).toBe(0)
  visibility(false)
  await advance()
  expect(api.live).toHaveBeenCalledTimes(1)
  const snapshot = hook.result.current
  visibility(false)
  expect(api.live).toHaveBeenCalledTimes(1)
  visibility(true)
  expect(vi.getTimerCount()).toBe(0)
  await advance(60_000)
  expect(api.live).toHaveBeenCalledTimes(1)
  expect(hook.result.current).toBe(snapshot)

  const pending = deferred()
  vi.mocked(api.live).mockReturnValueOnce(pending.promise)
  visibility(false)
  visibility(true)
  visibility(false)
  await advance(30_000)
  expect(api.live).toHaveBeenCalledTimes(2)
  visibility(true)
  await act(async () => { pending.resolve(laterBoard) })
  expect(hook.result.current.data).toBe(laterBoard)
  expect(vi.getTimerCount()).toBe(0)
  visibility(false)
  await advance()
  expect(api.live).toHaveBeenCalledTimes(3)
  expect(vi.getTimerCount()).toBe(1)
})

it('keeps the last good data and receipt on error, shares errors, and clears them on recovery', async () => {
  const header = renderHook(() => useLiveGames(60_000))
  await advance()
  const receivedAt = header.result.current.receivedAt
  vi.mocked(api.live).mockRejectedValueOnce(new Error('Offline'))
  await advance(60_000)
  expect(header.result.current).toEqual({ data: board, error: 'Offline', receivedAt })
  const games = renderHook(() => useLiveGames(10_000))
  expect(games.result.current).toBe(header.result.current)
  expect(api.live).toHaveBeenCalledTimes(2)
  vi.mocked(api.live).mockResolvedValue(laterBoard)
  await advance(10_000)
  expect(games.result.current).toEqual({ data: laterBoard, error: null, receivedAt: Date.now() })
  expect(header.result.current).toBe(games.result.current)
})

it.each(['resolve', 'reject'] as const)('ignores an old session that later %ss after the last subscriber unmounts', async (settle) => {
  const old = deferred()
  const fresh = deferred()
  vi.mocked(api.live).mockReturnValueOnce(old.promise).mockReturnValueOnce(fresh.promise)
  const first = renderHook(() => useLiveGames(10_000))
  first.unmount()
  expect(vi.getTimerCount()).toBe(0)
  visibility(true)
  visibility(false)
  expect(api.live).toHaveBeenCalledTimes(1)
  const second = renderHook(() => useLiveGames(60_000))
  await act(async () => { fresh.resolve(laterBoard) })
  const snapshot = second.result.current
  await act(async () => {
    if (settle === 'resolve') old.resolve(board)
    else old.reject(new Error('Old failure'))
  })
  expect(second.result.current).toBe(snapshot)
  expect(snapshot).toEqual({ data: laterBoard, error: null, receivedAt: Date.now() })
  expect(vi.getTimerCount()).toBe(1)
  second.unmount()
  expect(vi.getTimerCount()).toBe(0)
  const third = renderHook(() => useLiveGames(10_000))
  expect(third.result.current).toEqual({ data: null, error: null, receivedAt: null })
  await advance()
})
