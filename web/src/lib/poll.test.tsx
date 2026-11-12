// @vitest-environment jsdom
import { act, cleanup, renderHook } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { usePoll } from './poll'

afterEach(() => { cleanup(); vi.useRealTimers() })

it('keeps the successful receipt time on failure and never overlaps visibility refreshes', async () => {
  vi.useFakeTimers()
  vi.setSystemTime(new Date('2026-11-12T01:00:00Z'))
  let resolve!: (value: string) => void
  const load = vi.fn().mockReturnValueOnce(new Promise<string>((done) => { resolve = done }))
    .mockRejectedValueOnce(new Error('Offline'))
  const hook = renderHook(() => usePoll(load, 10_000, 'games'))
  act(() => document.dispatchEvent(new Event('visibilitychange')))
  expect(load).toHaveBeenCalledTimes(1)
  await act(async () => resolve('board'))
  const receivedAt = hook.result.current.receivedAt
  expect(receivedAt).toBe(Date.now())
  await act(async () => vi.advanceTimersByTimeAsync(10_000))
  expect(hook.result.current.data).toBe('board')
  expect(hook.result.current.error).toBe('Offline')
  expect(hook.result.current.receivedAt).toBe(receivedAt)
})
