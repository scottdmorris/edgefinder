// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { api, type GradedSlip, type Leg, type Review as ReviewData } from '../lib/api'
import { Review } from './Review'

const pick = { player: 'Sam Hauser', player_id: 2, photo: '', bet: 'Over 9.5 points', game_short: 'MIL @ BOS', odds: -110,
  models: ['Minutes', 'Shot profile'], projects: 15.5, actual: 2, status: 'Missed' as const, off_by: 13.5,
  note: 'Played 8 minutes, usually 30' }
const night: ReviewData = {
  date: '2026-11-10', label: 'Tue, Nov 10', days: [{ date: '2026-11-10', label: 'Tue, Nov 10' }],
  models: [{ id: 'context-v2', short: 'Shot profile', record: '1-1', picks: 2, settled: 2, units: -0.09 }],
  picks: [pick, { ...pick, player: 'Jaylen Brown', player_id: 1, status: 'Hit', actual: 31, note: '' }],
  misses: [pick], pending: 0, kalshi: null,
}
const leg = { id: 5, player: 'Sam Hauser', player_id: 2, photo: '', stat: 'points', side: 'Over', line: 9.5,
  bet: 'Over 9.5 points', chance_pct: 61 } as Leg

beforeEach(() => { localStorage.clear(); vi.spyOn(api, 'review').mockResolvedValue(night) })
afterEach(() => { cleanup(); vi.restoreAllMocks() })

it('sums up the night, each model, and the miss with its reason', async () => {
  render(<Review />)
  expect(await screen.findByText('Tue, Nov 10: 1 of 2 model picks hit.')).toBeTruthy()
  expect(screen.getByText('1-1')).toBeTruthy()
  expect(screen.getAllByText('Played 8 minutes, usually 30').length).toBeGreaterThan(0)
  expect(screen.getByText(/No slip was built in this browser/)).toBeTruthy()
})

it('grades the slip built for that day and names the leg that sank it', async () => {
  localStorage.setItem('bk-slip-v2:2026-11-10|fanduel|context-v2',
    JSON.stringify({ market: '2026-11-10|fanduel|context-v2', legs: [5], snapshots: { 5: leg } }))
  const graded: GradedSlip = { date: '2026-11-10', status: 'Missed', hit: 0, missed: 1,
    legs: [{ player_id: 2, stat: 'points', side: 'Over', line: 9.5, actual: 2, status: 'Missed', note: '' }] }
  const grade = vi.spyOn(api, 'gradeSlip').mockResolvedValue(graded)
  render(<Review />)
  expect(await screen.findByText('This leg sank the slip.')).toBeTruthy()
  expect(screen.getByText(/Finished with 2 · you added it at a 61% chance/)).toBeTruthy()
  expect(grade).toHaveBeenCalledWith('2026-11-10', [{ player_id: 2, stat: 'points', side: 'Over', line: 9.5 }])
})
