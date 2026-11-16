// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { api, type RecordData } from '../lib/api'
import { Record } from './Record'

afterEach(() => { cleanup(); vi.restoreAllMocks() })

it('labels fair-close value and its sample size without calling it price movement', async () => {
  const data: RecordData = {
    empty: false,
    integrity: { picks: 2, graded: 2, after_tip: 0, first_lock: null, last_lock: null },
    chain: { started: false },
    clv: [{ book: 'fanduel', name: 'FanDuel', measured: 17, avg_pct: -4.2, beat_pct: 24 }],
    gaps: null, by_book: [], models: [], alt: { picks: 0, settled: 0, record: '0-0' },
    running: [], days: [], log: [],
  }
  vi.spyOn(api, 'record').mockResolvedValue(data)
  render(<Record />)
  expect(await screen.findByText('Did we beat the fair closing price?')).toBeTruthy()
  expect(screen.getByText('Value vs fair close')).toBeTruthy()
  expect(screen.getByText('-4.2%')).toBeTruthy()
  expect(screen.getByText('17')).toBeTruthy()
  expect(screen.queryByText('Average move')).toBeNull()
})
