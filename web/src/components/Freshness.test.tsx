// @vitest-environment jsdom
import { act, cleanup, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { Freshness } from './Freshness'

afterEach(() => { cleanup(); vi.useRealTimers() })

it('ages the actual receipt time and distinguishes stale data from connection failures', () => {
  vi.useFakeTimers()
  vi.setSystemTime(new Date('2026-11-12T01:00:00Z'))
  const view = render(<Freshness receivedAt="2026-11-12T01:00:00Z" />)
  expect(screen.getByText('NBA feed received 0s ago')).toBeTruthy()
  act(() => vi.advanceTimersByTime(31_000))
  expect(screen.getByText(/31s ago · Stale data/)).toBeTruthy()
  view.rerender(<Freshness receivedAt="2026-11-12T01:00:00Z" error="Offline" />)
  expect(screen.getByText(/31s ago · Connection failed; retrying/)).toBeTruthy()
})
