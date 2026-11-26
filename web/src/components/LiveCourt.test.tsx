// @vitest-environment jsdom
import { act, cleanup, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import type { GameDetail } from '../lib/api'
import { LiveCourt } from './LiveCourt'
import type { ShotMark } from './CourtStage'

vi.mock('./CourtStage', () => ({
  CourtStage: ({ flying, shots }: { flying: ShotMark | null; shots: ShotMark[] }) =>
    <div>{flying ? `Flying ${flying.key}` : `On court ${shots.map((shot) => shot.key).join(',')}`}</div>,
}))
afterEach(() => { cleanup(); vi.useRealTimers() })

it('clears the flying shot after a rerender and a refresh with the same shot', () => {
  vi.useFakeTimers()
  const side = (team: string) => ({ team, logo: '', color: '#fff', score: 12, timeouts: 0, bonus: false, fouls: null })
  const game = (n: number): GameDetail & { detail: NonNullable<GameDetail['detail']> } => ({
    id: 'game', state: 'final', status: 'Final', away: side('BOS'), home: side('WAS'),
    detail: {
      quarters: { columns: [], rows: [] }, compare: [], leaders: [], box: {}, foul_trouble: [], plays: [],
      shots: [{ n, x: 80, y: 40, made: true, team: 'WAS', three: false, period: 1, period_label: 'Q1', text: 'Layup' }],
    },
  })
  const view = render(<LiveCourt game={game(1)} />)
  view.rerender(<LiveCourt game={game(2)} />)
  expect(screen.getByText('Flying 2')).toBeTruthy()
  act(() => { vi.advanceTimersByTime(750) })
  view.rerender(<LiveCourt game={game(2)} />)
  act(() => { vi.advanceTimersByTime(750) })
  expect(screen.getByText('On court 2')).toBeTruthy()
})
