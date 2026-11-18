// @vitest-environment jsdom
import { cleanup, render, screen, within } from '@testing-library/react'
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

it('exposes calibration and cumulative values as named keyboard-accessible data tables', async () => {
  const model = { id: 'test-v1', name: 'Test model', short: 'Test', record: '1-1', picks: 2, settled: 2,
    units: 0.4, roi_pct: 20, verdict: 'Small sample', calibration: [{ bucket: '50–60%', lines: 2, model: 55, market: 52, actual: 50 }] }
  const data: RecordData = { empty: false, integrity: { picks: 2, graded: 2, after_tip: 0, first_lock: null, last_lock: null },
    chain: { started: false }, clv: [], gaps: null, by_book: [], models: [model], alt: { picks: 0, settled: 0, record: '0-0' },
    running: [{ day: '2026-11-10', model: model.id, units: 0.4 }], days: [],
    log: [{ day: '2026-11-10', player: 'A player with a long name', bet: 'Over 25.5 points', odds: -110,
      model: model.id, locked: '2026-11-10T21:00:00Z', lead: '3h before tip', result: 'win', units: 0.4 }] }
  vi.spyOn(api, 'record').mockResolvedValue(data)
  render(<Record />)
  const calibration = await screen.findByRole('table', { name: 'Test model calibration (%)' })
  expect(within(calibration).getByText('55%')).toBeTruthy()
  expect(within(calibration).getByText('52%')).toBeTruthy()
  const cumulative = screen.getByRole('table', { name: 'Cumulative profit by game day (units)' })
  expect(within(cumulative).getByText('2026-11-10')).toBeTruthy()
  expect(within(cumulative).getByText('+0.40')).toBeTruthy()
  expect(screen.getByRole('region', { name: 'Cumulative profit data' }).tabIndex).toBe(0)
  expect(screen.getByText(/3h before tip/)).toBeTruthy()
})
