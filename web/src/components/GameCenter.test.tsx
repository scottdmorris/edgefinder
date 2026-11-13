// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, expect, it } from 'vitest'
import type { GameDetail } from '../lib/api'
import { GameCenter } from './GameCenter'

afterEach(cleanup)
const side = (team: string, score: number, color: string) => ({ team, score, color, logo: '', timeouts: 3, bonus: false, fouls: 0 })
const away = side('ORL', 107, '#0077c0')
const home = side('UTA', 99, '#4b2e83')
const plays = [
  { order: 3, period: 'Q4', clock: '4:45', team: 'ORL', text: 'Banchero makes driving layup', score: 'ORL 107 - UTA 99' },
  { order: 2, period: 'Q4', clock: '5:02', team: 'UTA', text: 'Sexton misses 3-pointer', score: '' },
]
const game = {
  id: 'g1', state: 'live', status: '4th Qtr 4:45', away, home,
  detail: { quarters: { columns: [], rows: [] }, shots: [], compare: [], leaders: [], plays, box: {}, foul_trouble: [] },
} as GameDetail & { detail: NonNullable<GameDetail['detail']> }

it('shows the latest plays on a live game and marks the ones by your players', () => {
  render(<GameCenter game={game} mine={['Paolo Banchero']} />)
  expect(screen.getByText('Latest plays')).toBeTruthy()
  expect(screen.getByText('Banchero makes driving layup').className).toContain('text-accent')
  expect(screen.getByText('Sexton misses 3-pointer').className).not.toContain('text-accent')
})
